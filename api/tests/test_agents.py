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

    @pytest.mark.asyncio
    async def test_create_agent_with_step_objects(self, client):
        """Steps sent as objects with per-step computer_use."""
        resp = await client.post("/api/agents", json={
            "name": "Multi Step",
            "description": "Do a multi-step task",
            "steps": [
                {"name": "Research sources", "computer_use": False},
                {"name": "Create PR in browser", "computer_use": True},
            ],
        })
        assert resp.status_code == 201
        data = resp.json()
        assert len(data["steps"]) == 2
        assert data["steps"][0] == {"name": "Research sources", "computer_use": False}
        assert data["steps"][1] == {"name": "Create PR in browser", "computer_use": True}

    @pytest.mark.asyncio
    async def test_create_agent_with_string_steps_normalized(self, client):
        """Plain string steps are normalized to objects with computer_use=False."""
        resp = await client.post("/api/agents", json={
            "name": "String Steps",
            "description": "Uses old format",
            "steps": ["Research sources", "Format report"],
        })
        assert resp.status_code == 201
        data = resp.json()
        assert data["steps"] == [
            {"name": "Research sources", "computer_use": False},
            {"name": "Format report", "computer_use": False},
        ]

    @pytest.mark.asyncio
    async def test_create_agent_with_mixed_steps(self, client):
        """Mix of string and object steps are all normalized."""
        resp = await client.post("/api/agents", json={
            "name": "Mixed Steps",
            "description": "Mixed format",
            "steps": [
                "CLI step",
                {"name": "Desktop step", "computer_use": True},
            ],
        })
        assert resp.status_code == 201
        data = resp.json()
        assert data["steps"][0] == {"name": "CLI step", "computer_use": False}
        assert data["steps"][1] == {"name": "Desktop step", "computer_use": True}

    @pytest.mark.asyncio
    async def test_create_agent_computer_use_derived_from_steps(self, client):
        """Agent-level computer_use is True when any step has computer_use=True."""
        resp = await client.post("/api/agents", json={
            "name": "Derived CU",
            "description": "Has desktop step",
            "steps": [
                {"name": "CLI step", "computer_use": False},
                {"name": "Desktop step", "computer_use": True},
            ],
        })
        assert resp.status_code == 201
        assert resp.json()["computer_use"] is True

    @pytest.mark.asyncio
    async def test_create_agent_without_steps_defaults_empty(self, client):
        resp = await client.post("/api/agents", json={
            "name": "No Steps",
            "description": "Simple task",
        })
        assert resp.status_code == 201
        assert resp.json()["steps"] == []


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
    async def test_update_agent_status(self, client):
        create = await client.post("/api/agents", json={"name": "S", "description": ""})
        agent_id = create.json()["id"]
        assert create.json()["status"] == "creating"
        resp = await client.put(f"/api/agents/{agent_id}", json={"status": "error"})
        assert resp.status_code == 200
        assert resp.json()["status"] == "error"

    @pytest.mark.asyncio
    async def test_update_nonexistent_returns_404(self, client):
        resp = await client.put("/api/agents/nonexistent", json={"name": "X"})
        assert resp.status_code == 404


