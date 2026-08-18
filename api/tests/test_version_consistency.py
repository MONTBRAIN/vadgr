"""The two daemons and the changelog must agree on the version.

The Python daemon and the Rust daemon serve the same product while the rewrite
is in progress, so `GET /api/health` must report one version regardless of which
half answered. Nothing checked that, and it drifted: the crate moved to `0.4.7`
while `api/config.py` still answered `0.4.5`, and the gap shipped as far as a
pull request caveat before anyone noticed.

The changelog is included because a version that moves without a changelog entry
is the same defect one step earlier.
"""

import re
import pathlib

import pytest

from api.config import settings

REPO = pathlib.Path(__file__).resolve().parents[2]


def crate_version() -> str:
    text = (REPO / "rust" / "Cargo.toml").read_text()
    match = re.search(r'^version\s*=\s*"([^"]+)"', text, re.MULTILINE)
    assert match, "the crate manifest has no top-level version"
    return match.group(1)


def changelog_versions() -> list[str]:
    text = (REPO / "CHANGELOG.md").read_text()
    return re.findall(r"^## \[([0-9]+\.[0-9]+\.[0-9]+)\]", text, re.MULTILINE)


def test_python_daemon_reports_the_crate_version():
    assert settings.version == crate_version(), (
        f"api/config.py serves {settings.version} and the crate serves "
        f"{crate_version()}; a client cannot tell which half answered it"
    )


def test_the_changelog_documents_the_version_being_served():
    versions = changelog_versions()
    assert versions, "the changelog has no released version headings"
    assert settings.version in versions, (
        f"{settings.version} is served but has no changelog entry"
    )


def test_the_changelog_leads_with_the_current_version():
    assert changelog_versions()[0] == settings.version, (
        "the newest changelog entry is not the version being served"
    )
