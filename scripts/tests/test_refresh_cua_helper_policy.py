"""Helper policies must follow the exact approved replacement closure."""

from pathlib import Path

from scripts.refresh_cua_helper_policy import rebuild

ROOT = Path(__file__).resolve().parents[2]


def test_helper_policies_match_approved_replacement_records():
    for architecture in ("x86_64", "aarch64"):
        path = ROOT / "packaging/cua/helper-signing" / f"{architecture}.json"
        assert path.read_bytes() == rebuild(ROOT, architecture)
