"""Compile only the std-only build selector against isolated synthetic inputs."""

import os
import platform
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

    def run_selector(self, *, required=False, target="x86_64-pc-windows-msvc", files=(), profile=None,
                     qualification=False, verifier=False, host=None, identity=None):
        with tempfile.TemporaryDirectory(dir=self.root) as directory:
            source = Path(directory)
            output = source / "out"
            output.mkdir()
            for name in files:
                path = source / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(b"synthetic input, not an approved runtime")
            environment = {key: value for key, value in os.environ.items()
                           if key not in ("VADGR_RELEASE_PAYLOAD_BUILD", "VADGR_RELEASE_PROFILE",
                               "CARGO_FEATURE_LINUX_UNSIGNED_QUALIFICATION", "CARGO_FEATURE_RELEASE_VERIFIER",
                               "VADGR_QUALIFICATION_SOURCE_COMMIT", "VADGR_QUALIFICATION_SOURCE_TREE")}
            environment.update(CARGO_MANIFEST_DIR=str(source), TARGET=target, OUT_DIR=str(output), HOST=host or target)
            if qualification:
                environment["CARGO_FEATURE_LINUX_UNSIGNED_QUALIFICATION"] = "1"
            if verifier:
                environment["CARGO_FEATURE_RELEASE_VERIFIER"] = "1"
            environment.update(identity or {})
            if required:
                environment["VADGR_RELEASE_PAYLOAD_BUILD"] = "1"
            if profile is not None:
                environment["VADGR_RELEASE_PROFILE"] = profile
            result = subprocess.run([str(self.binary)], env=environment, capture_output=True, timeout=10)
            self.last_stdout = result.stdout.decode()
            generated = output / "cua_release_pins.rs"
            return result.returncode, generated.read_text() if generated.exists() else ""

    def test_development_compilation_does_not_create_release_pins(self):
        code, generated = self.run_selector()
        self.assertEqual(code, 0)
        self.assertEqual(generated.count("= None;"), 5)

    def test_release_compilation_refuses_missing_or_partial_reviewed_inputs(self):
        self.assertNotEqual(self.run_selector(required=True)[0], 0)
        for name in ("packaging/cua/native-wheel-manifest.json",
                     "packaging/cua/locks/x86_64-pc-windows-msvc.lock"):
            self.assertNotEqual(self.run_selector(required=True, files=(name,))[0], 0)
        self.assertNotEqual(self.run_selector(files=("packaging/cua/locks/x86_64-pc-windows-msvc.lock",))[0], 0)

    def test_ordinary_unpromoted_targets_compile_without_enabling_payload_assembly(self):
        for target in ("x86_64-unknown-linux-gnu", "aarch64-unknown-linux-gnu",
                       "x86_64-apple-darwin", "aarch64-apple-darwin", "aarch64-pc-windows-msvc"):
            with self.subTest(target=target):
                files = ("packaging/cua/native-wheel-manifest.json",
                         "packaging/cua/locks/x86_64-pc-windows-msvc.lock")
                code, generated = self.run_selector(target=target, files=files)
                self.assertEqual(code, 0)
                self.assertEqual(generated.count("= None;"), 5)
                self.assertIn("const RELEASE_TARGET_UNPROMOTED: bool = true;", generated)
                self.assertNotEqual(self.run_selector(required=True, target=target, files=files)[0], 0)

    def test_compiled_inputs_are_selected_for_exact_cargo_target(self):
        names = ("packaging/cua/native-wheel-manifest.json",
                 "packaging/cua/locks/aarch64-pc-windows-msvc.lock")
        code, generated = self.run_selector(required=True, target="aarch64-pc-windows-msvc", files=names)
        self.assertEqual(code, 0)
        self.assertIn("aarch64-pc-windows-msvc.lock", generated)
        self.assertNotIn("x86_64-pc-windows-msvc.lock", generated)
        self.assertNotEqual(self.run_selector(required=True, files=names)[0], 0)

    def test_profile_cannot_fall_back_to_native_target_lock(self):
        files = ("packaging/cua/native-wheel-manifest.json", "packaging/cua/locks/x86_64-pc-windows-msvc.lock")
        self.assertNotEqual(self.run_selector(profile="windows-x86_64", files=files)[0], 0)
        self.assertNotEqual(self.run_selector(profile="wsl-x86_64", files=files)[0], 0)

    def test_complete_profile_pins_are_embedded_without_runtime_override(self):
        files = ("packaging/cua/native-wheel-manifest.json", "packaging/cua/profile-locks/wsl-aarch64.lock",
                 "packaging/cua/profile-inputs.json", "packaging/cua/cua-profile-catalog.json")
        code, generated = self.run_selector(profile="wsl-aarch64", target="aarch64-unknown-linux-gnu", files=files)
        self.assertEqual(code, 0)
        self.assertIn('const RELEASE_PROFILE: Option<&str> = Some("wsl-aarch64")', generated)
        self.assertIn('profile-locks/wsl-aarch64.lock', generated)
        self.assertIn('cua-profile-catalog.json', generated)
        self.assertNotEqual(self.run_selector(profile="linux-aarch64", target="aarch64-unknown-linux-gnu", files=files)[0], 0)

    def test_qualification_refuses_nonnative_or_missing_identity(self):
        for target, profile, host in (("x86_64-pc-windows-msvc", "windows-x86_64", None),
                ("x86_64-apple-darwin", "macos-x86_64", None),
                ("x86_64-unknown-linux-gnu", "wsl-x86_64", None),
                ("aarch64-unknown-linux-gnu", "linux-aarch64", "x86_64-unknown-linux-gnu"),
                ("x86_64-unknown-linux-gnu", "linux-x86_64", None)):
            with self.subTest(target=target, profile=profile):
                self.assertNotEqual(self.run_selector(qualification=True, target=target,
                    profile=profile, host=host)[0], 0)

    @unittest.skipUnless(platform.system() == "Linux" and "microsoft" not in platform.release().lower(),
                         "qualification requires a native Linux host")
    def test_qualification_binds_both_exact_identities_and_excludes_release_verifier(self):
        identity = {"VADGR_QUALIFICATION_SOURCE_COMMIT": "a" * 40,
                    "VADGR_QUALIFICATION_SOURCE_TREE": "b" * 40}
        arguments = dict(qualification=True, target="x86_64-unknown-linux-gnu", profile="linux-x86_64",
            files=("packaging/cua/native-wheel-manifest.json", "packaging/cua/profile-locks/linux-x86_64.lock",
                   "packaging/cua/profile-inputs.json", "packaging/cua/cua-profile-catalog.json"))
        self.assertEqual(self.run_selector(**arguments, identity=identity)[0], 0)
        for name, value in identity.items():
            self.assertIn(f"cargo:rustc-env={name}={value}", self.last_stdout)
        self.assertNotEqual(self.run_selector(**arguments, identity=identity, verifier=True)[0], 0)
        for key in identity:
            for value in ("", "a" * 39, "A" * 40, "g" * 40):
                self.assertNotEqual(self.run_selector(**arguments, identity=dict(identity, **{key: value}))[0], 0)


if __name__ == "__main__":
    unittest.main()
