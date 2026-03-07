"""Tests for SQLite persistence layer.

RED phase -- tests define the repository contract.
"""

import pytest
import pytest_asyncio

from api.persistence.database import Database
from api.persistence.repositories import TaskRepository, ProjectRepository, RunRepository


@pytest_asyncio.fixture
async def db():
    database = Database(":memory:")
    await database.connect()
    await database.create_tables()
    yield database
    await database.disconnect()


@pytest_asyncio.fixture
async def task_repo(db):
    return TaskRepository(db)


@pytest_asyncio.fixture
async def project_repo(db):
    return ProjectRepository(db)


@pytest_asyncio.fixture
async def run_repo(db):
    return RunRepository(db)


class TestTaskRepository:

    @pytest.mark.asyncio
    async def test_create_and_get(self, task_repo):
        task = await task_repo.create(
            name="Research",
            description="Research a topic",
        )
        assert task["id"] is not None
        assert task["name"] == "Research"
        assert task["type"] == "task"

        fetched = await task_repo.get(task["id"])
        assert fetched["name"] == "Research"

    @pytest.mark.asyncio
    async def test_get_nonexistent_returns_none(self, task_repo):
        result = await task_repo.get("nonexistent")
        assert result is None

    @pytest.mark.asyncio
    async def test_list_all(self, task_repo):
        await task_repo.create(name="A", description="")
        await task_repo.create(name="B", description="")
        tasks = await task_repo.list_all()
        assert len(tasks) == 2

    @pytest.mark.asyncio
    async def test_update(self, task_repo):
        task = await task_repo.create(name="Old", description="")
        updated = await task_repo.update(task["id"], name="New")
        assert updated["name"] == "New"

    @pytest.mark.asyncio
    async def test_update_nonexistent_returns_none(self, task_repo):
        result = await task_repo.update("nonexistent", name="X")
        assert result is None

    @pytest.mark.asyncio
    async def test_delete(self, task_repo):
        task = await task_repo.create(name="ToDelete", description="")
        deleted = await task_repo.delete(task["id"])
        assert deleted is True
        assert await task_repo.get(task["id"]) is None

    @pytest.mark.asyncio
    async def test_delete_nonexistent(self, task_repo):
        deleted = await task_repo.delete("nonexistent")
        assert deleted is False

    @pytest.mark.asyncio
    async def test_create_with_samples(self, task_repo):
        task = await task_repo.create(
            name="WithSamples",
            description="desc",
            samples=["sample 1", "sample 2"],
        )
        fetched = await task_repo.get(task["id"])
        assert fetched["samples"] == ["sample 1", "sample 2"]

    @pytest.mark.asyncio
    async def test_create_with_schemas(self, task_repo):
        task = await task_repo.create(
            name="WithSchema",
            description="desc",
            input_schema=[{"name": "topic", "type": "text", "required": True}],
            output_schema=[{"name": "result", "type": "text", "required": True}],
        )
        fetched = await task_repo.get(task["id"])
        assert len(fetched["input_schema"]) == 1
        assert fetched["input_schema"][0]["name"] == "topic"


