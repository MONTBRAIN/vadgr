"""Tests for registry security module.

Covers: zip slip, zip bombs, path traversal, SSRF, SHA256 integrity,
TLS context, URL validation, env var token resolution, local adapter safety.
"""

import hashlib
import json
import os
import ssl
import struct
import zipfile
from pathlib import Path
from unittest import mock

import pytest

from registry.security import (
    MAX_FILE_COUNT,
    MAX_UNCOMPRESSED_SIZE,
    MAX_ZIP_PATH_LENGTH,
    compute_sha256,
    create_ssl_context,
    resolve_token,
    safe_extract,
    validate_download_url,
    validate_local_path,
    verify_sha256,
)


# ---------------------------------------------------------------------------
# safe_extract: zip slip
# ---------------------------------------------------------------------------

class TestZipSlip:
    """Zip slip attacks via path traversal in archive entries."""

    def test_blocks_dotdot_path(self, tmp_path):
        """Archive with ../../etc/passwd must be rejected."""
        zip_path = tmp_path / "evil.zip"
        with zipfile.ZipFile(zip_path, "w") as zf:
            zf.writestr("../../etc/passwd", "root:x:0:0:")

        dest = tmp_path / "output"
        with zipfile.ZipFile(zip_path, "r") as zf:
            with pytest.raises(ValueError, match="path traversal"):
                safe_extract(zf, dest)

    def test_blocks_absolute_path(self, tmp_path):
        """Archive with absolute path /etc/cron.d/backdoor must be rejected."""
        zip_path = tmp_path / "evil.zip"
        with zipfile.ZipFile(zip_path, "w") as zf:
            zf.writestr("/etc/cron.d/backdoor", "* * * * * evil")

        dest = tmp_path / "output"
        with zipfile.ZipFile(zip_path, "r") as zf:
            with pytest.raises(ValueError, match="absolute path"):
                safe_extract(zf, dest)

    def test_blocks_dotdot_in_middle(self, tmp_path):
        """Archive with legit/../../../escape must be rejected."""
        zip_path = tmp_path / "evil.zip"
        with zipfile.ZipFile(zip_path, "w") as zf:
            zf.writestr("legit/../../../escape.txt", "gotcha")

        dest = tmp_path / "output"
        with zipfile.ZipFile(zip_path, "r") as zf:
            with pytest.raises(ValueError, match="path traversal"):
                safe_extract(zf, dest)

    def test_allows_normal_paths(self, tmp_path):
        """Normal archive entries should extract fine."""
        zip_path = tmp_path / "good.zip"
        with zipfile.ZipFile(zip_path, "w") as zf:
            zf.writestr("manifest.json", "{}")
            zf.writestr("agent/steps/step_01.md", "# Step 1")
            zf.writestr("nested/dir/file.txt", "content")

        dest = tmp_path / "output"
        with zipfile.ZipFile(zip_path, "r") as zf:
            safe_extract(zf, dest)

        assert (dest / "manifest.json").exists()
        assert (dest / "agent/steps/step_01.md").exists()
        assert (dest / "nested/dir/file.txt").read_text() == "content"

    def test_blocks_symlink_entry(self, tmp_path):
        """Archive containing a symlink entry must be rejected."""
        zip_path = tmp_path / "symlink.zip"
        with zipfile.ZipFile(zip_path, "w") as zf:
            info = zipfile.ZipInfo("evil_link")
            # Set symlink flag in external attributes (Unix)
            info.external_attr = 0o120000 << 16
            zf.writestr(info, "/etc/shadow")

        dest = tmp_path / "output"
        with zipfile.ZipFile(zip_path, "r") as zf:
            with pytest.raises(ValueError, match="symlink"):
                safe_extract(zf, dest)


# ---------------------------------------------------------------------------
# safe_extract: zip bomb
# ---------------------------------------------------------------------------

