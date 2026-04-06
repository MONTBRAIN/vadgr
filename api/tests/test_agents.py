"""Tests for agent CRUD routes."""

import json
import pytest
import zipfile


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


class TestStepsFromDisk:
    """Unit tests for _steps_from_disk helper."""

    def test_parses_step_filenames_to_steps_array(self, tmp_path):
        import io
        from api.routes.agents import _steps_from_disk
        steps_dir = tmp_path / "output" / "my-agent" / "agent" / "steps"
        steps_dir.mkdir(parents=True)
        (steps_dir / "step_01_extract-meeting-insights.md").write_text("# Step 1")
        (steps_dir / "step_02_draft-decision-brief.md").write_text("# Step 2")

        result = _steps_from_disk("output/my-agent", tmp_path)
        assert result == [
            {"name": "Extract Meeting Insights", "computer_use": False},
            {"name": "Draft Decision Brief", "computer_use": False},
        ]

    def test_returns_empty_when_no_steps_dir(self, tmp_path):
        from api.routes.agents import _steps_from_disk
        result = _steps_from_disk("output/my-agent", tmp_path)
        assert result == []

    def test_returns_empty_when_forge_path_empty(self, tmp_path):
        from api.routes.agents import _steps_from_disk
        result = _steps_from_disk("", tmp_path)
        assert result == []

    def test_ignores_non_step_files(self, tmp_path):
        from api.routes.agents import _steps_from_disk
        steps_dir = tmp_path / "output" / "agent" / "agent" / "steps"
        steps_dir.mkdir(parents=True)
        (steps_dir / "step_01_research.md").write_text("# Step 1")
        (steps_dir / "README.md").write_text("# Readme")
        (steps_dir / "step_02_write.md").write_text("# Step 2")

        result = _steps_from_disk("output/agent", tmp_path)
        assert len(result) == 2
        assert result[0]["name"] == "Research"
        assert result[1]["name"] == "Write"

    def test_returns_sorted_by_step_number(self, tmp_path):
        from api.routes.agents import _steps_from_disk
        steps_dir = tmp_path / "output" / "agent" / "agent" / "steps"
        steps_dir.mkdir(parents=True)
        (steps_dir / "step_03_review.md").write_text("")
        (steps_dir / "step_01_research.md").write_text("")
        (steps_dir / "step_02_write.md").write_text("")

        result = _steps_from_disk("output/agent", tmp_path)
        assert [s["name"] for s in result] == ["Research", "Write", "Review"]


