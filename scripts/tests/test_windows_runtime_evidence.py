"""Fail-closed data validation for native runtime source-scope observations."""

import json
import io
from pathlib import Path
import subprocess
import tarfile

import pytest

from scripts import windows_runtime_evidence as runtime
from scripts.validate_package_inputs import PackageInputError


@pytest.fixture
def observed(tmp_path):
    def put(name, raw):
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(raw)
        return runtime.file_record(raw)

    payload = runtime.canonical_json({"target": runtime.TARGETS["x64"], "python_version": "3.12.14"})
    put("payload/lib/cua/payload.json", payload)
    pillow = "payload/lib/cua/environments/fixture/Lib/site-packages/PIL/__init__.py"
    files = {pillow: put(pillow, b"__version__ = '12.3.0'\n")}
    manifest = b'[pkg.rust-std.target.x86_64-pc-windows-msvc]\navailable = true\nxz_url = "https://static.rust-lang.org/dist/fixture.tar.xz"\nxz_hash = "' + b"a" * 64 + b'"\n'
    libraries = {"libstd-fixture.rlib": b"synthetic Rust build input"}
    maps = {}
    for executable, name in runtime.LINK_MAPS.items():
        maps[executable] = {"executable": put(executable, b"synthetic unsigned binary"), "path": name,
                            **put(name, b"synthetic link map")}
    record = {"schema": 1, **runtime.BOUNDARY, "architecture": "x64", "target": runtime.TARGETS["x64"],
        "payload_sha256": runtime.sha256_bytes(payload),
        "pillow": {"files": files, "probe_source_sha256": runtime.sha256_bytes(runtime.PILLOW_PROBE.encode()),
            "probe": {"schema": 1, "machine": "AMD64", "python": "3.12.14", "pillow": "12.3.0",
                "groups": {group: {"fixture": {"supported": True, "version": "1.0"}}
                           for group in ("modules", "codecs", "features")}},
            "loaded_modules": [{"scope": "observed-input", "path": "payload/vadgr.exe", **maps["payload/vadgr.exe"]["executable"]}]},
        "rust": {"members": {name: runtime.file_record(raw) for name, raw in libraries.items()},
            "library_archive": put(runtime.RUST_ZIP, runtime.library_zip(libraries)),
            "channel_manifest": put(runtime.RUST_MANIFEST, manifest),
            "target_distribution": runtime.tomllib.loads(manifest.decode())["pkg"]["rust-std"]["target"][runtime.TARGETS["x64"]],
            "compiler_observation": put("rustc-version.txt", b"rustc fixture\n"), "link_maps": maps}}
    put(runtime.RECORD, runtime.canonical_json(record))
    return tmp_path, record, put


def test_validation_is_data_only_and_keeps_build_libraries_inside_zip(observed, monkeypatch):
    root, record, _ = observed
    monkeypatch.setattr(subprocess, "run", lambda *args, **kwargs: pytest.fail("validator executed a process"))
    assert runtime.validate(root, "x64") == record
    assert not list((root / "runtime-evidence").rglob("*.dll"))


@pytest.mark.parametrize("defect", ["approval", "architecture", "probe", "feature", "pillow-omission",
    "pillow-extra", "loaded-hash", "loaded-duplicate", "manifest", "compiler", "map-omission", "map-hash",
    "map-path", "archive-trailer", "archive-member", "archive-alias", "payload-target"])
