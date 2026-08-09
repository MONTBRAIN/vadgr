"""The run's lifecycle: resolve its configuration, drive the provider, record
its outcome."""

import asyncio
import logging
from collections.abc import Awaitable, Callable
from typing import Any, Coroutine

from api.engine.native_bridge import (
    NativeLoopProvider,
    build_native_provider,
    is_native_provider,
)
from api.engine.providers import (
    CLIAgentProvider,
    create_provider,
    machine_default_model,
    machine_default_provider,
)
from api.persistence.repositories import RunRepository

logger = logging.getLogger(__name__)


EmitFn = Callable[[str, str, dict], Coroutine[Any, Any, None]]
ProviderFactory = Callable[..., Awaitable[CLIAgentProvider]]

# What a legacy CLI subprocess is given before it is killed. The native path
# gets no deadline at all: what bounds an unattended run there is the gate layer
# and max_iterations, not a stopwatch, and the target is one real batch
# completing over hours.
_CLI_TIMEOUT_SECONDS = 900
_CLI_COMPUTER_USE_TIMEOUT_SECONDS = 1800


class ExecutionService:
    """Owns a run's lifecycle: resolve its configuration, drive the provider,
    record its outcome. It knows nothing about what asked for the run."""

    def __init__(
        self,
        run_repo: RunRepository,
        emit: EmitFn,
        provider_factory: ProviderFactory | None = None,
    ):
        self.run_repo = run_repo
        self.emit = emit
        self.provider_factory = provider_factory or create_provider

    async def _resolve_config(self, run: dict) -> tuple[str, str | None]:
        """The provider and model this run executes on.

        Order: what the caller asked for, then the machine's default, then the
        first provider on the machine that answers as available. A run that
        named neither is not a misconfiguration, it is the ordinary case.
        """
        provider_key = run.get("provider") or await machine_default_provider()
        model = run.get("model") or machine_default_model(provider_key)
        return provider_key, model

    async def _get_run_provider(
        self,
        provider_key: str,
        model: str | None,
        timeout: int | None,
        run_id: str | None = None,
        resume_state: object | None = None,
    ):
        """The provider a run executes on.

        A provider marked ``kind: native`` in `providers.yaml` is the engine, and
        it arrives wrapped in `NativeLoopProvider` so the caller keeps iterating
        the interface it already iterates. Anything else is a legacy CLI provider
        and behaves exactly as it did, until those are deleted in Beta.
        """
        if is_native_provider(provider_key):
            return NativeLoopProvider(
                build_native_provider(provider_key, model),
                mcp_servers=[],
            )
        return await self.provider_factory(
            provider_key=provider_key,
            model=model,
            timeout=timeout,
        )

    def _timeout_for(self, provider_key: str) -> int | None:
        if is_native_provider(provider_key):
            return None
        from api.services.computer_use_setup import get_status

        try:
            computer_use = bool(get_status().get("enabled"))
        except Exception:
            computer_use = False
        return (
            _CLI_COMPUTER_USE_TIMEOUT_SECONDS
            if computer_use
            else _CLI_TIMEOUT_SECONDS
        )

    async def _drive(self, run_id: str, provider, prompt: str, title: str = "") -> dict:
        """Stream one provider run and turn its events into frames.

        The frame names are wire vocabulary on a surface the shipped phone
        reads, so they are frozen: `agent_started` still opens the timeline and
        still carries `name`, which now holds the run's own title.
        """
        await self.emit(run_id, "agent_started", {"run_id": run_id, "name": title})
        collected_output = ""
        try:
            async for event in provider.execute_streaming(
                prompt=prompt,
                workspace=None,
                timeout=None,
                # The native loop names its journal after this. Without it the
                # loop mints its own id and the journal cannot be tied back to
                # the run - which also breaks resume, since resume-on-boot finds
                # a journal by id and then has to look that run up.
                run_id=run_id,
            ):
                if event.type == "output":
                    await self.emit(run_id, "agent_log", {
                        "run_id": run_id,
                        "message": event.data,
                    })
                elif event.type == "todos":
                    await self.emit(run_id, "todos", {"items": event.data})
                elif event.type == "awaiting":
                    await self.emit(run_id, "awaiting", {"prompt": event.data})
                elif event.type == "done":
                    collected_output = event.data
                elif event.type == "error":
                    raise RuntimeError(event.data)
        except Exception as e:
            await self.emit(run_id, "agent_failed", {"run_id": run_id, "error": str(e)})
            raise

        result = {"result": collected_output}
        await self.emit(run_id, "agent_completed", {"run_id": run_id, "outputs": result})
        return result

    async def _execute(self, run_id: str, provider, prompt: str, title: str) -> None:
        """The outcome half, shared by a fresh run and a resumed one."""
        try:
            result = await self._drive(run_id, provider, prompt, title=title)
            await self.run_repo.update_status(run_id, "completed", outputs=result)
            await self.emit(run_id, "run_completed", {"outputs": result})
        except asyncio.CancelledError:
            await self.run_repo.update_status(run_id, "failed")
            await self.emit(run_id, "run_failed", {"error": "Run was cancelled"})
            raise
        except Exception as e:
            await self.run_repo.update_status(run_id, "failed", outputs={"error": str(e)})
            await self.emit(run_id, "run_failed", {"error": str(e)})

    @staticmethod
    def _title_of(run: dict) -> str:
        """The run's title, as the published row carries it.

        Storage calls this `title`; the published row keeps the older key
        because the shipped phone reads it literally. This service reads rows
        rather than tables, so it reads the published key. The translation
        itself lives in exactly one place, and this is not it.
        """
        return run.get("agent_name") or ""

    @staticmethod
    def _prompt_of(run: dict) -> str:
        """The task sentence, verbatim. There is no agent to assemble a prompt
        from and nothing to point the model at, so the sentence is the prompt."""
        return (run.get("inputs") or {}).get("task", "")

    async def start_run(self, run_id: str) -> None:
        run = await self.run_repo.get(run_id)
        provider_key, model = await self._resolve_config(run)
        provider = await self._get_run_provider(
            provider_key, model, self._timeout_for(provider_key), run_id=run_id
        )

        await self.run_repo.update_status(run_id, "running")
        await self.emit(run_id, "run_started", {})
        await self._execute(
            run_id, provider, self._prompt_of(run), self._title_of(run)
        )

    async def resume_run(self, run_id: str) -> None:
        """Re-run a failed run from the top. Without a journal to open at there
        is nothing finer to resume from; `continue_run` is the one that does."""
        run = await self.run_repo.get(run_id)
        provider_key, model = await self._resolve_config(run)
        provider = await self._get_run_provider(
            provider_key, model, self._timeout_for(provider_key), run_id=run_id
        )

        await self.run_repo.update_status(run_id, "running")
        await self.emit(run_id, "run_resumed", {})
        await self._execute(
            run_id, provider, self._prompt_of(run), self._title_of(run)
        )

    async def continue_run(self, run_id: str, resume_state) -> None:
        """Continue a run a previous process died inside.

        The same path as a fresh run, with one difference that is the whole
        point: the resume state goes to the provider, so the loop opens at the
        first UNcompleted step and appends to the journal it crashed inside
        rather than starting a second one.
        """
        run = await self.run_repo.get(run_id)
        provider_key, model = await self._resolve_config(run)
        if not is_native_provider(provider_key):
            # Only the native path has a journal to resume from. A legacy CLI
            # run that died is dead: the subprocess took its state with it.
            logger.info("run %s is not native; not resuming", run_id)
            return
        provider = await self._get_run_provider(
            provider_key,
            model,
            None,
            run_id=run_id,
            resume_state=resume_state,
        )
        await self.run_repo.update_status(run_id, "running")
        await self.emit(run_id, "run_resumed", {"from_seq": resume_state.next_seq})
        await self._execute(
            run_id, provider, self._prompt_of(run), self._title_of(run)
        )


