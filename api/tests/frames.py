"""The frame names the daemon can broadcast, read from the source that emits
them.

Read rather than listed, because a list is a second copy of a fact and the
whole point of asserting on the vocabulary is that the two sides cannot drift.
A dead branch and a rare branch look identical from inside, so both directions
are checked against this.
"""

from __future__ import annotations

import re
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]

# Every site that turns something into a frame. `native_bridge.py` produces the
# loop's event types rather than frame names, so it is not one of them: those
# arrive here through the execution service.
_EMITTERS = ("api/services/execution_service.py",)


def emitted_frame_names() -> set[str]:
    names: set[str] = set()
    for relative in _EMITTERS:
        source = (_REPO_ROOT / relative).read_text()
        names |= set(re.findall(r'self\.emit\(\s*run_id,\s*"([a-z_]+)"', source))
    return names
