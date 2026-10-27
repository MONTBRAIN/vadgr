"""Source facts must preserve uncertainty and reject mismatched upstream bytes."""

from copy import deepcopy
import io
import tarfile

import pytest

from scripts import windows_runtime_source_scope as scope
from scripts.validate_package_inputs import PackageInputError


def archive(files):
    out = io.BytesIO()
    with tarfile.open(fileobj=out, mode="w:xz") as tar:
        for name, raw in files.items():
            member = tarfile.TarInfo(name)
            member.size = len(raw)
            tar.addfile(member, io.BytesIO(raw))
    return out.getvalue()


@pytest.fixture
def pillow(monkeypatch):
    prefix = "pillow-12.3.0/"
    files = {
        "pyproject.toml": b'[build-system]\nrequires=["pybind11"]\n',
        "setup.py": b'from pybind11.setup_helpers import ParallelCompile\nParallelCompile("MAX_CONCURRENCY", default).install()\n',
        "src/_imagingft.c": b'#include "thirdparty/pythoncapi_compat.h"\nhave_raqm = !!p_fribidi;\n',
        "src/_imagingcms.c": b'vn = cmsGetEncodedCMMversion();\n',
        "src/thirdparty/pythoncapi_compat.h": b'synthetic header\n',
        "src/thirdparty/fribidi-shim/fribidi.c": b'synthetic loader\n',
    }
    raw = archive({prefix + name: data for name, data in files.items()})
    monkeypatch.setattr(scope, "PILLOW_SHA256", scope.sha256_bytes(raw))
    record = {"target": "x86_64-pc-windows-msvc", "pillow": {"probe": {"pillow": "12.3.0"},
        "files": {"PIL/_imagingft.cp312-win_amd64.pyd": scope.identity(b"native bytes")}}}
    catalogue = {"metadata": {"component": {"version": "12.3.0"}}, "components": [
        {"bom-ref": "pkg:github/python/pythoncapi-compat", "hashes": [{"alg": "SHA-256", "content": scope.sha256_bytes(files["src/thirdparty/pythoncapi_compat.h"])}]},
        {"bom-ref": "pkg:pypi/pillow@12.3.0#thirdparty/fribidi-shim", "hashes": [{"alg": "SHA-256", "content": scope.sha256_bytes(files["src/thirdparty/fribidi-shim/fribidi.c"])}]},
        {"bom-ref": "pkg:pypi/pybind11", "scope": "excluded", "description": "build-time dependency"}]}
    return record, catalogue, raw


def test_pillow_source_separates_header_helper_and_unresolved_loader(pillow):
    result = scope.pillow_source_scope(*pillow)
    rows = result["components"]
    assert rows["pkg:pypi/pybind11"]["classification"] == "upstream-declared-build-only-compilation-helper"
    assert rows["pkg:github/python/pythoncapi-compat"]["classification"] == "source-header-relevant-to-installed-font-extension"
    assert rows["pkg:pypi/pillow@12.3.0#thirdparty/fribidi-shim"]["classification"] == "conditional-native-loader-needs-build-or-symbol-evidence"
    assert "remains a source/build identity question" in result["littlecms_version_boundary"]
    assert result["candidate_approval"] is False
    assert all(row["sha256"] == scope.sha256_bytes(row["text"].encode()) for row in result["reviewed_source_files"].values())


@pytest.mark.parametrize("defect", ["archive", "version", "hash", "scope", "native-missing", "duplicate"])
def test_pillow_rejects_unbound_source_scope(pillow, defect):
    record, catalogue, raw = deepcopy(pillow)
    if defect == "archive":
        raw += b"changed"
    elif defect == "version":
        record["pillow"]["probe"]["pillow"] = "12.2.0"
    elif defect == "hash":
        catalogue["components"][0]["hashes"][0]["content"] = "0" * 64
    elif defect == "scope":
        catalogue["components"][2]["scope"] = "required"
    elif defect == "native-missing":
        record["pillow"]["files"] = {}
    else:
        catalogue["components"].append(catalogue["components"][0])
    with pytest.raises(PackageInputError):
        scope.pillow_source_scope(record, catalogue, raw)


