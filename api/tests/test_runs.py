"""Tests for run lifecycle routes."""

import pytest


async def _start(client, task="Tidy the inbox", **extra):
    body = {"task": task, **extra}
    return await client.post("/api/runs", json=body)


class TestRunTrigger:

    @pytest.mark.asyncio
    async def test_returns_202_and_the_run_row(self, client):
        resp = await _start(client)
        assert resp.status_code == 202
        row = resp.json()
        assert row["id"]
        assert row["status"] == "queued"
        assert row["agent_name"] == "Tidy the inbox"
        assert row["inputs"] == {"task": "Tidy the inbox"}

    @pytest.mark.asyncio
    async def test_registers_the_task_so_cancel_can_reach_it(self, client, app):
        resp = await _start(client)
        assert resp.json()["id"] in app.state.active_run_tasks

    @pytest.mark.asyncio
    async def test_missing_task_is_422(self, client):
        resp = await client.post("/api/runs", json={})
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_empty_task_is_422(self, client):
        resp = await client.post("/api/runs", json={"task": "   "})
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_an_undeclared_field_is_422(self, client):
        """The old body's `inputs` key must fail loudly, not be dropped."""
        resp = await client.post("/api/runs", json={"task": "T", "inputs": {"topic": "AI"}})
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_provider_without_model_is_422(self, client):
        resp = await _start(client, provider="codex")
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_model_without_provider_is_422(self, client):
        resp = await _start(client, model="gpt-5.4")
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_a_named_pair_is_persisted(self, client, app):
        resp = await _start(client, provider="codex", model="gpt-5.4")
        assert resp.status_code == 202
        run = await app.state.run_repo.get(resp.json()["id"])
        assert run["provider"] == "codex"
        assert run["model"] == "gpt-5.4"

    @pytest.mark.asyncio
    async def test_a_run_that_named_nothing_stores_nothing(self, client, app):
        """Resolution happens when the run starts, not when the row is written."""
        resp = await _start(client)
        run = await app.state.run_repo.get(resp.json()["id"])
        assert run["provider"] is None
        assert run["model"] is None


class TestRunGet:

    @pytest.mark.asyncio
    async def test_get_run(self, client):
        run_id = (await _start(client)).json()["id"]
        resp = await client.get(f"/api/runs/{run_id}")
        assert resp.status_code == 200
        assert resp.json()["id"] == run_id

    @pytest.mark.asyncio
    async def test_get_nonexistent_run_returns_404(self, client):
        resp = await client.get("/api/runs/nonexistent")
        assert resp.status_code == 404
        assert resp.json()["error"]["code"] == "RUN_NOT_FOUND"

    @pytest.mark.asyncio
    async def test_the_row_keeps_the_shape_the_phone_reads(self, client):
        """The transitional watch surface's keys are frozen."""
        run_id = (await _start(client)).json()["id"]
        row = (await client.get(f"/api/runs/{run_id}")).json()
        assert set(row) == {
            "id", "agent_name", "status", "inputs", "outputs",
            "provider", "model", "log_path", "started_at", "completed_at",
        }


class TestRunList:

    @pytest.mark.asyncio
    async def test_list_runs(self, client):
        await _start(client)
        resp = await client.get("/api/runs")
        assert resp.status_code == 200
        assert len(resp.json()) >= 1

    @pytest.mark.asyncio
    async def test_list_runs_filter_by_status(self, client):
        await _start(client)
        resp = await client.get("/api/runs", params={"status": "queued"})
        assert resp.status_code == 200
        assert all(r["status"] == "queued" for r in resp.json())


class TestRunLogPath:
    """`log_path` is dead weight on a frozen row, and it stays until the row
    is regenerated. Nothing writes it any more."""

    @pytest.mark.asyncio
    async def test_run_includes_log_path_field(self, client):
        run_id = (await _start(client)).json()["id"]
        row = (await client.get(f"/api/runs/{run_id}")).json()
        assert "log_path" in row
        assert row["log_path"] is None