def test_runtime_evidence_refuses_incomplete_or_changed_bindings(observed, defect):
    root, record, put = observed
    if defect == "approval":
        record["candidate_approval"] = True
    elif defect == "architecture":
        record["architecture"] = "arm64"
    elif defect == "probe":
        record["pillow"]["probe_source_sha256"] = "a" * 64
    elif defect == "feature":
        record["pillow"]["probe"]["groups"]["modules"]["fixture"]["supported"] = "true"
    elif defect == "pillow-omission":
        record["pillow"]["files"] = {}
    elif defect == "pillow-extra":
        put("payload/lib/cua/environments/fixture/Lib/site-packages/PIL/extra.py", b"extra")
    elif defect == "loaded-hash":
        record["pillow"]["loaded_modules"][0]["sha256"] = "a" * 64
    elif defect == "loaded-duplicate":
        record["pillow"]["loaded_modules"] *= 2
    elif defect == "manifest":
        record["rust"]["target_distribution"]["xz_hash"] = "b" * 64
    elif defect == "compiler":
        put("rustc-version.txt", b"changed compiler")
    elif defect == "map-omission":
        del record["rust"]["link_maps"]["ba-functions.dll"]
    elif defect == "map-hash":
        put("link-maps/vadgr.map", b"changed map")
    elif defect == "map-path":
        record["rust"]["link_maps"]["payload/vadgr.exe"]["path"] = "link-maps/vadgr-app.map"
    elif defect == "archive-trailer":
        record["rust"]["library_archive"] = put(runtime.RUST_ZIP, (root / runtime.RUST_ZIP).read_bytes() + b"extra")
    elif defect == "archive-member":
        record["rust"]["members"] = {}
    elif defect == "archive-alias":
        members = {"libstd.rlib": b"one", "LIBSTD.rlib": b"two"}
        record["rust"]["library_archive"] = put(runtime.RUST_ZIP, runtime.library_zip(members))
        record["rust"]["members"] = {name: runtime.file_record(raw) for name, raw in members.items()}
    else:
        payload = runtime.canonical_json({"target": runtime.TARGETS["arm64"], "python_version": "3.12.14"})
        put("payload/lib/cua/payload.json", payload)
        record["payload_sha256"] = runtime.sha256_bytes(payload)
    put(runtime.RECORD, runtime.canonical_json(record))
    with pytest.raises(PackageInputError):
        runtime.validate(root, "x64")


def test_capture_uses_nonmutating_isolated_interpreter_flags():
    source = Path(runtime.__file__).read_text()
    assert '"-I", "-S", "-B", "-c", PILLOW_PROBE' in source
    assert 'require(pillow_tree(raw_root)[1] == pillow_files' in source
    assert '"ACTIONS_ID_TOKEN_REQUEST_TOKEN"' in source


@pytest.mark.parametrize("defect", [None, "source-hash", "member-hash", "map-symbols", "map-format"])
def test_rust_binding_requires_exact_distribution_and_actual_library_symbols(observed, defect):
    root, record, put = observed
    output = io.BytesIO()
    member = "rust-std-fixture/rust-std-x86_64-pc-windows-msvc/lib/rustlib/x86_64-pc-windows-msvc/lib/libstd-fixture.rlib"
    with tarfile.open(fileobj=output, mode="w:xz") as archive:
        info = tarfile.TarInfo(member)
        data = b"synthetic Rust build input"
        info.size = len(data)
        archive.addfile(info, io.BytesIO(data))
        unused = tarfile.TarInfo(member.replace("libstd-fixture.rlib", "libunused-fixture.rlib"))
        unused.size = 4
        archive.addfile(unused, io.BytesIO(b"data"))
        record["rust"]["members"]["libunused-fixture.rlib"] = runtime.file_record(b"data")
    raw = output.getvalue()
    put("fixture.tar.xz", raw)
    component = {"download_location": "https://static.rust-lang.org/dist/fixture.tar.xz", "sha256": runtime.sha256_bytes(raw)}
    record["rust"]["target_distribution"]["xz_hash"] = component["sha256"]
    for row in record["rust"]["link_maps"].values():
        text = b" Address Publics by Value Rva+Base Lib:Object\n 0001:00000000 std_symbol 0000000140001000 f libstd-fixture:std-fixture.rcgu.o\n entry point at 0001:00000000\n"
        if defect == "map-symbols":
            text = text.replace(b"libstd-fixture:", b"unrelated:")
        elif defect == "map-format":
            text = b"not a map"
        row.update(put(row["path"], text))
    if defect == "source-hash":
        component["sha256"] = "b" * 64
    elif defect == "member-hash":
        record["rust"]["members"]["libstd-fixture.rlib"]["sha256"] = "b" * 64
    if defect:
        with pytest.raises(PackageInputError):
            runtime.rust_source_binding(root, record, component, root)
    else:
        binding = runtime.rust_source_binding(root, record, component, root)
        assert binding["candidate_approval"] is False
        assert len(binding["linked"]) == 3
        assert all(list(row["libraries"]) == ["libstd-fixture.rlib"] for row in binding["linked"].values())
        assert binding["library_scope"]["libstd-fixture.rlib"]["classification"] == "observed-public-symbol-reference"
        assert binding["library_scope"]["libunused-fixture.rlib"] == {
            "identity": runtime.file_record(b"data"), "referenced_by": [],
            "classification": "available-build-input-not-observed-in-public-symbol-map"}


