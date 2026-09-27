"""Synthetic extraction records exercise byte binding, not a real package build."""

from copy import deepcopy
import os
import re
import subprocess

import pytest

from scripts import windows_wix_evidence as wix
from scripts.candidate_artifacts import Refused
from scripts.synthesize_windows_legal import Packet, synthesize
from scripts.validate_package_inputs import PackageInputError


def pe(architecture, suffix):
    raw = bytearray(128)
    raw[:2] = b"MZ"
    raw[0x3c:0x40] = (64).to_bytes(4, "little")
    raw[64:68] = b"PE\0\0"
    raw[68:70] = {"x64": 0x8664, "arm64": 0xaa64}[architecture].to_bytes(2, "little")
    return bytes(raw) + suffix


@pytest.fixture(params=["x64", "arm64"])
def extracted(tmp_path, request):
    architecture = request.param
    root, observed = tmp_path / "extraction", tmp_path / "observed"
    root.mkdir()
    observed.mkdir()

    def put(name, raw):
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(raw)
        return wix.file_record(raw)

    observation = {"schema": 1, **wix.BOUNDARY, "architecture": architecture,
                   "target": wix.TARGETS[architecture], "files": {}}
    refs = []
    for name, raw, identifier in (
        ("payload/vadgr.exe", pe(architecture, b"backend"), "VadgrBackendFile"),
        ("payload/vadgr-app.exe", pe(architecture, b"console"), "VadgrApplicationFile"),
        ("payload/lib/data.txt", b"observed private payload", wix.wix_id("payload", "PrivatePayload/data.txt")),
    ):
        target = "msi/File/" + identifier
        observation["files"][name] = put(target, raw)
        refs.append(f'<File Id="{identifier}" Source="{target}"/>')
    observation["files"]["ba-functions.dll"] = put("ba/ba-functions.dll", pe(architecture, b"functions"))
    for kind, name, path in (("msi", "utilca.dll", "msi/Binary/util"),
                              ("bundle", "wixstdba.exe", "ba/wixstdba.exe")):
        identity = put(path, pe(architecture, name.encode()))
        put(f"wix-vendor-{kind}.json", wix.canonical_json({"schema": 1, "wix_version": "7.0.0",
            "name": name, "architecture": architecture, **identity,
            "status": "not-signature-qualified"}))
    refs.append('<Binary Id="util" SourceFile="msi/Binary/util"/>')
    put("msi.wxs", ('<Wix xmlns="http://wixtoolset.org/schemas/v4/wxs"><Package>'
                    + ''.join(refs) + '</Package></Wix>').encode())
    put("ba/theme.xml", b"synthetic theme")
    names = wix.package_names(architecture)
    msi = bytes.fromhex("d0cf11e0a1b11ae1") + b"synthetic unsigned MSI"
    put(names["msi"], msi)
    put(names["bundle"], pe(architecture, b"synthetic unsigned bundle"))
    put("burn-engine.exe", pe(architecture, b"synthetic unsigned engine"))
    put("containers/attached/" + names["msi"], msi)
    put("ba/manifest.xml", (f'<BurnManifest xmlns="{wix.BURN_NAMESPACE[1:-1]}">'
        '<UX PrimaryPayloadId="ba">'
        '<Payload Id="ba" FilePath="wixstdba.exe" SourcePath="u0"/>'
        '<Payload Id="functions" FilePath="ba-functions.dll" SourcePath="u1"/>'
        '<Payload Id="theme" FilePath="theme.xml" SourcePath="u2"/>'
        f'</UX><Payload Id="msi" FilePath="{names["msi"]}" FileSize="{len(msi)}"'
        ' Packaging="embedded" SourcePath="a0" Container="attached"/></BurnManifest>').encode())
    (observed / "preparation-observation.json").write_bytes(wix.canonical_json(observation))
    tool_files = {"wix.exe": wix.file_record(b"synthetic tool, never executed")}

    def seal():
        record = {"schema": 1, **wix.BOUNDARY, "architecture": architecture,
            "preparation_observation_sha256": wix.sha256_bytes((observed / "preparation-observation.json").read_bytes()),
            "commands": wix.extraction_commands(architecture),
            "tool": {"version": "7.0.0+fixture", "files": tool_files,
                     "files_sha256": wix.sha256_bytes(wix.canonical_json(tool_files))},
            "membership": wix.classify(root, observation, architecture), "files": wix.inventory(root)}
        raw = wix.canonical_json(record)
        put(wix.RECORD, raw)
        return record, wix.sha256_bytes(raw)

    record, digest = seal()
    return root, observed, architecture, observation, record, digest, put, seal


