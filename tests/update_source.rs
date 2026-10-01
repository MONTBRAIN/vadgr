//! Update failures through the public CLI preserve an isolated installation.

#![cfg(target_os = "linux")]

use std::collections::BTreeMap;
use std::path::{Path, PathBuf};
use std::process::Command;

struct Installation {
    directory: tempfile::TempDir,
    package: PathBuf,
    state: PathBuf,
}

impl Installation {
    fn new() -> Self {
        let directory = tempfile::tempdir().unwrap();
        let package = directory.path().join("package");
        let state = directory.path().join("state");
        std::fs::create_dir(&package).unwrap();
        std::fs::create_dir(&state).unwrap();
        let development = cfg!(feature = "linux-unsigned-qualification");
        let receipt = serde_json::json!({
            "schema": 1, "version": "0.5.0", "package_kind": "appimage",
            "release_sequence": (!development).then_some(500),
            "manifest_sha256": (!development).then(|| "a".repeat(64)),
            "development_receipt_sha256": development.then(|| "b".repeat(64)),
            "update_origin": null
        });
        std::fs::write(
            package.join("install-receipt.json"),
            serde_json::to_vec(&receipt).unwrap(),
        )
        .unwrap();
        std::fs::write(package.join("Vadgr.AppImage"), b"unchanged fixture vehicle").unwrap();
        std::fs::write(state.join("owner-state"), b"unchanged fixture state").unwrap();
        Self {
            directory,
            package,
            state,
        }
    }

    fn run(&self, arguments: &[&str]) -> std::process::Output {
        Command::new(env!("CARGO_BIN_EXE_vadgr"))
            .args(arguments)
            .env("VADGR_INSTALL_ROOT", &self.package)
            .env("VADGR_STATE_HOME", &self.state)
            .env("VADGR_HOME", self.directory.path().join("runtime"))
            .env("XDG_CONFIG_HOME", self.directory.path().join("config"))
            .env("XDG_DATA_HOME", self.directory.path().join("data"))
            .env("XDG_STATE_HOME", self.directory.path().join("xdg-state"))
            .output()
            .unwrap()
    }

    fn check_failure(&self, source: &str, reason: &str) {
        let before = snapshot(self.directory.path());
        let output = self.run(&["update", "--check", "--source", source]);
        let error = String::from_utf8_lossy(&output.stderr);
        assert_eq!(output.status.code(), Some(1), "{error}");
        assert!(error.contains(reason), "{error}");
        assert!(!error.contains("no update origin"), "{error}");
        assert_eq!(snapshot(self.directory.path()), before);
    }
}

fn snapshot(root: &Path) -> BTreeMap<PathBuf, Vec<u8>> {
    let mut result = BTreeMap::new();
    let mut pending = vec![root.to_path_buf()];
    while let Some(directory) = pending.pop() {
        for entry in std::fs::read_dir(directory).unwrap() {
            let path = entry.unwrap().path();
            let relative = path.strip_prefix(root).unwrap().to_path_buf();
            if path.is_dir() {
                result.insert(relative, Vec::new());
                pending.push(path);
            } else {
                result.insert(relative, std::fs::read(path).unwrap());
            }
        }
    }
    result
}

#[test]
fn update_source_missing_local_manifest_preserves_installation() {
    let installation = Installation::new();
    let source = installation.directory.path().join("source");
    std::fs::create_dir(&source).unwrap();
    installation.check_failure(source.to_str().unwrap(), "release-manifest.json");
}

#[test]
fn update_source_invalid_bundle_preserves_installation() {
    let installation = Installation::new();
    let source = installation.directory.path().join("source");
    std::fs::create_dir(&source).unwrap();
    std::fs::write(source.join("release-manifest.json"), b"{}").unwrap();
    std::fs::write(source.join("release-manifest.json.bundle.jsonl"), b"{}").unwrap();
    installation.check_failure(source.to_str().unwrap(), "parsing the release attestation");
}

#[test]
fn update_source_https_failure_preserves_installation() {
    let installation = Installation::new();
    let before = snapshot(installation.directory.path());
    let output = installation.run(&[
        "update",
        "--check",
        "--source",
        "https://127.0.0.1:9/private-source",
    ]);
    let error = String::from_utf8_lossy(&output.stderr);
    assert_eq!(output.status.code(), Some(1), "{error}");
    assert!(error.contains("The update download failed."), "{error}");
    assert!(error.contains("Try again"), "{error}");
    assert!(!error.contains("127.0.0.1"), "{error}");
    assert!(!error.contains("private-source"), "{error}");
    assert_eq!(snapshot(installation.directory.path()), before);
}

#[cfg(feature = "linux-unsigned-qualification")]
#[test]
fn update_source_development_apply_refuses_before_fetch_or_mutation() {
    let installation = Installation::new();
    let before = snapshot(installation.directory.path());
    let output = installation.run(&["update", "--source", "https://127.0.0.1:9"]);
    let error = String::from_utf8_lossy(&output.stderr);
    assert_eq!(output.status.code(), Some(1), "{error}");
    assert!(
        error.contains("Signed updates cannot replace an unsigned development installation"),
        "{error}"
    );
    assert_eq!(snapshot(installation.directory.path()), before);
}
