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
        assert resp.json()["provider"] == "claude_code"
        assert resp.json()["model"] == "claude-sonnet-4-6"

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


class TestStandaloneRunProviderSelection:

    @pytest.mark.asyncio
    async def test_run_agent_persists_runtime_provider_and_model_override(self, client, app):
        create = await client.post("/api/agents", json={
            "name": "T",
            "description": "do something",
            "provider": "claude_code",
            "model": "claude-sonnet-4-6",
        })
        agent_id = create.json()["id"]
        await app.state.agent_repo.update(agent_id, status="ready")

        resp = await client.post(f"/api/agents/{agent_id}/run", json={
            "inputs": {"topic": "AI"},
            "provider": "codex",
            "model": "gpt-5-codex",
        })
        assert resp.status_code == 202

        run = await app.state.run_repo.get(resp.json()["run_id"])
        assert run["provider"] == "codex"
        assert run["model"] == "gpt-5-codex"

    @pytest.mark.asyncio
    async def test_run_agent_falls_back_to_agent_provider_and_model(self, client, app):
        create = await client.post("/api/agents", json={
            "name": "T",
            "description": "do something",
            "provider": "gemini",
            "model": "gemini-2.5-pro",
        })
        agent_id = create.json()["id"]
        await app.state.agent_repo.update(agent_id, status="ready")

        resp = await client.post(f"/api/agents/{agent_id}/run", json={"inputs": {"topic": "AI"}})
        assert resp.status_code == 202

        run = await app.state.run_repo.get(resp.json()["run_id"])
        assert run["provider"] == "gemini"
        assert run["model"] == "gemini-2.5-pro"

    @pytest.mark.asyncio
    async def test_run_agent_rejects_partial_runtime_override(self, client, app):
        create = await client.post("/api/agents", json={"name": "T", "description": "do something"})
        agent_id = create.json()["id"]
        await app.state.agent_repo.update(agent_id, status="ready")

        resp = await client.post(f"/api/agents/{agent_id}/run", json={
            "inputs": {},
            "provider": "codex",
        })
        assert resp.status_code == 422


