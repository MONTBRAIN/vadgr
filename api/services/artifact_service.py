"""Helpers for staged runtime input artifacts."""

import mimetypes
import shutil
from pathlib import Path
from uuid import uuid4


class ArtifactService:
    """Stages uploaded artifacts and materializes them into run input dirs."""

    def __init__(self, project_root: Path):
        self.project_root = project_root

    def stage_upload(self, forge_path: str, filename: str, content: bytes) -> dict:
        """Store an uploaded file under the agent folder before a run starts."""
        safe_name = Path(filename).name or "upload.bin"
        upload_dir = self.project_root / forge_path / "uploads" / uuid4().hex
        upload_dir.mkdir(parents=True, exist_ok=True)
        target = upload_dir / safe_name
        target.write_bytes(content)
        return self._descriptor_for_path(target, safe_name, forge_path=forge_path)

    def validate_upload(
        self,
        schema_field: dict | None,
        filename: str,
        content_type: str | None,
        size_bytes: int,
    ) -> str | None:
        """Validate an uploaded artifact against schema metadata."""
        if not schema_field:
            return None

        safe_name = Path(filename).name
        suffix = Path(safe_name).suffix.lower()
        allowed_suffixes = [
            ext.lower() if ext.startswith(".") else f".{ext.lower()}"
            for ext in (schema_field.get("accept") or [])
        ]
        if allowed_suffixes and suffix not in allowed_suffixes:
            allowed_text = ", ".join(allowed_suffixes)
            return f"Expected one of: {allowed_text}"

        mime_type = (content_type or mimetypes.guess_type(safe_name)[0] or "").lower()
        allowed_mime_types = [item.lower() for item in (schema_field.get("mime_types") or [])]
        if allowed_mime_types and not self._mime_type_allowed(
            mime_type=mime_type,
            allowed_mime_types=allowed_mime_types,
            suffix=suffix,
        ):
            allowed_text = ", ".join(allowed_mime_types)
            return f"Expected MIME type: {allowed_text}"

        max_size_mb = schema_field.get("max_size_mb")
        if max_size_mb is not None and size_bytes > int(max_size_mb) * 1024 * 1024:
            return f"File exceeds maximum size of {max_size_mb} MB"

        return None

    def materialize_run_inputs(self, forge_path: str, run_id: str, inputs: dict) -> dict:
        """Copy staged artifacts into output/{run_id}/inputs/ and rewrite descriptors."""
        if not forge_path or not run_id:
            return inputs

        materialized = {}
        for key, value in inputs.items():
            if not self._is_artifact_descriptor(value):
                materialized[key] = value
                continue

            source = self._resolve_agent_relative_path(forge_path, value["path"])
            if not source.is_file():
                materialized[key] = value
                continue

            target_dir = self.project_root / forge_path / "output" / run_id / "inputs" / key
            target_dir.mkdir(parents=True, exist_ok=True)
            filename = value.get("filename") or source.name
            target = target_dir / filename
            shutil.copy2(source, target)
            materialized[key] = self._descriptor_for_path(target, filename, forge_path=forge_path)

        return materialized

    def _descriptor_for_path(
        self,
        path: Path,
        filename: str,
        forge_path: str | None = None,
    ) -> dict:
        mime_type, _ = mimetypes.guess_type(filename)
        relative_path = path
        if forge_path:
            relative_path = path.relative_to(self.project_root / forge_path)
        else:
            relative_path = path.relative_to(self.project_root)
        return {
            "kind": "file",
            "path": str(relative_path),
            "filename": filename,
            "mime_type": mime_type or "application/octet-stream",
        }

    def _resolve_agent_relative_path(self, forge_path: str, path: str) -> Path:
        candidate = self.project_root / forge_path / path
        resolved = candidate.resolve()
        agent_root = (self.project_root / forge_path).resolve()
        if agent_root not in resolved.parents and resolved != agent_root:
            raise ValueError("Artifact path escapes agent root")
        return resolved

    @staticmethod
    def _is_artifact_descriptor(value: object) -> bool:
        return (
            isinstance(value, dict)
            and value.get("kind") in {"file", "archive", "directory"}
            and isinstance(value.get("path"), str)
        )

    @staticmethod
    def _mime_type_allowed(mime_type: str, allowed_mime_types: list[str], suffix: str) -> bool:
        if mime_type in allowed_mime_types:
            return True

        if not mime_type or mime_type == "application/octet-stream":
            return True

        markdown_family = {"text/markdown", "text/x-markdown", "text/plain"}
        if suffix in {".md", ".markdown"} and mime_type in markdown_family:
            return bool(markdown_family & set(allowed_mime_types))

        return False