class TestProjectRepository:

    @pytest.mark.asyncio
    async def test_create_and_get(self, project_repo):
        project = await project_repo.create(name="My Project", description="desc")
        assert project["id"] is not None
        fetched = await project_repo.get(project["id"])
        assert fetched["name"] == "My Project"

    @pytest.mark.asyncio
    async def test_get_nonexistent_returns_none(self, project_repo):
        result = await project_repo.get("nonexistent")
        assert result is None

    @pytest.mark.asyncio
    async def test_add_and_get_nodes(self, project_repo, task_repo):
        task = await task_repo.create(name="T", description="")
        project = await project_repo.create(name="P", description="")
        node = await project_repo.add_node(
            project_id=project["id"],
            task_id=task["id"],
            position_x=100.0,
            position_y=200.0,
        )
        assert node["id"] is not None
        assert node["position_x"] == 100.0

        nodes = await project_repo.get_nodes(project["id"])
        assert len(nodes) == 1

    @pytest.mark.asyncio
    async def test_add_and_get_edges(self, project_repo, task_repo):
        t1 = await task_repo.create(name="T1", description="")
        t2 = await task_repo.create(name="T2", description="")
        project = await project_repo.create(name="P", description="")
        n1 = await project_repo.add_node(project["id"], t1["id"])
        n2 = await project_repo.add_node(project["id"], t2["id"])
        edge = await project_repo.add_edge(
            project_id=project["id"],
            source_node_id=n1["id"],
            target_node_id=n2["id"],
            source_output="out",
            target_input="in",
        )
        assert edge["id"] is not None

        edges = await project_repo.get_edges(project["id"])
        assert len(edges) == 1

    @pytest.mark.asyncio
    async def test_delete_node(self, project_repo, task_repo):
        task = await task_repo.create(name="T", description="")
        project = await project_repo.create(name="P", description="")
        node = await project_repo.add_node(project["id"], task["id"])
        deleted = await project_repo.delete_node(node["id"])
        assert deleted is True
        nodes = await project_repo.get_nodes(project["id"])
        assert len(nodes) == 0

    @pytest.mark.asyncio
    async def test_delete_project(self, project_repo):
        project = await project_repo.create(name="P", description="")
        deleted = await project_repo.delete(project["id"])
        assert deleted is True
        assert await project_repo.get(project["id"]) is None

    @pytest.mark.asyncio
    async def test_list_all(self, project_repo):
        await project_repo.create(name="A", description="")
        await project_repo.create(name="B", description="")
        projects = await project_repo.list_all()
        assert len(projects) == 2


class TestRunRepository:

    @pytest.mark.asyncio
    async def test_create_standalone_run(self, run_repo, task_repo):
        task = await task_repo.create(name="T", description="")
        run = await run_repo.create(task_id=task["id"], inputs={"topic": "AI"})
        assert run["id"] is not None
        assert run["task_id"] == task["id"]
        assert run["project_id"] is None
        assert run["status"] == "queued"

    @pytest.mark.asyncio
    async def test_create_project_run(self, run_repo, project_repo):
        project = await project_repo.create(name="P", description="")
        run = await run_repo.create(project_id=project["id"], inputs={"x": 1})
        assert run["project_id"] == project["id"]
        assert run["task_id"] is None

    @pytest.mark.asyncio
    async def test_get_run(self, run_repo, task_repo):
        task = await task_repo.create(name="T", description="")
        run = await run_repo.create(task_id=task["id"])
        fetched = await run_repo.get(run["id"])
        assert fetched["id"] == run["id"]

    @pytest.mark.asyncio
    async def test_update_status(self, run_repo, task_repo):
        task = await task_repo.create(name="T", description="")
        run = await run_repo.create(task_id=task["id"])
        updated = await run_repo.update_status(run["id"], "running")
        assert updated["status"] == "running"
        assert updated["started_at"] is not None

    @pytest.mark.asyncio
    async def test_complete_run(self, run_repo, task_repo):
        task = await task_repo.create(name="T", description="")
        run = await run_repo.create(task_id=task["id"])
        await run_repo.update_status(run["id"], "running")
        completed = await run_repo.update_status(
            run["id"], "completed", outputs={"result": "done"}
        )
        assert completed["status"] == "completed"
        assert completed["outputs"] == {"result": "done"}
        assert completed["completed_at"] is not None

    @pytest.mark.asyncio
    async def test_list_runs_by_task(self, run_repo, task_repo):
        task = await task_repo.create(name="T", description="")
        await run_repo.create(task_id=task["id"])
        await run_repo.create(task_id=task["id"])
        runs = await run_repo.list_by_task(task["id"])
        assert len(runs) == 2

    @pytest.mark.asyncio
    async def test_list_runs_by_project(self, run_repo, project_repo):
        project = await project_repo.create(name="P", description="")
        await run_repo.create(project_id=project["id"])
        runs = await run_repo.list_by_project(project["id"])
        assert len(runs) == 1