class TestExportManifestStepsFallback:
    """Export manifest reads steps from disk when DB steps is empty."""

    @pytest.mark.asyncio
    async def test_export_manifest_reads_steps_from_disk_when_db_empty(self, client, app, tmp_path):
        import io
        import subprocess
        import api.routes.agents as agents_mod

        forge_root = tmp_path / "output" / "agent-123"
        steps_dir = forge_root / "agent" / "steps"
        steps_dir.mkdir(parents=True)
        (steps_dir / "step_01_extract-insights.md").write_text("# Step 1")
        (steps_dir / "step_02_write-brief.md").write_text("# Step 2")
        (forge_root / "agentic.md").write_text("# Agent")
        (forge_root / ".gitignore").write_text("output/\n")

        subprocess.run(["git", "-C", str(forge_root), "init"], check=True, capture_output=True)
        subprocess.run(["git", "-C", str(forge_root), "config", "user.name", "Agent Forge"], check=True, capture_output=True)
        subprocess.run(["git", "-C", str(forge_root), "config", "user.email", "agent-forge@local"], check=True, capture_output=True)
        subprocess.run(["git", "-C", str(forge_root), "add", "."], check=True, capture_output=True)
        subprocess.run(["git", "-C", str(forge_root), "commit", "-m", "init"], check=True, capture_output=True)

        create = await client.post("/api/agents", json={"name": "T", "description": ""})
        agent_id = create.json()["id"]
        # DB steps intentionally empty — simulates agent created without declaring steps
        await app.state.agent_repo.update(agent_id, status="ready", forge_path="output/agent-123/")

        original_root = agents_mod.PROJECT_ROOT
        agents_mod.PROJECT_ROOT = tmp_path
        try:
            resp = await client.get(f"/api/agents/{agent_id}/export")
            assert resp.status_code == 200
            with zipfile.ZipFile(io.BytesIO(resp.content)) as zf:
                manifest = json.loads(zf.read("agent-forge.json"))
            assert manifest["steps"] == [
                {"name": "Extract Insights", "computer_use": False},
                {"name": "Write Brief", "computer_use": False},
            ]
        finally:
            agents_mod.PROJECT_ROOT = original_root

    @pytest.mark.asyncio
    async def test_export_manifest_uses_db_steps_when_present(self, client, app, tmp_path):
        """When DB has steps (including computer_use: True), export uses DB, not disk."""
        import io
        import subprocess
        import api.routes.agents as agents_mod

        forge_root = tmp_path / "output" / "agent-123"
        steps_dir = forge_root / "agent" / "steps"
        steps_dir.mkdir(parents=True)
        # Disk has different name than DB — DB should win
        (steps_dir / "step_01_disk-name.md").write_text("# Step 1")
        (forge_root / "agentic.md").write_text("# Agent")
        (forge_root / ".gitignore").write_text("output/\n")

        subprocess.run(["git", "-C", str(forge_root), "init"], check=True, capture_output=True)
        subprocess.run(["git", "-C", str(forge_root), "config", "user.name", "Agent Forge"], check=True, capture_output=True)
        subprocess.run(["git", "-C", str(forge_root), "config", "user.email", "agent-forge@local"], check=True, capture_output=True)
        subprocess.run(["git", "-C", str(forge_root), "add", "."], check=True, capture_output=True)
        subprocess.run(["git", "-C", str(forge_root), "commit", "-m", "init"], check=True, capture_output=True)

        create = await client.post("/api/agents", json={"name": "T", "description": ""})
        agent_id = create.json()["id"]
        db_steps = [
            {"name": "DB Step One", "computer_use": False},
            {"name": "DB Step Two", "computer_use": True},
        ]
        await app.state.agent_repo.update(
            agent_id, status="ready", forge_path="output/agent-123/", steps=db_steps
        )

        original_root = agents_mod.PROJECT_ROOT
        agents_mod.PROJECT_ROOT = tmp_path
        try:
            resp = await client.get(f"/api/agents/{agent_id}/export")
            assert resp.status_code == 200
            with zipfile.ZipFile(io.BytesIO(resp.content)) as zf:
                manifest = json.loads(zf.read("agent-forge.json"))
            assert manifest["steps"] == db_steps
        finally:
            agents_mod.PROJECT_ROOT = original_root