class TestRunOutputEndpoint:
    """Tests for GET /api/runs/{run_id}/outputs/{field_name}."""

    @pytest.mark.asyncio
    async def test_returns_raw_value_when_not_a_file(self, client, app):
        """When output value is plain text (not a file path), return it as-is."""
        agent = await client.post("/api/agents", json={"name": "T", "description": ""})
        agent_id = agent.json()["id"]
        await app.state.agent_repo.update(agent_id, status="ready")
        run_resp = await client.post(f"/api/agents/{agent_id}/run", json={"inputs": {}})
        run_id = run_resp.json()["run_id"]
        # Manually set outputs with a plain text value
        await app.state.run_repo.update_status(run_id, "completed", outputs={"summary": "This is the summary content."})

        resp = await client.get(f"/api/runs/{run_id}/outputs/summary")
        assert resp.status_code == 200
        assert resp.text == "This is the summary content."

    @pytest.mark.asyncio
    async def test_returns_file_content_when_path_exists(self, client, app, tmp_path):
        """When output value is a valid file path, read and return the file content."""
        # Create a temp file with real content
        content = "# Dependency Report\n\nPython 3.12, FastAPI 0.115"
        output_file = tmp_path / "report.md"
        output_file.write_text(content)

        agent = await client.post("/api/agents", json={"name": "T", "description": ""})
        agent_id = agent.json()["id"]
        await app.state.agent_repo.update(agent_id, status="ready")
        run_resp = await client.post(f"/api/agents/{agent_id}/run", json={"inputs": {}})
        run_id = run_resp.json()["run_id"]
        # Use the absolute path as the output value
        await app.state.run_repo.update_status(run_id, "completed", outputs={"report": str(output_file)})

        # Patch _PROJECT_ROOT so the path resolves
        import api.routes.runs as runs_mod
        original_root = runs_mod._PROJECT_ROOT
        runs_mod._PROJECT_ROOT = tmp_path
        try:
            resp = await client.get(f"/api/runs/{run_id}/outputs/report")
            assert resp.status_code == 200
            assert resp.text == content
        finally:
            runs_mod._PROJECT_ROOT = original_root

    @pytest.mark.asyncio
    async def test_returns_file_content_via_forge_path(self, client, app, tmp_path):
        """When output is a relative path, resolve via agent's forge_path."""
        content = "# Architecture Summary\n\nMonolith pattern"
        # Create forge_path/relative structure
        forge_dir = tmp_path / "output" / "agent-123"
        output_dir = forge_dir / "output" / "run-456" / "user_outputs" / "step_03"
        output_dir.mkdir(parents=True)
        output_file = output_dir / "arch.md"
        output_file.write_text(content)

        agent = await client.post("/api/agents", json={"name": "T", "description": ""})
        agent_id = agent.json()["id"]
        await app.state.agent_repo.update(
            agent_id, status="ready", forge_path="output/agent-123/"
        )
        run_resp = await client.post(f"/api/agents/{agent_id}/run", json={"inputs": {}})
        run_id = run_resp.json()["run_id"]
        # Relative path as stored by the executor
        await app.state.run_repo.update_status(
            run_id, "completed", outputs={"arch": "output/run-456/user_outputs/step_03/arch.md"}
        )

        import api.routes.runs as runs_mod
        original_root = runs_mod._PROJECT_ROOT
        runs_mod._PROJECT_ROOT = tmp_path
        try:
            resp = await client.get(f"/api/runs/{run_id}/outputs/arch")
            assert resp.status_code == 200
            assert resp.text == content
        finally:
            runs_mod._PROJECT_ROOT = original_root

    @pytest.mark.asyncio
    async def test_returns_404_for_missing_field(self, client, app):
        """Requesting a nonexistent output field returns 404."""
        agent = await client.post("/api/agents", json={"name": "T", "description": ""})
        agent_id = agent.json()["id"]
        await app.state.agent_repo.update(agent_id, status="ready")
        run_resp = await client.post(f"/api/agents/{agent_id}/run", json={"inputs": {}})
        run_id = run_resp.json()["run_id"]
        await app.state.run_repo.update_status(run_id, "completed", outputs={"existing": "value"})

        resp = await client.get(f"/api/runs/{run_id}/outputs/nonexistent")
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_returns_404_for_missing_run(self, client):
        """Requesting outputs for a nonexistent run returns 404."""
        resp = await client.get("/api/runs/nonexistent/outputs/field")
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_rejects_path_traversal(self, client, app, tmp_path):
        """Path traversal attempts must not escape project root."""
        # Create a file outside project root
        secret = tmp_path / "outside" / "secret.txt"
        secret.parent.mkdir(parents=True)
        secret.write_text("SECRET DATA")

        agent = await client.post("/api/agents", json={"name": "T", "description": ""})
        agent_id = agent.json()["id"]
        await app.state.agent_repo.update(agent_id, status="ready")
        run_resp = await client.post(f"/api/agents/{agent_id}/run", json={"inputs": {}})
        run_id = run_resp.json()["run_id"]
        await app.state.run_repo.update_status(
            run_id, "completed", outputs={"evil": "../../outside/secret.txt"}
        )

        import api.routes.runs as runs_mod
        original_root = runs_mod._PROJECT_ROOT
        # Set project root to a subdirectory so traversal goes "above" it
        runs_mod._PROJECT_ROOT = tmp_path / "project"
        (tmp_path / "project").mkdir(exist_ok=True)
        try:
            resp = await client.get(f"/api/runs/{run_id}/outputs/evil")
            # Should return the raw path string, NOT the file content
            assert "SECRET DATA" not in resp.text
        finally:
            runs_mod._PROJECT_ROOT = original_root


class TestRunLogPath:
    """Tests for log_path field on runs."""

    @pytest.mark.asyncio
    async def test_run_includes_log_path_field(self, client, app):
        agent = await client.post("/api/agents", json={"name": "T", "description": ""})
        agent_id = agent.json()["id"]
        await app.state.agent_repo.update(agent_id, status="ready")
        run = await client.post(f"/api/agents/{agent_id}/run", json={"inputs": {}})
        run_id = run.json()["run_id"]
        resp = await client.get(f"/api/runs/{run_id}")
        assert resp.status_code == 200
        assert "log_path" in resp.json()
        assert resp.json()["log_path"] is None

    @pytest.mark.asyncio
    async def test_set_log_path(self, app):
        run_repo = app.state.run_repo
        agent = await app.state.agent_repo.create(name="T", status="ready")
        run = await run_repo.create(agent_id=agent["id"])
        updated = await run_repo.set_log_path(run["id"], "output/run-1/agent_logs")
        assert updated["log_path"] == "output/run-1/agent_logs"
        fetched = await run_repo.get(run["id"])
        assert fetched["log_path"] == "output/run-1/agent_logs"


