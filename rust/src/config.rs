//! Process configuration and the native provider catalog.

use serde::Deserialize;
use serde_json::Value;
use std::ffi::OsString;
use std::path::{Path, PathBuf};

/// The version this daemon reports at `GET /api/health`.
pub const VERSION: &str = "0.4.6";

pub struct Config {
    pub port: u16,
    pub db_path: PathBuf,
    pub transport_name: String,
    pub providers_path: PathBuf,
    pub runs_dir: PathBuf,
}

impl Config {
    pub fn from_env() -> Self {
        Self::from_values(
            std::env::var("VADGR_PORT").ok(),
            std::env::var_os("VADGR_DB"),
            std::env::var("VADGR_TRANSPORT").ok(),
            std::env::var_os("VADGR_PROVIDERS"),
            std::env::var_os("VADGR_RUNS_DIR"),
        )
    }

    fn from_values(
        port: Option<String>,
        db_path: Option<OsString>,
        transport_name: Option<String>,
        providers_path: Option<OsString>,
        runs_dir: Option<OsString>,
    ) -> Self {
        let port = port
            .and_then(|v| v.parse().ok())
            // Not 8000. The strangler runs both daemons at once, so the Rust
            // one takes its own port by default and only shares when told to.
            .unwrap_or(8100);
        Self {
            port,
            db_path: db_path
                .map(PathBuf::from)
                .unwrap_or_else(|| PathBuf::from("data").join("vadgr-rust.db")),
            transport_name: transport_name.unwrap_or_else(|| "loopback".to_string()),
            providers_path: providers_path
                .map(PathBuf::from)
                .unwrap_or_else(|| PathBuf::from("providers.yaml")),
            runs_dir: runs_dir.map(PathBuf::from).unwrap_or_else(default_runs_dir),
        }
    }
}

fn default_runs_dir() -> PathBuf {
    let home = if cfg!(windows) {
        std::env::var_os("USERPROFILE")
    } else {
        std::env::var_os("HOME")
    };
    home.map(PathBuf::from)
        .filter(|path| path.is_absolute())
        .map(|path| path.join(".vadgr").join("runs"))
        .unwrap_or_else(|| PathBuf::from("data").join("runs"))
}

pub fn resolve_provider_model(
    path: impl AsRef<Path>,
    provider: Option<&str>,
    model: Option<&str>,
) -> Result<(String, String), String> {
    if let (Some(provider), Some(model)) = (provider, model) {
        return Ok((provider.to_owned(), model.to_owned()));
    }
    let text = std::fs::read_to_string(path).map_err(|error| error.to_string())?;
    let doc: serde_norway::Value =
        serde_norway::from_str(&text).map_err(|error| error.to_string())?;
    let provider = doc
        .get("default_provider")
        .and_then(|value| value.as_str())
        .ok_or("providers.yaml has no default_provider")?;
    let entry = doc
        .get("providers")
        .and_then(|value| value.as_mapping())
        .and_then(|providers| providers.get(serde_norway::Value::String(provider.to_owned())))
        .ok_or_else(|| format!("default provider `{provider}` is not configured"))?;
    if entry.get("kind").and_then(|value| value.as_str()) != Some("native") {
        return Err(format!("default provider `{provider}` is not native"));
    }
    let model = entry
        .get("default_model")
        .and_then(|value| value.as_str())
        .ok_or_else(|| format!("provider `{provider}` has no default_model"))?;
    Ok((provider.to_owned(), model.to_owned()))
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
pub fn load_providers(path: impl AsRef<Path>) -> Vec<(String, ProviderEntry)> {
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
pub fn provider_catalog(path: impl AsRef<Path>) -> Vec<Value> {
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

#[cfg(test)]
mod tests {
    use super::Config;
    use std::path::Path;

    #[test]
    fn default_paths_are_built_from_native_components() {
        let config = Config::from_values(None, None, None, None, None);

        assert_eq!(config.db_path, Path::new("data").join("vadgr-rust.db"));
        assert_eq!(config.providers_path, Path::new("providers.yaml"));
        assert!(
            config.runs_dir.ends_with(Path::new(".vadgr").join("runs"))
                || config.runs_dir == Path::new("data").join("runs")
        );
    }

    #[cfg(unix)]
    #[test]
    fn configured_paths_preserve_non_utf8_os_strings() {
        use std::ffi::OsString;
        use std::os::unix::ffi::OsStringExt;

        let db_path = OsString::from_vec(b"/tmp/vadgr-\xff.db".to_vec());
        let providers_path = OsString::from_vec(b"/tmp/providers-\xfe.yaml".to_vec());
        let config = Config::from_values(
            None,
            Some(db_path.clone()),
            None,
            Some(providers_path.clone()),
            None,
        );

        assert_eq!(config.db_path.as_os_str(), db_path);
        assert_eq!(config.providers_path.as_os_str(), providers_path);
    }
}
