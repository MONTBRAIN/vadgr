"""Agent executor -- routes execution to CLI providers or computer use."""

import json
import mimetypes
from pathlib import Path
from typing import Any, Callable, Coroutine

from api.engine.providers import CLIAgentProvider, build_agent_prompt, build_step_prompt

# Project root -- used as fallback workspace so CLI picks up .mcp.json
_PROJECT_ROOT = str(Path(__file__).resolve().parent.parent.parent)


EventCallback = Callable[[str, dict], Coroutine[Any, Any, None]]


class AgentExecutor:
    """Executes a single agent node."""

    def __init__(self, provider: CLIAgentProvider, computer_use_service):
        self.provider = provider
        self.computer_use_service = computer_use_service

    async def execute(
        self,
        agent: dict,
        inputs: dict,
        callback: EventCallback,
        run_id: str = "",
        provider: CLIAgentProvider | None = None,
    ) -> dict:
        """Run an agent and return its outputs.

        - Computer use agents: delegates to ComputerUseService.
        - All others: builds a prompt and sends to the configured CLI provider.

        When the agent has multiple steps, each step runs as a separate
        subprocess. CLI steps use stream-json (live logs), Desktop steps
        use regular json (avoids base64 screenshot crash). Context flows
        between steps through output files.
        """
        await callback("agent_started", {"agent_id": agent["id"], "name": agent["name"]})

        try:
            selected_provider = provider or self.provider
            # CLI providers (claude_code, codex, etc.) handle computer use via
            # MCP/plugins natively. Only route to computer_use_service for the
            # direct anthropic provider, which needs the separate desktop engine.
            use_cu_service = (
                agent.get("computer_use")
                and agent.get("provider") not in ("claude_code", "codex", "aider", "cline", "gemini")
            )
            if use_cu_service:
                result = await self.computer_use_service.run_agent(agent, inputs, callback)
            else:
                steps = agent.get("steps") or []
                has_steps = len(steps) > 1 and agent.get("forge_path")

                if has_steps:
                    result = await self._execute_per_step(
                        agent,
                        inputs,
                        callback,
                        run_id,
                        provider=selected_provider,
                    )
                else:
                    result = await self._execute_single(
                        agent,
                        inputs,
                        callback,
                        run_id,
                        provider=selected_provider,
                    )

            await callback("agent_completed", {"agent_id": agent["id"], "outputs": result})
            return result
        except Exception as e:
            await callback("agent_failed", {"agent_id": agent["id"], "error": str(e)})
            raise

    async def _execute_single(
        self,
        agent: dict,
        inputs: dict,
        callback: EventCallback,
        run_id: str = "",
        provider: CLIAgentProvider | None = None,
    ) -> dict:
        """Run the entire agent as a single subprocess."""
        prompt = build_agent_prompt(agent, inputs, run_id=run_id)
        workspace = _PROJECT_ROOT
        timeout = 1800 if agent.get("computer_use") else 900
        can_stream = not agent.get("computer_use")

        collected_output = ""
        selected_provider = provider or self.provider
        async for event in selected_provider.execute_streaming(
            prompt=prompt,
            workspace=workspace,
            timeout=timeout,
            use_stream_json=can_stream,
        ):
            if event.type == "output":
                if can_stream:
                    await callback("agent_log", {
                        "agent_id": agent["id"],
                        "message": event.data,
                    })
            elif event.type == "done":
                collected_output = event.data
            elif event.type == "error":
                raise RuntimeError(event.data)

        # Prefer file paths from disk over parsed stdout JSON
        file_outputs = self._collect_output_paths(
            agent.get("forge_path", ""), run_id, agent.get("output_schema", [])
        )
        if file_outputs:
            return file_outputs
        parsed = self._parse_output(collected_output, agent.get("output_schema", []))
        return self._normalize_outputs(
            parsed,
            forge_path=agent.get("forge_path", ""),
            run_id=run_id,
            output_schema=agent.get("output_schema", []),
        )

    async def _execute_per_step(
        self,
        agent: dict,
        inputs: dict,
        callback: EventCallback,
        run_id: str = "",
        provider: CLIAgentProvider | None = None,
    ) -> dict:
        """Run each step as a separate subprocess.

        CLI steps use stream-json for live logs. Desktop steps use regular
        json to avoid the base64 screenshot chunk buffer crash. Context
        flows between steps through output files on disk.
        """
        steps = agent.get("steps", [])
        workspace = _PROJECT_ROOT
        last_output = ""

        for i, step in enumerate(steps, 1):
            step_name = step["name"] if isinstance(step, dict) else step
            uses_cu = step.get("computer_use", False) if isinstance(step, dict) else False
            can_stream = not uses_cu
            timeout = 1800 if uses_cu else 900

            # Step context is included in event data for log routing
            step_ctx = {"step_num": i, "step_name": step_name}

            await callback("agent_log", {
                "agent_id": agent["id"],
                "message": f"--- Step {i}: {step_name} {'[Desktop]' if uses_cu else '[CLI]'} ---",
                **step_ctx,
            })

            prompt = build_step_prompt(agent, inputs, step_number=i, step=step, run_id=run_id)

            collected_output = ""
            selected_provider = provider or self.provider
            async for event in selected_provider.execute_streaming(
                prompt=prompt,
                workspace=workspace,
                timeout=timeout,
                use_stream_json=can_stream,
            ):
                if event.type == "output":
                    if can_stream:
                        await callback("agent_log", {
                            "agent_id": agent["id"],
                            "message": event.data,
                            **step_ctx,
                        })
                elif event.type == "done":
                    collected_output = event.data
                elif event.type == "error":
                    raise RuntimeError(
                        f"Step {i} ({step_name}) failed: {event.data}"
                    )

            last_output = collected_output
            await callback("agent_log", {
                "agent_id": agent["id"],
                "message": f"--- Step {i} complete ---",
                **step_ctx,
            })

        # Prefer file paths from disk over parsed stdout JSON
        file_outputs = self._collect_output_paths(
            agent.get("forge_path", ""), run_id, agent.get("output_schema", [])
        )
        if file_outputs:
            return file_outputs
        parsed = self._parse_output(last_output, agent.get("output_schema", []))
        return self._normalize_outputs(
            parsed,
            forge_path=agent.get("forge_path", ""),
            run_id=run_id,
            output_schema=agent.get("output_schema", []),
        )

    def _collect_output_paths(
        self,
        forge_path: str,
        run_id: str,
        output_schema: list[dict],
        project_root: Path | None = None,
    ) -> dict:
        """Scan user_outputs/ for files and map to output schema fields.

        Returns a dict of {field_name: artifact_descriptor_or_relative_path} for files that match
        schema field names (kebab-case filenames → snake_case field names).
        Returns empty dict if no forge_path, no schema, or no files found.
        """
        if not forge_path or not output_schema or not run_id:
            return {}

        root = project_root or Path(_PROJECT_ROOT)
        user_outputs = root / forge_path / "output" / run_id / "user_outputs"
        if not user_outputs.exists():
            return {}

        # Build lookup: kebab-stem -> schema field name
        schema_lookup = {}
        for field in output_schema:
            kebab = field["name"].replace("_", "-")
            schema_lookup[kebab] = field["name"]

        outputs = {}
        step_dirs = sorted(
            [step_dir for step_dir in user_outputs.iterdir() if step_dir.is_dir()]
        )
        for step_dir in step_dirs:
            if not step_dir.is_dir():
                continue
            for file in step_dir.iterdir():
                if not file.is_file():
                    continue
                if file.stem in schema_lookup:
                    field_name = schema_lookup[file.stem]
                    outputs[field_name] = self._build_output_value(
                        file, root, self._schema_field_type(output_schema, field_name)
                    )

        unresolved_fields = [
            field["name"] for field in output_schema if field["name"] not in outputs
        ]
        if (
            len(output_schema) != 1
            or outputs
            or len(unresolved_fields) != 1
            or not step_dirs
        ):
            return outputs

        latest_step_files = [
            file for file in sorted(step_dirs[-1].iterdir()) if file.is_file()
        ]
        if len(latest_step_files) != 1:
            return outputs

        only_file = latest_step_files[0]
        outputs[unresolved_fields[0]] = self._build_output_value(
            only_file, root, self._schema_field_type(output_schema, unresolved_fields[0])
        )

        return outputs

    @staticmethod
    def _schema_field_type(output_schema: list[dict], field_name: str) -> str:
        for field in output_schema:
            if field.get("name") == field_name:
                return field.get("type", "text")
        return "text"

    @staticmethod
    def _build_output_value(file: Path, root: Path, field_type: str) -> str | dict:
        rel_path = str(file.relative_to(root))
        if field_type not in {"file", "archive", "directory"}:
            return rel_path
        mime_type, _ = mimetypes.guess_type(file.name)
        kind = "archive" if field_type == "archive" else field_type
        return {
            "kind": kind,
            "path": rel_path,
            "filename": file.name,
            "mime_type": mime_type or "application/octet-stream",
        }

    def _parse_output(self, raw_response: str, output_schema: list[dict]) -> dict:
        """Parse provider response into output dict.

        Handles three cases:
        1. Clean JSON object → parse directly
        2. JSON embedded in text (leading/trailing prose) → scan and extract
        3. Plain text → map to schema fields
        """
        # Try direct parse first
        try:
            parsed = json.loads(raw_response)
            if isinstance(parsed, dict):
                return parsed
        except (json.JSONDecodeError, TypeError):
            pass

        # Scan for an embedded JSON object (handles leading/trailing text)
        text = raw_response.strip()
        start = text.find("{")
        if start != -1:
            # Try progressively shorter substrings from the last `}` backwards.
            # Use `end = pos` (not `pos - 1`) so the next rfind searches [start, pos)
            # and naturally finds the next `}` to the left without skipping any.
            end = len(text)
            while end > start:
                pos = text.rfind("}", start, end)
                if pos == -1:
                    break
                try:
                    parsed = json.loads(text[start:pos + 1])
                    if isinstance(parsed, dict):
                        return parsed
                except json.JSONDecodeError:
                    pass
                end = pos

        # Map raw text to schema fields
        if output_schema:
            result = {output_schema[0]["name"]: raw_response}
            for field in output_schema[1:]:
                result.setdefault(field["name"], "")
            return result
        return {"result": raw_response}

    def _normalize_outputs(
        self,
        outputs: dict,
        forge_path: str,
        run_id: str,
        output_schema: list[dict],
        project_root: Path | None = None,
    ) -> dict:
        """Normalize parsed outputs so file-like fields become artifact descriptors."""
        if not isinstance(outputs, dict) or not output_schema or not forge_path or not run_id:
            return outputs

        root = project_root or Path(_PROJECT_ROOT)
        normalized = dict(outputs)
        for field in output_schema:
            field_name = field.get("name")
            field_type = field.get("type", "text")
            if field_name not in normalized or field_type not in {"file", "archive", "directory"}:
                continue
            normalized[field_name] = self._normalize_output_value(
                normalized[field_name],
                forge_path=forge_path,
                run_id=run_id,
                field_type=field_type,
                root=root,
            )
        return normalized

    def _normalize_output_value(
        self,
        value: object,
        forge_path: str,
        run_id: str,
        field_type: str,
        root: Path,
    ) -> object:
        if isinstance(value, dict) and value.get("kind") in {"file", "archive", "directory"}:
            resolved = self._resolve_user_output_path(
                forge_path=forge_path,
                run_id=run_id,
                path=value.get("path", ""),
                root=root,
            )
            if resolved:
                mime_type, _ = mimetypes.guess_type(resolved.name)
                kind = "archive" if field_type == "archive" else field_type
                return {
                    "kind": kind,
                    "path": str(resolved.relative_to(root)),
                    "filename": value.get("filename") or resolved.name,
                    "mime_type": value.get("mime_type") or mime_type or "application/octet-stream",
                }
            return value

        if not isinstance(value, str):
            return value

        resolved = self._resolve_user_output_path(
            forge_path=forge_path,
            run_id=run_id,
            path=value,
            root=root,
        )
        if not resolved:
            return value

        return self._build_output_value(resolved, root, field_type)

    @staticmethod
    def _resolve_user_output_path(
        forge_path: str,
        run_id: str,
        path: str,
        root: Path,
    ) -> Path | None:
        if not path:
            return None

        candidates = []
        candidate_path = Path(path)
        if candidate_path.is_absolute():
            candidates.append(candidate_path)
        else:
            candidates.append(root / path)
            if forge_path:
                candidates.append(root / forge_path / path)

        user_outputs_root = (root / forge_path / "output" / run_id / "user_outputs").resolve()
        if not user_outputs_root.exists():
            return None

        for candidate in candidates:
            resolved = candidate.resolve()
            if resolved.is_file() and (resolved == user_outputs_root or user_outputs_root in resolved.parents):
                return resolved
        return None
