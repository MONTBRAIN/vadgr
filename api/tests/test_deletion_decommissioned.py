"""Decommission tests for the 0.4.4 deletion.

The workflow layer is gone: the agent entity, projects and the DAG, the
scaffolder, the bundle installer, the per-run output tree, and every run route
with no live consumer. Each test below pins one piece of that removal, so none
of it creeps back one import at a time.

Half of them pin the opposite fact, and that half is the more important one. A
transitional watch surface survives this release for the shipped phone and the
CLI, and a guard that only checked absence would pass a release that deleted it
by accident. Presence is asserted as loudly as absence.

Follows the two shipped precedents (`test_frontend_decommissioned.py`,
`test_gateway_decommissioned.py`), including their two rules: assertions may
hold by construction, and CLI facts are asserted at source level so they run in
the api venv, which does not ship the CLI dependency tree.
"""

from __future__ import annotations

import importlib
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent.parent


# --- 1. the trees -----------------------------------------------------------


def test_scaffolder_and_installer_trees_are_gone():
    assert not (REPO_ROOT / "forge").exists(), "forge/ still present"
    assert not (REPO_ROOT / "registry").exists(), "registry/ still present"


def test_the_output_tree_is_no_longer_part_of_the_repository():
    """The repository loses `output/`; an owner's disk keeps theirs.

    Asserted on what the repository carries rather than on what happens to be
    on this machine: deleting hundreds of megabytes of somebody's own files
    during an upgrade is exactly the unscoped destructive behaviour this
    release is removing from the API, so an existing directory is left alone
    and only the tracked placeholder goes.
    """
    assert not (REPO_ROOT / "output" / ".gitkeep").exists(), "output/ is still tracked"


# --- 2. the modules ---------------------------------------------------------


_DELETED_MODULES = [
    "api.routes.agents",
    "api.routes.projects",
    "api.engine.dag",
    "api.engine.executor",
    "api.services.agent_service",
    "api.services.project_service",
    "api.services.artifact_service",
    "api.services.log_writer",
    "api.services.computer_use_service",
    "api.models.agent",
    "api.models.project",
    "cli.commands.agents",
    "cli.commands.registry",
]


@pytest.mark.parametrize("module", _DELETED_MODULES)
def test_deleted_module_cannot_be_imported(module):
    with pytest.raises(ModuleNotFoundError):
        importlib.import_module(module)


# --- 3. the routes that are gone --------------------------------------------


def _routes(app):
    return [r for r in app.routes if hasattr(r, "path")]


@pytest.fixture(scope="module")
def app():
    from api.main import create_app

    return create_app()


def test_no_agent_or_project_route_survives(app):
    offending = [
        r.path for r in _routes(app)
        if "agents" in r.path or "projects" in r.path
    ]
    assert offending == [], f"workflow routes still mounted: {offending}"


def test_runs_cannot_be_deleted_wholesale(app):
    """An unscoped destructive verb with no confirmation."""
    methods = set()
    for r in _routes(app):
        if r.path == "/api/runs":
            methods |= set(getattr(r, "methods", set()) or set())
    assert "DELETE" not in methods


def test_the_output_and_log_reading_routes_are_gone(app):
    for suffix in ("/approve", "/logs", "/logs/{step_file}", "/outputs/{field_name}"):
        offending = [r.path for r in _routes(app) if r.path.endswith(suffix)]
        assert offending == [], f"{suffix} still served at {offending}"


# --- 4. the quarantine, which must NOT be gone ------------------------------


_QUARANTINE = [
    ("/api/runs", "GET"),
    ("/api/runs/{run_id}", "GET"),
    ("/api/runs", "POST"),
]

_SOCKETS = ["/api/runs/{run_id}/stream", "/api/ws/runs/{run_id}"]


@pytest.mark.parametrize("path,method", _QUARANTINE)
def test_the_watch_surface_is_intact(app, path, method):
    """What the shipped phone reads. Frozen, not contract, and deleted only
    when its replacement ships."""
    matches = [
        r for r in _routes(app)
        if r.path == path and method in (getattr(r, "methods", set()) or set())
    ]
    assert matches, f"{method} {path} is missing"


