"""Tests for the SQLite persistence layer."""

import pytest
import pytest_asyncio

from api.persistence.database import Database
from api.persistence.repositories import RunRepository


@pytest_asyncio.fixture
async def db():
    database = Database(":memory:")
    await database.connect()
    await database.create_tables()
    yield database
    await database.disconnect()


@pytest_asyncio.fixture
async def run_repo(db):
    return RunRepository(db)


class TestSchema:

    @pytest.mark.asyncio
    async def test_holds_two_tables_and_one_index(self, db):
        """The schema is runs and devices, and nothing else."""
        rows = await db.conn.execute_fetchall(
            "SELECT type, name FROM sqlite_master WHERE name NOT LIKE 'sqlite_%'"
        )
        tables = sorted(r["name"] for r in rows if r["type"] == "table")
        indexes = sorted(r["name"] for r in rows if r["type"] == "index")
        assert tables == ["devices", "runs"]
        assert indexes == ["idx_devices_token_hash"]

    @pytest.mark.asyncio
    async def test_runs_has_title_and_no_owner_columns(self, db):
        cols = {r["name"] for r in await db.conn.execute_fetchall("PRAGMA table_info(runs)")}
        assert "title" in cols
        assert "agent_id" not in cols
        assert "project_id" not in cols


class TestRunRepository:

    @pytest.mark.asyncio
    async def test_create_and_get(self, run_repo):
        run = await run_repo.create(title="Tidy the inbox", inputs={"task": "Tidy the inbox"})
        assert run["id"] is not None
        assert run["status"] == "queued"
        assert run["inputs"] == {"task": "Tidy the inbox"}
        assert run["provider"] is None
        assert run["model"] is None

        fetched = await run_repo.get(run["id"])
        assert fetched["id"] == run["id"]

    @pytest.mark.asyncio
    async def test_get_nonexistent_returns_none(self, run_repo):
        assert await run_repo.get("nonexistent") is None

    @pytest.mark.asyncio
    async def test_title_is_published_as_agent_name(self, run_repo):
        """The wire key outlives the entity it was named for."""
        run = await run_repo.create(title="Summarise the week")
        assert run["agent_name"] == "Summarise the week"
        assert "title" not in run

    @pytest.mark.asyncio
    async def test_row_carries_no_owner_keys(self, run_repo):
        run = await run_repo.create(title="X")
        assert "agent_id" not in run
        assert "project_id" not in run

    @pytest.mark.asyncio
    async def test_untitled_run_serves_an_empty_string(self, run_repo):
        run = await run_repo.create()
        assert run["agent_name"] == ""

    @pytest.mark.asyncio
    async def test_create_with_provider_and_model(self, run_repo):
        run = await run_repo.create(
            title="T", inputs={"task": "T"}, provider="codex", model="gpt-5.4",
        )
        assert run["provider"] == "codex"
        assert run["model"] == "gpt-5.4"

    @pytest.mark.asyncio
    async def test_update_status(self, run_repo):
        run = await run_repo.create(title="T")
        updated = await run_repo.update_status(run["id"], "running")
        assert updated["status"] == "running"
        assert updated["started_at"] is not None

    @pytest.mark.asyncio
    async def test_complete_run(self, run_repo):
        run = await run_repo.create(title="T")
        await run_repo.update_status(run["id"], "running")
        completed = await run_repo.update_status(
            run["id"], "completed", outputs={"result": "done"}
        )
        assert completed["status"] == "completed"
        assert completed["outputs"] == {"result": "done"}
        assert completed["completed_at"] is not None

    @pytest.mark.asyncio
    async def test_list_all(self, run_repo):
        await run_repo.create(title="A")
        await run_repo.create(title="B")
        assert len(await run_repo.list_all()) == 2

    @pytest.mark.asyncio
    async def test_list_all_filters_by_status(self, run_repo):
        a = await run_repo.create(title="A")
        await run_repo.create(title="B")
        await run_repo.update_status(a["id"], "running")
        running = await run_repo.list_all(status="running")
        assert [r["id"] for r in running] == [a["id"]]
