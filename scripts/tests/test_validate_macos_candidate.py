"""Offline candidate snapshots; no credentials, GitHub writes or signing."""

from copy import deepcopy
import json
from pathlib import Path
import subprocess
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import validate_macos_candidate as candidate  # noqa: E402

HEAD = "a" * 40
TREE = "b" * 40
OTHER = "c" * 40


def snapshot():
    repo = {"full_name": candidate.REPOSITORY, "fork": False, "default_branch": "master"}
    pull = {"number": 17, "state": "open",
            "head": {"ref": candidate.BRANCH, "sha": HEAD, "repo": deepcopy(repo)},
            "base": {"ref": "master", "sha": OTHER, "repo": deepcopy(repo)}}
    branch = {"ref": "refs/heads/" + candidate.BRANCH, "object": {"sha": HEAD, "type": "commit"}}
    root = Path(__file__).resolve().parents[2]
    return {
        "repository": repo, "branch": branch, "branch_end": deepcopy(branch),
        "pull_requests": [pull], "pull_request_end": deepcopy(pull),
        "commit": {"sha": HEAD, "tree": {"sha": TREE}},
        "local": {"sha": HEAD, "tree": TREE, "clean": True,
                  "files": {name: (root / name).read_text(encoding="utf-8") for name in candidate.FILES}},
        "rules": [{"type": "required_status_checks", "parameters": {"required_status_checks": [
            {"context": "rust (macos-latest)", "integration_id": 15368},
            {"context": "secret-scan", "integration_id": None},
        ]}}],
        "check_runs": [{"id": 12, "head_sha": HEAD, "name": "rust (macos-latest)",
                        "app": {"id": 15368}, "status": "completed", "conclusion": "success"}],
        "statuses": {"sha": HEAD, "statuses": [{"id": 14, "context": "secret-scan", "state": "success"}]},
        "tags": [{"name": "v0.4.12"}], "releases": [{"tag_name": "v0.4.12"}],
    }


def validate(value):
    return candidate.validate(value, HEAD, candidate.REPOSITORY, candidate.BRANCH)


def changed(value, path, replacement):
    parent = value
    for key in path[:-1]:
        parent = parent[key]
    parent[path[-1]] = replacement
    return value


NEGATIVE = [
    (("repository", "full_name"), "someone/fork"),
    (("repository", "fork"), True),
    (("pull_requests", 0, "head", "repo", "fork"), True),
    (("pull_requests", 0, "head", "repo", "full_name"), "someone/fork"),
    (("pull_requests", 0, "state"), "closed"),
    (("pull_request_end", "state"), "closed"),
    (("pull_requests", 0, "head", "ref"), "other-branch"),
    (("pull_requests", 0, "head", "sha"), OTHER),
    (("pull_requests", 0, "base", "ref"), "other-base"),
    (("pull_requests",), []),
    (("branch", "object", "sha"), OTHER),
    (("branch_end", "object", "sha"), OTHER),
    (("commit", "tree", "sha"), "unknown"),
    (("local", "tree"), OTHER),
    (("local", "clean"), False),
    (("check_runs",), []),
    (("check_runs", 0, "status"), "in_progress"),
    (("check_runs", 0, "conclusion"), "failure"),
    (("check_runs", 0, "conclusion"), "skipped"),
    (("check_runs", 0, "head_sha"), OTHER),
    (("check_runs", 0, "app", "id"), 999),
    (("statuses", "statuses", 0, "state"), "pending"),
    (("statuses", "sha"), OTHER),
    (("rules",), []),
    (("tags",), [{"name": "v0.5.0"}]),
    (("releases",), [{"tag_name": "v0.5.0", "draft": True}]),
]


@pytest.mark.parametrize("path,replacement", NEGATIVE)
def test_rejects_unverified_candidate(path, replacement):
    with pytest.raises(candidate.Refused):
        validate(changed(snapshot(), path, replacement))


def test_outputs_only_sanitized_provenance():
    value = snapshot()
    value["repository"]["owner"] = {"id": 123456, "private_detail": "fixture-private-marker"}
    value["pull_requests"][0]["body"] = "fixture-private-marker"
    value["check_runs"][0]["output"] = {"text": "fixture-private-marker"}
    metadata = validate(value)
    assert metadata["source_sha"] == HEAD
    assert metadata["source_tree"] == TREE
    assert metadata["pull_request"] == 17
    assert metadata["version"] == "0.5.0"
    assert metadata["required_checks"] == ["rust (macos-latest)", "secret-scan"]
    assert set(metadata["inputs_sha256"]) == set(candidate.FILES)
    assert "fixture-private-marker" not in json.dumps(metadata)
    assert "123456" not in json.dumps(metadata)


