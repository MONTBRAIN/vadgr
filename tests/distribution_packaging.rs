use std::path::PathBuf;

fn root() -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR"))
}

fn read(relative: &str) -> String {
    std::fs::read_to_string(root().join(relative)).unwrap()
}

#[test]
fn every_runtime_surface_derives_the_cargo_package_version() {
    assert!(read("Cargo.toml").contains("version = \"0.5.0\""));
    let config = read("src/config.rs");
    assert!(config.contains("env!(\"CARGO_PKG_VERSION\")"));
    assert!(!config.contains("pub const VERSION: &str = \"0."));
}

#[test]
fn release_manifest_schema_and_runtime_have_the_same_closed_shape() {
    let schema: serde_json::Value =
        serde_json::from_str(&read("packaging/manifest-schema.json")).unwrap();
    assert_eq!(schema["properties"]["schema"]["const"], 1);
    assert_eq!(schema["properties"]["product"]["const"], "vadgr");
    assert_eq!(schema["additionalProperties"], false);
    assert!(read("src/install/manifest.rs").contains("#[serde(deny_unknown_fields)]"));
    assert!(read("src/install/manifest.rs").contains("verify_signature(&bytes"));
}

#[test]
fn native_linux_is_graphical_and_wsl_is_cli_only() {
    let app_run = read("packaging/linux/AppRun");
    let linux_build = read("packaging/linux/build.sh");
    let wsl = read("install.sh");
    assert!(app_run.contains("--installer --vehicle"));
    assert!(linux_build.contains("--features native-gui"));
    assert!(wsl.contains("Native Linux uses the graphical AppImage installer"));
    assert!(!wsl.contains(".desktop"));
    assert!(!wsl.contains("autostart"));
    assert!(!wsl.contains("systemctl"));
}

#[test]
fn every_unsigned_or_unconfigured_trust_path_fails_closed() {
    assert_eq!(
        read("packaging/release-public-key.txt").trim(),
        "UNCONFIGURED"
    );
    for source in [
        read("packaging/linux/build.sh"),
        read("packaging/macos/build.sh"),
        read("install.sh"),
    ] {
        assert!(source.contains("UNCONFIGURED"));
        assert!(!source.contains("self-sign"));
        assert!(!source.contains("ad-hoc"));
    }
}

#[test]
fn macos_packages_the_stable_responsible_process() {
    let app = read("packaging/macos/Vadgr-Info.plist");
    let host = read("packaging/macos/CuaHost-Info.plist");
    let build = read("packaging/macos/build.sh");
    let runtime = read("src/cua_payload.rs");
    assert!(app.contains("com.montbrain.vadgr"));
    assert!(host.contains("com.montbrain.vadgr.cua"));
    assert!(build.contains("Vadgr Computer Use.app"));
    assert!(runtime.contains("Vadgr Computer Use.app/Contents/MacOS/vadgr-cua-host"));
    assert!(runtime.contains("the signed Vadgr Computer Use host is missing"));
}

#[test]
fn e2e_runbook_names_every_required_lifecycle_negative() {
    let runbook = read("E2E/0.5.0/e2e.md").to_ascii_lowercase();
    for required in [
        "terms declined",
        "tampered",
        "health-check failure",
        "repair",
        "roll back",
        "uninstall-preserve",
        "delete owner data",
        "authenticode",
        "designated requirement",
        "screen reader",
        "cleanup",
    ] {
        assert!(runbook.contains(required), "runbook lacks {required}");
    }
}
