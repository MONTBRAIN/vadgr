"""Check source metadata and notices before generating a distribution inventory."""

from pathlib import Path
import tomllib

import pytest


ROOT = Path(__file__).resolve().parents[2]


def check_license(root):
    package = tomllib.loads((root / "Cargo.toml").read_text(encoding="utf-8"))["package"]
    assert package.get("license") == "Apache-2.0"
    license_text = (root / "LICENSE").read_text(encoding="utf-8")
    assert "Apache License" in license_text and "Version 2.0, January 2004" in license_text


def check_notice(root):
    notice = " ".join((root / "NOTICE").read_text(encoding="utf-8").split())
    assert "machine daemon" in notice
    assert "provider APIs directly" in notice
    assert "builds the agent" not in notice
    assert "or any CLI agent tool" not in notice
    copyright_line = next(line.strip() for line in (root / "LICENSE").read_text(encoding="utf-8").splitlines()
                          if line.strip().startswith("Copyright "))
    assert copyright_line in notice
    assert "https://github.com/MONTBRAIN/vadgr" in notice
    assert "Licensed under the Apache License, Version 2.0." in notice


def test_package_declares_the_license_shipped_in_source():
    check_license(ROOT)


def test_notice_describes_the_current_runtime_and_preserves_attribution():
    check_notice(ROOT)


@pytest.fixture
def isolated_package(tmp_path):
    for name in ("Cargo.toml", "LICENSE", "NOTICE"):
        (tmp_path / name).write_bytes((ROOT / name).read_bytes())
    return tmp_path


def test_prior_missing_license_metadata_is_rejected(isolated_package):
    manifest = isolated_package / "Cargo.toml"
    manifest.write_text(manifest.read_text(encoding="utf-8").replace('license = "Apache-2.0"\n', ""), encoding="utf-8")
    with pytest.raises(AssertionError):
        check_license(isolated_package)


def test_prior_cli_agent_notice_is_rejected(isolated_package):
    copyright_line = next(line.strip() for line in (isolated_package / "LICENSE").read_text(encoding="utf-8").splitlines()
                          if line.strip().startswith("Copyright "))
    (isolated_package / "NOTICE").write_text(
        f"Vadgr\n{copyright_line}\n\n"
        "Vadgr is a platform for AI agents that work on your computer. Describe\n"
        "your task, Vadgr builds the agent, and the agent runs autonomously --\n"
        "writing code, controlling apps, and delivering results. Works with\n"
        "Claude, Codex, Gemini, or any CLI agent tool.\n\n"
        "https://github.com/MONTBRAIN/vadgr\n\n"
        "Licensed under the Apache License, Version 2.0.\n", encoding="utf-8",
    )
    with pytest.raises(AssertionError):
        check_notice(isolated_package)
