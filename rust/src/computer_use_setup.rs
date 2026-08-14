//! Daemon-owned computer-use state.
//!
//! The Python service configured external agent CLIs. The native loop owns its
//! MCP host, so this service writes only vadgr's settings and never edits a
//! project file or another program's global configuration.

use crate::platform;
use anyhow::{Context, Result};
use serde_json::{Map, Value, json};
use std::path::{Path, PathBuf};

const SETTINGS_FILE: &str = "settings.json";

#[derive(Clone)]
pub struct SetupService {
    settings_path: PathBuf,
    runtime_path: Option<PathBuf>,
    default_enabled: bool,
}

impl SetupService {
    pub fn from_env() -> Self {
        Self {
            settings_path: config_home().join(SETTINGS_FILE),
            runtime_path: find_runtime(),
            default_enabled: std::env::var("VADGR_COMPUTER_USE")
                .map(|value| value == "1" || value.eq_ignore_ascii_case("true"))
                .unwrap_or(true),
        }
    }

    #[cfg(test)]
    fn new(settings_path: PathBuf, runtime_path: Option<PathBuf>) -> Self {
        Self {
            settings_path,
            runtime_path,
            default_enabled: true,
        }
    }

    pub fn status(&self) -> Value {
        json!({
            "enabled": self.read_enabled().unwrap_or(self.default_enabled),
            // This wire key is kept for the released CLI. It means that a cua
            // runtime can be mounted, not that vadgr owns a Python virtualenv.
            "venv_ready": self.runtime_path.is_some(),
            "daemon": Value::Null,
            "platform": platform::computer_use_platform(),
        })
    }

    pub fn enable(&self) -> Result<Value> {
        self.set_enabled(true)
    }

    pub fn disable(&self) -> Result<Value> {
        self.set_enabled(false)
    }

    fn read_enabled(&self) -> Option<bool> {
        let document = read_document(&self.settings_path).ok()?;
        document
            .get("computer_use")
            .and_then(Value::as_object)
            .and_then(|section| section.get("enabled"))
            .and_then(Value::as_bool)
    }

    fn set_enabled(&self, enabled: bool) -> Result<Value> {
        let mut document = read_document(&self.settings_path)?;
        let root = document
            .as_object_mut()
            .context("vadgr settings must be a JSON object")?;
        let section = root
            .entry("computer_use")
            .or_insert_with(|| Value::Object(Map::new()))
            .as_object_mut()
            .context("computer_use settings must be a JSON object")?;
        section.insert("enabled".into(), Value::Bool(enabled));
        write_document(&self.settings_path, &document)?;
        Ok(self.status())
    }
}

fn config_home() -> PathBuf {
    config_home_from(
        std::env::var_os("VADGR_CONFIG_HOME"),
        std::env::var_os("XDG_CONFIG_HOME"),
        std::env::var_os("HOME"),
        std::env::var_os("USERPROFILE"),
    )
}

fn config_home_from(
    vadgr_home: Option<std::ffi::OsString>,
    xdg_home: Option<std::ffi::OsString>,
    home: Option<std::ffi::OsString>,
    user_profile: Option<std::ffi::OsString>,
) -> PathBuf {
    if let Some(path) = vadgr_home {
        return path.into();
    }
    if let Some(path) = xdg_home {
        return PathBuf::from(path).join("vadgr");
    }
    if let Some(path) = home.or(user_profile) {
        return PathBuf::from(path).join(".config/vadgr");
    }
    PathBuf::from(".vadgr")
}

fn read_document(path: &Path) -> Result<Value> {
    match std::fs::read_to_string(path) {
        Ok(text) => {
            serde_json::from_str(&text).with_context(|| format!("parsing {}", path.display()))
        }
        Err(error) if error.kind() == std::io::ErrorKind::NotFound => Ok(Value::Object(Map::new())),
        Err(error) => Err(error).with_context(|| format!("reading {}", path.display())),
    }
}

fn write_document(path: &Path, document: &Value) -> Result<()> {
    let parent = path
        .parent()
        .context("vadgr settings path has no parent directory")?;
    std::fs::create_dir_all(parent).with_context(|| format!("creating {}", parent.display()))?;

    let file_name = path
        .file_name()
        .and_then(|name| name.to_str())
        .context("vadgr settings path has no file name")?;
    let temporary = parent.join(format!(".{file_name}.{}.tmp", uuid::Uuid::new_v4()));
    let bytes = serde_json::to_vec_pretty(document)?;
    std::fs::write(&temporary, bytes)
        .with_context(|| format!("writing {}", temporary.display()))?;
    if let Err(error) = replace_file(&temporary, path) {
        let _ = std::fs::remove_file(&temporary);
        return Err(error).with_context(|| format!("replacing {}", path.display()));
    }
    Ok(())
}

