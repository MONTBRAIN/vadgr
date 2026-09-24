"""Local manifest builder checks; no credentials, network or signing required."""

import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/build_release_manifest.py"
SPEC = importlib.util.spec_from_file_location("release_manifest", SCRIPT)
BUILDER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(BUILDER)


class KeylessManifest(unittest.TestCase):
    def test_final_artifact_bytes_and_keyless_rules_are_deterministic(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            artifacts = root / "artifacts"
            artifacts.mkdir()
            for name in BUILDER.ARTIFACTS:
                (artifacts / name).write_bytes(name.encode())
            terms = root / "terms.txt"
            terms.write_text("Test terms", encoding="utf-8")
            legal = root / "legal"
            legal.mkdir()
            (legal / "TERMS.txt").write_bytes(terms.read_bytes())
            sbom = root / "sbom"
            sbom.mkdir()
            (sbom / "release.json").write_text("{}", encoding="utf-8")
            cua = root / "cua"
            cua.mkdir()
            for name in ("payload.json", "installed-inventory.json"):
                (cua / name).write_text("{}", encoding="utf-8")
            output = root / "manifest.json"
            command = [sys.executable, str(SCRIPT), "--artifacts", str(artifacts),
                       "--target", "windows-x86_64",
                       "--source-commit", "a" * 40, "--terms-version", "1.0",
                       "--terms", str(terms), "--pins", str(ROOT / "packaging/cua/pins.toml"),
                       "--legal-root", str(legal), "--sbom-root", str(sbom),
                       "--cua-records", str(cua),
                       "--output", str(output)]
            subprocess.run(command, check=True, capture_output=True)
            first = output.read_bytes()
            subprocess.run(command, check=True, capture_output=True)
            self.assertEqual(first, output.read_bytes())
            rows = json.loads(first)["artifacts"]
            self.assertEqual(json.loads(first)["legal_hashes"]["legal/TERMS.txt"],
                             hashlib.sha256(terms.read_bytes()).hexdigest())
            self.assertEqual(json.loads(first)["sbom_hashes"]["sbom/release.json"],
                             hashlib.sha256((sbom / "release.json").read_bytes()).hexdigest())
            self.assertEqual(len(rows), 1)
            for row in rows:
                self.assertEqual(row["sha256"], hashlib.sha256(row["name"].encode()).hexdigest())
                self.assertEqual(row["size"], len(row["name"].encode()))
                if row["target"].startswith(("linux-", "wsl-")):
                    self.assertEqual(row["native_signature"], "keyless-manifest")
            self.assertNotIn(b"minisign", first)
            for target in sorted({row[0] for row in BUILDER.ARTIFACTS.values()}):
                command[command.index("--target") + 1] = target
                subprocess.run(command, check=True, capture_output=True)
                selected = json.loads(output.read_bytes())["artifacts"]
                self.assertEqual(len(selected), 1)
                self.assertEqual(selected[0]["target"], target)
            first = output.read_bytes()
            (legal / "TERMS.txt").write_text("Different terms", encoding="utf-8")
            changed = subprocess.run(command, capture_output=True, text=True)
            self.assertNotEqual(changed.returncode, 0)
            self.assertIn("terms checksum", changed.stderr)
            self.assertEqual(output.read_bytes(), first)


if __name__ == "__main__":
    unittest.main()