class TestZipBomb:
    """Zip bomb protection via size and file count limits."""

    def test_blocks_excessive_file_count(self, tmp_path):
        """Archive with more than MAX_FILE_COUNT entries must be rejected."""
        zip_path = tmp_path / "bomb.zip"
        with zipfile.ZipFile(zip_path, "w") as zf:
            for i in range(MAX_FILE_COUNT + 1):
                zf.writestr(f"file_{i}.txt", "x")

        dest = tmp_path / "output"
        with zipfile.ZipFile(zip_path, "r") as zf:
            with pytest.raises(ValueError, match="exceeds limit"):
                safe_extract(zf, dest)

    def test_blocks_excessive_uncompressed_size(self):
        """Archive with entries whose total reported size exceeds limit."""
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            zip_path = td / "bomb.zip"
            with zipfile.ZipFile(zip_path, "w") as zf:
                zf.writestr("small.txt", "x")

            dest = td / "output"
            with zipfile.ZipFile(zip_path, "r") as zf:
                for entry in zf.infolist():
                    entry.file_size = MAX_UNCOMPRESSED_SIZE + 1
                with pytest.raises(ValueError, match="MB limit"):
                    safe_extract(zf, dest)

    def test_allows_within_limits(self, tmp_path):
        """Archive within both limits should extract fine."""
        zip_path = tmp_path / "ok.zip"
        with zipfile.ZipFile(zip_path, "w") as zf:
            for i in range(10):
                zf.writestr(f"file_{i}.txt", f"content {i}")

        dest = tmp_path / "output"
        with zipfile.ZipFile(zip_path, "r") as zf:
            safe_extract(zf, dest)

        assert len(list(dest.iterdir())) == 10

    def test_blocks_long_path(self, tmp_path):
        """Archive entry with excessively long path must be rejected."""
        zip_path = tmp_path / "longpath.zip"
        long_name = "a" * (MAX_ZIP_PATH_LENGTH + 1)
        with zipfile.ZipFile(zip_path, "w") as zf:
            zf.writestr(long_name, "content")

        dest = tmp_path / "output"
        with zipfile.ZipFile(zip_path, "r") as zf:
            with pytest.raises(ValueError, match="path too long"):
                safe_extract(zf, dest)


# ---------------------------------------------------------------------------
# SHA256 integrity
# ---------------------------------------------------------------------------

class TestSHA256:
    """SHA256 compute and verify."""

    def test_compute_sha256(self, tmp_path):
        """compute_sha256 returns correct hex digest."""
        f = tmp_path / "test.bin"
        content = b"hello world"
        f.write_bytes(content)
        expected = hashlib.sha256(content).hexdigest()
        assert compute_sha256(f) == expected

    def test_compute_sha256_large_file(self, tmp_path):
        """compute_sha256 handles files larger than chunk size."""
        f = tmp_path / "large.bin"
        # 256KB of data -- larger than the 64KB chunk
        content = b"x" * (256 * 1024)
        f.write_bytes(content)
        expected = hashlib.sha256(content).hexdigest()
        assert compute_sha256(f) == expected

    def test_verify_sha256_pass(self, tmp_path):
        """verify_sha256 returns True when hash matches."""
        f = tmp_path / "test.bin"
        f.write_bytes(b"test data")
        h = compute_sha256(f)
        assert verify_sha256(f, h) is True

    def test_verify_sha256_case_insensitive(self, tmp_path):
        """verify_sha256 accepts uppercase hex digest."""
        f = tmp_path / "test.bin"
        f.write_bytes(b"test data")
        h = compute_sha256(f)
        assert verify_sha256(f, h.upper()) is True

    def test_verify_sha256_fail(self, tmp_path):
        """verify_sha256 raises ValueError on mismatch."""
        f = tmp_path / "test.bin"
        f.write_bytes(b"real content")
        with pytest.raises(ValueError, match="Integrity check failed"):
            verify_sha256(f, "0000000000000000000000000000000000000000000000000000000000000000")

    def test_verify_sha256_includes_both_hashes(self, tmp_path):
        """Error message includes expected and actual hashes for debugging."""
        f = tmp_path / "test.bin"
        f.write_bytes(b"data")
        fake = "a" * 64
        with pytest.raises(ValueError, match=f"expected sha256={fake}"):
            verify_sha256(f, fake)


# ---------------------------------------------------------------------------
# URL validation (SSRF)
# ---------------------------------------------------------------------------

