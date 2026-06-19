"""Device model -- a paired phone as an auth principal."""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class Device(BaseModel):
    """A paired device. The persistent ``token_hash`` is never serialized here;
    it lives only in the ``devices`` table."""

    id: str
    machine_name: str
    paired_at: datetime
    last_seen: Optional[datetime] = None
