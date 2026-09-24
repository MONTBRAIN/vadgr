"""Compile only the std-only build selector against isolated synthetic inputs."""

import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest


@unittest.skipUnless(shutil.which("rustc"), "build-selector tests need the Rust compiler")
class BuildPinsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.root = Path(cls.temp.name)
        cls.binary = cls.root / ("build-selector.exe" if os.name == "nt" else "build-selector")
        source = Path(__file__).resolve().parents[2] / "build.rs"
        subprocess.run(["rustc", "--edition=2024", str(source), "-o", str(cls.binary)],
                       check=True, capture_output=True, timeout=60)

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def run_selector(self, *, required=False, target="x86_64-pc-windows-msvc", files=()):
        with tempfile.TemporaryDirectory(dir=self.root) as directory:
            source = Path(directory)
            output = source / "out"
            output.mkdir()
            for name in files:
                path = source / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(b"synthetic input, not an approved runtime")
            environment = {key: value for key, value in os.environ.items()
                           if key != "VADGR_RELEASE_PAYLOAD_BUILD"}
            environment.update(CARGO_MANIFEST_DIR=str(source), TARGET=target, OUT_DIR=str(output))
            if required:
                environment["VADGR_RELEASE_PAYLOAD_BUILD"] = "1"
            result = subprocess.run([str(self.binary)], env=environment, capture_output=True, timeout=10)
            generated = output / "cua_release_pins.rs"
            return result.returncode, generated.read_text() if generated.exists() else ""

    def test_development_compilation_does_not_create_release_pins(self):
        code, generated = self.run_selector()
        self.assertEqual(code, 0)
        self.assertEqual(generated.count("= None;"), 2)

    def test_release_compilation_refuses_missing_or_partial_reviewed_inputs(self):
        self.assertNotEqual(self.run_selector(required=True)[0], 0)
        for name in ("packaging/cua/native-wheel-manifest.json",
                     "packaging/cua/locks/x86_64-pc-windows-msvc.lock"):
            self.assertNotEqual(self.run_selector(files=(name,))[0], 0)

    def test_compiled_inputs_are_selected_for_exact_cargo_target(self):
        names = ("packaging/cua/native-wheel-manifest.json",
                 "packaging/cua/locks/aarch64-pc-windows-msvc.lock")
        code, generated = self.run_selector(required=True, target="aarch64-pc-windows-msvc", files=names)
        self.assertEqual(code, 0)
        self.assertIn("aarch64-pc-windows-msvc.lock", generated)
        self.assertNotIn("x86_64-pc-windows-msvc.lock", generated)
        self.assertNotEqual(self.run_selector(required=True, files=names)[0], 0)


if __name__ == "__main__":
    unittest.main()
