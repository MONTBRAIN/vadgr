"""Data access layer for runs."""

import json
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from .database import Database


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _uuid() -> str:
    return str(uuid.uuid4())


def _parse_json(value: str) -> Any:
    if value is None:
        return None
    return json.loads(value)


def _row_to_run(row) -> dict:
    """One row, in the shape the transitional watch surface publishes.

    `agent_name` is a wire key whose entity is gone: storage calls the fact
    `title`, and the published run row keeps the older name because the shipped
    phone reads it literally and renaming it would turn every card into a raw
    id. This function is the only place the two names meet, so there is exactly
    one line to delete when the row is regenerated and the surface retires.
    """
    return {
        "id": row["id"],
        "agent_name": row["title"],
        "status": row["status"],
        "inputs": _parse_json(row["inputs"]),
        "outputs": _parse_json(row["outputs"]),
        "provider": row["provider"],
        "model": row["model"],
        "log_path": row["log_path"],
        "started_at": row["started_at"],
        "completed_at": row["completed_at"],
    }


class RunRepository:
    def __init__(self, db: Database):
        self.db = db

    async def create(
        self,
        title: str = "",
        inputs: dict | None = None,
        provider: str | None = None,
        model: str | None = None,
    ) -> dict:
        run_id = _uuid()
        await self.db.conn.execute(
            """INSERT INTO runs (id, title, status, inputs, provider, model)
               VALUES (?, ?, 'queued', ?, ?, ?)""",
            (run_id, title, json.dumps(inputs or {}), provider, model),
        )
        await self.db.conn.commit()
        return await self.get(run_id)

    async def get(self, run_id: str) -> Optional[dict]:
        cursor = await self.db.conn.execute(
            "SELECT * FROM runs WHERE id = ?", (run_id,)
        )
        row = await cursor.fetchone()
        return _row_to_run(row) if row else None

    async def update_status(
        self, run_id: str, status: str, outputs: dict | None = None,
    ) -> Optional[dict]:
        now = _now()
        sets = ["status = ?"]
        values: list = [status]

        if status == "running":
            sets.append("started_at = COALESCE(started_at, ?)")
            values.append(now)

        if status in ("completed", "failed"):
            sets.append("completed_at = ?")
            values.append(now)

        if outputs is not None:
            sets.append("outputs = ?")
            values.append(json.dumps(outputs))

        values.append(run_id)
        await self.db.conn.execute(
            f"UPDATE runs SET {', '.join(sets)} WHERE id = ?", values
        )
        await self.db.conn.commit()
        return await self.get(run_id)

    async def set_config(
        self, run_id: str, provider: str, model: str | None,
    ) -> Optional[dict]:
        """Record what the run actually resolved to.

        A run that named neither stores neither at creation, so without this the
        row reports `null` for both while the work goes to whatever the machine
        defaults to. The published row is what a client has to answer "what ran
        this?" from, and a null there is the row lying by omission.
        """
        await self.db.conn.execute(
            "UPDATE runs SET provider = ?, model = ? WHERE id = ?",
            (provider, model, run_id),
        )
        await self.db.conn.commit()
        return await self.get(run_id)

    async def list_all(self, status: str | None = None) -> list[dict]:
        if status:
            cursor = await self.db.conn.execute(
                "SELECT * FROM runs WHERE status = ? ORDER BY started_at DESC",
                (status,),
            )
        else:
            cursor = await self.db.conn.execute(
                "SELECT * FROM runs ORDER BY started_at DESC"
            )
        return [_row_to_run(row) for row in await cursor.fetchall()]
