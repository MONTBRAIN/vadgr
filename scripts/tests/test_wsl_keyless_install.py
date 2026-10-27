"""WSL refuses untrusted/downgraded archives before touching the install root."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_sequence_and_archive_verification_precede_extraction_and_activation():
    installer = (ROOT / "install.sh").read_text()
    verifier = (ROOT / "src/bin/vadgr-release-verify.rs").read_text()
    assert "--state-root \"$STATE_HOME\" --artifact \"$ARCHIVE\"" in installer
    assert verifier.index("verified.ensure_sequence(&state_root)?") < verifier.index("validate_tar_gz(&path)?")
    assert installer.index("--state-root \"$STATE_HOME\"") < installer.index("tar -xzf \"$ARCHIVE\"")
    assert installer.index("tar -xzf \"$ARCHIVE\"") < installer.index("mkdir -p \"$VERSIONS\"")


def test_candidate_is_bounded_before_and_after_activation():
    installer = (ROOT / "install.sh").read_text()
    assert 'version_output=$(timeout -k 5s 30s "$PAYLOAD/bin/vadgr" --version)' in installer
    assert installer.index("timeout -k 5s 30s") < installer.index("mv -- \"$PAYLOAD\" \"$staging\"")
    assert installer.count('timeout -k 5s 60s "$CURRENT/bin/vadgr" restart') == 2


def test_unsupported_libc_refused_before_fetch_without_blocking_uninstall():
    installer = (ROOT / "install.sh").read_text()
    assert "getconf GNU_LIBC_VERSION" in installer
    assert "glibc 2.35 or newer" in installer
    assert installer.index("  uninstall)") < installer.index("getconf GNU_LIBC_VERSION")
    assert installer.index("getconf GNU_LIBC_VERSION") < installer.index("fetch release-manifest.json")
