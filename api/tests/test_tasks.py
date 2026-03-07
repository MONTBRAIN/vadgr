"""Tests for task CRUD routes."""

import pytest


class TestTaskCreate:

    @pytest.mark.asyncio
    async def test_create_task(self, client):
        resp = await client.post("/api/tasks", json={
            "name": "Research Topic",
            "description": "Research a given topic thoroughly",
        })
        assert resp.status_code == 201
        data = resp.json()
        assert data["name"] == "Research Topic"
        assert data["id"] is not None
        assert data["type"] == "task"

    @pytest.mark.asyncio
    async def test_create_task_with_samples(self, client):
        resp = await client.post("/api/tasks", json={
            "name": "Write Article",
            "description": "Write an article",
            "samples": ["## Example Article\n\nContent here..."],
        })
        assert resp.status_code == 201
        assert resp.json()["samples"] == ["## Example Article\n\nContent here..."]

    @pytest.mark.asyncio
    async def test_create_task_empty_name_fails(self, client):
        resp = await client.post("/api/tasks", json={
            "name": "",
            "description": "desc",
        })
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_create_task_missing_name_fails(self, client):
        resp = await client.post("/api/tasks", json={
            "description": "desc",
        })
        assert resp.status_code == 422


class TestTaskGet:

    @pytest.mark.asyncio
    async def test_get_task(self, client):
        create = await client.post("/api/tasks", json={"name": "T", "description": ""})
        task_id = create.json()["id"]
        resp = await client.get(f"/api/tasks/{task_id}")
        assert resp.status_code == 200
        assert resp.json()["id"] == task_id

    @pytest.mark.asyncio
    async def test_get_nonexistent_returns_404(self, client):
        resp = await client.get("/api/tasks/nonexistent")
        assert resp.status_code == 404
        assert resp.json()["error"]["code"] == "TASK_NOT_FOUND"


class TestTaskList:

    @pytest.mark.asyncio
    async def test_list_tasks(self, client):
        await client.post("/api/tasks", json={"name": "A", "description": ""})
        await client.post("/api/tasks", json={"name": "B", "description": ""})
        resp = await client.get("/api/tasks")
        assert resp.status_code == 200
        assert len(resp.json()) == 2


class TestTaskUpdate:

    @pytest.mark.asyncio
    async def test_update_task(self, client):
        create = await client.post("/api/tasks", json={"name": "Old", "description": ""})
        task_id = create.json()["id"]
        resp = await client.put(f"/api/tasks/{task_id}", json={"name": "New"})
        assert resp.status_code == 200
        assert resp.json()["name"] == "New"

    @pytest.mark.asyncio
    async def test_update_nonexistent_returns_404(self, client):
        resp = await client.put("/api/tasks/nonexistent", json={"name": "X"})
        assert resp.status_code == 404


class TestTaskDelete:

    @pytest.mark.asyncio
    async def test_delete_task(self, client):
        create = await client.post("/api/tasks", json={"name": "T", "description": ""})
        task_id = create.json()["id"]
        resp = await client.delete(f"/api/tasks/{task_id}")
        assert resp.status_code == 204
        get_resp = await client.get(f"/api/tasks/{task_id}")
        assert get_resp.status_code == 404

    @pytest.mark.asyncio
    async def test_delete_nonexistent_returns_404(self, client):
        resp = await client.delete("/api/tasks/nonexistent")
        assert resp.status_code == 404


class TestTaskRun:

    @pytest.mark.asyncio
    async def test_run_task_standalone(self, client):
        create = await client.post("/api/tasks", json={
            "name": "T", "description": "do something",
        })
        task_id = create.json()["id"]
        resp = await client.post(f"/api/tasks/{task_id}/run", json={
            "inputs": {"topic": "AI Safety"},
        })
        assert resp.status_code == 202
        data = resp.json()
        assert data["run_id"] is not None
        assert data["status"] == "queued"

    @pytest.mark.asyncio
    async def test_run_nonexistent_task_returns_404(self, client):
        resp = await client.post("/api/tasks/nonexistent/run", json={"inputs": {}})
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_list_task_runs(self, client):
        create = await client.post("/api/tasks", json={"name": "T", "description": ""})
        task_id = create.json()["id"]
        await client.post(f"/api/tasks/{task_id}/run", json={"inputs": {}})
        await client.post(f"/api/tasks/{task_id}/run", json={"inputs": {}})
        resp = await client.get(f"/api/tasks/{task_id}/runs")
        assert resp.status_code == 200
        assert len(resp.json()) == 2
