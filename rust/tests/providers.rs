//! The provider catalogue, read the way the real file is shaped.
//!
//! `providers.yaml` nests its entries under a top-level `providers:` key,
//! carries `models` as `{id, name}` maps, and writes `available_check` as an
//! argv list. Each of those shapes broke an earlier reading of the file, so
//! each is pinned here against a file written in this test.

use std::io::Write;
use vadgr_daemon::config::{load_providers, provider_available, ProviderEntry};

fn write_yaml(content: &str) -> std::path::PathBuf {
    let path = std::env::temp_dir().join(format!("vadgr-providers-{}.yaml", uuid::Uuid::new_v4()));
    let mut f = std::fs::File::create(&path).unwrap();
    f.write_all(content.as_bytes()).unwrap();
    path
}

const REALISTIC: &str = r#"
default_provider: zeta

providers:
  zeta:
    name: "Zeta (native)"
    kind: native
    module: "engine.providers.zeta:ZetaProvider"
    models:
      - { id: "zeta-large", name: "Zeta Large" }
      - { id: "zeta-small", name: "Zeta Small" }
  alpha:
    name: "Alpha CLI"
    command: alpha
    args: ["-p", "{{prompt}}"]
    available_check: ["alpha", "--version"]
    timeout: 900
    models: []
"#;

#[test]
fn entries_are_read_from_under_the_providers_key() {
    // Reading the whole document as the provider map parses nothing and
    // reports an empty catalogue against a perfectly good file.
    let path = write_yaml(REALISTIC);
    let providers = load_providers(path.to_str().unwrap());
    let _ = std::fs::remove_file(&path);
    assert_eq!(providers.len(), 2);
}

#[test]
fn the_files_order_is_kept_not_alphabetized() {
    // The list is what the phone's model picker draws, and the file's order
    // is the owner's: `zeta` before `alpha` because the file says so.
    let path = write_yaml(REALISTIC);
    let providers = load_providers(path.to_str().unwrap());
    let _ = std::fs::remove_file(&path);
    let keys: Vec<&str> = providers.iter().map(|(k, _)| k.as_str()).collect();
    assert_eq!(keys, vec!["zeta", "alpha"]);
}

#[test]
fn models_pass_through_as_the_file_wrote_them() {
    let path = write_yaml(REALISTIC);
    let providers = load_providers(path.to_str().unwrap());
    let _ = std::fs::remove_file(&path);
    let (_, zeta) = &providers[0];
    assert_eq!(zeta.models[0]["id"], "zeta-large");
    assert_eq!(zeta.models[0]["name"], "Zeta Large");
}

#[test]
fn a_missing_file_is_an_empty_catalogue_not_a_crash() {
    assert!(load_providers("/nonexistent/providers.yaml").is_empty());
}

#[test]
fn a_native_provider_with_nothing_to_spawn_is_available() {
    // No command and no check is the in-process engine: there is nothing to
    // find on PATH and nothing to run.
    let entry = ProviderEntry::default();
    assert!(provider_available(&entry));
}

#[test]
fn an_argv_check_decides_availability_by_exit_code() {
    let ok = ProviderEntry {
        available_check: vec!["true".into()],
        ..Default::default()
    };
    assert!(provider_available(&ok));
    let bad = ProviderEntry {
        available_check: vec!["false".into()],
        ..Default::default()
    };
    assert!(!provider_available(&bad));
    let gone = ProviderEntry {
        available_check: vec!["definitely-not-a-command-vadgr".into()],
        ..Default::default()
    };
    assert!(!provider_available(&gone));
}

#[test]
fn a_command_with_no_check_is_looked_up_on_path() {
    let found = ProviderEntry {
        command: Some("sh".into()),
        ..Default::default()
    };
    assert!(provider_available(&found));
    let missing = ProviderEntry {
        command: Some("definitely-not-a-command-vadgr".into()),
        ..Default::default()
    };
    assert!(!provider_available(&missing));
}