def test_unsigned_membership_is_complete_deterministic_and_data_only(extracted, monkeypatch):
    root, observed, architecture, observation, record, digest, _, seal = extracted
    monkeypatch.setattr(subprocess, "run", lambda *args, **kwargs: pytest.fail("validator executed output"))
    monkeypatch.setattr(subprocess, "check_output", lambda *args, **kwargs: pytest.fail("validator executed output"))
    assert wix.validate(root, observed, architecture, digest) == record
    assert seal()[1] == digest
    assert len(record["membership"]["members"]) == 9
    assert len(record["membership"]["burn_manifest_members"]) == 4
    assert record["membership"]["candidate_approval"] is False
    observation["files"] = dict(reversed(list(observation["files"].items())))
    assert wix.classify(root, observation, architecture) == record["membership"]


def test_actual_wix_source_directory_prefix_maps_to_the_selected_extraction_root(extracted):
    root, _, architecture, observation, record, _, _, _ = extracted
    path = root / "msi.wxs"
    path.write_bytes(path.read_bytes().replace(b'="msi/', b'="SourceDir/'))
    assert wix.classify(root, observation, architecture) == record["membership"]


@pytest.mark.parametrize("defect", ["digest", "approval", "observation", "commands", "tool-empty", "tool-hash",
    "tool-alias", "tool-path", "tool-identity", "membership", "extra-evidence", "changed-package"])
def test_import_rejects_changed_record_or_retained_bytes(extracted, defect):
    root, observed, architecture, _, record, digest, put, _ = extracted
    if defect == "digest":
        digest = "0" * 64
    elif defect == "approval":
        record["candidate_approval"] = True
    elif defect == "observation":
        (observed / "preparation-observation.json").write_bytes(b"{}")
    elif defect == "commands":
        record["commands"][0].append("different")
    elif defect.startswith("tool-"):
        files = record["tool"]["files"]
        if defect == "tool-empty":
            files.clear()
        elif defect == "tool-alias":
            files["WIX.EXE"] = files["wix.exe"]
        elif defect == "tool-path":
            files["../other"] = files["wix.exe"]
        elif defect == "tool-identity":
            files["wix.exe"]["size"] = -1
        record["tool"]["files_sha256"] = "0" * 64 if defect == "tool-hash" else wix.sha256_bytes(wix.canonical_json(files))
    elif defect == "membership":
        record["membership"]["members"].pop()
    elif defect == "extra-evidence":
        put("unrecorded.txt", b"extra")
    else:
        put(wix.package_names(architecture)["bundle"], pe(architecture, b"different"))
    if defect not in {"digest", "observation", "extra-evidence", "changed-package"}:
        raw = wix.canonical_json(record)
        put(wix.RECORD, raw)
        digest = wix.sha256_bytes(raw)
    with pytest.raises(PackageInputError):
        wix.validate(root, observed, architecture, digest)


@pytest.mark.parametrize("defect", ["target", "payload-omission", "payload-hash", "payload-extra", "native-unknown",
    "native-duplicate", "architecture", "attached-hash", "attached-extra", "ux-extra", "ux-omission",
    "ux-duplicate", "ux-escape", "ux-primary", "manifest-package", "manifest-size", "xml-dtd", "msi-alias", "msi-escape"])