@pytest.mark.parametrize("path", _SOCKETS)
def test_the_two_sockets_are_intact(app, path):
    matches = [r for r in _routes(app) if r.path == path and not hasattr(r, "methods")]
    assert matches, f"socket {path} is missing"


# --- 5. the schema ----------------------------------------------------------


@pytest.mark.asyncio
async def test_the_schema_is_two_tables_and_one_index():
    from api.persistence.database import Database

    db = Database(":memory:")
    await db.connect()
    try:
        await db.create_tables()
        rows = await db.conn.execute_fetchall(
            "SELECT type, name FROM sqlite_master WHERE name NOT LIKE 'sqlite_%'"
        )
        assert sorted(r["name"] for r in rows if r["type"] == "table") == ["devices", "runs"]
        assert sorted(r["name"] for r in rows if r["type"] == "index") == ["idx_devices_token_hash"]

        cols = {r["name"] for r in await db.conn.execute_fetchall("PRAGMA table_info(runs)")}
        assert "title" in cols
        assert "agent_id" not in cols
        assert "project_id" not in cols
    finally:
        await db.disconnect()


# --- 6. the frame vocabulary ------------------------------------------------


def test_step_completed_left_the_vocabulary():
    from api.routes.ws import _EVENT_TYPE_MAP

    assert "step_completed" not in _EVENT_TYPE_MAP


def test_the_map_is_asserted_in_both_directions():
    """A dead branch and a rare branch look identical from inside."""
    from api.routes.ws import _EVENT_TYPE_MAP, _NOT_YET_ON_THIS_STREAM
    from api.tests.frames import emitted_frame_names

    emitted = emitted_frame_names()
    known = set(_EVENT_TYPE_MAP) | set(_NOT_YET_ON_THIS_STREAM)

    assert not (set(_EVENT_TYPE_MAP) - emitted), (
        f"mapped but never broadcast: {sorted(set(_EVENT_TYPE_MAP) - emitted)}"
    )
    assert not (emitted - known), (
        f"broadcast but neither mapped nor deferred: {sorted(emitted - known)}"
    )


# --- 7. the dependency and the helper ---------------------------------------


def test_the_upload_dependency_is_gone():
    """Only the agent upload and import routes needed it."""
    requirements = (REPO_ROOT / "api" / "requirements.txt").read_text()
    assert "python-multipart" not in requirements


def test_the_tree_removing_helper_is_gone():
    """Both of its callers were deleted, so it went with them."""
    source = (REPO_ROOT / "api" / "utils" / "platform.py").read_text()
    assert "force_rmtree" not in source


# --- 8. the CLI, at source level --------------------------------------------


def test_the_cli_registers_no_deleted_group():
    source = (REPO_ROOT / "cli" / "main.py").read_text()
    for needle in ("agents_group", "registry_group", '"ps"'):
        assert needle not in source, f"cli/main.py still registers {needle}"


def test_the_run_commands_lost_approve_and_logs():
    source = (REPO_ROOT / "cli" / "commands" / "runs.py").read_text()
    for needle in ("approve", "logs"):
        assert needle not in source, f"cli/commands/runs.py still offers {needle}"


def test_the_watcher_no_longer_expects_a_step_frame():
    source = (REPO_ROOT / "cli" / "stream.py").read_text()
    assert "step_completed" not in source
    assert "_extract_step" not in source


# --- 9. CI and the ignore file ----------------------------------------------


def test_ci_runs_no_scaffolder_job():
    workflow = (REPO_ROOT / ".github" / "workflows" / "ci.yml").read_text()
    assert "forge" not in workflow


def test_the_ignore_file_no_longer_names_the_output_tree():
    lines = (REPO_ROOT / ".gitignore").read_text().splitlines()
    assert "/output" not in [line.strip() for line in lines]


# --- 10. the health payload -------------------------------------------------


@pytest.mark.asyncio
async def test_health_reports_no_module_the_machine_does_not_have(client):
    modules = (await client.get("/api/health")).json()["modules"]
    assert "forge" not in modules
    assert "computer_use" in modules
