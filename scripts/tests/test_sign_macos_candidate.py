"""Signing boundary tests use synthetic archives and never invoke signing tools."""

import importlib.util
import io
import json
import os
from pathlib import Path
import plistlib
import subprocess
import tarfile
from types import SimpleNamespace

import pytest


SCRIPT = Path(__file__).resolve().parents[1] / "sign_macos_candidate.py"
APP = "Applications/Vadgr.app"
HELPER = APP + "/Contents/Library/LoginItems/Vadgr Computer Use.app"
REQUIREMENT = 'identifier "com.montbrain.vadgr.cua" and anchor apple generic and certificate leaf[subject.OU] = "TESTTEAM00"'
requires_posix_filesystem = pytest.mark.skipif(
    os.name != "posix", reason="requires real POSIX permissions, ownership and symlink semantics",
)


@pytest.fixture
def signer(monkeypatch):
    monkeypatch.syspath_prepend(str(SCRIPT.parent))
    spec = importlib.util.spec_from_file_location("sign_macos_candidate", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.sys = SimpleNamespace(**vars(module.sys))
    return module


def archive(path, entries):
    with tarfile.open(path, "w:gz") as output:
        for name, value in entries:
            member = tarfile.TarInfo(name)
            member.mode = 0o755
            if isinstance(value, tuple):
                member.type, member.linkname = value
                output.addfile(member)
            else:
                member.size = len(value)
                output.addfile(member, io.BytesIO(value))


@pytest.fixture
def candidate(tmp_path, signer, monkeypatch, request):
    from test_validate_package_inputs import make_approved_fixture

    monkeypatch.setattr(signer.sys, "platform", "darwin")
    arch = getattr(request, "param", "arm64")
    target = {"arm64": "aarch64-apple-darwin", "x86_64": "x86_64-apple-darwin"}[arch]
    repo = tmp_path / "repo"
    inputs = repo / "packaging/inputs" / f"macos-{arch}"
    make_approved_fixture(inputs, repo, target=target)
    macos = repo / "packaging/macos"
    (macos / "scripts").mkdir(parents=True)
    (macos / "resources").mkdir()
    (macos / "Vadgr.entitlements").write_bytes(plistlib.dumps({}))
    (macos / "cua-designated-requirement.txt").write_text("UNCONFIGURED\n")
    (macos / "Distribution.xml").write_text('<installer-gui-script><options hostArchitectures="arm64,x86_64"/></installer-gui-script>')
    for name in ("preinstall", "postinstall"):
        (macos / "scripts" / name).write_text("#!/bin/sh\nexit 0\n")
    for name in ("WELCOME.txt", "CONCLUSION.txt"):
        (macos / "resources" / name).write_text("Public package text")
    entries = []
    for path, identifier, executable in ((APP, "com.montbrain.vadgr", "vadgr-app"),
                                         (HELPER, "com.montbrain.vadgr.cua", "vadgr-cua-host")):
        entries.append((path + "/Contents/Info.plist", plistlib.dumps({
            "CFBundleIdentifier": identifier, "CFBundleExecutable": executable,
            "CFBundleShortVersionString": "0.5.0",
        })))
        entries.append((path + "/Contents/MacOS/" + executable, b"\xcf\xfa\xed\xfefixture"))
    entries += [(APP + "/Contents/MacOS/vadgr", b"\xcf\xfa\xed\xfefixture"),
                (APP + "/Contents/Resources/lib/extension.so", b"\xcf\xfa\xed\xfefixture")]
    entries.extend((APP + "/Contents/Resources/" + path.relative_to(inputs).as_posix(), path.read_bytes())
                   for path in sorted(inputs.rglob("*")) if path.is_file())
    if os.name == "posix":
        entries.append(("usr/local/bin/vadgr", (tarfile.SYMTYPE, "/Applications/Vadgr.app/Contents/MacOS/vadgr")))
    source = tmp_path / f"Vadgr-0.5.0-macos-{arch}-unsigned-root.tar.gz"
    archive(source, entries)
    key = tmp_path / "key.p8"
    key.write_text("synthetic key")
    key.chmod(0o600)
    keychain = tmp_path / "temporary.keychain-db"
    keychain.write_bytes(b"synthetic keychain")
    env = {
        "GITHUB_ACTIONS": "true", "RUNNER_ENVIRONMENT": "github-hosted",
        "GITHUB_REPOSITORY": "MONTBRAIN/vadgr", "GITHUB_EVENT_NAME": "workflow_dispatch",
        "SOURCE_SHA": "a" * 40, "GITHUB_SHA": "a" * 40, "SOURCE_TREE": "b" * 40,
        "GITHUB_RUN_ID": "123", "GITHUB_RUN_ATTEMPT": "2", "RUNNER_TEMP": str(tmp_path),
        "APPLICATION_IDENTITY": "C" * 40, "INSTALLER_IDENTITY": "D" * 40,
        "VADGR_MACOS_KEYCHAIN": str(keychain), "VADGR_NOTARY_KEY_FILE": str(key),
        "VADGR_NOTARY_KEY_ID": "TESTKEY123", "VADGR_NOTARY_ISSUER_ID": "00000000-0000-0000-0000-000000000001",
        "MACOS_CUA_REQUIREMENT": REQUIREMENT,
    }
    metadata = {
        "schema": 1, "source_sha": env["SOURCE_SHA"], "source_tree": env["SOURCE_TREE"],
        "run_id": "123", "run_attempt": "2", "architecture": arch,
        "archive_name": source.name, "archive_sha256": signer.sha256(source),
        "lock_sha256": {name: signer.sha256(repo / name) for name in signer.LOCKS},
        "unsigned_development": True,
    }
    record = tmp_path / "build.json"
    record.write_text(json.dumps(metadata))
    return repo, source, record, env, tmp_path / "published"


class NativeTools:
    def __init__(self, env, status="Accepted", arch="arm64"):
        self.env, self.status, self.calls, self.arch = env, status, [], arch

    def __call__(self, argv, phase, **kwargs):
        self.calls.append((argv, phase))
        tool = Path(argv[0]).name
        if tool == "git":
            return self.env["SOURCE_TREE" if argv[-1] == "HEAD^{tree}" else "SOURCE_SHA"]
        if tool in ("pkgbuild", "productbuild"):
            if tool == "pkgbuild":
                scripts = Path(argv[argv.index("--scripts") + 1])
                assert all((scripts / name).stat().st_mode & 0o777 == 0o755 for name in ("preinstall", "postinstall"))
            else:
                assert f'hostArchitectures="{self.arch}"' in Path(argv[argv.index("--distribution") + 1]).read_text()
            Path(argv[-1]).write_bytes(b"signed package fixture")
        if tool == "csreq":
            Path(argv[argv.index("-b") + 1]).write_bytes(argv[argv.index("-r") + 1].replace(" ", "").encode())
        if tool == "codesign" and "--display" in argv:
            if "--requirements" in argv:
                return "designated => " + REQUIREMENT
            if "--entitlements" in argv:
                return plistlib.dumps({}).decode()
            return "flags=0x10000(runtime)\nTimestamp=Sep 15, 2026\n"
        if tool == "xcrun" and "notarytool" in argv:
            return json.dumps({"status": self.status, "message": "private diagnostic text"})
        return ""


def execute(signer, candidate, tools=None):
    repo, source, record, env, output = candidate
    tools = tools or NativeTools(env)
    signer.sign_candidate(source, record, "arm64", output, env=env, repo=repo, run=tools)
    return tools


@pytest.mark.parametrize("field,value", [("archive_sha256", "0" * 64), ("source_sha", "c" * 40),
    ("source_tree", "d" * 40), ("architecture", "x86_64"), ("run_id", "124"), ("run_attempt", "3")])
def test_metadata_mismatch_stops_before_signing(signer, candidate, field, value):
    record = candidate[2]
    metadata = json.loads(record.read_text())
    metadata[field] = value
    record.write_text(json.dumps(metadata))
    tools = NativeTools(candidate[3])
    with pytest.raises(signer.SigningError):
        execute(signer, candidate, tools)
    assert not any(Path(argv[0]).name == "codesign" for argv, _ in tools.calls)
    assert not candidate[4].exists()


@pytest.mark.parametrize("entries", [
    [("/outside", b"bad")], [(APP + "/../../outside", b"bad")], [("unexpected/file", b"bad")],
    [(APP + "/escape", (tarfile.SYMTYPE, "../../outside"))],
    [(APP + "/escape", (tarfile.SYMTYPE, "/tmp/outside"))],
    [(APP + "/alias", (tarfile.SYMTYPE, "Contents")), (APP + "/alias/file", b"bad")],
    [(APP + "/alias/file", b"bad"), (APP + "/alias", (tarfile.SYMTYPE, "Contents"))],
    [(APP + "/Alias", (tarfile.SYMTYPE, "Contents")), (APP + "/alias/file", b"bad")],
    [(APP + "/deep/link", (tarfile.SYMTYPE, "..")),
     (APP + "/escape", (tarfile.SYMTYPE, "deep/link/../../outside"))],
    [(APP + "/one", (tarfile.SYMTYPE, "two")), (APP + "/two", (tarfile.SYMTYPE, "one"))],
    [(APP + "/hardlink", (tarfile.LNKTYPE, "../../outside"))],
])
def test_archive_paths_are_rejected_before_any_extraction(signer, tmp_path, entries):
    source, output = tmp_path / "unsafe.tar.gz", tmp_path / "root"
    archive(source, entries)
    with pytest.raises(signer.SigningError):
        signer.extract_archive(source, output, signer.sha256(source))
    assert not output.exists()


@requires_posix_filesystem
def test_signing_is_inside_out_and_publishes_only_verified_sanitized_results(signer, candidate):
    tools = execute(signer, candidate)
    signed = [argv for argv, _ in tools.calls if Path(argv[0]).name == "codesign" and "--sign" in argv]
    depths = [len(Path(argv[-1]).parts) for argv in signed]
    assert depths == sorted(depths, reverse=True)
    assert Path(signed[-1][-1]).name == "Vadgr.app"
    for argv in signed:
        assert "--deep" not in argv
        assert argv[argv.index("--options") + 1] == "runtime"
        assert "--timestamp" in argv
        assert argv[argv.index("--keychain") + 1] == candidate[3]["VADGR_MACOS_KEYCHAIN"]
    assert sum("--entitlements" in argv for argv in signed) == 2
    helper = next(argv for argv in signed if Path(argv[-1]).name == "Vadgr Computer Use.app")
    assert helper[helper.index("--requirements") + 1] == "=designated => " + REQUIREMENT
    for argv, _ in tools.calls:
        if Path(argv[0]).name in ("pkgbuild", "productbuild"):
            assert argv[argv.index("--keychain") + 1] == candidate[3]["VADGR_MACOS_KEYCHAIN"]
    files = sorted(path.name for path in candidate[4].iterdir())
    assert files == ["Vadgr-0.5.0-macos-arm64.pkg", "provenance.json"]
    text = (candidate[4] / files[1]).read_text()
    assert REQUIREMENT not in text and "TESTTEAM00" not in text and str(candidate[0]) not in text
    assert "private diagnostic" not in text
    result = json.loads(text)
    assert result["package_sha256"] == signer.sha256(candidate[4] / files[0])


@requires_posix_filesystem
def test_notary_rejection_publishes_nothing_and_never_staples(signer, candidate):
    tools = NativeTools(candidate[3], "Invalid")
    with pytest.raises(signer.SigningError, match="notarization"):
        execute(signer, candidate, tools)
    assert not candidate[4].exists()
    assert not any("stapler" in argv for argv, _ in tools.calls)


def test_missing_requirement_fails_before_native_operations(signer, candidate):
    candidate[3].pop("MACOS_CUA_REQUIREMENT")
    tools = NativeTools(candidate[3])
    with pytest.raises(signer.SigningError, match="requirement"):
        execute(signer, candidate, tools)
    assert tools.calls == []


def test_non_macos_fork_and_untrusted_runner_are_refused(signer, candidate, monkeypatch):
    for key, value in (("GITHUB_REPOSITORY", "someone/fork"), ("RUNNER_ENVIRONMENT", "self-hosted"),
                       ("GITHUB_EVENT_NAME", "pull_request_target"), ("GITHUB_HEAD_REF", "untrusted")):
        with pytest.raises(signer.SigningError):
            signer.require_runner({**candidate[3], key: value})
    monkeypatch.setattr(signer.sys, "platform", "linux")
    with pytest.raises(signer.SigningError):
        signer.require_runner(candidate[3])


def test_subprocess_failures_never_echo_output_or_arguments(signer, monkeypatch):
    def failed(*args, **kwargs):
        assert kwargs["capture_output"] and kwargs["timeout"]
        return subprocess.CompletedProcess(args[0], 1, "private-owner-path", "private-key-identifier")
    monkeypatch.setattr(signer.subprocess, "run", failed)
    with pytest.raises(signer.SigningError) as result:
        signer.run_tool(["codesign", "private-identity"], "nested signature")
    assert str(result.value) == "nested signature failed"


@requires_posix_filesystem
@pytest.mark.parametrize("candidate", ["x86_64"], indirect=True)
def test_x86_installer_targets_only_its_architecture(signer, candidate):
    repo, source, record, env, output = candidate
    tools = NativeTools(env, arch="x86_64")
    signer.sign_candidate(source, record, "x86_64", output, env=env, repo=repo, run=tools)
    assert (output / "Vadgr-0.5.0-macos-x86_64.pkg").is_file()
    assert all(argv[2] == "x86_64" for argv, _ in tools.calls if Path(argv[0]).name == "lipo")


@requires_posix_filesystem
@pytest.mark.parametrize("failure", ["runtime", "timestamp", "entitlements", "requirement", "staple verification", "installer trust assessment"])
def test_failed_signature_or_post_notary_verification_publishes_nothing(signer, candidate, failure):
    native = NativeTools(candidate[3])
    phases = []
    def run(argv, phase, **kwargs):
        phases.append(phase)
        if phase == failure:
            raise signer.SigningError("verification failed")
        result = native(argv, phase, **kwargs)
        if phase == "signature attributes" and failure == "runtime":
            return result.replace("runtime", "none")
        if phase == "signature attributes" and failure == "timestamp":
            return "flags=0x10000(runtime)\nTimestamp=none\n"
        if phase == "signed entitlements" and failure == "entitlements":
            return plistlib.dumps({"com.apple.security.cs.disable-library-validation": True}).decode()
        if phase == "CUA designated requirement" and failure == "requirement":
            return result.replace("TESTTEAM00", "OTHERTEAM0")
        return result
    with pytest.raises(signer.SigningError):
        execute(signer, candidate, run)
    expected_phase = {"runtime": "signature attributes", "timestamp": "signature attributes",
                      "entitlements": "signed entitlements", "requirement": "CUA designated requirement"}.get(failure, failure)
    assert expected_phase in phases
    assert not candidate[4].exists()


def test_lock_tampering_is_rejected(signer, candidate):
    (candidate[0] / "Cargo.lock").write_text("changed")
    with pytest.raises(signer.SigningError, match="lock"):
        execute(signer, candidate)


def test_checkout_tree_must_match_even_when_metadata_matches(signer, candidate):
    native = NativeTools(candidate[3])
    def run(argv, phase, **kwargs):
        return "c" * 40 if argv[-1] == "HEAD^{tree}" else native(argv, phase, **kwargs)
    with pytest.raises(signer.SigningError, match="checkout"):
        execute(signer, candidate, run)
    assert not any("--sign" in argv for argv, _ in native.calls)


@requires_posix_filesystem
def test_notary_key_must_be_private(signer, candidate):
    Path(candidate[3]["VADGR_NOTARY_KEY_FILE"]).chmod(0o644)
    native = NativeTools(candidate[3])
    with pytest.raises(signer.SigningError, match="credentials"):
        execute(signer, candidate, native)
    assert not any("--sign" in argv for argv, _ in native.calls)


@requires_posix_filesystem
def test_internal_framework_links_and_canonical_cli_link_remain_supported(signer, tmp_path):
    source, output = tmp_path / "links.tar.gz", tmp_path / "root"
    entries = [(APP + "/Contents/Frameworks/Python.framework/Versions/A/Python", b"fixture"),
               (APP + "/Contents/Frameworks/Python.framework/Versions/Current", (tarfile.SYMTYPE, "A")),
               (APP + "/Contents/Frameworks/Python.framework/Python", (tarfile.SYMTYPE, "Versions/Current/Python")),
               ("usr/local/bin/vadgr", (tarfile.SYMTYPE, signer.SHIM_TARGET))]
    archive(source, entries)
    signer.extract_archive(source, output, signer.sha256(source))
    assert (output / APP / "Contents/Frameworks/Python.framework/Python").read_bytes() == b"fixture"
    assert (output / "usr/local/bin/vadgr").readlink() == Path(signer.SHIM_TARGET)


def test_archive_digest_is_rechecked_at_extraction(signer, tmp_path):
    source, output = tmp_path / "changed.tar.gz", tmp_path / "root"
    archive(source, [(APP + "/file", b"fixture")])
    with pytest.raises(signer.SigningError, match="digest"):
        signer.extract_archive(source, output, "0" * 64)
    assert not output.exists()


def test_archive_without_review_is_rejected_before_native_signing(signer, candidate):
    rewrite_candidate_archive(signer, candidate, lambda name, value: (
        None if name.endswith("/package-input-review.json") else (name, value)))
    tools = NativeTools(candidate[3])
    with pytest.raises(signer.SigningError, match="package input"):
        execute(signer, candidate, tools)
    assert not any(Path(argv[0]).name == "codesign" for argv, _ in tools.calls)
    assert not candidate[4].exists()


def rewrite_candidate_archive(signer, candidate, transform, extra=()):
    source, record = candidate[1:3]
    entries = []
    with tarfile.open(source, "r:gz") as current:
        for entry in current.getmembers():
            if entry.isdir():
                continue
            value = ((entry.type, entry.linkname) if entry.issym()
                     else current.extractfile(entry).read())
            changed = transform(entry.name, value)
            if changed is not None:
                entries.append(changed)
    entries.extend(extra)
    archive(source, entries)
    metadata = json.loads(record.read_text())
    metadata["archive_sha256"] = signer.sha256(source)
    record.write_text(json.dumps(metadata))


def test_source_only_review_result_is_not_artifact_verification(signer, candidate, monkeypatch):
    calls = []
    def source_only(resources, repo, version, target, **kwargs):
        calls.append((resources, repo, version, target, kwargs))
        return {"scope": "source-inputs"}
    monkeypatch.setattr(signer, "validate_package_inputs", source_only)
    tools = NativeTools(candidate[3])
    with pytest.raises(signer.SigningError, match="assembled payload"):
        execute(signer, candidate, tools)
    assert len(calls) == 1
    resources, repo, version, target, kwargs = calls[0]
    assert resources.parts[-4:] == ("Applications", "Vadgr.app", "Contents", "Resources")
    assert repo == candidate[0] and version == "0.5.0" and target == "aarch64-apple-darwin"
    assert kwargs == {}
    assert not any(Path(argv[0]).name == "codesign" for argv, _ in tools.calls)


@pytest.mark.parametrize("name", ["legal/TERMS.txt", "legal/TERMS.rtf", "README-OFFLINE.txt",
                                 "sbom/vadgr-0.5.0.spdx.json", "lib/cua/payload.json"])
def test_archive_resource_tampering_fails_with_unchanged_source_review(signer, candidate, name):
    source_inputs = candidate[0] / "packaging/inputs/macos-arm64"
    result = signer.validate_package_inputs(source_inputs, candidate[0], "0.5.0", "aarch64-apple-darwin", source_only=True)
    assert result["scope"] == "source-inputs"
    resource = APP + "/Contents/Resources/" + name
    rewrite_candidate_archive(signer, candidate, lambda path, value: (
        path, value + b" altered" if path == resource else value))
    tools = NativeTools(candidate[3])
    with pytest.raises(signer.SigningError, match="package input"):
        execute(signer, candidate, tools)
    assert not any(Path(argv[0]).name == "codesign" for argv, _ in tools.calls)
    assert not candidate[4].exists()


@pytest.mark.parametrize("field,value", [("status", "draft"), ("synthetic", True),
                                         ("target", "x86_64-apple-darwin"), ("version", "0.5.1")])
def test_unapproved_archive_review_fails_before_codesign(signer, candidate, field, value):
    def change_review(path, content):
        if path.endswith("/package-input-review.json"):
            review = json.loads(content)
            review[field] = value
            content = json.dumps(review).encode()
        return path, content
    rewrite_candidate_archive(signer, candidate, change_review)
    tools = NativeTools(candidate[3])
    with pytest.raises(signer.SigningError, match="package input"):
        execute(signer, candidate, tools)
    assert not any(Path(argv[0]).name == "codesign" for argv, _ in tools.calls)


def test_archive_review_must_be_the_exact_review_from_source(signer, candidate):
    rewrite_candidate_archive(signer, candidate, lambda path, value: (
        path, value + b"\n" if path.endswith("/package-input-review.json") else value))
    tools = NativeTools(candidate[3])
    with pytest.raises(signer.SigningError, match="approved source"):
        execute(signer, candidate, tools)
    assert not any(Path(argv[0]).name == "codesign" for argv, _ in tools.calls)


def test_extra_unreviewed_legal_file_is_rejected(signer, candidate):
    rewrite_candidate_archive(signer, candidate, lambda path, value: (path, value),
                              [(APP + "/Contents/Resources/legal/unreviewed.txt", b"Unreviewed fixture")])
    tools = NativeTools(candidate[3])
    with pytest.raises(signer.SigningError, match="package input"):
        execute(signer, candidate, tools)
    assert not any(Path(argv[0]).name == "codesign" for argv, _ in tools.calls)


def test_current_lock_must_still_match_review_after_provenance_refresh(signer, candidate):
    lock = candidate[0] / "Cargo.lock"
    lock.write_text(lock.read_text() + "\n# Changed fixture lock\n")
    record = candidate[2]
    metadata = json.loads(record.read_text())
    metadata["lock_sha256"]["Cargo.lock"] = signer.sha256(lock)
    record.write_text(json.dumps(metadata))
    tools = NativeTools(candidate[3])
    with pytest.raises(signer.SigningError, match="package input"):
        execute(signer, candidate, tools)
    assert not any(Path(argv[0]).name == "codesign" for argv, _ in tools.calls)


def test_package_review_error_never_echoes_input_contents(signer, tmp_path, monkeypatch):
    def failed(*args, **kwargs):
        raise signer.PackageInputError("private-input-value")
    monkeypatch.setattr(signer, "validate_package_inputs", failed)
    with pytest.raises(signer.SigningError) as result:
        signer.validate_package_review(tmp_path, tmp_path, "arm64")
    assert str(result.value) == "package input review failed"


@requires_posix_filesystem
@pytest.mark.parametrize("relative", ["packaging/inputs", "packaging/inputs/macos-arm64"])
def test_source_review_parent_cannot_redirect_to_another_directory(signer, candidate, relative):
    original = candidate[0] / relative
    outside = candidate[0].parent / "redirected-inputs"
    original.rename(outside)
    original.symlink_to(outside, target_is_directory=True)
    tools = NativeTools(candidate[3])
    with pytest.raises(signer.SigningError, match="not package-owned"):
        execute(signer, candidate, tools)
    assert not any(Path(argv[0]).name == "codesign" for argv, _ in tools.calls)