class TestAgentUpdateTriggersForge:

    @pytest.mark.asyncio
    async def test_substantive_update_sets_status_updating(self, client, app):
        """Updating description on a ready agent sets status to 'updating'."""
        create = await client.post("/api/agents", json={"name": "T", "description": "old"})
        agent_id = create.json()["id"]
        await app.state.agent_repo.update(agent_id, status="ready")
        resp = await client.put(f"/api/agents/{agent_id}", json={"description": "new desc"})
        assert resp.status_code == 200
        assert resp.json()["status"] == "updating"

    @pytest.mark.asyncio
    async def test_cosmetic_update_keeps_status(self, client, app):
        """Updating only name on a ready agent keeps the current status."""
        create = await client.post("/api/agents", json={"name": "T", "description": "d"})
        agent_id = create.json()["id"]
        await app.state.agent_repo.update(agent_id, status="ready")
        resp = await client.put(f"/api/agents/{agent_id}", json={"name": "NewName"})
        assert resp.status_code == 200
        assert resp.json()["status"] == "ready"

    @pytest.mark.asyncio
    async def test_update_creating_agent_returns_409(self, client, app):
        """Cannot update substantive fields while agent is still creating."""
        # Create via repo to avoid background task changing status
        agent = await app.state.agent_repo.create(name="T", description="d", status="creating")
        agent_id = agent["id"]
        resp = await client.put(f"/api/agents/{agent_id}", json={"description": "new"})
        assert resp.status_code == 409
        assert resp.json()["error"]["code"] == "AGENT_BUSY"

    @pytest.mark.asyncio
    async def test_update_updating_agent_returns_409(self, client, app):
        """Cannot update substantive fields while agent is already updating."""
        agent = await app.state.agent_repo.create(name="T", description="d", status="updating")
        agent_id = agent["id"]
        resp = await client.put(f"/api/agents/{agent_id}", json={"description": "new"})
        assert resp.status_code == 409
        assert resp.json()["error"]["code"] == "AGENT_BUSY"

    @pytest.mark.asyncio
    async def test_cosmetic_update_allowed_during_creating(self, client, app):
        """Name-only update is allowed even when agent is creating."""
        create = await client.post("/api/agents", json={"name": "T", "description": "d"})
        agent_id = create.json()["id"]
        # Simulate a creating state (e.g., during forge regeneration)
        await app.state.agent_repo.update(agent_id, status="creating")
        resp = await client.put(f"/api/agents/{agent_id}", json={"name": "NewName"})
        assert resp.status_code == 200
        assert resp.json()["name"] == "NewName"

    @pytest.mark.asyncio
    async def test_samples_update_triggers_forge(self, client, app):
        """Updating samples on a ready agent sets status to 'updating'."""
        create = await client.post("/api/agents", json={"name": "T", "description": "d"})
        agent_id = create.json()["id"]
        await app.state.agent_repo.update(agent_id, status="ready")
        resp = await client.put(f"/api/agents/{agent_id}", json={"samples": ["example"]})
        assert resp.status_code == 200
        assert resp.json()["status"] == "updating"

    @pytest.mark.asyncio
    async def test_steps_update_triggers_forge(self, client, app):
        """Updating steps on a ready agent sets status to 'updating'."""
        create = await client.post("/api/agents", json={"name": "T", "description": "d"})
        agent_id = create.json()["id"]
        await app.state.agent_repo.update(agent_id, status="ready")
        resp = await client.put(f"/api/agents/{agent_id}", json={
            "steps": [
                {"name": "Step 1", "computer_use": False},
                {"name": "Step 2", "computer_use": True},
            ],
        })
        assert resp.status_code == 200
        assert resp.json()["status"] == "updating"
        assert resp.json()["steps"][1]["computer_use"] is True


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

    @pytest.mark.asyncio
    async def test_delete_agent_removes_output_folder(self, client, app, tmp_path):
        """Deleting an agent also removes its output folder."""
        create = await client.post("/api/agents", json={"name": "T", "description": "d"})
        agent_id = create.json()["id"]
        # Simulate forge having created an output folder
        output_dir = tmp_path / agent_id
        output_dir.mkdir()
        (output_dir / "agentic.md").write_text("test")
        await app.state.agent_repo.update(agent_id, forge_path=str(output_dir))

        resp = await client.delete(f"/api/agents/{agent_id}")
        assert resp.status_code == 204
        assert not output_dir.exists()

    @pytest.mark.asyncio
    async def test_delete_agent_no_forge_path_still_works(self, client):
        """Deleting an agent with empty forge_path still succeeds."""
        create = await client.post("/api/agents", json={"name": "T", "description": "d"})
        agent_id = create.json()["id"]
        resp = await client.delete(f"/api/agents/{agent_id}")
        assert resp.status_code == 204

    @pytest.mark.asyncio
    async def test_delete_all_agents(self, client):
        """Bulk delete removes all agents."""
        await client.post("/api/agents", json={"name": "A", "description": ""})
        await client.post("/api/agents", json={"name": "B", "description": ""})
        resp = await client.delete("/api/agents")
        assert resp.status_code == 200
        assert resp.json()["deleted"] == 2
        list_resp = await client.get("/api/agents")
        assert len(list_resp.json()) == 0

    @pytest.mark.asyncio
    async def test_delete_all_agents_empty(self, client):
        """Bulk delete on empty table returns zero."""
        resp = await client.delete("/api/agents")
        assert resp.status_code == 200
        assert resp.json()["deleted"] == 0