class TestRunLogsEndpoint:
    """Tests for GET /api/runs/{run_id}/logs and /logs/{step_file}."""

    @pytest.mark.asyncio
    async def test_get_logs_empty_when_no_log_path(self, client, app):
        agent = await client.post("/api/agents", json={"name": "T", "description": ""})
        agent_id = agent.json()["id"]
        await app.state.agent_repo.update(agent_id, status="ready")
        run = await client.post(f"/api/agents/{agent_id}/run", json={"inputs": {}})
        run_id = run.json()["run_id"]
        resp = await client.get(f"/api/runs/{run_id}/logs")
        assert resp.status_code == 200
        assert resp.json() == []

    @pytest.mark.asyncio
    async def test_get_logs_returns_execution_events(self, client, app, tmp_path):
        import json as json_mod
        agent = await client.post("/api/agents", json={"name": "T", "description": ""})
        agent_id = agent.json()["id"]
        await app.state.agent_repo.update(agent_id, status="ready")
        run = await client.post(f"/api/agents/{agent_id}/run", json={"inputs": {}})
        run_id = run.json()["run_id"]

        # Write JSONL log file
        log_dir = tmp_path / "agent_logs"
        log_dir.mkdir(parents=True)
        log_file = log_dir / "execution.jsonl"
        events = [
            {"type": "run_started", "data": {}, "timestamp": "2026-03-15T18:00:00Z"},
            {"type": "run_completed", "data": {}, "timestamp": "2026-03-15T18:05:00Z"},
        ]
        log_file.write_text("\n".join(json_mod.dumps(e) for e in events) + "\n")

        # Set log_path — use relative path that resolves under _PROJECT_ROOT
        rel_path = str(log_dir.relative_to(tmp_path))
        await app.state.run_repo.set_log_path(run_id, rel_path)

        import api.routes.runs as runs_mod
        original_root = runs_mod._PROJECT_ROOT
        runs_mod._PROJECT_ROOT = tmp_path
        try:
            resp = await client.get(f"/api/runs/{run_id}/logs")
            assert resp.status_code == 200
            data = resp.json()
            assert len(data) == 2
            assert data[0]["type"] == "run_started"
            assert data[1]["type"] == "run_completed"
        finally:
            runs_mod._PROJECT_ROOT = original_root

    @pytest.mark.asyncio
    async def test_get_logs_404_for_missing_run(self, client):
        resp = await client.get("/api/runs/nonexistent/logs")
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_get_step_log_returns_events(self, client, app, tmp_path):
        import json as json_mod
        agent = await client.post("/api/agents", json={"name": "T", "description": ""})
        agent_id = agent.json()["id"]
        await app.state.agent_repo.update(agent_id, status="ready")
        run = await client.post(f"/api/agents/{agent_id}/run", json={"inputs": {}})
        run_id = run.json()["run_id"]

        log_dir = tmp_path / "agent_logs"
        log_dir.mkdir(parents=True)
        step_file = log_dir / "step_01_analyze.jsonl"
        events = [
            {"type": "agent_started", "data": {"name": "Analyze"}, "timestamp": "2026-03-15T18:01:00Z"},
            {"type": "agent_log", "data": {"message": "Working"}, "timestamp": "2026-03-15T18:01:05Z"},
        ]
        step_file.write_text("\n".join(json_mod.dumps(e) for e in events) + "\n")
        rel_path = str(log_dir.relative_to(tmp_path))
        await app.state.run_repo.set_log_path(run_id, rel_path)

        import api.routes.runs as runs_mod
        original_root = runs_mod._PROJECT_ROOT
        runs_mod._PROJECT_ROOT = tmp_path
        try:
            resp = await client.get(f"/api/runs/{run_id}/logs/step_01_analyze.jsonl")
            assert resp.status_code == 200
            data = resp.json()
            assert len(data) == 2
            assert data[0]["data"]["name"] == "Analyze"
        finally:
            runs_mod._PROJECT_ROOT = original_root

    @pytest.mark.asyncio
    async def test_get_step_log_404_for_missing_file(self, client, app, tmp_path):
        agent = await client.post("/api/agents", json={"name": "T", "description": ""})
        agent_id = agent.json()["id"]
        await app.state.agent_repo.update(agent_id, status="ready")
        run = await client.post(f"/api/agents/{agent_id}/run", json={"inputs": {}})
        run_id = run.json()["run_id"]

        log_dir = tmp_path / "agent_logs"
        log_dir.mkdir(parents=True)
        rel_path = str(log_dir.relative_to(tmp_path))
        await app.state.run_repo.set_log_path(run_id, rel_path)

        import api.routes.runs as runs_mod
        original_root = runs_mod._PROJECT_ROOT
        runs_mod._PROJECT_ROOT = tmp_path
        try:
            resp = await client.get(f"/api/runs/{run_id}/logs/step_99_nope.jsonl")
            assert resp.status_code == 200
            assert resp.json() == []
        finally:
            runs_mod._PROJECT_ROOT = original_root