@pytest.fixture
def rust():
    prefix = "rust-src-fixture/rust-src/lib/rustlib/src/rust/library/"
    files = {
        prefix + "std/Cargo.toml": b'[package]\nname="std"\nversion="0.0.0"\nlicense="MIT OR Apache-2.0"\n[dependencies]\ncompiler_builtins={path="../compiler-builtins/compiler-builtins"}\n[target.\'cfg(unix)\'.dependencies]\nlibc="1"\n[target.\'cfg(windows)\'.dependencies]\nwindows-link="1"\n',
        prefix + "compiler-builtins/compiler-builtins/Cargo.toml": b'[package]\nname="compiler_builtins"\nversion="0.1.0"\nlicense="Apache-2.0 WITH LLVM-exception"\n',
        prefix + "compiler-builtins/builtins-shim/Cargo.toml": b'[package]\nname="compiler_builtins"\nversion="0.1.0"\nlicense="Apache-2.0 WITH LLVM-exception"\n',
    }
    raw = archive(files)
    manifest = ('[pkg.rust-src.target."*"]\navailable=true\nxz_url="https://static.rust-lang.org/dist/rust-src-fixture.tar.xz"\nxz_hash="' + scope.sha256_bytes(raw) + '"\n').encode()
    record = {"target": "aarch64-pc-windows-msvc"}
    binding = {"library_scope": {name: {"identity": scope.identity(name.encode()), "referenced_by": refs}
        for name, refs in (("libstd-aaa.rlib", ["payload/vadgr.exe"]), ("libstd-aaa.rmeta", []),
                           ("std-aaa.dll", []), ("libcompiler_builtins-bbb.rlib", ["payload/vadgr.exe"]))}}
    return record, binding, manifest, raw


def test_rust_maps_metadata_and_code_to_exact_manifests_without_absence_claims(rust):
    result = scope.rust_source_scope(*rust)
    assert len(result["libraries"]) == 4
    assert len(result["source_manifests"]) == 2
    compiler = result["libraries"]["libcompiler_builtins-bbb.rlib"]
    assert compiler["source_manifest"]["path"].endswith("compiler-builtins/compiler-builtins/Cargo.toml")
    assert compiler["license_declared"] == "Apache-2.0 WITH LLVM-exception"
    dependencies = {row["name"]: row for row in result["libraries"]["libstd-aaa.rlib"]["dependencies"]}
    assert dependencies["libc"]["target_predicate_matches"] is False
    assert dependencies["windows-link"]["target_predicate_matches"] is True
    assert result["libraries"]["std-aaa.dll"]["referenced_by"] == []
    assert result["candidate_approval"] is False and "No absence" in result["limitation"]


@pytest.mark.parametrize("defect", ["hash", "unavailable", "unmapped", "name", "ambiguous", "host"])
def test_rust_rejects_changed_or_ambiguous_source(rust, defect):
    record, binding, manifest, raw = deepcopy(rust)
    if defect == "hash":
        raw += b"changed"
    elif defect == "unavailable":
        manifest = manifest.replace(b"available=true", b"available=false")
    elif defect == "unmapped":
        binding["library_scope"]["libunknown-aaa.rlib"] = {}
    elif defect == "name":
        binding["library_scope"]["unknown.ext"] = {}
    elif defect == "host":
        manifest = manifest.replace(b"https://static.rust-lang.org/dist/", b"https://example.invalid/")
    else:
        files = scope.archive_members(raw, scope.sha256_bytes(raw))
        path = next(name for name in files if name.endswith("std/Cargo.toml"))
        files[path] = b'[package]\nname="std"\nversion="0.0.0"\n'
        new = archive(files)
        manifest = manifest.replace(scope.sha256_bytes(raw).encode(), scope.sha256_bytes(new).encode())
        raw = new
    with pytest.raises(PackageInputError):
        scope.rust_source_scope(record, binding, manifest, raw)


def test_source_archive_rejects_links_aliases_and_traversal():
    for names in (("x/a", "x/A"), ("../outside",)):
        raw = archive({name: b"x" for name in names})
        with pytest.raises(PackageInputError):
            scope.archive_members(raw, scope.sha256_bytes(raw))
    out = io.BytesIO()
    with tarfile.open(fileobj=out, mode="w") as tar:
        item = tarfile.TarInfo("x/link")
        item.type = tarfile.SYMTYPE
        item.linkname = "target"
        tar.addfile(item)
    raw = out.getvalue()
    with pytest.raises(PackageInputError):
        scope.archive_members(raw, scope.sha256_bytes(raw))
