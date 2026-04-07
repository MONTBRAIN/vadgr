"""Persistent memory for forge agents.

Stores markdown files with YAML frontmatter at FORGE_HOME/memory/{agent}/{key}.md.
CLI-agnostic: works with Claude Code, Codex, Gemini, or any provider.
Respects the FORGE_HOME environment variable (defaults to ~/.forge).
"""

from __future__ import annotations

import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional


_FORGE_HOME = Path(os.environ.get("FORGE_HOME", Path.home() / ".forge"))
MEMORY_DIR = _FORGE_HOME / "memory"


def _frontmatter(agent: str, key: str) -> str:
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    return f"---\nagent: {agent}\nkey: {key}\nupdated: {now}\n---\n\n"


def _parse_frontmatter(text: str) -> tuple[dict, str]:
    """Split a file into frontmatter dict and body string."""
    match = re.match(r"^---\n(.*?)\n---\n*(.*)", text, re.DOTALL)
    if not match:
        return {}, text
    meta = {}
    for line in match.group(1).splitlines():
        if ":" in line:
            k, v = line.split(":", 1)
            meta[k.strip()] = v.strip()
    return meta, match.group(2)


def write_memory(
    agent_name: str,
    key: str = "global",
    *,
    content: str,
    max_lines: int = 30,
) -> Path:
    """Write a memory file with auto-generated frontmatter.

    Overwrites existing content. Truncates body to max_lines.
    Returns the path to the written file.
    """
    agent_dir = MEMORY_DIR / agent_name
    agent_dir.mkdir(parents=True, exist_ok=True)
    path = agent_dir / f"{key}.md"

    lines = content.strip().splitlines()
    if len(lines) > max_lines:
        lines = lines[:max_lines]

    body = "\n".join(lines) + "\n"
    path.write_text(_frontmatter(agent_name, key) + body)
    return path


def read_memory(agent_name: str, key: str = "global") -> Optional[str]:
    """Read memory content (without frontmatter). Returns None if not found."""
    path = MEMORY_DIR / agent_name / f"{key}.md"
    if not path.exists():
        return None
    text = path.read_text()
    _, body = _parse_frontmatter(text)
    return body.strip() or None


def list_memories(agent_name: str) -> list[dict]:
    """List all memory keys for an agent with their frontmatter metadata."""
    agent_dir = MEMORY_DIR / agent_name
    if not agent_dir.exists():
        return []
    result = []
    for f in sorted(agent_dir.glob("*.md")):
        text = f.read_text()
        meta, _ = _parse_frontmatter(text)
        if not meta:
            meta = {"agent": agent_name, "key": f.stem}
        result.append(meta)
    return result


def clear_memory(agent_name: str, key: Optional[str] = None) -> int:
    """Clear one key or all memories for an agent. Returns count of files deleted."""
    agent_dir = MEMORY_DIR / agent_name
    if not agent_dir.exists():
        return 0
    if key:
        path = agent_dir / f"{key}.md"
        if path.exists():
            path.unlink()
            return 1
        return 0
    # Clear all
    count = 0
    for f in agent_dir.glob("*.md"):
        f.unlink()
        count += 1
    # Remove empty dir
    if not any(agent_dir.iterdir()):
        agent_dir.rmdir()
    return count


def repo_key(repo_path: str) -> str:
    """Convert a repo path to a safe memory key.

    '/home/user/my-app' -> 'repo--home-user-my-app'
    'C:\\Users\\me\\project' -> 'repo-c-users-me-project'
    """
    clean = repo_path.replace("\\", "/").replace("~", "").lower()
    clean = re.sub(r"[^a-z0-9/\-]", "", clean)
    clean = clean.strip("/").replace("/", "-")
    return f"repo-{clean}"
