"""Authoring fixtures use temporary directories and never run an installer."""

from pathlib import Path
import re
import xml.etree.ElementTree as ET

import pytest

from scripts.generate_windows_payload_wxs import render, scan


def test_compliance_trees_keep_all_license_and_source_offer_files(tmp_path: Path):
    root = tmp_path / "legal"
    root.mkdir()
    for name in ("TERMS.txt", "LICENSES/component.txt", "SOURCE-OFFERS/component.txt"):
        path = root / name
        path.parent.mkdir(exist_ok=True)
        path.write_text("fixture", encoding="utf-8")
    directories, files = scan(root)
    output = render(root, directories, files, directory_id="LegalFolder", group_id="LegalPayload")
    document = ET.fromstring(output)
    namespace = {"w": "http://wixtoolset.org/schemas/v4/wxs"}
    assert document.find(".//w:DirectoryRef", namespace).get("Id") == "LegalFolder"
    assert len(document.findall(".//w:File", namespace)) == 3
    assert document.find(".//w:ComponentGroup", namespace).get("Id") == "LegalPayload"


def test_same_relative_names_across_payload_groups_have_distinct_identities(tmp_path: Path):
    first = render(tmp_path, [], ["same.txt"], group_id="PrivatePayload")
    second = render(tmp_path, [], ["same.txt"], group_id="LegalPayload")
    first_ids = set(re.findall(r'Id="([^\"]+)"', first))
    second_ids = set(re.findall(r'Id="([^\"]+)"', second))
    assert first_ids & second_ids == {"PrivateLibFolder"}


@pytest.mark.parametrize("name", ["$(sys.CURRENTDIR).txt", "!(bind.evil).txt", "evil;name.txt"])
def test_authoring_refuses_preprocessor_names(tmp_path: Path, name: str):
    (tmp_path / name).write_text("fixture", encoding="utf-8")
    with pytest.raises(SystemExit):
        scan(tmp_path)
