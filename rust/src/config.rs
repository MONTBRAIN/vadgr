//! Process configuration and the native provider catalog.

use serde::Deserialize;
use serde_json::Value;

/// The version this daemon reports at `GET /api/health`.
pub const VERSION: &str = "0.4.5";

pub struct Config {
    pub port: u16,
    pub db_path: String,
    pub transport_name: String,
    pub providers_path: String,
}

impl Config {
    pub fn from_env() -> Self {
        let port = std::env::var("VADGR_PORT")
            .ok()
            .and_then(|v| v.parse().ok())
            // Not 8000. The strangler runs both daemons at once, so the Rust
            // one takes its own port by default and only shares when told to.
            .unwrap_or(8100);
        Self {
            port,
            db_path: std::env::var("VADGR_DB").unwrap_or_else(|_| "data/vadgr-rust.db".to_string()),
            transport_name: std::env::var("VADGR_TRANSPORT")
                .unwrap_or_else(|_| "loopback".to_string()),
            providers_path: std::env::var("VADGR_PROVIDERS")
                .unwrap_or_else(|_| "providers.yaml".to_string()),
        }
    }
}

/// One entry under the document's `providers:` key. `models` stays an untyped
/// value because the
/// route publishes it verbatim, and the real file carries `{id, name}` maps,
/// not strings.
#[derive(Debug, Deserialize)]
pub struct ProviderEntry {
    #[serde(default)]
    pub name: Option<String>,
    #[serde(default)]
    pub kind: Option<String>,
    #[serde(default)]
    pub deprecated: bool,
    #[serde(default = "empty_models")]
    pub models: Value,
}

fn empty_models() -> Value {
    Value::Array(Vec::new())
}

/// The providers, **in the order the file declares them**: the list is what
/// the phone's model picker draws, and the file's order is the owner's.
///
/// The document nests them under a top-level `providers:` key beside
/// `default_provider`; reading the whole file as the provider map parses
/// nothing and reports an empty catalogue against a perfectly good file.
///
/// A missing or unreadable file is an empty list, not a crash: a daemon that
/// refuses to start because a config file moved is worse than one that
/// reports nothing available.
pub fn load_providers(path: &str) -> Vec<(String, ProviderEntry)> {
    let Ok(text) = std::fs::read_to_string(path) else {
        return Vec::new();
    };
    let Ok(doc) = serde_norway::from_str::<serde_norway::Value>(&text) else {
        return Vec::new();
    };
    let Some(mapping) = doc.get("providers").and_then(|v| v.as_mapping()) else {
        return Vec::new();
    };
    mapping
        .iter()
        .filter_map(|(key, value)| {
            let key = key.as_str()?.to_string();
            // A malformed entry keeps its slot rather than taking the list
            // down, which is the same posture the Python route takes per
            // provider: it just reports nothing useful about itself.
            let entry = serde_norway::from_value::<ProviderEntry>(value.clone()).ok()?;
            (entry.kind.as_deref() == Some("native") && !entry.deprecated).then_some((key, entry))
        })
        .collect()
}

/// Resolve the native provider catalog once when the daemon starts.
pub fn provider_catalog(path: &str) -> Vec<Value> {
    load_providers(path)
        .into_iter()
        .map(|(key, cfg)| {
            serde_json::json!({
                "id": key,
                "name": cfg.name.clone().unwrap_or_else(|| key.clone()),
                "available": true,
                "models": cfg.models,
            })
        })
        .collect()
}
