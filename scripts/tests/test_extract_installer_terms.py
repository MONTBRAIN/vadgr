"""Terms extraction must preserve the public block and exclude surrounding notes."""

import importlib.util
from pathlib import Path
import re

import pytest


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "extract_installer_terms.py"


@pytest.fixture
def extractor():
    spec = importlib.util.spec_from_file_location("extract_installer_terms", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def public_terms():
    return (ROOT / "packaging/legal/TERMS.txt").read_bytes()


def test_extracts_complete_public_block_without_surrounding_notes(extractor, public_terms):
    document = (b"# Editorial source\n\nDraft and research notes.\n\n"
                b"## Proposed installer terms\n\nNot approved for release.\n\n"
                + public_terms + b"\n## Acceptance, mechanically\n\nInternal record.\n")
    assert extractor.extract_terms(document) == public_terms
    assert extractor.extract_terms(document.replace(b"\n", b"\r\n")) == public_terms


@pytest.mark.parametrize("mutation", ["missing", "duplicate", "truncated", "internal", "invalid_utf8"])
def test_rejects_ambiguous_incomplete_or_internal_text(extractor, public_terms, mutation):
    document = public_terms + b"\n## End\n"
    if mutation == "missing":
        document = document.replace(b"### Vadgr packaged distribution terms", b"### Other terms")
    elif mutation == "duplicate":
        document += public_terms
    elif mutation == "truncated":
        document = document[:document.index(b"#### 12.")] + b"## End\n"
    elif mutation == "internal":
        document = document.replace(b"**Version 1.0**", b"**Version 1.0**\nDraft: legal review required.")
    else:
        document += b"\xff"
    with pytest.raises(ValueError):
        extractor.extract_terms(document)


def test_public_sources_are_utf8_lf_and_self_contained():
    paths = list((ROOT / "packaging/legal").glob("*.txt"))
    assert {path.name for path in paths} == {
        "TERMS.txt", "LICENSE.txt", "NOTICE.txt", "PRIVACY-NOTICE.txt",
        "SECURITY-AND-PERMISSIONS.txt", "SUPPORT.txt", "UNINSTALL-AND-DATA.txt",
        "README-OFFLINE.txt",
    }
    for path in paths:
        data = path.read_bytes()
        assert not data.startswith(b"\xef\xbb\xbf"), path
        assert b"\r" not in data and data.endswith(b"\n"), path
        text = data.decode("utf-8")
        assert not re.search(r"\b(?:draft|roadmap|runbook|research basis|legal review|"
                             r"engineering note|development phase)\b|D-\d+", text, re.I), path


@pytest.mark.parametrize("name", ["LICENSE", "NOTICE"])
def test_preserves_repository_license_and_notice(name):
    canonical = (ROOT / name).read_bytes().replace(b"\r\n", b"\n")
    assert (ROOT / "packaging/legal" / (name + ".txt")).read_bytes() == canonical


def test_all_twelve_terms_clauses_and_publisher_are_preserved(public_terms):
    text = public_terms.decode("utf-8")
    assert re.findall(r"^#### (\d+)\. ", text, re.M) == [str(n) for n in range(1, 13)]
    assert "Victor Santiago Montaño Díaz" in text
    assert "Pasto, Nariño, Colombia" in text
    assert text.endswith("applies where you live.\n")