#[cfg(not(windows))]
fn replace_file(source: &Path, destination: &Path) -> std::io::Result<()> {
    std::fs::rename(source, destination)
}

#[cfg(windows)]
fn replace_file(source: &Path, destination: &Path) -> std::io::Result<()> {
    // Windows does not replace an existing destination with rename.
    if destination.exists() {
        std::fs::remove_file(destination)?;
    }
    std::fs::rename(source, destination)
}

fn find_runtime() -> Option<PathBuf> {
    if let Some(path) = std::env::var_os("VADGR_CUA_BIN").map(PathBuf::from) {
        return path.is_file().then_some(path);
    }

    let local = if cfg!(windows) {
        PathBuf::from(".cu_venv/Scripts/vadgr-cua.exe")
    } else {
        PathBuf::from(".cu_venv/bin/vadgr-cua")
    };
    if local.is_file() {
        return Some(local);
    }
    find_on_path("vadgr-cua")
}

fn find_on_path(command: &str) -> Option<PathBuf> {
    let path = std::env::var_os("PATH")?;
    for directory in std::env::split_paths(&path) {
        for name in command_names(command) {
            let candidate = directory.join(name);
            if candidate.is_file() && is_executable(&candidate) {
                return Some(candidate);
            }
        }
    }
    None
}

#[cfg(not(windows))]
fn command_names(command: &str) -> Vec<std::ffi::OsString> {
    vec![command.into()]
}

#[cfg(windows)]
fn command_names(command: &str) -> Vec<std::ffi::OsString> {
    use std::ffi::OsString;
    use std::path::Path;

    if Path::new(command).extension().is_some() {
        return vec![command.into()];
    }
    std::env::var_os("PATHEXT")
        .unwrap_or_else(|| ".COM;.EXE;.BAT;.CMD".into())
        .to_string_lossy()
        .split(';')
        .filter(|extension| !extension.is_empty())
        .map(|extension| OsString::from(format!("{command}{extension}")))
        .collect()
}

#[cfg(unix)]
fn is_executable(path: &Path) -> bool {
    use std::os::unix::fs::PermissionsExt;
    std::fs::metadata(path)
        .map(|metadata| metadata.permissions().mode() & 0o111 != 0)
        .unwrap_or(false)
}

#[cfg(not(unix))]
fn is_executable(_path: &Path) -> bool {
    true
}

#[cfg(test)]
mod tests {
    use super::{SetupService, config_home_from};
    use serde_json::Value;

    #[test]
    fn toggle_writes_only_daemon_settings_and_preserves_other_keys() {
        let directory = tempfile::tempdir().unwrap();
        let path = directory.path().join("settings.json");
        std::fs::write(&path, r#"{"transport":"loopback"}"#).unwrap();
        let service = SetupService::new(path.clone(), None);

        assert_eq!(service.disable().unwrap()["enabled"], false);
        let document: Value = serde_json::from_slice(&std::fs::read(path).unwrap()).unwrap();
        assert_eq!(document["transport"], "loopback");
        assert_eq!(document["computer_use"]["enabled"], false);
        assert_eq!(service.enable().unwrap()["enabled"], true);
    }

    #[test]
    fn status_reports_runtime_presence_without_starting_a_process() {
        let directory = tempfile::tempdir().unwrap();
        let runtime = directory.path().join("vadgr-cua");
        std::fs::write(&runtime, "runtime").unwrap();
        let service = SetupService::new(directory.path().join("settings.json"), Some(runtime));

        let status = service.status();
        assert_eq!(status["enabled"], true);
        assert_eq!(status["venv_ready"], true);
        assert!(status["daemon"].is_null());
    }

    #[test]
    fn malformed_settings_are_not_overwritten() {
        let directory = tempfile::tempdir().unwrap();
        let path = directory.path().join("settings.json");
        std::fs::write(&path, "not json").unwrap();
        let service = SetupService::new(path.clone(), None);

        assert!(service.disable().is_err());
        assert_eq!(std::fs::read_to_string(path).unwrap(), "not json");
    }

    #[test]
    fn the_windows_profile_has_the_same_daemon_owned_config_layout() {
        let path = config_home_from(None, None, None, Some(r"C:\Users\owner".into()));

        assert_eq!(
            path,
            std::path::Path::new(r"C:\Users\owner").join(".config/vadgr")
        );
    }
}
