"""The isolated signing probe has no credentials and never calls a signing service."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_workflow_is_one_exact_branch_and_protected():
    workflow = (ROOT / '.github/workflows/signing-smoke.yml').read_text()
    assert 'signing-smoke-iv-20260916' in workflow
    assert 'environment: release-windows' in workflow
    assert 'github.run_attempt == 1' in workflow
    assert 'persist-credentials: false' in workflow
    assert 'contents: write' not in workflow
    assert 'upload-artifact' not in workflow
    assert 'pull_request' not in workflow
    assert 'tags:' not in workflow


def test_launcher_does_not_call_vendor_main_or_spawn():
    source = (ROOT / 'scripts/signing/SigningSmoke.java').read_text()
    assert 'new CommandLine(new CodeSignTool()).execute' in source
    assert 'CodeSignTool.main' not in source
    assert 'ProcessBuilder' not in source
    assert 'Runtime.getRuntime().exec' not in source
    assert 'System.setOut(sink)' in source
    assert 'System.setErr(sink)' in source
    assert '"-malware_block=true"' in source
    assert 'certificate.checkValidity()' in source
    assert 'EXPECTED_CERT_SHA256' in source
    assert 'isOtpTypeOnline' in source


def test_log_config_has_no_appender():
    config = (ROOT / 'scripts/signing/log4j2-off.xml').read_text()
    assert '<Root level="OFF"' in config
    assert '<RollingFile' not in config
    assert '<Console' not in config


def test_subject_is_compared_before_signing_as_x500_not_display_text():
    java = (ROOT / 'scripts/signing/SigningSmoke.java').read_text()
    shell = (ROOT / 'scripts/signing/smoke.ps1').read_text()
    assert 'new X500Principal(required("EXPECTED_CERT_SUBJECT")).equals(' in java
    assert 'CN=Sample, O=Sample, C=CO' in java
    assert '$cert.Subject -ne $env:EXPECTED_CERT_SUBJECT' not in shell


def test_inspect_workflow_never_receives_totp_or_sign_mode():
    workflow = (ROOT / '.github/workflows/signing-smoke.yml').read_text()
    assert 'ES_TOTP_SECRET' not in workflow
    assert '-Mode sign' not in workflow


def test_java_pin_uses_supported_three_component_version():
    workflow = (ROOT / '.github/workflows/signing-smoke.yml').read_text()
    assert "java-version: '17.0.20+8'" in workflow
    assert '17.0.20.1+1' not in workflow


def test_shell_never_substitutes_secrets_into_commands():
    script = (ROOT / 'scripts/signing/smoke.ps1').read_text()
    assert '-password=' not in script
    assert '-totp_secret=' not in script
    assert '-username=' not in script
    assert 'Get-AuthenticodeSignature' in script
    assert 'verify /pa /all /tw' in script
    assert 'TimeStamperCertificate' in script
