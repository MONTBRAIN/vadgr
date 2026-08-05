"""Decommission tests for the 0.4.2 web-frontend removal.

The React dashboard is gone and the machine's clients are the CLI and the
phone.  Each test below pins one piece of that removal, so the frontend -- and
with it the whole Node toolchain -- cannot creep back one import at a time.
Mirrors the 0.2.0 gateway guard.
"""

from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent


def test_frontend_directory_removed():
    """The React dashboard directory must not exist."""
    assert not (REPO_ROOT / "frontend").exists(), "frontend/ directory still present"


def test_no_node_manifests_anywhere():
    """No npm manifest may return to the repo, in any subtree."""
    manifests = [
        p
        for p in REPO_ROOT.rglob("package.json")
        if ".venv" not in p.parts and "node_modules" not in p.parts
    ]
    assert manifests == [], f"npm manifests present: {manifests}"


def test_settings_has_no_frontend_port_or_cors():
    """Settings must carry neither a frontend port nor a CORS allowlist."""
    from api.config import Settings

    fields = Settings.model_fields
    assert "frontend_port" not in fields
    assert "cors_origins" not in fields
    assert not hasattr(Settings(), "frontend_port")
    assert not hasattr(Settings(), "cors_origins")


def test_no_cors_middleware_installed():
    """No browser client remains, so the app serves no CORS headers."""
    from api.main import create_app

    app = create_app()
    installed = [m.cls.__name__ for m in app.user_middleware]
    assert "CORSMiddleware" not in installed, f"CORS still installed: {installed}"


def test_service_module_has_no_npm_start_path():
    """`vadgr start` must not look for node/npm or spawn a dev server.

    Source-level assertion so it runs in the api venv, which does not ship the
    CLI dep tree.
    """
    src = (REPO_ROOT / "cli" / "commands" / "service.py").read_text()
    for needle in ("_find_node", "_find_npm", "npm", "node", "frontend", "vite"):
        assert needle not in src.lower(), f"service.py still references {needle!r}"


def test_cli_exposes_no_frontend_port_flag():
    """No command may still offer a --frontend-port flag."""
    for module in ("cli/main.py", "cli/commands/service.py", "cli/stream.py"):
        src = (REPO_ROOT / module).read_text()
        assert "frontend-port" not in src, f"{module} still offers --frontend-port"
        assert "FRONTEND_PORT" not in src, f"{module} still reads a frontend port"


def test_setup_scripts_install_no_node():
    """Installing vadgr must pull in no Node.js, NVM or npm."""
    for script in ("setup.sh", "setup.ps1"):
        lowered = (REPO_ROOT / script).read_text().lower()
        for needle in ("nvm", "node", "npm", "frontend"):
            assert needle not in lowered, f"{script} still installs/uses {needle!r}"