class TestRunCancel:

    @pytest.mark.asyncio
    async def test_cancel_marks_the_run_failed(self, client):
        run_id = (await _start(client)).json()["id"]
        resp = await client.post(f"/api/runs/{run_id}/cancel")
        assert resp.status_code == 200
        assert resp.json()["status"] == "failed"

    @pytest.mark.asyncio
    async def test_cancel_finished_run_returns_409(self, client, app):
        run_id = (await _start(client)).json()["id"]
        await app.state.run_repo.update_status(run_id, "completed")
        resp = await client.post(f"/api/runs/{run_id}/cancel")
        assert resp.status_code == 409
        assert resp.json()["error"]["code"] == "RUN_NOT_ACTIVE"

    @pytest.mark.asyncio
    async def test_cancel_nonexistent_run_returns_404(self, client):
        resp = await client.post("/api/runs/nonexistent/cancel")
        assert resp.status_code == 404


class TestRunResume:

    @pytest.mark.asyncio
    async def test_resume_failed_run_returns_200(self, client, app):
        run_id = (await _start(client)).json()["id"]
        await app.state.run_repo.update_status(run_id, "failed")
        resp = await client.post(f"/api/runs/{run_id}/resume")
        assert resp.status_code == 200
        data = resp.json()
        assert data["run_id"] == run_id
        assert data["status"] == "running"

    @pytest.mark.asyncio
    async def test_resume_running_run_is_idempotent(self, client, app):
        run_id = (await _start(client)).json()["id"]
        await app.state.run_repo.update_status(run_id, "running")
        resp = await client.post(f"/api/runs/{run_id}/resume")
        assert resp.status_code == 200
        assert resp.json()["message"] == "Already running"

    @pytest.mark.asyncio
    async def test_resume_completed_run_returns_409(self, client, app):
        run_id = (await _start(client)).json()["id"]
        await app.state.run_repo.update_status(run_id, "completed")
        resp = await client.post(f"/api/runs/{run_id}/resume")
        assert resp.status_code == 409

    @pytest.mark.asyncio
    async def test_resume_nonexistent_run_returns_404(self, client):
        resp = await client.post("/api/runs/nonexistent-id/resume")
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_resume_queued_run_returns_409(self, client):
        run_id = (await _start(client)).json()["id"]
        resp = await client.post(f"/api/runs/{run_id}/resume")
        assert resp.status_code == 409
        data = resp.json()
        assert data["error"]["code"] == "RUN_NOT_RESUMABLE"
        assert "queued" in data["error"]["message"]

    @pytest.mark.asyncio
    async def test_resume_awaiting_approval_run_returns_409(self, client, app):
        run_id = (await _start(client)).json()["id"]
        await app.state.run_repo.update_status(run_id, "awaiting_approval")
        resp = await client.post(f"/api/runs/{run_id}/resume")
        assert resp.status_code == 409
        assert "awaiting_approval" in resp.json()["error"]["message"]

    @pytest.mark.asyncio
    async def test_resume_cancelled_run_returns_409(self, client, app):
        run_id = (await _start(client)).json()["id"]
        await app.state.run_repo.update_status(run_id, "cancelled")
        resp = await client.post(f"/api/runs/{run_id}/resume")
        assert resp.status_code == 409
        assert "cancelled" in resp.json()["error"]["message"]

    @pytest.mark.asyncio
    async def test_resume_duplicate_active_task_returns_already_resuming(self, client, app):
        """If an active asyncio task is already resuming the run, return 200 with 'Already resuming'."""
        import asyncio

        run_id = (await _start(client)).json()["id"]
        await app.state.run_repo.update_status(run_id, "failed")

        # Plant a fake active task that is not done
        never_done = asyncio.get_event_loop().create_future()
        app.state.active_run_tasks[run_id] = never_done

        try:
            resp = await client.post(f"/api/runs/{run_id}/resume")
            assert resp.status_code == 200
            assert resp.json()["message"] == "Already resuming"
        finally:
            never_done.cancel()
            app.state.active_run_tasks.pop(run_id, None)