@pytest.fixture
def pillow_catalogue(observed):
    _, record, put = observed
    pillow = record["pillow"]
    prefix = next(iter(pillow["files"])).rsplit("/", 1)[0]
    for name in ("_imaging.pyd", "_imagingcms.cp312-win_amd64.pyd", "_imagingtk.pyd"):
        path = prefix + "/" + name
        pillow["files"][path] = put(path, b"synthetic module " + name.encode())
    pillow["loaded_modules"].append({"scope": "observed-input", "path": prefix + "/_imaging.pyd",
                                   **pillow["files"][prefix + "/_imaging.pyd"]})
    pillow["probe"]["groups"]["modules"]["littlecms2"] = {"supported": True, "version": "2.19"}
    pillow["probe"]["groups"]["features"]["raqm"] = {"supported": False, "version": None}
    catalogue = {"metadata": {"component": {"name": "pillow", "version": "12.3.0"}}, "components": [
        {"bom-ref": "PIL._imaging", "name": "PIL._imaging"},
        {"bom-ref": "PIL._imagingcms", "name": "PIL._imagingcms"},
        {"bom-ref": "PIL._imagingtk", "name": "PIL._imagingtk"},
        {"bom-ref": "PIL._missing", "name": "PIL._missing"},
        {"bom-ref": "pkg:generic/littlecms2", "name": "LittleCMS2", "version": "2.19.1"},
        {"bom-ref": "pkg:pypi/pillow@12.3.0#thirdparty/raqm", "name": "raqm", "version": "0.10.5"},
        {"bom-ref": "pkg:generic/pybind11", "name": "pybind11", "version": "3.0.1"}]}
    return record, catalogue


def test_pillow_scope_preserves_unloaded_modules_unsupported_features_and_version_differences(pillow_catalogue):
    record, catalogue = pillow_catalogue
    result = runtime.pillow_scope(record, catalogue)
    rows = {row["name"]: row for row in result["components"]}
    assert rows["PIL._imaging"]["loaded_by_probe"] is True
    for name in ("PIL._imagingcms", "PIL._imagingtk"):
        assert rows[name]["classification"] == "observed-installed-native-module"
        assert rows[name]["loaded_by_probe"] is False
    assert rows["PIL._missing"]["classification"] == "catalogue-module-not-observed"
    assert rows["LittleCMS2"]["native_feature"] == {"supported": True, "version": "2.19"}
    assert rows["LittleCMS2"]["version_matches_declaration"] is False
    assert rows["raqm"]["classification"] == "native-feature-not-supported"
    assert rows["pybind11"]["classification"] == "catalogue-entry-needs-build-scope"
    assert result["candidate_approval"] is False and result["publishable"] is False
    assert len(result["native_members"]) == 3
    catalogue["components"].reverse()
    assert runtime.pillow_scope(record, catalogue) == result


@pytest.mark.parametrize("defect", ["version", "duplicate", "ambiguous-module", "empty", "reference"])
def test_pillow_scope_rejects_ambiguous_catalogues(pillow_catalogue, defect):
    record, catalogue = pillow_catalogue
    if defect == "version":
        catalogue["metadata"]["component"]["version"] = "12.2.0"
    elif defect == "duplicate":
        catalogue["components"].append(catalogue["components"][0])
    elif defect == "ambiguous-module":
        record["pillow"]["files"]["other/PIL/_imaging.pyd"] = runtime.file_record(b"another")
    elif defect == "empty":
        catalogue["components"] = []
    else:
        catalogue["components"][0]["bom-ref"] = ""
    with pytest.raises(PackageInputError):
        runtime.pillow_scope(record, catalogue)
