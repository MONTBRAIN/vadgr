"""Tests for run lifecycle routes."""

import pytest


class TestProjectRuns:

    @pytest.mark.asyncio
    async def test_start_project_run(self, client):
        agent = await client.post("/api/agents", json={"name": "T", "description": ""})
        project = await client.post("/api/projects", json={"name": "P", "description": ""})
        pid = project.json()["id"]
        await client.post(f"/api/projects/{pid}/nodes", json={
            "agent_id": agent.json()["id"],
        })
        resp = await client.post(f"/api/projects/{pid}/runs", json={
            "inputs": {"topic": "AI"},
        })
        assert resp.status_code == 202
        data = resp.json()
        assert data["run_id"] is not None
        assert data["status"] == "queued"

    @pytest.mark.asyncio
    async def test_start_run_nonexistent_project_returns_404(self, client):
        resp = await client.post("/api/projects/nonexistent/runs", json={"inputs": {}})
        assert resp.status_code == 404


class TestRunGet:

    @pytest.mark.asyncio
    async def test_get_run(self, client, app):
        agent = await client.post("/api/agents", json={"name": "T", "description": ""})
        agent_id = agent.json()["id"]
        await app.state.agent_repo.update(agent_id, status="ready")
        run = await client.post(f"/api/agents/{agent_id}/run", json={"inputs": {}})
        run_id = run.json()["run_id"]
        resp = await client.get(f"/api/runs/{run_id}")
        assert resp.status_code == 200
        assert resp.json()["id"] == run_id

    @pytest.mark.asyncio
    async def test_get_nonexistent_run_returns_404(self, client):
        resp = await client.get("/api/runs/nonexistent")
        assert resp.status_code == 404


class TestRunList:

    @pytest.mark.asyncio
    async def test_list_runs(self, client, app):
        agent = await client.post("/api/agents", json={"name": "T", "description": ""})
        agent_id = agent.json()["id"]
        await app.state.agent_repo.update(agent_id, status="ready")
        await client.post(f"/api/agents/{agent_id}/run", json={"inputs": {}})
        resp = await client.get("/api/runs")
        assert resp.status_code == 200
        assert len(resp.json()) >= 1

    @pytest.mark.asyncio
    async def test_list_runs_filter_by_status(self, client, app):
        agent = await client.post("/api/agents", json={"name": "T", "description": ""})
        agent_id = agent.json()["id"]
        await app.state.agent_repo.update(agent_id, status="ready")
        await client.post(f"/api/agents/{agent_id}/run", json={"inputs": {}})
        resp = await client.get("/api/runs", params={"status": "queued"})
        assert resp.status_code == 200
        assert all(r["status"] == "queued" for r in resp.json())
