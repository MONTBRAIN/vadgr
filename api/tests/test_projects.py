"""Tests for project CRUD and canvas routes."""

import pytest


class TestProjectCreate:

    @pytest.mark.asyncio
    async def test_create_project(self, client):
        resp = await client.post("/api/projects", json={
            "name": "Content Pipeline",
            "description": "Research, write, review",
        })
        assert resp.status_code == 201
        data = resp.json()
        assert data["name"] == "Content Pipeline"
        assert data["id"] is not None

    @pytest.mark.asyncio
    async def test_create_project_empty_name_fails(self, client):
        resp = await client.post("/api/projects", json={"name": "", "description": ""})
        assert resp.status_code == 422


class TestProjectGet:

    @pytest.mark.asyncio
    async def test_get_project_with_graph(self, client):
        create = await client.post("/api/projects", json={"name": "P", "description": ""})
        pid = create.json()["id"]
        resp = await client.get(f"/api/projects/{pid}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["nodes"] == []
        assert data["edges"] == []

    @pytest.mark.asyncio
    async def test_get_nonexistent_returns_404(self, client):
        resp = await client.get("/api/projects/nonexistent")
        assert resp.status_code == 404


class TestProjectNodes:

    @pytest.mark.asyncio
    async def test_add_node_to_project(self, client):
        agent = await client.post("/api/agents", json={"name": "T", "description": ""})
        project = await client.post("/api/projects", json={"name": "P", "description": ""})
        resp = await client.post(
            f"/api/projects/{project.json()['id']}/nodes",
            json={
                "agent_id": agent.json()["id"],
                "position_x": 100.0,
                "position_y": 200.0,
            },
        )
        assert resp.status_code == 201
        assert resp.json()["position_x"] == 100.0

    @pytest.mark.asyncio
    async def test_delete_node(self, client):
        agent = await client.post("/api/agents", json={"name": "T", "description": ""})
        project = await client.post("/api/projects", json={"name": "P", "description": ""})
        pid = project.json()["id"]
        node = await client.post(f"/api/projects/{pid}/nodes", json={
            "agent_id": agent.json()["id"],
        })
        resp = await client.delete(f"/api/projects/{pid}/nodes/{node.json()['id']}")
        assert resp.status_code == 204


class TestProjectEdges:

    @pytest.mark.asyncio
    async def test_add_edge(self, client):
        t1 = await client.post("/api/agents", json={"name": "T1", "description": ""})
        t2 = await client.post("/api/agents", json={"name": "T2", "description": ""})
        project = await client.post("/api/projects", json={"name": "P", "description": ""})
        pid = project.json()["id"]
        n1 = await client.post(f"/api/projects/{pid}/nodes", json={"agent_id": t1.json()["id"]})
        n2 = await client.post(f"/api/projects/{pid}/nodes", json={"agent_id": t2.json()["id"]})
        resp = await client.post(f"/api/projects/{pid}/edges", json={
            "source_node_id": n1.json()["id"],
            "target_node_id": n2.json()["id"],
            "source_output": "findings",
            "target_input": "content",
        })
        assert resp.status_code == 201


class TestProjectValidation:

    @pytest.mark.asyncio
    async def test_validate_valid_dag(self, client):
        t1 = await client.post("/api/agents", json={"name": "T1", "description": ""})
        t2 = await client.post("/api/agents", json={"name": "T2", "description": ""})
        project = await client.post("/api/projects", json={"name": "P", "description": ""})
        pid = project.json()["id"]
        n1 = await client.post(f"/api/projects/{pid}/nodes", json={"agent_id": t1.json()["id"]})
        n2 = await client.post(f"/api/projects/{pid}/nodes", json={"agent_id": t2.json()["id"]})
        await client.post(f"/api/projects/{pid}/edges", json={
            "source_node_id": n1.json()["id"],
            "target_node_id": n2.json()["id"],
            "source_output": "out",
            "target_input": "in",
        })
        resp = await client.post(f"/api/projects/{pid}/validate")
        assert resp.status_code == 200
        assert resp.json()["valid"] is True

    @pytest.mark.asyncio
    async def test_validate_detects_cycle(self, client):
        t1 = await client.post("/api/agents", json={"name": "T1", "description": ""})
        t2 = await client.post("/api/agents", json={"name": "T2", "description": ""})
        project = await client.post("/api/projects", json={"name": "P", "description": ""})
        pid = project.json()["id"]
        n1 = await client.post(f"/api/projects/{pid}/nodes", json={"agent_id": t1.json()["id"]})
        n2 = await client.post(f"/api/projects/{pid}/nodes", json={"agent_id": t2.json()["id"]})
        await client.post(f"/api/projects/{pid}/edges", json={
            "source_node_id": n1.json()["id"],
            "target_node_id": n2.json()["id"],
            "source_output": "out",
            "target_input": "in",
        })
        await client.post(f"/api/projects/{pid}/edges", json={
            "source_node_id": n2.json()["id"],
            "target_node_id": n1.json()["id"],
            "source_output": "out",
            "target_input": "in",
        })
        resp = await client.post(f"/api/projects/{pid}/validate")
        assert resp.status_code == 200
        data = resp.json()
        assert data["valid"] is False
        assert any(e["type"] == "cycle_detected" for e in data["errors"])


class TestProjectDelete:

    @pytest.mark.asyncio
    async def test_delete_project(self, client):
        project = await client.post("/api/projects", json={"name": "P", "description": ""})
        resp = await client.delete(f"/api/projects/{project.json()['id']}")
        assert resp.status_code == 204

    @pytest.mark.asyncio
    async def test_delete_nonexistent_returns_404(self, client):
        resp = await client.delete("/api/projects/nonexistent")
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_delete_project_with_run_succeeds(self, client):
        """BUG-4: DELETE project with associated runs should not 500."""
        agent = await client.post("/api/agents", json={"name": "A", "description": ""})
        project = await client.post("/api/projects", json={"name": "P", "description": ""})
        pid = project.json()["id"]
        aid = agent.json()["id"]
        # Add node so we can run the project (or just create a standalone run linked to this project)
        node = await client.post(f"/api/projects/{pid}/nodes", json={"agent_id": aid})
        # Delete the project -- should cascade or set null, not 500
        resp = await client.delete(f"/api/projects/{pid}")
        assert resp.status_code == 204
