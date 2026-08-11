//! Configuration: the port, the database, the computer-use flag, and
//! `providers.yaml`.

use serde::Deserialize;
use serde_json::Value;

/// The version this daemon reports at `GET /api/health`.
pub const VERSION: &str = "0.4.5";

pub struct Config {
    pub port: u16,
    pub db_path: String,
    pub transport_name: String,
    pub providers_path: String,
    pub computer_use_enabled: bool,
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
            db_path: std::env::var("VADGR_DB")
                .unwrap_or_else(|_| "data/vadgr-rust.db".to_string()),
            transport_name: std::env::var("VADGR_TRANSPORT")
                .unwrap_or_else(|_| "loopback".to_string()),
            providers_path: std::env::var("VADGR_PROVIDERS")
                .unwrap_or_else(|_| "providers.yaml".to_string()),
            computer_use_enabled: std::env::var("VADGR_COMPUTER_USE")
                .map(|v| v == "1" || v.eq_ignore_ascii_case("true"))
                .unwrap_or(false),
        }
    }
}

/// One entry under the document's `providers:` key. The fields this daemon
/// does not read (`kind`, `module`, `args`, `timeout`, ...) pass through
/// deserialization untouched; `models` stays an untyped value because the
/// route publishes it verbatim, and the real file carries `{id, name}` maps,
/// not strings.
#[derive(Debug, Deserialize, Default)]
pub struct ProviderEntry {
    #[serde(default)]
    pub name: Option<String>,
    #[serde(default)]
    pub command: Option<String>,
    /// An argv, run directly: `["claude", "--version"]`. The Python daemon
    /// execs it without a shell, and a port that handed it to `sh -c` would
    /// change both its parsing and its failure modes.
    #[serde(default)]
    pub available_check: Vec<String>,
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
            let entry = serde_norway::from_value(value.clone()).unwrap_or_default();
            Some((key, entry))
        })
        .collect()
}

/// A provider with no command and no check is the in-process engine, which is
/// always available: there is nothing to find on `PATH` and nothing to spawn.
/// Without this the empty argv reached the spawn and raised, which is what put
/// every native provider into `error` at creation.
pub fn provider_available(entry: &ProviderEntry) -> bool {
    if entry.available_check.is_empty() {
        return match &entry.command {
            None => true,
            Some(cmd) => which(cmd).is_some(),
        };
    }
    run_check(&entry.available_check)
}

fn which(cmd: &str) -> Option<String> {
    let path = std::env::var("PATH").ok()?;
    for dir in path.split(':') {
        let candidate = std::path::Path::new(dir).join(cmd);
        if candidate.is_file() && is_executable(&candidate) {
            return Some(candidate.to_string_lossy().into_owned());
        }
    }
    None
}

#[cfg(unix)]
fn is_executable(path: &std::path::Path) -> bool {
    use std::os::unix::fs::PermissionsExt;
    std::fs::metadata(path)
        .map(|m| m.permissions().mode() & 0o111 != 0)
        .unwrap_or(false)
}

#[cfg(not(unix))]
fn is_executable(_path: &std::path::Path) -> bool {
    true
}

fn run_check(argv: &[String]) -> bool {
    let Some((cmd, args)) = argv.split_first() else {
        return false;
    };
    std::process::Command::new(cmd)
        .args(args)
        .stdout(std::process::Stdio::null())
        .stderr(std::process::Stdio::null())
        .status()
        .map(|s| s.success())
        .unwrap_or(false)
}