@pytest.mark.parametrize("repository,ref,sha", [
    ("someone/fork", candidate.BRANCH, HEAD),
    (candidate.REPOSITORY, "master", HEAD),
    (candidate.REPOSITORY, candidate.BRANCH, "HEAD"),
    (candidate.REPOSITORY, candidate.BRANCH, "a" * 39),
])
def test_rejects_untrusted_invocation(repository, ref, sha):
    with pytest.raises(candidate.Refused):
        candidate.validate(snapshot(), sha, repository, ref)


def test_own_check_cannot_be_silently_excluded():
    value = snapshot()
    value["rules"][0]["parameters"]["required_status_checks"].append({"context": candidate.SELF_CHECK})
    with pytest.raises(candidate.Refused, match="own check"):
        validate(value)


def test_obsolete_required_contexts_remain_required():
    value = snapshot()
    value["rules"][0]["parameters"]["required_status_checks"] = [{"context": "computer-use (3.10)"}]
    with pytest.raises(candidate.Refused, match=r"missing.*computer-use \(3.10\)"):
        validate(value)


def test_an_older_success_cannot_hide_a_pending_check():
    value = snapshot()
    pending = deepcopy(value["check_runs"][0])
    pending.update(id=13, status="queued", conclusion=None)
    value["check_runs"].append(pending)
    with pytest.raises(candidate.Refused, match="not succeeded"):
        validate(value)


def test_status_success_cannot_replace_the_required_check_app():
    value = snapshot()
    value["check_runs"] = []
    value["statuses"]["statuses"].append({"id": 15, "context": "rust (macos-latest)", "state": "success"})
    with pytest.raises(candidate.Refused, match="missing"):
        validate(value)


@pytest.mark.parametrize("name", candidate.FILES)
def test_missing_source_inputs_refuse(name):
    value = snapshot()
    value["local"]["files"].pop(name)
    with pytest.raises(candidate.Refused, match="missing"):
        validate(value)


@pytest.mark.parametrize("name,old,new", [
    ("Cargo.toml", 'version = "0.5.0"', 'version = "0.5.1"'),
    ("CHANGELOG.md", "[0.5.0] - Unreleased", "[0.5.0] - 2026-01-01"),
    ("packaging/cua/requirements.lock", "vadgr-computer-use==0.7.8", "vadgr-computer-use==0.7.7"),
    ("packaging/cua/requirements.lock", "--hash=sha256:", "--hash=sha512:"),
    (".github/workflows/ci.yml", "dtolnay/rust-toolchain@4360b52568e2003a75bf9bc1d59f33a8e3fc893c", "dtolnay/rust-toolchain@stable"),
])
def test_invalid_metadata_and_pins_refuse(name, old, new):
    value = snapshot()
    assert old in value["local"]["files"][name]
    value["local"]["files"][name] = value["local"]["files"][name].replace(old, new)
    with pytest.raises(candidate.Refused):
        validate(value)


