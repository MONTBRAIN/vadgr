//! The Rust catalog exposes only providers used by the native model loop.

use std::io::Write;
use vadgr_daemon::config::{load_providers, provider_catalog};

fn write_yaml(content: &str) -> std::path::PathBuf {
    let path = std::env::temp_dir().join(format!("vadgr-providers-{}.yaml", uuid::Uuid::new_v4()));
    let mut file = std::fs::File::create(&path).unwrap();
    file.write_all(content.as_bytes()).unwrap();
    path
}

const REALISTIC: &str = r#"
default_provider: zeta

providers:
  zeta:
    name: "Zeta (native)"
    kind: native
    models:
      - { id: "zeta-large", name: "Zeta Large" }
  alpha:
    name: "Alpha (native)"
    kind: native
    models: []
  codex:
    name: "Codex CLI"
    deprecated: true
    command: codex
    available_check: ["codex", "--version"]
    models: []
"#;

#[test]
fn entries_are_read_from_under_the_providers_key() {
    let path = write_yaml(REALISTIC);
    let providers = load_providers(path.to_str().unwrap());
    let _ = std::fs::remove_file(&path);
    assert_eq!(providers.len(), 2);
}

#[test]
fn native_provider_order_is_kept() {
    let path = write_yaml(REALISTIC);
    let providers = load_providers(path.to_str().unwrap());
    let _ = std::fs::remove_file(&path);
    let keys: Vec<&str> = providers.iter().map(|(key, _)| key.as_str()).collect();
    assert_eq!(keys, vec!["zeta", "alpha"]);
}

#[test]
fn models_pass_through_as_the_file_wrote_them() {
    let path = write_yaml(REALISTIC);
    let providers = load_providers(path.to_str().unwrap());
    let _ = std::fs::remove_file(&path);
    assert_eq!(providers[0].1.models[0]["id"], "zeta-large");
    assert_eq!(providers[0].1.models[0]["name"], "Zeta Large");
}

#[test]
fn deprecated_cli_providers_never_enter_the_rust_catalog() {
    let path = write_yaml(REALISTIC);
    let catalog = provider_catalog(path.to_str().unwrap());
    let _ = std::fs::remove_file(&path);
    assert_eq!(catalog.len(), 2);
    assert!(catalog.iter().all(|provider| provider["id"] != "codex"));
    assert!(catalog.iter().all(|provider| provider["available"] == true));
}

#[test]
fn a_missing_or_malformed_file_is_an_empty_catalog() {
    assert!(load_providers("/nonexistent/providers.yaml").is_empty());
    let path = write_yaml("providers: [not, a, map]");
    assert!(load_providers(path.to_str().unwrap()).is_empty());
    let _ = std::fs::remove_file(path);
}

#[test]
fn a_malformed_entry_is_omitted() {
    let path = write_yaml("providers:\n  broken:\n    kind: [native]\n");
    assert!(load_providers(path.to_str().unwrap()).is_empty());
    let _ = std::fs::remove_file(path);
}
