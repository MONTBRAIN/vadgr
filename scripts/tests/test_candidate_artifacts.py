"""Untrusted build output cannot authorize a privileged signing request."""

import io
from pathlib import Path
import tempfile
import unittest
import zipfile

from scripts import candidate_artifacts as artifacts


class ArchiveTests(unittest.TestCase):
    def setUp(self):
        self.workspace = tempfile.TemporaryDirectory()
        self.addCleanup(self.workspace.cleanup)
        self.archive = Path(self.workspace.name) / "artifact.zip"

    def make_archive(self, members):
        with zipfile.ZipFile(self.archive, "w") as output:
            for name, data in members.items():
                output.writestr(name, data)

    def test_reject_case_collision_and_traversal(self):
        for names in ({"payload/A.exe": b"a", "payload/a.exe": b"b"},
                      {"payload/../escape": b"a"},
                      {"payload/CON.txt": b"a"},
                      {"payload/a:stream": b"a"},
                      {"payload/a$(evil).exe": b"a"},
                      {"payload/a. ": b"a"}):
            with self.subTest(names=names):
                self.make_archive(names)
                with self.assertRaises(artifacts.Refused):
                    artifacts.inspect(self.archive)

    def test_reject_symlink_and_duplicate(self):
        info = zipfile.ZipInfo("payload/lib/escape")
        info.create_system = 3
        info.external_attr = (0o120777 << 16)
        with zipfile.ZipFile(self.archive, "w") as output:
            output.writestr(info, "../outside")
        with self.assertRaises(artifacts.Refused):
            artifacts.inspect(self.archive)
        with zipfile.ZipFile(self.archive, "w") as output:
            output.writestr("TERMS.rtf", b"first")
            output.writestr("TERMS.rtf", b"second")
        with self.assertRaises(artifacts.Refused):
            artifacts.inspect(self.archive)

    def test_reject_zip_bomb_and_unexpected_input(self):
        self.make_archive({"payload/legal/terms.txt": b"A" * 100000})
        with self.assertRaises(artifacts.Refused):
            artifacts.inspect(self.archive, expanded_limit=100)
        self.make_archive({".github/workflows/evil.yml": b"test"})
        with self.assertRaises(artifacts.Refused):
            artifacts.inspect(self.archive)

    def test_read_safe_member_without_executing_it(self):
        self.make_archive({"payload/README-OFFLINE.txt": b"instructions"})
        actual = artifacts.inspect(self.archive)
        self.assertEqual(actual["payload/README-OFFLINE.txt"]["size"], 12)

    def test_signing_budget_includes_every_payload_pe_plus_four(self):
        members = ["payload/vadgr.exe", "payload/vadgr-app.exe",
                   "payload/lib/one.dll", "payload/lib/python.pyd", "ba-functions.dll"]
        self.assertEqual(8, artifacts.operation_budget(members))

    def test_pe_architecture_read_from_header_not_filename(self):
        binary = bytearray(160)
        binary[:2] = b"MZ"
        binary[0x3c:0x40] = (128).to_bytes(4, "little")
        binary[128:132] = b"PE\0\0"
        binary[132:134] = (0x8664).to_bytes(2, "little")
        artifacts.verify_pe(bytes(binary), "x64")
        with self.assertRaises(artifacts.Refused):
            artifacts.verify_pe(bytes(binary), "arm64")


if __name__ == "__main__":
    unittest.main()