def test_recomputed_membership_rejects_incomplete_or_unmapped_extraction(extracted, defect):
    root, _, architecture, observation, _, _, put, _ = extracted
    if defect == "target":
        observation["target"] = "wrong-target"
    elif defect == "payload-omission":
        path = root / "msi.wxs"
        path.write_bytes(path.read_bytes().replace(b'Id="VadgrBackendFile"', b'Id="unmapped"'))
    elif defect == "payload-hash":
        put("msi/File/VadgrBackendFile", pe(architecture, b"different"))
    elif defect == "payload-extra":
        put("msi/extra", b"undeclared data")
    elif defect in {"native-unknown", "native-duplicate", "architecture"}:
        value = pe(architecture, b"unknown") if defect == "native-unknown" else (root / "ba/wixstdba.exe").read_bytes()
        if defect == "architecture":
            value = pe("arm64" if architecture == "x64" else "x64", b"wrong architecture")
        put("ba/theme.xml", value)
    elif defect == "attached-hash":
        put("containers/attached/" + wix.package_names(architecture)["msi"], b"different")
    elif defect == "attached-extra":
        put("containers/another", b"extra")
    elif defect == "ux-extra":
        put("ba/unrecorded.txt", b"extra")
    elif defect == "ux-omission":
        (root / "ba/theme.xml").unlink()
    elif defect.startswith("ux-") or defect.startswith("manifest-"):
        path = root / "ba/manifest.xml"
        raw = path.read_bytes()
        changes = {"ux-duplicate": (b'FilePath="theme.xml"', b'FilePath="wixstdba.exe"'),
            "ux-escape": (b'FilePath="theme.xml"', b'FilePath="../theme.xml"'),
            "ux-primary": (b'PrimaryPayloadId="ba"', b'PrimaryPayloadId="missing"'),
            "manifest-package": (b'Packaging="embedded"', b'Packaging="external"'),
            "manifest-size": (b'FileSize="30"', b'FileSize="1"')}
        if defect == "manifest-size":
            raw = re.sub(rb'FileSize="[0-9]+"', b'FileSize="1"', raw)
        else:
            raw = raw.replace(*changes[defect])
        path.write_bytes(raw)
    else:
        path = root / "msi.wxs"
        raw = path.read_bytes()
        if defect == "xml-dtd":
            raw = b'<!DOCTYPE Wix [<!ENTITY x "evil">]>' + raw
        elif defect == "msi-alias":
            raw = raw.replace(b'</Package>', b'<Icon Id="alias" SourceFile="msi/Binary/util"/></Package>')
        else:
            raw = raw.replace(b'SourceFile="msi/Binary/util"', b'SourceFile="../outside"')
        path.write_bytes(raw)
    with pytest.raises((PackageInputError, Refused)):
        wix.classify(root, observation, architecture)


def test_packet_import_does_not_approve_or_clear_source_duties(extracted):
    root, observed, architecture, _, _, digest, _, _ = extracted
    packet = Packet()
    mapping = {"schema": 1, **wix.BOUNDARY, "packages": [
        {"id": "framework-wixtoolset." + name + "-7.0.0", "source_commit": wix.SOURCE_REVISION,
         "included_source_sha256": wix.SOURCE_SHA256} for name in ("sdk", "bal.wixext", "util.wixext")]}
    packet.put("wix-source-mapping.json", wix.canonical_json(mapping))
    packet.pending.append({"id": "wix", "items": ["source-duties", "modifications", "official-build-terms"]})
    before = deepcopy(packet.pending)
    for identifier in ["native-wix", *(row["id"] for row in mapping["packages"])]:
        packet.pending.append({"id": identifier, "items": ["target-binary-to-source-mapping", "notice-and-source-duty"]})
        packet.evidence.append({"id": identifier, "scope": "not-yet-mapped"})
    wix.retain_in_packet(packet, root, observed, architecture, digest)
    assert packet.pending[0] == before[0]
    assert all(row["items"] == ["WiX-source-completeness-and-modification-review", "notice-and-source-duty"]
               for row in packet.pending[1:])
    assert all(row["native_runtime_observation"]["source_archive_sha256"] == wix.SOURCE_SHA256
               for row in packet.evidence)
    assert packet.files["wix-source-mapping.json"] == wix.canonical_json(mapping)
    result = wix.parse_json(packet.files["wix-runtime-membership.json"])
    assert result["candidate_approval"] is False
    assert result["runtime_membership_observation_sha256"] == digest
    assert packet.files["producer-evidence/" + wix.RECORD] == (root / wix.RECORD).read_bytes()
    mapping["packages"][0]["source_commit"] = "0" * 40
    packet.files["wix-source-mapping.json"] = wix.canonical_json(mapping)
    with pytest.raises(PackageInputError, match="source package mapping"):
        wix.retain_in_packet(packet, root, observed, architecture, digest)