def test_fixture_cli_never_calls_a_metadata_command(tmp_path, monkeypatch, capsys):
    fixture = tmp_path / "snapshot.json"
    fixture.write_text(json.dumps(snapshot()), encoding="utf-8")
    monkeypatch.setattr(candidate, "run", lambda *_: pytest.fail("fixture invoked a process"))
    assert candidate.main(["--sha", HEAD, "--repository", candidate.REPOSITORY, "--ref", candidate.BRANCH,
                           "--fixtures", str(fixture)]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["fixture_mode"] is True


def test_cli_errors_do_not_print_response_or_private_path(tmp_path, capsys):
    fixture = tmp_path / "fixture-private-marker.json"
    fixture.write_text('{"fixture-private-marker":1}', encoding="utf-8")
    assert candidate.main(["--sha", HEAD, "--repository", candidate.REPOSITORY, "--ref", candidate.BRANCH,
                           "--fixtures", str(fixture)]) == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "fixture-private-marker" not in captured.err
    assert "missing or malformed" in captured.err


def test_gh_errors_are_sanitized_and_token_never_enters_argv(monkeypatch):
    seen = []
    def failed(argv, **kwargs):
        seen.append(argv)
        assert kwargs["capture_output"] is True
        return subprocess.CompletedProcess(argv, 1, "fixture-private-marker", "fixture-private-marker")
    monkeypatch.setenv("GH_TOKEN", "fixture-private-marker")
    monkeypatch.setattr(candidate.subprocess, "run", failed)
    with pytest.raises(candidate.Refused, match="metadata command failed"):
        candidate.GitHub().get("rules/branches/master")
    assert "fixture-private-marker" not in repr(seen)
    assert "Authorization" not in repr(seen)


def test_local_checkout_must_match_exact_head_and_be_clean(monkeypatch, tmp_path):
    answers = iter([OTHER])
    monkeypatch.setattr(candidate, "run", lambda *_: next(answers))
    with pytest.raises(candidate.Refused, match="requested commit"):
        candidate.local_source(tmp_path, HEAD)
    answers = iter([HEAD, " M Cargo.toml"])
    with pytest.raises(candidate.Refused, match="not clean"):
        candidate.local_source(tmp_path, HEAD)


def test_collect_reads_active_rules_and_paginates_exact_head_results(monkeypatch, tmp_path):
    value = snapshot()
    calls = []
    monkeypatch.setattr(candidate, "local_source", lambda *_: value["local"])
    class API:
        def get(self, endpoint, pages=False):
            calls.append((endpoint, pages))
            if endpoint == "":
                return value["repository"]
            if endpoint.startswith("git/ref/heads/"):
                return value["branch"]
            if endpoint.startswith("pulls?"):
                return [value["pull_requests"]]
            if endpoint == "pulls/17":
                return value["pull_request_end"]
            if endpoint == f"git/commits/{HEAD}":
                return value["commit"]
            if endpoint.startswith("rules/branches/master?"):
                return [[value["rules"][0]], [{"type": "deletion"}]]
            if endpoint.startswith(f"commits/{HEAD}/check-runs?"):
                return [{"check_runs": []}, {"check_runs": value["check_runs"]}]
            if endpoint.startswith(f"commits/{HEAD}/status?"):
                return [value["statuses"]]
            if endpoint.startswith("tags?"):
                return [value["tags"]]
            if endpoint.startswith("releases?"):
                return [value["releases"]]
            pytest.fail("unexpected metadata endpoint")
    result = candidate.collect(tmp_path, HEAD, API())
    assert validate(result)["source_sha"] == HEAD
    assert all("protection" not in endpoint for endpoint, _ in calls)
    assert all(pages for endpoint, pages in calls if "?" in endpoint)
    assert (f"commits/{HEAD}/check-runs?filter=latest&per_page=100", True) in calls
    assert calls[-2:] == [(f"git/ref/heads/{candidate.BRANCH}", False), ("pulls/17", False)]


def test_gh_pagination_and_sanitized_command_contract(monkeypatch):
    def response(argv, **kwargs):
        assert argv[:3] == ["gh", "api", "--method"]
        assert "--paginate" in argv and "--slurp" in argv
        assert "--hostname" in argv and "github.com" in argv
        assert kwargs["timeout"] == 60
        return subprocess.CompletedProcess(argv, 0, b"[[], []]", b"")
    monkeypatch.setattr(candidate.subprocess, "run", response)
    assert candidate.GitHub().get("rules/branches/master?per_page=100", True) == [[], []]


def test_fixture_cli_as_a_process(tmp_path):
    fixture = tmp_path / "snapshot.json"
    fixture.write_text(json.dumps(snapshot()), encoding="utf-8")
    result = subprocess.run([
        sys.executable, str(Path(candidate.__file__)), "--sha", HEAD,
        "--repository", candidate.REPOSITORY, "--ref", candidate.BRANCH,
        "--fixtures", str(fixture),
    ], capture_output=True, text=True, timeout=15)
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["fixture_mode"] is True


def test_negative_oracles_detect_validation_removed_in_memory(monkeypatch):
    # This mutation never writes a file or changes Git state. These seven
    # inputs are accepted only when the authorization guards are removed.
    monkeypatch.setattr(candidate, "require", lambda *_: None)
    for index in (0, 1, 4, 10, 12, 15, 17):
        path, replacement = NEGATIVE[index]
        with pytest.raises(pytest.fail.Exception, match="DID NOT RAISE"):
            test_rejects_unverified_candidate(path, replacement)


def test_git_blob_newlines_are_not_normalized(monkeypatch):
    monkeypatch.setattr(candidate.subprocess, "run", lambda argv, **kwargs:
                        subprocess.CompletedProcess(argv, 0, b"committed\r\nbytes\r\n", b""))
    assert candidate.run(["git", "show", "fixture"]) == "committed\r\nbytes\r\n"


def test_both_check_and_status_must_pass_when_the_context_is_shared():
    value = snapshot()
    value["check_runs"].append({"id": 19, "head_sha": HEAD, "name": "secret-scan", "app": {"id": 15368},
                               "status": "completed", "conclusion": "failure"})
    with pytest.raises(candidate.Refused, match="not succeeded: secret-scan"):
        validate(value)


def test_untrusted_check_name_is_not_exposed(tmp_path, capsys):
    value = snapshot()
    value["rules"][0]["parameters"]["required_status_checks"][0]["context"] = "fixture-private-marker\nunsafe"
    fixture = tmp_path / "snapshot.json"
    fixture.write_text(json.dumps(value), encoding="utf-8")
    assert candidate.main(["--sha", HEAD, "--repository", candidate.REPOSITORY, "--ref", candidate.BRANCH,
                           "--fixtures", str(fixture)]) == 1
    assert "fixture-private-marker" not in capsys.readouterr().err
