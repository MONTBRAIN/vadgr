"""Precondition: source checkout only; never authenticates or requests a signature."""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[2]


class ReleaseSigning(unittest.TestCase):
    def test_credentials_are_only_in_sign_steps(self):
        workflow = (ROOT / '.github/workflows/candidate.yml').read_text()
        steps = workflow.split('      - name: ')
        secret_steps = [step for step in steps if 'secrets.ES_PASSWORD' in step]
        self.assertEqual(len(secret_steps), 5)
        for step in secret_steps:
            self.assertIn('release.ps1 -Mode sign', step)
            self.assertIn('-Authorization authorization.json', step)
            self.assertIn('-Qualification qualification.json', step)
            self.assertIn('-Claim claim.json', step)
            self.assertNotIn('dotnet build', step)
            self.assertNotIn('cargo rustc', step)
        self.assertNotIn('$signTool sign', workflow)
        self.assertNotIn('Cert:\\CurrentUser\\My', workflow)

    def test_launcher_stays_in_process_and_pins_endpoints(self):
        source = (ROOT / 'scripts/signing/CodeSignRunner.java').read_text()
        self.assertNotIn('ProcessBuilder', source)
        self.assertNotIn('Runtime.getRuntime', source)
        self.assertLess(source.index('System.setErr(sink)'), source.index('new AccessToken'))
        self.assertIn('"-malware_block=true"', source)
        self.assertIn('SIGNING_INPUT', source)
        self.assertIn('https://cs.ssl.com', source)

    def test_one_shot_ledger_and_independent_verifier(self):
        source = (ROOT / 'scripts/signing/release.ps1').read_text()
        self.assertIn("$env:GITHUB_RUN_ATTEMPT -ne '1'", source)
        self.assertIn("$env:GITHUB_REF_TYPE -ne 'branch'", source)
        self.assertIn("$env:GITHUB_REF -ne 'refs/heads/master'", source)
        self.assertIn('candidate_claims.py', source)
        self.assertLess(source.index('Reserve-Attempt $relative $inputHash'), source.index("Invoke-Wrapper 'sign'"))
        self.assertIn('verify /pa /all /tw /v', source)
        self.assertIn('TimeStamperCertificate', source)
        self.assertIn('SHA256', source)
        self.assertIn('Thumbprint', source)

    def test_python_extensions_keep_one_attempt_and_restore_their_name(self):
        source = (ROOT / 'scripts/signing/release.ps1').read_text()
        self.assertIn("'python-extension.dll'", source)
        self.assertIn('Move-Item -LiteralPath $signed -Destination $restoredName', source)
        self.assertEqual(source.count("Invoke-Wrapper 'sign'"), 1)

    def test_metadata_verification_requires_bound_sha256_rfc3161(self):
        source = (ROOT / 'scripts/signing/CodeSignRunner.java').read_text()
        self.assertIn('SPC_RFC3161_OBJID', source)
        self.assertIn('getMessageImprintDigest()', source)
        self.assertIn('digest(signer.getSignature())', source)
        self.assertLess(source.index('equals("verify-metadata")'), source.index('String username'))


if __name__ == '__main__':
    unittest.main()
