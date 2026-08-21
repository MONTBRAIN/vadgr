use vadgr_daemon::db::Db;
use vadgr_daemon::engine::provider::credentials::CredentialStore;
use vadgr_daemon::engine::provider::service::{ProviderEndpoints, ProviderService};

#[test]
fn rust_provider_rows_come_from_compiled_descriptors() {
    let directory = tempfile::tempdir().unwrap();
    std::fs::write(
        directory.path().join("providers.yaml"),
        "providers:\n  injected:\n    kind: native\n    models:\n      - id: injected-model\n",
    )
    .unwrap();
    let service = ProviderService::new(
        Db::open(":memory:").unwrap(),
        CredentialStore::new(directory.path().join("credentials")).unwrap(),
        ProviderEndpoints::default(),
    )
    .unwrap();

    let rows = service.list_rows().unwrap();
    let ids = rows
        .iter()
        .map(|row| row["id"].as_str().unwrap())
        .collect::<Vec<_>>();
    assert_eq!(ids, ["openai", "gemini", "anthropic"]);
    assert!(
        rows.iter()
            .all(|row| row["models"].as_array().unwrap().is_empty())
    );
}