async def find_resumable_runs(runs_dir: str | None = None) -> list[str]:
    """Run ids whose journal ends mid-action, newest first.

    A journal that ends clean is finished, not interrupted: `find_latest()`
    keys on a **dangling** `in_flight`, which is the record the loop writes
    BEFORE dispatch and closes after. Its presence is the only durable evidence
    that a process died inside a tool call.
    """
    from engine.trajectory import find_latest

    run_id = find_latest(runs_dir)
    return [run_id] if run_id else []


async def resume_interrupted_runs(
    execution_service: "ExecutionService | None" = None,
    runs_dir: str | None = None,
) -> list[str]:
    """Continue runs the last process died inside. Called once, at startup.

    **Continue, never replay.** `resume()` returns the first UNcompleted step,
    so work that finished before the kill is not redone. That distinction is the
    whole point and it is not visible from the outcome: a replayed run also ends
    `completed`, so "it finished after a restart" proves nothing on its own. The
    proof is a side effect that did not happen twice.

    Returns the ids it resumed, so a caller (and a test) can see what it did
    rather than infer it from logs.
    """
    from engine.trajectory import resume

    resumed: list[str] = []
    for run_id in await find_resumable_runs(runs_dir):
        state = await resume(run_id, runs_dir=runs_dir)
        if state.dangling is None:
            continue  # clean journal: finished, nothing to continue
        logger.info(
            "resuming run %s from seq %s (%s step(s) already done)",
            run_id, state.next_seq, len(state.completed_seqs),
        )
        resumed.append(run_id)
        if execution_service is not None:
            await execution_service.continue_run(run_id, state)
    return resumed
