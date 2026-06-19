"""Persistent device repository (SRP).

The single owner of the ``devices`` table: store a paired device with its
token *hash* (never plaintext), look a device up by token hash for the auth
gate, list/touch, and revoke. Swapping the storage backend touches only this
file.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Optional

from api.persistence.database import Database


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _row_to_device(row) -> dict:
    return {
        "id": row["id"],
        "machine_name": row["machine_name"],
        "paired_at": row["paired_at"],
        "last_seen": row["last_seen"],
    }


class DeviceRepository:
    """CRUD for paired devices. Token hashes only -- never plaintext tokens."""

    def __init__(self, db: Database):
        self.db = db

    async def create(self, machine_name: str, token_hash: str) -> dict:
        device_id = str(uuid.uuid4())
        now = _now()
        await self.db.conn.execute(
            """INSERT INTO devices (id, machine_name, token_hash, paired_at, last_seen)
               VALUES (?, ?, ?, ?, ?)""",
            (device_id, machine_name, token_hash, now, now),
        )
        await self.db.conn.commit()
        return await self.get(device_id)

    async def get(self, device_id: str) -> Optional[dict]:
        cursor = await self.db.conn.execute(
            "SELECT * FROM devices WHERE id = ?", (device_id,)
        )
        row = await cursor.fetchone()
        return _row_to_device(row) if row else None

    async def find_by_token_hash(self, token_hash: str) -> Optional[dict]:
        cursor = await self.db.conn.execute(
            "SELECT * FROM devices WHERE token_hash = ?", (token_hash,)
        )
        row = await cursor.fetchone()
        return _row_to_device(row) if row else None

    async def list_all(self) -> list[dict]:
        cursor = await self.db.conn.execute(
            "SELECT * FROM devices ORDER BY paired_at DESC"
        )
        return [_row_to_device(row) for row in await cursor.fetchall()]

    async def touch(self, device_id: str) -> None:
        await self.db.conn.execute(
            "UPDATE devices SET last_seen = ? WHERE id = ?", (_now(), device_id)
        )
        await self.db.conn.commit()

    async def delete(self, device_id: str) -> bool:
        cursor = await self.db.conn.execute(
            "DELETE FROM devices WHERE id = ?", (device_id,)
        )
        await self.db.conn.commit()
        return cursor.rowcount > 0
