"""Tests for agent CRUD routes."""

import pytest


class TestAgentCreate:

    @pytest.mark.asyncio
    async def test_create_agent(self, client):
        resp = await client.post("/api/agents", json={
            "name": "Research Topic",
            "description": "Research a given topic thoroughly",
        })
        assert resp.status_code == 201
        data = resp.json()
        assert data["name"] == "Research Topic"
        assert data["id"] is not None
        assert data["type"] == "agent"
        assert data["status"] == "creating"

    @pytest.mark.asyncio
    async def test_create_agent_with_samples(self, client):
        resp = await client.post("/api/agents", json={
            "name": "Write Article",
            "description": "Write an article",
            "samples": ["## Example Article\n\nContent here..."],
        })
        assert resp.status_code == 201
        assert resp.json()["samples"] == ["## Example Article\n\nContent here..."]

    @pytest.mark.asyncio
    async def test_create_agent_empty_name_fails(self, client):
        resp = await client.post("/api/agents", json={
            "name": "",
            "description": "desc",
        })
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_create_agent_missing_name_fails(self, client):
        resp = await client.post("/api/agents", json={
            "description": "desc",
        })
        assert resp.status_code == 422


class TestAgentGet:

    @pytest.mark.asyncio
    async def test_get_agent(self, client):
        create = await client.post("/api/agents", json={"name": "T", "description": ""})
        agent_id = create.json()["id"]
        resp = await client.get(f"/api/agents/{agent_id}")
        assert resp.status_code == 200
        assert resp.json()["id"] == agent_id

    @pytest.mark.asyncio
    async def test_get_nonexistent_returns_404(self, client):
        resp = await client.get("/api/agents/nonexistent")
        assert resp.status_code == 404
        assert resp.json()["error"]["code"] == "AGENT_NOT_FOUND"


class TestAgentList:

    @pytest.mark.asyncio
    async def test_list_agents(self, client):
        await client.post("/api/agents", json={"name": "A", "description": ""})
        await client.post("/api/agents", json={"name": "B", "description": ""})
        resp = await client.get("/api/agents")
        assert resp.status_code == 200
        assert len(resp.json()) == 2


class TestAgentUpdate:

    @pytest.mark.asyncio
    async def test_update_agent(self, client):
        create = await client.post("/api/agents", json={"name": "Old", "description": ""})
        agent_id = create.json()["id"]
        resp = await client.put(f"/api/agents/{agent_id}", json={"name": "New"})
        assert resp.status_code == 200
        assert resp.json()["name"] == "New"

    @pytest.mark.asyncio
    async def test_update_nonexistent_returns_404(self, client):
        resp = await client.put("/api/agents/nonexistent", json={"name": "X"})
        assert resp.status_code == 404


class TestAgentDelete:

    @pytest.mark.asyncio
    async def test_delete_agent(self, client):
        create = await client.post("/api/agents", json={"name": "T", "description": ""})
        agent_id = create.json()["id"]
        resp = await client.delete(f"/api/agents/{agent_id}")
        assert resp.status_code == 204
        get_resp = await client.get(f"/api/agents/{agent_id}")
        assert get_resp.status_code == 404

    @pytest.mark.asyncio
    async def test_delete_nonexistent_returns_404(self, client):
        resp = await client.delete("/api/agents/nonexistent")
        assert resp.status_code == 404


class TestAgentRun:

    @pytest.mark.asyncio
    async def test_run_agent_standalone(self, client):
        create = await client.post("/api/agents", json={
            "name": "T", "description": "do something",
        })
        agent_id = create.json()["id"]
        resp = await client.post(f"/api/agents/{agent_id}/run", json={
            "inputs": {"topic": "AI Safety"},
        })
        assert resp.status_code == 202
        data = resp.json()
        assert data["run_id"] is not None
        assert data["status"] == "queued"

    @pytest.mark.asyncio
    async def test_run_nonexistent_agent_returns_404(self, client):
        resp = await client.post("/api/agents/nonexistent/run", json={"inputs": {}})
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_list_agent_runs(self, client):
        create = await client.post("/api/agents", json={"name": "T", "description": ""})
        agent_id = create.json()["id"]
        await client.post(f"/api/agents/{agent_id}/run", json={"inputs": {}})
        await client.post(f"/api/agents/{agent_id}/run", json={"inputs": {}})
        resp = await client.get(f"/api/agents/{agent_id}/runs")
        assert resp.status_code == 200
        assert len(resp.json()) == 2