class TestAgentArtifactsAndExport:

    @pytest.mark.asyncio
    async def test_upload_artifact_returns_descriptor(self, client, app, tmp_path):
        import api.routes.agents as agents_mod

        create = await client.post("/api/agents", json={"name": "T", "description": ""})
        agent_id = create.json()["id"]
        await app.state.agent_repo.update(
            agent_id,
            status="ready",
            forge_path="output/agent-123/",
            input_schema=[
                {
                    "name": "project_brief",
                    "type": "file",
                    "required": True,
                    "accept": [".txt"],
                    "mime_types": ["text/plain"],
                    "max_size_mb": 1,
                }
            ],
        )

        original_root = agents_mod.PROJECT_ROOT
        original_artifact_root = app.state.artifact_service.project_root
        agents_mod.PROJECT_ROOT = tmp_path
        app.state.artifact_service.project_root = tmp_path
        try:
            resp = await client.post(
                f"/api/agents/{agent_id}/uploads",
                data={"field_name": "project_brief"},
                files={"file": ("notes.txt", b"hello world", "text/plain")},
            )
            assert resp.status_code == 201
            data = resp.json()
            assert data["kind"] == "file"
            assert data["filename"] == "notes.txt"
            assert data["mime_type"] == "text/plain"
            assert data["path"].startswith("uploads/")
            assert data["path"].endswith("/notes.txt")
        finally:
            agents_mod.PROJECT_ROOT = original_root
            app.state.artifact_service.project_root = original_artifact_root

    @pytest.mark.asyncio
    async def test_run_materializes_uploaded_artifacts_into_inputs_dir(self, client, app, tmp_path):
        import api.routes.agents as agents_mod

        create = await client.post("/api/agents", json={"name": "T", "description": ""})
        agent_id = create.json()["id"]
        await app.state.agent_repo.update(
            agent_id,
            status="ready",
            forge_path="output/agent-123/",
            input_schema=[
                {
                    "name": "project_brief",
                    "type": "file",
                    "required": True,
                    "accept": [".txt"],
                    "mime_types": ["text/plain"],
                    "max_size_mb": 1,
                }
            ],
        )

        original_root = agents_mod.PROJECT_ROOT
        original_artifact_root = app.state.artifact_service.project_root
        agents_mod.PROJECT_ROOT = tmp_path
        app.state.artifact_service.project_root = tmp_path
        try:
            upload = await client.post(
                f"/api/agents/{agent_id}/uploads",
                data={"field_name": "project_brief"},
                files={"file": ("notes.txt", b"hello world", "text/plain")},
            )
            assert upload.status_code == 201
            descriptor = upload.json()

            run = await client.post(
                f"/api/agents/{agent_id}/run",
                json={"inputs": {"project_brief": descriptor}},
            )
            assert run.status_code == 202
            run_id = run.json()["run_id"]

            materialized = (
                tmp_path
                / "output"
                / "agent-123"
                / "output"
                / run_id
                / "inputs"
                / "project_brief"
                / "notes.txt"
            )
            assert materialized.exists()
            assert materialized.read_text() == "hello world"
        finally:
            agents_mod.PROJECT_ROOT = original_root
            app.state.artifact_service.project_root = original_artifact_root

    @pytest.mark.asyncio
    async def test_upload_artifact_rejects_wrong_extension(self, client, app, tmp_path):
        import api.routes.agents as agents_mod

        create = await client.post("/api/agents", json={"name": "T", "description": ""})
        agent_id = create.json()["id"]
        await app.state.agent_repo.update(
            agent_id,
            status="ready",
            forge_path="output/agent-123/",
            input_schema=[
                {
                    "name": "project_brief",
                    "type": "file",
                    "required": True,
                    "accept": [".docx"],
                    "mime_types": ["application/vnd.openxmlformats-officedocument.wordprocessingml.document"],
                }
            ],
        )

        original_root = agents_mod.PROJECT_ROOT
        original_artifact_root = app.state.artifact_service.project_root
        agents_mod.PROJECT_ROOT = tmp_path
        app.state.artifact_service.project_root = tmp_path
        try:
            resp = await client.post(
                f"/api/agents/{agent_id}/uploads",
                data={"field_name": "project_brief"},
                files={"file": ("notes.txt", b"hello world", "text/plain")},
            )
            assert resp.status_code == 400
            assert resp.json()["error"]["code"] == "INVALID_ARTIFACT_UPLOAD"
        finally:
            agents_mod.PROJECT_ROOT = original_root
            app.state.artifact_service.project_root = original_artifact_root

    @pytest.mark.asyncio
    async def test_upload_artifact_accepts_markdown_variant_mime(self, client, app, tmp_path):
        import api.routes.agents as agents_mod

        create = await client.post("/api/agents", json={"name": "T", "description": ""})
        agent_id = create.json()["id"]
        await app.state.agent_repo.update(
            agent_id,
            status="ready",
            forge_path="output/agent-123/",
            input_schema=[
                {
                    "name": "meeting_notes",
                    "type": "file",
                    "required": True,
                    "accept": [".md"],
                    "mime_types": ["text/plain", "text/markdown"],
                }
            ],
        )

        original_root = agents_mod.PROJECT_ROOT
        original_artifact_root = app.state.artifact_service.project_root
        agents_mod.PROJECT_ROOT = tmp_path
        app.state.artifact_service.project_root = tmp_path
        try:
            resp = await client.post(
                f"/api/agents/{agent_id}/uploads",
                data={"field_name": "meeting_notes"},
                files={"file": ("notes.md", b"# hello", "text/x-markdown")},
            )
            assert resp.status_code == 201
            assert resp.json()["filename"] == "notes.md"
        finally:
            agents_mod.PROJECT_ROOT = original_root
            app.state.artifact_service.project_root = original_artifact_root

    @pytest.mark.asyncio
    async def test_upload_artifact_accepts_octet_stream_for_allowed_markdown_extension(self, client, app, tmp_path):
        import api.routes.agents as agents_mod

        create = await client.post("/api/agents", json={"name": "T", "description": ""})
        agent_id = create.json()["id"]
        await app.state.agent_repo.update(
            agent_id,
            status="ready",
            forge_path="output/agent-123/",
            input_schema=[
                {
                    "name": "meeting_notes",
                    "type": "file",
                    "required": True,
                    "accept": [".md"],
                    "mime_types": ["text/plain", "text/markdown"],
                }
            ],
        )

        original_root = agents_mod.PROJECT_ROOT
        original_artifact_root = app.state.artifact_service.project_root
        agents_mod.PROJECT_ROOT = tmp_path
        app.state.artifact_service.project_root = tmp_path
        try:
            resp = await client.post(
                f"/api/agents/{agent_id}/uploads",
                data={"field_name": "meeting_notes"},
                files={"file": ("notes.md", b"# hello", "application/octet-stream")},
            )
            assert resp.status_code == 201
            assert resp.json()["filename"] == "notes.md"
        finally:
            agents_mod.PROJECT_ROOT = original_root
            app.state.artifact_service.project_root = original_artifact_root

    @pytest.mark.asyncio
    async def test_upload_artifact_rejects_unknown_field(self, client, app, tmp_path):
        import api.routes.agents as agents_mod

        create = await client.post("/api/agents", json={"name": "T", "description": ""})
        agent_id = create.json()["id"]
        await app.state.agent_repo.update(
            agent_id,
            status="ready",
            forge_path="output/agent-123/",
            input_schema=[{"name": "project_brief", "type": "file", "required": True}],
        )

        original_root = agents_mod.PROJECT_ROOT
        original_artifact_root = app.state.artifact_service.project_root
        agents_mod.PROJECT_ROOT = tmp_path
        app.state.artifact_service.project_root = tmp_path
        try:
            resp = await client.post(
                f"/api/agents/{agent_id}/uploads",
                data={"field_name": "dataset_csv"},
                files={"file": ("notes.txt", b"hello world", "text/plain")},
            )
            assert resp.status_code == 400
            assert resp.json()["error"]["code"] == "INVALID_INPUT_FIELD"
        finally:
            agents_mod.PROJECT_ROOT = original_root
            app.state.artifact_service.project_root = original_artifact_root

    @pytest.mark.asyncio
    async def test_export_agent_returns_zip_without_runtime_output(self, client, app, tmp_path):
        import api.routes.agents as agents_mod

        forge_root = tmp_path / "output" / "agent-123"
        (forge_root / "agent" / "Prompts").mkdir(parents=True)
        (forge_root / "output" / "run-1" / "user_outputs" / "step_01").mkdir(parents=True)
        (forge_root / "agentic.md").write_text("# Agent")
        (forge_root / "README.md").write_text("# Readme")
        (forge_root / ".gitignore").write_text("output/\n")
        (forge_root / "output" / "run-1" / "user_outputs" / "step_01" / "memo.md").write_text("runtime")

        import subprocess
        subprocess.run(["git", "-C", str(forge_root), "init"], check=True, capture_output=True)
        subprocess.run(["git", "-C", str(forge_root), "config", "user.name", "Agent Forge"], check=True, capture_output=True)
        subprocess.run(["git", "-C", str(forge_root), "config", "user.email", "agent-forge@local"], check=True, capture_output=True)
        subprocess.run(["git", "-C", str(forge_root), "add", "."], check=True, capture_output=True)
        subprocess.run(["git", "-C", str(forge_root), "commit", "-m", "Initial agent scaffold"], check=True, capture_output=True)

        create = await client.post("/api/agents", json={"name": "T", "description": ""})
        agent_id = create.json()["id"]
        await app.state.agent_repo.update(agent_id, status="ready", forge_path="output/agent-123/")

        original_root = agents_mod.PROJECT_ROOT
        agents_mod.PROJECT_ROOT = tmp_path
        try:
            resp = await client.get(f"/api/agents/{agent_id}/export")
            assert resp.status_code == 200
            assert resp.headers["content-type"] in {"application/zip", "application/octet-stream"}

            archive_path = tmp_path / "export.zip"
            archive_path.write_bytes(resp.content)
            with zipfile.ZipFile(archive_path) as zf:
                names = set(zf.namelist())
                manifest = zf.read("agent-forge.json")
                bundle_bytes = zf.read("agent.bundle")
            assert "agent.bundle" in names
            assert "agent-forge.json" in names
            assert b'"export_version": 2' in manifest
            assert bundle_bytes
        finally:
            agents_mod.PROJECT_ROOT = original_root

    @pytest.mark.asyncio
    async def test_import_agent_from_export_zip(self, client, app, tmp_path):
        import api.routes.agents as agents_mod
        import api.services.agent_service as agent_service_mod

        forge_root = tmp_path / "output" / "agent-123"
        (forge_root / "agent" / "steps").mkdir(parents=True)
        (forge_root / "agent" / "steps" / "step_01.md").write_text("# Step 1")
        (forge_root / "output").mkdir(parents=True)
        (forge_root / "output" / ".gitkeep").write_text("")
        (forge_root / "agentic.md").write_text("# Agent")
        (forge_root / "README.md").write_text("# Readme")
        (forge_root / ".gitignore").write_text("output/*\n!output/.gitkeep\n")

        import subprocess
        subprocess.run(["git", "-C", str(forge_root), "init"], check=True, capture_output=True)
        subprocess.run(["git", "-C", str(forge_root), "config", "user.name", "Agent Forge"], check=True, capture_output=True)
        subprocess.run(["git", "-C", str(forge_root), "config", "user.email", "agent-forge@local"], check=True, capture_output=True)
        subprocess.run(["git", "-C", str(forge_root), "add", "."], check=True, capture_output=True)
        subprocess.run(["git", "-C", str(forge_root), "commit", "-m", "Initial agent scaffold"], check=True, capture_output=True)
        (forge_root / "README.md").write_text("# Updated Readme")
        subprocess.run(["git", "-C", str(forge_root), "add", "."], check=True, capture_output=True)
        subprocess.run(["git", "-C", str(forge_root), "commit", "-m", "Update readme"], check=True, capture_output=True)

        create = await client.post("/api/agents", json={"name": "Source Agent", "description": "desc"})
        agent_id = create.json()["id"]
        await app.state.agent_repo.update(
            agent_id,
            status="ready",
            forge_path="output/agent-123/",
            steps=[{"name": "Step 1", "computer_use": False}],
            input_schema=[{"name": "project_brief", "type": "file", "required": True}],
            output_schema=[{"name": "summary_pdf", "type": "file", "required": True}],
            provider="codex",
            model="gpt-5-codex",
        )

        original_root = agents_mod.PROJECT_ROOT
        original_service_root = agent_service_mod.PROJECT_ROOT
        original_ensure_script_environment = app.state.agent_service.ensure_agent_script_environment
        script_env_calls: list[str] = []

        def fake_ensure_script_environment(forge_path: str) -> None:
            script_env_calls.append(forge_path)
            scripts_dir = tmp_path / forge_path / "agent" / "scripts" / ".venv"
            scripts_dir.mkdir(parents=True, exist_ok=True)

        agents_mod.PROJECT_ROOT = tmp_path
        agent_service_mod.PROJECT_ROOT = tmp_path
        app.state.agent_service.ensure_agent_script_environment = fake_ensure_script_environment
        try:
            export_resp = await client.get(f"/api/agents/{agent_id}/export")
            assert export_resp.status_code == 200

            import_resp = await client.post(
                "/api/agents/import",
                files={"file": ("agent.zip", export_resp.content, "application/zip")},
            )
            assert import_resp.status_code == 201
            importing = import_resp.json()
            # Route returns immediately with "importing" status
            assert importing["status"] == "importing"
            assert importing["name"] == "Source Agent"
            assert importing["forge_path"]  # pre-set before background task runs

            # Background task has completed by now (ASGI test transport); verify final state
            final_resp = await client.get(f"/api/agents/{importing['id']}")
            assert final_resp.status_code == 200
            imported = final_resp.json()
            assert imported["status"] == "ready"
            assert imported["provider"] == "codex"
            assert imported["model"] == "gpt-5-codex"
            assert imported["input_schema"][0]["name"] == "project_brief"
            assert imported["output_schema"][0]["name"] == "summary_pdf"

            imported_root = tmp_path / imported["forge_path"]
            assert (imported_root / "agentic.md").exists()
            assert (imported_root / "agent" / "steps" / "step_01.md").exists()
            assert (imported_root / ".git").exists()
            assert (imported_root / "output" / ".gitkeep").exists()
            assert (imported_root / "agent" / "scripts" / ".venv").is_dir()
            assert script_env_calls == [imported["forge_path"]]
            original_log = subprocess.run(
                ["git", "-C", str(forge_root), "log", "--oneline", "-n", "5"],
                check=True,
                capture_output=True,
                text=True,
            ).stdout.strip()
            imported_log = subprocess.run(
                ["git", "-C", str(imported_root), "log", "--oneline", "-n", "5"],
                check=True,
                capture_output=True,
                text=True,
            ).stdout.strip()
            # Imported repo has original commits plus a schema sync commit
            original_messages = [line.split(" ", 1)[1] for line in original_log.splitlines()]
            imported_messages = [line.split(" ", 1)[1] for line in imported_log.splitlines()]
            assert imported_messages[0] == "Sync schemas after import"
            assert imported_messages[1:] == original_messages
            # schema.json should exist in imported repo
            assert (imported_root / "schema.json").exists()
        finally:
            agents_mod.PROJECT_ROOT = original_root
            agent_service_mod.PROJECT_ROOT = original_service_root
            app.state.agent_service.ensure_agent_script_environment = original_ensure_script_environment


