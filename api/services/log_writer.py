"""Per-step JSONL log writer for run execution events."""

import json
from pathlib import Path
from typing import Any


class LogWriter:
    """Append-only JSONL writer that persists execution events to disk.

    Directory layout:
        {base_dir}/output/{run_id}/agent_logs/
            execution.jsonl              # run-level events
            step_01_step-name.jsonl      # per-step events
    """

    def __init__(self, base_dir: Path | str):
        self.base_dir = Path(base_dir)

    def _agent_logs_dir(self, run_id: str) -> Path:
        return self.base_dir / "output" / run_id / "agent_logs"

    @staticmethod
    def _sanitize_step_name(name: str) -> str:
        return name.lower().replace(" ", "-")

    def append_run_event(self, run_id: str, event: dict[str, Any]) -> str:
        """Append an event to execution.jsonl. Returns the relative log_path."""
        path = self._agent_logs_dir(run_id) / "execution.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "a") as f:
            f.write(json.dumps(event, default=str) + "\n")
        return f"output/{run_id}/agent_logs"

    def append_step_event(
        self, run_id: str, step_num: int, step_name: str, event: dict[str, Any]
    ) -> None:
        """Append an event to the step's JSONL file."""
        safe_name = self._sanitize_step_name(step_name)
        filename = f"step_{step_num:02d}_{safe_name}.jsonl"
        path = self._agent_logs_dir(run_id) / filename
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "a") as f:
            f.write(json.dumps(event, default=str) + "\n")

    def read_run_log(self, run_id: str) -> list[dict]:
        """Read all events from execution.jsonl. Returns [] if missing."""
        path = self._agent_logs_dir(run_id) / "execution.jsonl"
        return self._read_jsonl(path)

    def read_step_log(self, run_id: str, filename: str) -> list[dict]:
        """Read all events from a step JSONL file. Returns [] if missing."""
        path = self._agent_logs_dir(run_id) / filename
        return self._read_jsonl(path)

    def list_step_logs(self, run_id: str) -> list[str]:
        """List step log filenames (excludes execution.jsonl)."""
        logs_dir = self._agent_logs_dir(run_id)
        if not logs_dir.exists():
            return []
        return sorted(
            f.name for f in logs_dir.iterdir()
            if f.name.startswith("step_") and f.name.endswith(".jsonl")
        )

    @staticmethod
    def _read_jsonl(path: Path) -> list[dict]:
        if not path.exists():
            return []
        events = []
        for line in path.read_text().splitlines():
            if line.strip():
                events.append(json.loads(line))
        return events