@pytest.mark.parametrize("root,digest", [(None, "0" * 64), ("retained", None)])
def test_synthesis_requires_wix_root_and_independent_digest_together(root, digest):
    with pytest.raises(PackageInputError, match="independent digest"):
        synthesize(None, None, "x64", None, None, None, {}, root, digest)


@pytest.mark.skipif(os.name != "nt", reason="capture requires native Windows")
@pytest.mark.parametrize("defect", [None, "credentials", "overlap", "tool-digest", "tool-changed", "command-failed"])
def test_capture_executes_only_pinned_extractor_and_retains_replayable_record(extracted, monkeypatch, defect):
    root, observed, architecture, _, _, _, _, _ = extracted
    tool_root = root.parent / "tool"
    tool_root.mkdir()
    (tool_root / "wix.exe").write_bytes(b"synthetic extractor, never executed")
    tool_digest = wix.sha256_bytes(wix.canonical_json({"wix.exe": wix.file_record((tool_root / "wix.exe").read_bytes())}))
    output = root.parent / "capture"
    for name in ("GH_TOKEN", "GITHUB_TOKEN", "ES_USERNAME", "ES_PASSWORD", "ES_TOTP_SECRET", "ACTIONS_ID_TOKEN_REQUEST_TOKEN"):
        monkeypatch.delenv(name, raising=False)
    if defect == "credentials":
        monkeypatch.setenv("GH_TOKEN", "synthetic-test-only")
    elif defect == "overlap":
        output = observed / "capture"
    elif defect == "tool-digest":
        tool_digest = "0" * 64
    calls = []

    def version(command, **kwargs):
        assert command == [str(tool_root / "wix.exe"), "--version"]
        return "7.0.0+fixture\n"

    def run(command, **kwargs):
        assert command[0] == str(tool_root / "wix.exe")
        assert kwargs["cwd"] == output
        calls.append(command[1:])
        assert (output / command[-1]).is_dir()
        assert command[1:3] == ["-acceptEula", "wix7"]
        if command[3:5] == ["msi", "decompile"]:
            names = ["msi.wxs", *("msi/" + name for name in wix.tree(root / "msi"))]
        elif command[3:5] == ["burn", "extract"]:
            names = [directory + "/" + name for directory in ("ba", "containers") for name in wix.tree(root / directory)]
        else:
            assert command[3:5] == ["burn", "detach"]
            names = ["burn-engine.exe"]
        for name in names:
            target = output / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes((root / name).read_bytes())
        if defect == "tool-changed":
            (tool_root / "wix.exe").write_bytes(b"changed")
        return subprocess.CompletedProcess(command, 1 if defect == "command-failed" else 0, b"synthetic extraction log\n", b"")

    monkeypatch.setattr(subprocess, "check_output", version)
    monkeypatch.setattr(subprocess, "run", run)
    if defect:
        with pytest.raises(PackageInputError):
            wix.capture(root, observed, architecture, tool_root, tool_digest, output)
        assert not (output / wix.RECORD).exists()
    else:
        digest = wix.capture(root, observed, architecture, tool_root, tool_digest, output)
        assert calls == wix.extraction_commands(architecture)
        record = wix.validate(output, observed, architecture, digest)
        assert record["candidate_approval"] is False
        assert len([name for name in record["files"] if name.endswith(".log")]) == 3
