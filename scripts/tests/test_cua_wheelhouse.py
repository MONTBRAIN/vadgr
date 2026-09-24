"""Offline synthetic wheel fixtures, not approved runtime dependencies."""

import hashlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import zipfile

from scripts import cua_wheelhouse as wheels
from scripts.validate_package_inputs import PackageInputError


def wheel_bytes(tag="py3-none-any", extra=None):
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w") as archive:
        archive.writestr("synthetic-1.0.dist-info/METADATA", "Name: synthetic\nVersion: 1.0\n")
        archive.writestr("synthetic-1.0.dist-info/WHEEL", f"Wheel-Version: 1.0\nTag: {tag}\n")
        archive.writestr("synthetic/__init__.py", "# synthetic fixture\n")
        for name, data in (extra or {}).items():
            archive.writestr(name, data)
    return output.getvalue()


class WheelhouseTests(unittest.TestCase):
    def test_compatible_tags_use_native_architecture_and_supported_python(self):
        rows = [("py3-none-any", "aarch64-pc-windows-msvc", True),
                ("cp311-abi3-win_arm64", "aarch64-pc-windows-msvc", True),
                ("cp312-cp312-win_amd64", "aarch64-pc-windows-msvc", False),
                ("cp313-cp313-win_amd64", "x86_64-pc-windows-msvc", False),
                ("cp313-abi3-win_amd64", "x86_64-pc-windows-msvc", False),
                ("cp311-abi3-macosx_13_0_x86_64", "x86_64-apple-darwin", True),
                ("cp311-abi3-macosx_14_0_x86_64", "x86_64-apple-darwin", False),
                ("cp312-cp312-manylinux_2_28_aarch64", "aarch64-unknown-linux-gnu", True),
                ("cp312-cp312-manylinux_2_36_aarch64", "aarch64-unknown-linux-gnu", False),
                ("cp312-cp312-musllinux_1_2_aarch64", "aarch64-unknown-linux-gnu", False)]
        for tag, target, expected in rows:
            with self.subTest(tag=tag, target=target):
                self.assertEqual(wheels.compatible(tag, target), expected)

    def test_wheel_metadata_and_filename_must_agree(self):
        data = wheel_bytes()
        wheels.validate_wheel(data, "synthetic-1.0-py3-none-any.whl", "synthetic", "1.0",
                              "x86_64-pc-windows-msvc")
        for name, target in (("synthetic-1.0-cp312-cp312-win_arm64.whl", "x86_64-pc-windows-msvc"),
                             ("different-1.0-py3-none-any.whl", "x86_64-pc-windows-msvc")):
            with self.subTest(name=name), self.assertRaises(PackageInputError):
                wheels.validate_wheel(data, name, "synthetic", "1.0", target)
        with self.assertRaises(PackageInputError):
            wheels.validate_wheel(wheel_bytes(extra={"../escape": b"bad"}),
                                  "synthetic-1.0-py3-none-any.whl", "synthetic", "1.0",
                                  "x86_64-pc-windows-msvc")

    def test_catalog_selection_uses_only_exact_reviewed_hash(self):
        data = wheel_bytes()
        digest = hashlib.sha256(data).hexdigest()
        row = {"filename": "synthetic-1.0-py3-none-any.whl", "packagetype": "bdist_wheel",
               "digests": {"sha256": digest}, "url": "https://files.pythonhosted.org/synthetic.whl",
               "yanked": False, "size": len(data)}
        with patch.object(wheels, "fetch", side_effect=[json.dumps({"urls": [row]}).encode(), data]):
            name, actual = wheels.upstream_wheel("synthetic", "1.0", digest, "x86_64-pc-windows-msvc")
        self.assertEqual(name, row["filename"])
        self.assertEqual(actual, data)
        with patch.object(wheels, "fetch", return_value=json.dumps({"urls": [row, row]}).encode()), \
             self.assertRaises(PackageInputError):
            wheels.upstream_wheel("synthetic", "1.0", digest, "x86_64-pc-windows-msvc")

    def test_native_member_cannot_hide_behind_compatible_filename(self):
        native = bytearray(64)
        native[:6] = b"\x7fELF\x02\x01"
        native[18:20] = (183).to_bytes(2, "little")
        with self.assertRaises(PackageInputError):
            wheels.validate_wheel(wheel_bytes(extra={"synthetic/native.so": bytes(native)}),
                                  "synthetic-1.0-py3-none-any.whl", "synthetic", "1.0",
                                  "x86_64-pc-windows-msvc")

    def test_legacy_case_in_metadata_directory_is_normalized(self):
        data = io.BytesIO()
        with zipfile.ZipFile(data, "w") as archive:
            archive.writestr("Synthetic-1.0.dist-info/METADATA", "Name: Synthetic\nVersion: 1.0\n")
            archive.writestr("Synthetic-1.0.dist-info/WHEEL", "Wheel-Version: 1.0\nTag: py3-none-any\n")
        wheels.validate_wheel(data.getvalue(), "Synthetic-1.0-py3-none-any.whl", "synthetic", "1.0",
                              "x86_64-pc-windows-msvc")

    def test_candidate_builds_require_reviewed_wheelhouse_before_compilation(self):
        root = Path(__file__).resolve().parents[2]
        for name in ("build-windows.ps1", "build-native.sh"):
            source = (root / "scripts/candidate" / name).read_text()
            self.assertLess(source.index("cua_wheelhouse.py"), source.index("cargo build"))
            self.assertIn("VADGR_RELEASE_PAYLOAD_BUILD", source)
            self.assertIn("--wheelhouse", source)

    def test_failed_materialization_does_not_leave_output(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            output = root / "wheelhouse"
            binding = {"target": "x86_64-pc-windows-msvc", "requirements_sha256": "a" * 64,
                       "wheel_manifest_sha256": "b" * 64}
            with patch.object(wheels.release, "reviewed_inputs", return_value=binding), \
                 patch.object(wheels.release, "verify_origin"), \
                 patch.object(wheels.release, "manifest", return_value=(b"", {"wheels": []})), \
                 patch.object(wheels.release, "selected_lock", return_value={"synthetic": ("1.0", "c" * 64)}), \
                 patch.object(wheels, "read_owned", return_value=b"fixture"), \
                 patch.object(wheels, "upstream_wheel", side_effect=PackageInputError("missing wheel")), \
                 self.assertRaises(PackageInputError):
                wheels.materialize(root, root, binding["target"], output)
            self.assertFalse(output.exists())


if __name__ == "__main__":
    unittest.main()