class TestURLValidation:
    """Anti-SSRF URL validation."""

    def test_allows_https(self):
        assert validate_download_url("https://example.com/agent.agnt") == "https://example.com/agent.agnt"

    def test_allows_http(self):
        assert validate_download_url("http://example.com/agent.agnt") == "http://example.com/agent.agnt"

    def test_blocks_file_scheme(self):
        with pytest.raises(ValueError, match="Unsupported URL scheme"):
            validate_download_url("file:///etc/passwd")

    def test_blocks_ftp_scheme(self):
        with pytest.raises(ValueError, match="Unsupported URL scheme"):
            validate_download_url("ftp://evil.com/agent.agnt")

    def test_blocks_javascript_scheme(self):
        with pytest.raises(ValueError, match="Unsupported URL scheme"):
            validate_download_url("javascript:alert(1)")

    def test_blocks_localhost_ip(self):
        with pytest.raises(ValueError, match="private/reserved IP"):
            validate_download_url("http://127.0.0.1/agent.agnt")

    def test_blocks_private_10_network(self):
        with pytest.raises(ValueError, match="private/reserved IP"):
            validate_download_url("http://10.0.0.1/agent.agnt")

    def test_blocks_private_172_network(self):
        with pytest.raises(ValueError, match="private/reserved IP"):
            validate_download_url("http://172.16.0.1/agent.agnt")

    def test_blocks_private_192_network(self):
        with pytest.raises(ValueError, match="private/reserved IP"):
            validate_download_url("http://192.168.1.1/agent.agnt")

    def test_blocks_link_local(self):
        with pytest.raises(ValueError, match="private/reserved IP"):
            validate_download_url("http://169.254.169.254/latest/meta-data/")

    def test_blocks_ipv6_loopback(self):
        with pytest.raises(ValueError, match="private/reserved IP"):
            validate_download_url("http://[::1]/agent.agnt")

    def test_allows_private_when_flag_set(self):
        """allow_private=True disables the IP check (for testing/dev)."""
        result = validate_download_url("http://192.168.1.1/agent.agnt", allow_private=True)
        assert result == "http://192.168.1.1/agent.agnt"

    def test_blocks_credentials_in_url(self):
        with pytest.raises(ValueError, match="embedded credentials"):
            validate_download_url("https://user:pass@example.com/agent.agnt")

    def test_blocks_empty_hostname(self):
        with pytest.raises(ValueError, match="no hostname"):
            validate_download_url("http:///path")

    def test_allows_hostname_not_ip(self):
        """Hostnames that aren't IP literals should be allowed."""
        result = validate_download_url("https://registry.example.com/agents/my-agent.agnt")
        assert "registry.example.com" in result

    def test_allows_github_release_url(self):
        """Real-world GitHub release URLs should pass."""
        url = "https://github.com/MONTBRAIN/sample-registry/releases/download/agents/test-0.1.0.agnt"
        assert validate_download_url(url) == url


# ---------------------------------------------------------------------------
# Local path validation
# ---------------------------------------------------------------------------

class TestLocalPathValidation:
    """Path traversal prevention for local adapter."""

    def test_allows_normal_path(self, tmp_path):
        """Normal relative path within root is allowed."""
        (tmp_path / "agents").mkdir()
        (tmp_path / "agents" / "test.agnt").write_text("data")
        result = validate_local_path(Path("agents/test.agnt"), tmp_path)
        assert str(result).startswith(str(tmp_path.resolve()))

    def test_blocks_dotdot_escape(self, tmp_path):
        """../../etc/passwd must be rejected."""
        with pytest.raises(ValueError, match="Path traversal"):
            validate_local_path(Path("../../etc/passwd"), tmp_path)

    def test_blocks_absolute_path(self, tmp_path):
        """Absolute paths outside root must be rejected."""
        with pytest.raises(ValueError, match="Path traversal"):
            validate_local_path(Path("/etc/passwd"), tmp_path)

    def test_blocks_symlink_escape(self, tmp_path):
        """Symlink that resolves outside root must be rejected."""
        link = tmp_path / "evil_link"
        link.symlink_to("/etc")
        with pytest.raises(ValueError, match="Path traversal"):
            validate_local_path(Path("evil_link/passwd"), tmp_path)

    def test_allows_root_itself(self, tmp_path):
        """Path resolving to root itself should be allowed."""
        result = validate_local_path(Path("."), tmp_path)
        assert result == tmp_path.resolve()


# ---------------------------------------------------------------------------
# Token resolution
# ---------------------------------------------------------------------------

