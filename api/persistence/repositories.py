"""Data access layer for agents, projects, and runs."""

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


def _row_to_agent(row) -> dict:
    return {
        "id": row["id"],
        "name": row["name"],
        "description": row["description"],
        "type": row["type"],
        "status": row["status"],
        "forge_path": row["forge_path"],
        "steps": _parse_json(row["steps"]),
        "samples": _parse_json(row["samples"]),
        "input_schema": _parse_json(row["input_schema"]),
        "output_schema": _parse_json(row["output_schema"]),
        "computer_use": bool(row["computer_use"]),
        "forge_config": _parse_json(row["forge_config"]),
        "provider": row["provider"],
        "model": row["model"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


def _row_to_project(row) -> dict:
    return {
        "id": row["id"],
        "name": row["name"],
        "description": row["description"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


def _row_to_node(row) -> dict:
    return {
        "id": row["id"],
        "project_id": row["project_id"],
        "agent_id": row["agent_id"],
        "config": _parse_json(row["config"]),
        "position_x": row["position_x"],
        "position_y": row["position_y"],
    }


def _row_to_edge(row) -> dict:
    return {
        "id": row["id"],
        "project_id": row["project_id"],
        "source_node_id": row["source_node_id"],
        "target_node_id": row["target_node_id"],
        "source_output": row["source_output"],
        "target_input": row["target_input"],
    }


def _row_to_run(row) -> dict:
    return {
        "id": row["id"],
        "project_id": row["project_id"],
        "agent_id": row["agent_id"],
        "status": row["status"],
        "inputs": _parse_json(row["inputs"]),
        "outputs": _parse_json(row["outputs"]),
        "provider": row["provider"],
        "model": row["model"],
        "log_path": row["log_path"],
        "started_at": row["started_at"],
        "completed_at": row["completed_at"],
    }


class AgentRepository:
    def __init__(self, db: Database):
        self.db = db

    async def create(
        self,
        name: str,
        description: str = "",
        type: str = "agent",
        status: str = "creating",
        forge_path: str = "",
        steps: list | None = None,
        samples: list[str] | None = None,
        input_schema: list[dict] | None = None,
        output_schema: list[dict] | None = None,
        computer_use: bool = False,
        forge_config: dict | None = None,
        provider: str = "anthropic",
        model: str = "claude-sonnet-4-6",
    ) -> dict:
        agent_id = _uuid()
        now = _now()
        await self.db.conn.execute(
            """INSERT INTO agents (id, name, description, type, status, forge_path, steps, samples, input_schema,
               output_schema, computer_use, forge_config, provider, model, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                agent_id, name, description, type, status, forge_path,
                json.dumps(steps or []),
                json.dumps(samples or []),
                json.dumps(input_schema or []),
                json.dumps(output_schema or []),
                int(computer_use),
                json.dumps(forge_config or {}),
                provider, model, now, now,
            ),
        )
        await self.db.conn.commit()
        return await self.get(agent_id)

    async def get(self, agent_id: str) -> Optional[dict]:
        cursor = await self.db.conn.execute(
            "SELECT * FROM agents WHERE id = ?", (agent_id,)
        )
        row = await cursor.fetchone()
        return _row_to_agent(row) if row else None

    async def list_all(self) -> list[dict]:
        cursor = await self.db.conn.execute(
            "SELECT * FROM agents ORDER BY created_at DESC"
        )
        return [_row_to_agent(row) for row in await cursor.fetchall()]

    async def update(self, agent_id: str, **fields) -> Optional[dict]:
        existing = await self.get(agent_id)
        if not existing:
            return None

        json_fields = {"steps", "samples", "input_schema", "output_schema", "forge_config"}
        sets = []
        values = []
        for key, value in fields.items():
            if value is not None:
                sets.append(f"{key} = ?")
                if key in json_fields:
                    values.append(json.dumps(value))
                elif key == "computer_use":
                    values.append(int(value))
                else:
                    values.append(value)

        if not sets:
            return existing

        sets.append("updated_at = ?")
        values.append(_now())
        values.append(agent_id)

        await self.db.conn.execute(
            f"UPDATE agents SET {', '.join(sets)} WHERE id = ?", values
        )
        await self.db.conn.commit()
        return await self.get(agent_id)

    async def delete(self, agent_id: str) -> bool:
        cursor = await self.db.conn.execute(
            "DELETE FROM agents WHERE id = ?", (agent_id,)
        )
        await self.db.conn.commit()
        return cursor.rowcount > 0

    async def delete_all(self) -> int:
        cursor = await self.db.conn.execute("DELETE FROM agents")
        await self.db.conn.commit()
        return cursor.rowcount


class ProjectRepository:
    def __init__(self, db: Database):
        self.db = db

    async def create(self, name: str, description: str = "") -> dict:
        project_id = _uuid()
        now = _now()
        await self.db.conn.execute(
            "INSERT INTO projects (id, name, description, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
            (project_id, name, description, now, now),
        )
        await self.db.conn.commit()
        return await self.get(project_id)

    async def get(self, project_id: str) -> Optional[dict]:
        cursor = await self.db.conn.execute(
            "SELECT * FROM projects WHERE id = ?", (project_id,)
        )
        row = await cursor.fetchone()
        return _row_to_project(row) if row else None

    async def list_all(self) -> list[dict]:
        cursor = await self.db.conn.execute(
            "SELECT * FROM projects ORDER BY created_at DESC"
        )
        return [_row_to_project(row) for row in await cursor.fetchall()]

    async def update(self, project_id: str, **fields) -> Optional[dict]:
        existing = await self.get(project_id)
        if not existing:
            return None
        sets = []
        values = []
        for key, value in fields.items():
            if value is not None:
                sets.append(f"{key} = ?")
                values.append(value)
        if not sets:
            return existing
        sets.append("updated_at = ?")
        values.append(_now())
        values.append(project_id)
        await self.db.conn.execute(
            f"UPDATE projects SET {', '.join(sets)} WHERE id = ?", values
        )
        await self.db.conn.commit()
        return await self.get(project_id)

    async def delete(self, project_id: str) -> bool:
        cursor = await self.db.conn.execute(
            "DELETE FROM projects WHERE id = ?", (project_id,)
        )
        await self.db.conn.commit()
        return cursor.rowcount > 0

    async def add_node(
        self, project_id: str, agent_id: str,
        config: dict | None = None, position_x: float = 0.0, position_y: float = 0.0,
    ) -> dict:
        node_id = _uuid()
        await self.db.conn.execute(
            """INSERT INTO project_nodes (id, project_id, agent_id, config, position_x, position_y)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (node_id, project_id, agent_id, json.dumps(config or {}), position_x, position_y),
        )
        await self.db.conn.commit()
        return await self._get_node(node_id)

    async def _get_node(self, node_id: str) -> Optional[dict]:
        cursor = await self.db.conn.execute(
            "SELECT * FROM project_nodes WHERE id = ?", (node_id,)
        )
        row = await cursor.fetchone()
        return _row_to_node(row) if row else None

    async def update_node(self, node_id: str, **fields) -> Optional[dict]:
        existing = await self._get_node(node_id)
        if not existing:
            return None
        sets = []
        values = []
        for key, value in fields.items():
            if value is not None:
                sets.append(f"{key} = ?")
                values.append(json.dumps(value) if key == "config" else value)
        if not sets:
            return existing
        values.append(node_id)
        await self.db.conn.execute(
            f"UPDATE project_nodes SET {', '.join(sets)} WHERE id = ?", values
        )
        await self.db.conn.commit()
        return await self._get_node(node_id)

    async def get_nodes(self, project_id: str) -> list[dict]:
        cursor = await self.db.conn.execute(
            "SELECT * FROM project_nodes WHERE project_id = ?", (project_id,)
        )
        return [_row_to_node(row) for row in await cursor.fetchall()]

    async def delete_node(self, node_id: str) -> bool:
        cursor = await self.db.conn.execute(
            "DELETE FROM project_nodes WHERE id = ?", (node_id,)
        )
        await self.db.conn.commit()
        return cursor.rowcount > 0

    async def add_edge(
        self, project_id: str, source_node_id: str, target_node_id: str,
        source_output: str, target_input: str,
    ) -> dict:
        edge_id = _uuid()
        await self.db.conn.execute(
            """INSERT INTO project_edges (id, project_id, source_node_id, target_node_id,
               source_output, target_input) VALUES (?, ?, ?, ?, ?, ?)""",
            (edge_id, project_id, source_node_id, target_node_id, source_output, target_input),
        )
        await self.db.conn.commit()
        return await self._get_edge(edge_id)

    async def _get_edge(self, edge_id: str) -> Optional[dict]:
        cursor = await self.db.conn.execute(
            "SELECT * FROM project_edges WHERE id = ?", (edge_id,)
        )
        row = await cursor.fetchone()
        return _row_to_edge(row) if row else None

    async def get_edges(self, project_id: str) -> list[dict]:
        cursor = await self.db.conn.execute(
            "SELECT * FROM project_edges WHERE project_id = ?", (project_id,)
        )
        return [_row_to_edge(row) for row in await cursor.fetchall()]

    async def delete_edge(self, edge_id: str) -> bool:
        cursor = await self.db.conn.execute(
            "DELETE FROM project_edges WHERE id = ?", (edge_id,)
        )
        await self.db.conn.commit()
        return cursor.rowcount > 0


class RunRepository:
    def __init__(self, db: Database):
        self.db = db

    async def create(
        self,
        project_id: str | None = None,
        agent_id: str | None = None,
        inputs: dict | None = None,
        provider: str | None = None,
        model: str | None = None,
    ) -> dict:
        run_id = _uuid()
        await self.db.conn.execute(
            """INSERT INTO runs (id, project_id, agent_id, status, inputs, provider, model)
               VALUES (?, ?, ?, 'queued', ?, ?, ?)""",
            (run_id, project_id, agent_id, json.dumps(inputs or {}), provider, model),
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

    async def list_by_agent(self, agent_id: str) -> list[dict]:
        cursor = await self.db.conn.execute(
            "SELECT * FROM runs WHERE agent_id = ? ORDER BY started_at DESC", (agent_id,)
        )
        return [_row_to_run(row) for row in await cursor.fetchall()]

    async def list_by_project(self, project_id: str) -> list[dict]:
        cursor = await self.db.conn.execute(
            "SELECT * FROM runs WHERE project_id = ? ORDER BY started_at DESC",
            (project_id,),
        )
        return [_row_to_run(row) for row in await cursor.fetchall()]

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

    async def set_log_path(self, run_id: str, log_path: str) -> Optional[dict]:
        await self.db.conn.execute(
            "UPDATE runs SET log_path = ? WHERE id = ?", (log_path, run_id)
        )
        await self.db.conn.commit()
        return await self.get(run_id)

    async def delete_all(self) -> int:
        cursor = await self.db.conn.execute("DELETE FROM runs")
        await self.db.conn.commit()
        return cursor.rowcount
