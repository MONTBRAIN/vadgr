//! Configuration: the port, the database, the computer-use flag, and
//! `providers.yaml`.

use serde::Deserialize;
use std::collections::BTreeMap;

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

#[derive(Debug, Deserialize, Default)]
pub struct ProviderEntry {
    #[serde(default)]
    pub name: Option<String>,
    #[serde(default)]
    pub command: Option<String>,
    #[serde(default)]
    pub available_check: Option<String>,
    #[serde(default)]
    pub models: Vec<String>,
}

pub fn load_providers(path: &str) -> BTreeMap<String, ProviderEntry> {
    let text = match std::fs::read_to_string(path) {
        Ok(t) => t,
        // A missing providers.yaml is an empty list, not a crash: the Python
        // route swallows every per-provider failure too, and a daemon that
        // refuses to start because a config file moved is worse than one that
        // reports nothing available.
        Err(_) => return BTreeMap::new(),
    };
    serde_yaml::from_str(&text).unwrap_or_default()
}

/// A provider with no command is the in-process engine, which is always
/// available: there is nothing to find on `PATH` and nothing to spawn. Without
/// this the empty argv reached the spawn and raised, which is what put every
/// native provider into `error` at creation.
pub fn provider_available(entry: &ProviderEntry) -> bool {
    match (&entry.command, &entry.available_check) {
        (None, None) => true,
        (_, Some(check)) => run_check(check),
        (Some(cmd), None) => which(cmd).is_some(),
    }
}

fn which(cmd: &str) -> Option<String> {
    let path = std::env::var("PATH").ok()?;
    for dir in path.split(':') {
        let candidate = std::path::Path::new(dir).join(cmd);
        if candidate.is_file() {
            return Some(candidate.to_string_lossy().into_owned());
        }
    }
    None
}

fn run_check(check: &str) -> bool {
    std::process::Command::new("sh")
        .arg("-c")
        .arg(check)
        .stdout(std::process::Stdio::null())
        .stderr(std::process::Stdio::null())
        .status()
        .map(|s| s.success())
        .unwrap_or(false)
}
