"""License collection preserves evidence without deciding legal obligations."""

import hashlib
import io
from pathlib import Path
import sys
import tarfile

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import collect_legal_sources as collect


def archive(entries):
    stream = io.BytesIO()
    with tarfile.open(fileobj=stream, mode="w:gz") as output:
        for name, data in entries.items():
            member = tarfile.TarInfo(name)
            member.size = len(data)
            output.addfile(member, io.BytesIO(data))
    return stream.getvalue()


def test_archived_notices_and_nested_font_licenses_are_verbatim():
    data = archive({"crate/LICENSE-MIT": b"Copyright A\r\nPermission\r\n",
                    "crate/fonts/OFL.txt": b"Font copyright\n",
                    "crate/vendor/COPYING": b"Native obligations\n",
                    "crate/NOTICE": b"Attribution\n",
                    "crate/src/lib.rs": b"not a license"})
    result = collect.legal_members(data, "crate.tar.gz")
    assert set(result) == {"crate/LICENSE-MIT", "crate/fonts/OFL.txt", "crate/vendor/COPYING", "crate/NOTICE"}
    assert result["crate/LICENSE-MIT"] == b"Copyright A\r\nPermission\r\n"


def test_archive_paths_cannot_escape_or_collide():
    for entries in ({"../LICENSE": b"x"}, {"crate/LICENSE": b"a", "crate/license": b"b"}):
        with pytest.raises(ValueError):
            collect.legal_members(archive(entries), "crate.tar.gz")


def test_changed_cached_archive_is_rejected(tmp_path):
    path = tmp_path / "component.crate"
    path.write_bytes(b"changed")
    with pytest.raises(ValueError, match="digest"):
        collect.verified_archive("https://example.org/component.crate", hashlib.sha256(b"original").hexdigest(), path)


def test_cargo_traversal_excludes_dev_only_dependencies():
    graph = {"root": "root", "nodes": [
        {"id": "root", "deps": [{"pkg": "ship", "dep_kinds": [{"kind": None}]},
                                  {"pkg": "dev", "dep_kinds": [{"kind": "dev"}]}]},
        {"id": "ship", "deps": [{"pkg": "build", "dep_kinds": [{"kind": "build"}]}]},
        {"id": "dev", "deps": []}, {"id": "build", "deps": []}]}
    assert collect.cargo_closure(graph) == {"root", "ship", "build"}


def test_wheel_selection_uses_target_tags_and_locked_hash():
    files = [{"filename": "example-1.0-cp312-cp312-win_amd64.whl", "digests": {"sha256": "a" * 64}},
             {"filename": "example-1.0-cp312-cp312-win_arm64.whl", "digests": {"sha256": "b" * 64}}]
    assert collect.select_wheel(files, {"a" * 64, "b" * 64}, "win_arm64")["filename"].endswith("win_arm64.whl")
    with pytest.raises(ValueError):
        collect.select_wheel(files, {"a" * 64}, "win_arm64")


def test_collection_never_concludes_or_approves_licenses(tmp_path):
    item = collect.record_component(tmp_path, "cargo-example-1.0", "example", "1.0", "cargo",
                                    "https://example.org/source.crate", b"archive", "MIT OR Apache-2.0",
                                    {"example/LICENSE": b"Copyright Example\nMIT terms\n"})
    assert item["license_concluded"] is None
    assert item["review_status"] == "unreviewed"
    assert item["source_files"][0]["sha256"] == hashlib.sha256(b"Copyright Example\nMIT terms\n").hexdigest()


def test_non_ascii_wheel_metadata_remains_json_serializable():
    import json
    result = collect.wheel_license_metadata(b"License: Copyright \xc3\xa9\nClassifier: License :: OSI Approved\n\n")
    assert isinstance(result["license_declared"], str)
    json.dumps(result)


def test_source_commit_is_read_from_the_published_crate():
    import json
    data = archive({"example-1.0/.cargo_vcs_info.json": json.dumps({"git": {"sha1": "a" * 40}, "path_in_vcs": "crates/example"}).encode()})
    assert collect.crate_source_identity(data) == ("a" * 40, "crates/example")


def test_wix_license_can_be_represented_without_approving_it():
    import validate_package_inputs as package
    package.validate_conclusion("MS-RL")


def test_hack_font_license_can_be_represented_without_approving_it():
    import validate_package_inputs as package
    package.validate_conclusion("MIT AND Bitstream-Vera")


def test_nuget_metadata_name_is_case_independent():
    import zipfile
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w") as archive:
        archive.writestr("WixToolset.Sdk.nuspec", b"metadata")
    assert collect.nuget_metadata(stream.getvalue()) == ("WixToolset.Sdk.nuspec", b"metadata")


def test_font_terms_and_embedded_sboms_are_retained():
    data = archive({"crate/fonts/UFL.txt": b"Ubuntu terms", "crate/fonts/Hack-Regular.txt": b"Hack terms",
                    "crate/sboms/native.cdx.json": b"{}"})
    assert len(collect.legal_members(data, "crate.tar.gz")) == 3


@pytest.mark.parametrize("newline", [b"\n", b"\r\n"])
def test_metadata_headers_preserve_license_fields_without_readme_examples(newline):
    headers = newline.join([b"Name: example", b"License: verbatim terms", b"    more terms", b"License-File: LICENSE", b"", b""])
    assert collect.wheel_metadata_headers(headers + b"Unrelated README examples") == headers