class TestTokenResolution:
    """Env var reference support in token config."""

    def test_literal_value(self):
        assert resolve_token("my-secret-token") == "my-secret-token"

    def test_dollar_env_var(self):
        with mock.patch.dict(os.environ, {"MY_TOKEN": "secret123"}):
            assert resolve_token("$MY_TOKEN") == "secret123"

    def test_braced_env_var(self):
        with mock.patch.dict(os.environ, {"MY_TOKEN": "secret456"}):
            assert resolve_token("${MY_TOKEN}") == "secret456"

    def test_missing_env_var_returns_empty(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            assert resolve_token("$NONEXISTENT_VAR_XYZ") == ""

    def test_none_returns_empty(self):
        assert resolve_token(None) == ""

    def test_empty_returns_empty(self):
        assert resolve_token("") == ""

    def test_dollar_in_middle_is_literal(self):
        """Only $VAR at start is treated as env reference."""
        assert resolve_token("not$aref") == "not$aref"

    def test_github_token_env_var(self):
        with mock.patch.dict(os.environ, {"GITHUB_TOKEN": "ghp_abc123"}):
            assert resolve_token("$GITHUB_TOKEN") == "ghp_abc123"


# ---------------------------------------------------------------------------
# TLS context
# ---------------------------------------------------------------------------

class TestSSLContext:
    """SSL context creation."""

    def test_verify_enabled_by_default(self):
        ctx = create_ssl_context()
        assert ctx.verify_mode == ssl.CERT_REQUIRED
        assert ctx.check_hostname is True

    def test_minimum_tls_12(self):
        ctx = create_ssl_context()
        assert ctx.minimum_version >= ssl.TLSVersion.TLSv1_2

    def test_verify_disabled(self):
        ctx = create_ssl_context(verify=False)
        assert ctx.verify_mode == ssl.CERT_NONE
        assert ctx.check_hostname is False


# ---------------------------------------------------------------------------
# Integration: local adapter path traversal
# ---------------------------------------------------------------------------

class TestLocalAdapterSecurity:
    """Security tests for the local adapter."""

    def test_download_blocks_traversal(self, tmp_path):
        """Local adapter download_agent rejects path traversal."""
        from registry.adapters.local import LocalAdapter

        reg_dir = tmp_path / "registry"
        reg_dir.mkdir()
        (reg_dir / "index.json").write_text("{}")

        adapter = LocalAdapter({"name": "test", "path": str(reg_dir)})
        with pytest.raises(ValueError, match="Path traversal"):
            adapter.download_agent("../../etc/passwd", tmp_path / "dest.agnt")

    def test_push_includes_sha256(self, tmp_path):
        """Local adapter push_agent writes sha256 to index.json."""
        from registry.adapters.local import LocalAdapter

        reg_dir = tmp_path / "registry"
        reg_dir.mkdir()

        adapter = LocalAdapter({"name": "test", "path": str(reg_dir)})

        # Create a minimal .agnt
        agnt = tmp_path / "test.agnt"
        manifest = {"manifest_version": 1, "name": "test-agent", "version": "0.1.0"}
        with zipfile.ZipFile(agnt, "w") as zf:
            zf.writestr("manifest.json", json.dumps(manifest))
            zf.writestr("agentic.md", "# Test")

        adapter.push_agent(agnt, manifest)

        index = json.loads((reg_dir / "index.json").read_text())
        assert "sha256" in index["agents"]["test-agent"]
        assert len(index["agents"]["test-agent"]["sha256"]) == 64


# ---------------------------------------------------------------------------
# Integration: packer uses safe_extract
# ---------------------------------------------------------------------------

class TestPackerSecurity:
    """Verify packer.unpack rejects invalid archives."""

    def test_unpack_rejects_missing_manifest(self, tmp_path):
        """packer.unpack rejects archives without agent-forge.json."""
        from registry.packer import unpack

        zip_path = tmp_path / "evil.agnt"
        with zipfile.ZipFile(zip_path, "w") as zf:
            zf.writestr("agent.bundle", b"fake")

        dest = tmp_path / "output"
        with pytest.raises(ValueError, match="missing agent-forge.json"):
            unpack(zip_path, dest)

    def test_unpack_rejects_missing_bundle(self, tmp_path):
        """packer.unpack rejects archives without agent.bundle."""
        from registry.packer import unpack
        from registry.manifest import MANIFEST_FILENAME

        zip_path = tmp_path / "evil.agnt"
        manifest = {"manifest_version": 2, "name": "evil-agent", "version": "0.1.0"}
        with zipfile.ZipFile(zip_path, "w") as zf:
            zf.writestr(MANIFEST_FILENAME, json.dumps(manifest))

        dest = tmp_path / "output"
        with pytest.raises(ValueError, match="missing agent.bundle"):
            unpack(zip_path, dest)


# ---------------------------------------------------------------------------
# Integration: pull verifies SHA256
# ---------------------------------------------------------------------------

class TestPullIntegrity:
    """Verify that pull checks SHA256 when available."""

    def test_pull_rejects_tampered_download(self, tmp_path, monkeypatch):
        """If index has sha256, a tampered download should fail."""
        from registry import registry_client
        from registry.adapters.local import LocalAdapter

        # Set up a local registry
        reg_dir = tmp_path / "registry"
        reg_dir.mkdir()
        agents_dir = reg_dir / "agents"
        agents_dir.mkdir()

        # Create a valid .agnt
        agnt = agents_dir / "test-agent-0.1.0.agnt"
        manifest = {"manifest_version": 1, "name": "test-agent", "version": "0.1.0"}
        with zipfile.ZipFile(agnt, "w") as zf:
            zf.writestr("manifest.json", json.dumps(manifest))
            zf.writestr("agentic.md", "# Test")

        # Write index with WRONG sha256
        index = {
            "registry": {"name": "test"},
            "agents": {
                "test-agent": {
                    "version": "0.1.0",
                    "download_url": "agents/test-agent-0.1.0.agnt",
                    "sha256": "0" * 64,  # deliberately wrong
                }
            },
        }
        (reg_dir / "index.json").write_text(json.dumps(index))

        # Patch _get_adapter to return our local adapter
        adapter = LocalAdapter({"name": "test", "path": str(reg_dir)})
        monkeypatch.setattr(registry_client, "_get_adapter", lambda *a, **kw: adapter)

        install_dir = tmp_path / "installed"
        monkeypatch.setattr(registry_client, "load_config", lambda: {"agents_dir": str(install_dir)})
        monkeypatch.setattr(registry_client, "get_agents_dir", lambda c: install_dir)

        with pytest.raises(ValueError, match="Integrity check failed"):
            registry_client.pull("test-agent")

    def test_pull_succeeds_with_correct_hash(self, tmp_path, monkeypatch, sample_agnt_file):
        """Pull works when sha256 matches."""
        from registry import registry_client
        from registry.adapters.local import LocalAdapter
        from registry.security import compute_sha256
        import shutil

        reg_dir = tmp_path / "registry"
        reg_dir.mkdir()
        agents_dir = reg_dir / "agents"
        agents_dir.mkdir()

        agnt = agents_dir / "test-agent-0.1.0.agnt"
        shutil.copy2(sample_agnt_file, agnt)

        correct_hash = compute_sha256(agnt)

        index = {
            "registry": {"name": "test"},
            "agents": {
                "test-agent": {
                    "version": "0.1.0",
                    "download_url": "agents/test-agent-0.1.0.agnt",
                    "sha256": correct_hash,
                }
            },
        }
        (reg_dir / "index.json").write_text(json.dumps(index))

        adapter = LocalAdapter({"name": "test", "path": str(reg_dir)})
        monkeypatch.setattr(registry_client, "_get_adapter", lambda *a, **kw: adapter)

        install_dir = tmp_path / "installed"
        monkeypatch.setattr(registry_client, "load_config", lambda: {"agents_dir": str(install_dir)})
        monkeypatch.setattr(registry_client, "get_agents_dir", lambda c: install_dir)

        result = registry_client.pull("test-agent")
        assert "test-agent" in result

    def test_pull_skips_check_when_no_hash(self, tmp_path, monkeypatch, sample_agnt_file):
        """Pull succeeds without sha256 (backward compat with old registries)."""
        from registry import registry_client
        from registry.adapters.local import LocalAdapter
        import shutil

        reg_dir = tmp_path / "registry"
        reg_dir.mkdir()
        agents_dir = reg_dir / "agents"
        agents_dir.mkdir()

        agnt = agents_dir / "test-agent-0.1.0.agnt"
        shutil.copy2(sample_agnt_file, agnt)

        # No sha256 in index
        index = {
            "registry": {"name": "test"},
            "agents": {
                "test-agent": {
                    "version": "0.1.0",
                    "download_url": "agents/test-agent-0.1.0.agnt",
                }
            },
        }
        (reg_dir / "index.json").write_text(json.dumps(index))

        adapter = LocalAdapter({"name": "test", "path": str(reg_dir)})
        monkeypatch.setattr(registry_client, "_get_adapter", lambda *a, **kw: adapter)

        install_dir = tmp_path / "installed"
        monkeypatch.setattr(registry_client, "load_config", lambda: {"agents_dir": str(install_dir)})
        monkeypatch.setattr(registry_client, "get_agents_dir", lambda c: install_dir)

        result = registry_client.pull("test-agent")
        assert "test-agent" in result
