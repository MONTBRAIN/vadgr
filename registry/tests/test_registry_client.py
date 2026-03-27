"""Tests for registry adapters and client operations."""

import json
import zipfile
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock

from registry.adapters import create_adapter
from registry.adapters.local import LocalAdapter
from registry.adapters.http import HTTPAdapter
from registry.adapters.github import GitHubAdapter
from registry.adapters.base import RegistryAdapter


class TestCreateAdapter:

    def test_local_from_path(self):
        adapter = create_adapter({"name": "local", "path": "/tmp/test"})
        assert isinstance(adapter, LocalAdapter)

    def test_local_from_type(self):
        adapter = create_adapter({"name": "local", "type": "local", "path": "/tmp"})
        assert isinstance(adapter, LocalAdapter)

    def test_github_from_repo(self):
        adapter = create_adapter({"name": "gh", "url": "https://raw.github.com/x/y/main", "github_repo": "x/y"})
        assert isinstance(adapter, GitHubAdapter)

    def test_github_from_type(self):
        adapter = create_adapter({"name": "gh", "type": "github", "url": "https://example.com"})
        assert isinstance(adapter, GitHubAdapter)

    def test_http_default(self):
        adapter = create_adapter({"name": "remote", "url": "https://registry.example.com"})
        assert isinstance(adapter, HTTPAdapter)


class TestLocalAdapter:

    def test_fetch_index(self, local_registry):
        adapter = LocalAdapter({"name": "test", "path": str(local_registry)})
        index = adapter.fetch_index()
        assert "demo-agent" in index["agents"]

    def test_fetch_index_empty_registry(self, tmp_path):
        reg = tmp_path / "empty-reg"
        reg.mkdir()
        adapter = LocalAdapter({"name": "test", "path": str(reg)})
        index = adapter.fetch_index()
        assert index["agents"] == {}

    def test_download_agent(self, local_registry, tmp_path):
        adapter = LocalAdapter({"name": "test", "path": str(local_registry)})
        dest = tmp_path / "downloaded.agnt"
        result = adapter.download_agent("agents/demo-agent-1.0.0.agnt", dest)
        assert result.exists()
        assert zipfile.is_zipfile(result)

    def test_download_missing_raises(self, local_registry, tmp_path):
        adapter = LocalAdapter({"name": "test", "path": str(local_registry)})
        with pytest.raises(FileNotFoundError):
            adapter.download_agent("agents/nope.agnt", tmp_path / "out.agnt")

    def test_push_agent(self, local_registry, sample_agnt_file):
        adapter = LocalAdapter({"name": "test", "path": str(local_registry)})
        manifest = {"name": "new-agent", "version": "0.1.0", "description": "New"}
        result = adapter.push_agent(sample_agnt_file, manifest)
        assert "Published" in result
        # Check index was updated
        index = adapter.fetch_index()
        assert "new-agent" in index["agents"]
        # Check file was copied
        assert (local_registry / "agents" / "new-agent-0.1.0.agnt").exists()

    def test_search(self, local_registry):
        adapter = LocalAdapter({"name": "test", "path": str(local_registry)})
        results = adapter.search("demo")
        assert len(results) == 1
        assert results[0]["name"] == "demo-agent"

    def test_search_no_match(self, local_registry):
        adapter = LocalAdapter({"name": "test", "path": str(local_registry)})
        results = adapter.search("nonexistent-xyz")
        assert results == []

    def test_search_case_insensitive(self, local_registry):
        adapter = LocalAdapter({"name": "test", "path": str(local_registry)})
        results = adapter.search("DEMO")
        assert len(results) == 1

    def test_find_agent(self, local_registry):
        adapter = LocalAdapter({"name": "test", "path": str(local_registry)})
        agent = adapter.find_agent("demo-agent")
        assert agent is not None
        assert agent["version"] == "1.0.0"

    def test_find_agent_not_found(self, local_registry):
        adapter = LocalAdapter({"name": "test", "path": str(local_registry)})
        assert adapter.find_agent("nope") is None


class TestHTTPAdapter:

    def _mock_urlopen(self, response_data, status=200):
        mock_resp = MagicMock()
        mock_resp.read.return_value = (
            json.dumps(response_data).encode()
            if isinstance(response_data, dict)
            else response_data
        )
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)
        return mock_resp

    @patch("registry.adapters.http.urllib.request.urlopen")
    def test_fetch_index(self, mock_urlopen):
        index_data = {"registry": {"name": "test"}, "agents": {"foo": {"version": "1.0.0"}}}
        mock_urlopen.return_value = self._mock_urlopen(index_data)

        adapter = HTTPAdapter({"name": "test", "url": "https://example.com/registry"})
        index = adapter.fetch_index()
        assert "foo" in index["agents"]

    @patch("registry.adapters.http.urllib.request.urlopen")
    def test_download_agent(self, mock_urlopen, tmp_path):
        mock_urlopen.return_value = self._mock_urlopen(b"fake zip data")

        adapter = HTTPAdapter({"name": "test", "url": "https://example.com"})
        dest = tmp_path / "agent.agnt"
        adapter.download_agent("agents/test.agnt", dest)
        assert dest.exists()

    @patch("registry.adapters.http.urllib.request.urlopen")
    def test_push_agent(self, mock_urlopen, sample_agnt_file):
        mock_urlopen.return_value = self._mock_urlopen(b"ok")

        adapter = HTTPAdapter({"name": "test", "url": "https://example.com"})
        result = adapter.push_agent(sample_agnt_file, {"name": "test", "version": "0.1.0"})
        assert "Published" in result

    @patch("registry.adapters.http.urllib.request.urlopen")
    def test_search(self, mock_urlopen):
        index_data = {
            "agents": {
                "data-analysis": {"version": "1.0.0", "description": "Analyze data"},
                "web-scraper": {"version": "0.2.0", "description": "Scrape websites"},
            }
        }
        mock_urlopen.return_value = self._mock_urlopen(index_data)

        adapter = HTTPAdapter({"name": "test", "url": "https://example.com"})
        results = adapter.search("data")
        assert len(results) == 1
        assert results[0]["name"] == "data-analysis"

    def test_auth_header_set(self):
        adapter = HTTPAdapter({"name": "test", "url": "https://example.com", "token": "secret123"})
        headers = adapter._headers()
        assert headers["Authorization"] == "Bearer secret123"

    def test_no_auth_header_when_no_token(self):
        adapter = HTTPAdapter({"name": "test", "url": "https://example.com"})
        headers = adapter._headers()
        assert "Authorization" not in headers