class TestAgentRun:

    @pytest.mark.asyncio
    async def test_run_agent_standalone(self, client, app):
        create = await client.post("/api/agents", json={
            "name": "T", "description": "do something",
        })
        agent_id = create.json()["id"]
        # Background forge sets status to ready, but ensure it explicitly
        await app.state.agent_repo.update(agent_id, status="ready")
        resp = await client.post(f"/api/agents/{agent_id}/run", json={
            "inputs": {"topic": "AI Safety"},
        })
        assert resp.status_code == 202
        data = resp.json()
        assert data["run_id"] is not None
        assert data["status"] == "queued"

    @pytest.mark.asyncio
    async def test_run_agent_not_ready_returns_409(self, client, app):
        create = await client.post("/api/agents", json={
            "name": "T", "description": "do something",
        })
        agent_id = create.json()["id"]
        # Set agent to "error" status so it's not ready
        await app.state.agent_repo.update(agent_id, status="error")
        resp = await client.post(f"/api/agents/{agent_id}/run", json={"inputs": {}})
        assert resp.status_code == 409
        assert resp.json()["error"]["code"] == "AGENT_NOT_READY"

    @pytest.mark.asyncio
    async def test_run_nonexistent_agent_returns_404(self, client):
        resp = await client.post("/api/agents/nonexistent/run", json={"inputs": {}})
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_list_agent_runs(self, client, app):
        create = await client.post("/api/agents", json={"name": "T", "description": ""})
        agent_id = create.json()["id"]
        await app.state.agent_repo.update(agent_id, status="ready")
        await client.post(f"/api/agents/{agent_id}/run", json={"inputs": {}})
        await client.post(f"/api/agents/{agent_id}/run", json={"inputs": {}})
        resp = await client.get(f"/api/agents/{agent_id}/runs")
        assert resp.status_code == 200
        assert len(resp.json()) == 2

    @pytest.mark.asyncio
    async def test_delete_all_runs(self, client, app):
        """Bulk delete removes all runs."""
        create = await client.post("/api/agents", json={"name": "T", "description": ""})
        agent_id = create.json()["id"]
        await app.state.agent_repo.update(agent_id, status="ready")
        await client.post(f"/api/agents/{agent_id}/run", json={"inputs": {}})
        await client.post(f"/api/agents/{agent_id}/run", json={"inputs": {}})
        resp = await client.delete("/api/runs")
        assert resp.status_code == 200
        assert resp.json()["deleted"] == 2
        list_resp = await client.get("/api/runs")
        assert len(list_resp.json()) == 0

    @pytest.mark.asyncio
    async def test_delete_all_runs_empty(self, client):
        """Bulk delete on empty runs table returns zero."""
        resp = await client.delete("/api/runs")
        assert resp.status_code == 200
        assert resp.json()["deleted"] == 0


class TestProviders:

    @pytest.mark.asyncio
    async def test_list_providers(self, client):
        resp = await client.get("/api/providers")
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)
        assert len(data) >= 1

    @pytest.mark.asyncio
    async def test_providers_have_required_fields(self, client):
        resp = await client.get("/api/providers")
        data = resp.json()
        for provider in data:
            assert "id" in provider
            assert "name" in provider
            assert "models" in provider
            assert isinstance(provider["models"], list)

    @pytest.mark.asyncio
    async def test_claude_code_provider_has_models(self, client):
        resp = await client.get("/api/providers")
        data = resp.json()
        claude = next((p for p in data if p["id"] == "claude_code"), None)
        assert claude is not None
        assert claude["name"] == "Claude Code"
        model_ids = [m["id"] for m in claude["models"]]
        assert "claude-sonnet-4-6" in model_ids
        assert "claude-opus-4-6" in model_ids

    @pytest.mark.asyncio
    async def test_each_model_has_id_and_name(self, client):
        resp = await client.get("/api/providers")
        data = resp.json()
        for provider in data:
            for model in provider["models"]:
                assert "id" in model
                assert "name" in model
                assert len(model["id"]) > 0
                assert len(model["name"]) > 0