class TestAgentList:

    @pytest.mark.asyncio
    async def test_list_agents(self, client):
        await client.post("/api/agents", json={"name": "A", "description": ""})
        await client.post("/api/agents", json={"name": "B", "description": ""})
        resp = await client.get("/api/agents")
        assert resp.status_code == 200
        assert len(resp.json()) == 2


class TestSchemaField:
    """Tests for rich SchemaField with optional label/description/placeholder/options."""

    @pytest.mark.asyncio
    async def test_update_agent_with_rich_input_schema(self, client, app):
        """input_schema with label, description, placeholder, options is stored and returned."""
        create = await client.post("/api/agents", json={"name": "Schema Test", "description": ""})
        agent_id = create.json()["id"]
        await app.state.agent_repo.update(agent_id, status="ready")

        schema = [
            {
                "name": "topic",
                "type": "text",
                "required": True,
                "label": "Research Topic",
                "description": "The subject to research",
                "placeholder": "e.g. AI market trends",
            },
            {
                "name": "depth",
                "type": "select",
                "required": False,
                "label": "Depth",
                "options": ["quick", "standard", "deep"],
            },
        ]
        resp = await client.put(f"/api/agents/{agent_id}", json={"input_schema": schema})
        assert resp.status_code == 200
        result = resp.json()
        assert result["status"] == "updating"
        assert len(result["input_schema"]) == 2

        topic_field = result["input_schema"][0]
        assert topic_field["name"] == "topic"
        assert topic_field["label"] == "Research Topic"
        assert topic_field["description"] == "The subject to research"
        assert topic_field["placeholder"] == "e.g. AI market trends"

        depth_field = result["input_schema"][1]
        assert depth_field["name"] == "depth"
        assert depth_field["type"] == "select"
        assert depth_field["options"] == ["quick", "standard", "deep"]

    @pytest.mark.asyncio
    async def test_update_agent_with_rich_output_schema(self, client, app):
        """output_schema with label and description is stored and returned."""
        create = await client.post("/api/agents", json={"name": "Output Schema Test", "description": ""})
        agent_id = create.json()["id"]
        await app.state.agent_repo.update(agent_id, status="ready")

        schema = [
            {
                "name": "report",
                "type": "markdown",
                "required": False,
                "label": "Research Report",
                "description": "Full analysis with findings and recommendations",
            },
        ]
        resp = await client.put(f"/api/agents/{agent_id}", json={"output_schema": schema})
        assert resp.status_code == 200
        result = resp.json()
        assert result["status"] == "updating"
        assert result["output_schema"][0]["label"] == "Research Report"
        assert result["output_schema"][0]["description"] == "Full analysis with findings and recommendations"

    @pytest.mark.asyncio
    async def test_schema_field_optional_fields_default_none(self, client, app):
        """SchemaField without optional fields stores null and returns null."""
        create = await client.post("/api/agents", json={"name": "Minimal Schema", "description": ""})
        agent_id = create.json()["id"]
        await app.state.agent_repo.update(agent_id, status="ready")

        schema = [{"name": "task", "type": "text", "required": True}]
        resp = await client.put(f"/api/agents/{agent_id}", json={"input_schema": schema})
        assert resp.status_code == 200
        assert resp.json()["status"] == "updating"
        field = resp.json()["input_schema"][0]
        assert field["label"] is None
        assert field["description"] is None
        assert field["placeholder"] is None
        assert field["options"] is None

    @pytest.mark.asyncio
    async def test_schema_field_with_url_type(self, client, app):
        """URL type is accepted and stored."""
        create = await client.post("/api/agents", json={"name": "URL Schema", "description": ""})
        agent_id = create.json()["id"]
        await app.state.agent_repo.update(agent_id, status="ready")

        schema = [{"name": "source_url", "type": "url", "required": False, "label": "Source URL"}]
        resp = await client.put(f"/api/agents/{agent_id}", json={"input_schema": schema})
        assert resp.status_code == 200
        assert resp.json()["status"] == "updating"
        assert resp.json()["input_schema"][0]["type"] == "url"

    @pytest.mark.asyncio
    async def test_schema_update_triggers_forge(self, client, app):
        """Updating input_schema/output_schema is substantive and triggers forge."""
        create = await client.post("/api/agents", json={"name": "T", "description": "d"})
        agent_id = create.json()["id"]
        await app.state.agent_repo.update(agent_id, status="ready")

        schema = [{"name": "topic", "type": "text", "required": True}]
        resp = await client.put(f"/api/agents/{agent_id}", json={"input_schema": schema})
        assert resp.status_code == 200
        assert resp.json()["status"] == "updating"


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
    async def test_delete_agent_with_readonly_git_objects(self, client, app, tmp_path):
        """Issue #74: delete fails on Windows when .git has read-only files."""
        import stat

        create = await client.post("/api/agents", json={"name": "T", "description": "d"})
        agent_id = create.json()["id"]
        output_dir = tmp_path / agent_id
        git_obj = output_dir / ".git" / "objects" / "ab"
        git_obj.mkdir(parents=True)
        obj_file = git_obj / "1234567890abcdef"
        obj_file.write_bytes(b"blob")
        # Make read-only (simulates git pack objects on Windows)
        obj_file.chmod(stat.S_IRUSR | stat.S_IRGRP | stat.S_IROTH)
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

    @pytest.mark.asyncio
    async def test_list_runs_nonexistent_agent_returns_404(self, client):
        """BUG-5: GET /api/agents/{id}/runs should 404 for nonexistent agent."""
        resp = await client.get("/api/agents/nonexistent-id/runs")
        assert resp.status_code == 404


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
