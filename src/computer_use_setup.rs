//! Daemon-owned computer-use state.
//!
//! **This service writes only vadgr's own settings.** It never edits a project
//! file or another program's global configuration: the loop owns its MCP host,
//! so nothing outside this machine's state needs to know computer use is on.

use crate::cua_payload::{CuaCommand, CuaRuntime, install_root_from_executable};
use crate::platform;
use anyhow::{Context, Result, bail};
use serde_json::{Map, Value, json};
use std::ffi::OsString;
use std::io::Write;
use std::path::{Path, PathBuf};

const SETTINGS_FILE: &str = "settings.json";

#[derive(Clone)]
pub struct SetupService {
    settings_path: PathBuf,
    runtime: Option<CuaRuntime>,
    default_enabled: bool,
}

#[derive(Clone, Debug, Eq, PartialEq)]
pub struct ComputerUseEntry {
    pub enabled: bool,
    pub command: Option<CuaCommand>,
}

impl SetupService {
    pub fn from_env() -> Result<Self> {
        let default_enabled = match std::env::var("VADGR_COMPUTER_USE") {
            Ok(value) => parse_enabled(&value)?,
            Err(std::env::VarError::NotPresent) => true,
            Err(std::env::VarError::NotUnicode(_)) => {
                bail!("VADGR_COMPUTER_USE must be true, false, 1 or 0")
            }
        };
        let runtime = std::env::current_exe()
            .ok()
            .and_then(|executable| install_root_from_executable(&executable).ok())
            .and_then(|root| CuaRuntime::below_install_root(&root).ok());
        Ok(Self::new(
            config_home()?.join(SETTINGS_FILE),
            runtime,
            default_enabled,
        ))
    }

    /// Construct the service with explicit dependencies. The daemon uses
    /// `from_env`; tests and embedders use this constructor without mutating the
    /// process environment.
    pub fn new(settings_path: PathBuf, runtime: Option<CuaRuntime>, default_enabled: bool) -> Self {
        Self {
            settings_path,
            runtime,
            default_enabled,
        }
    }

    pub fn status(&self) -> Result<Value> {
        Ok(json!({
            "enabled": self.read_enabled()?.unwrap_or(self.default_enabled),
            // This wire key is kept for the released CLI. It means that a cua
            // runtime can be mounted, not that vadgr owns the environment it lives in.
            "venv_ready": self.runtime.is_some(),
            "platform": platform::computer_use_platform(),
        }))
    }

    pub fn entry(&self) -> Result<ComputerUseEntry> {
        Ok(ComputerUseEntry {
            enabled: self.read_enabled()?.unwrap_or(self.default_enabled),
            command: self.runtime.as_ref().map(CuaRuntime::stdio_command),
        })
    }

    pub fn enable(&self) -> Result<Value> {
        self.set_enabled(true)
    }

    pub fn disable(&self) -> Result<Value> {
        self.set_enabled(false)
    }

    fn read_enabled(&self) -> Result<Option<bool>> {
        let document = read_document(&self.settings_path)?;
        let root = document
            .as_object()
            .context("vadgr settings must be a JSON object")?;
        let Some(section) = root.get("computer_use") else {
            return Ok(None);
        };
        let section = section
            .as_object()
            .context("computer_use settings must be a JSON object")?;
        match section.get("enabled") {
            None => Ok(None),
            Some(Value::Bool(enabled)) => Ok(Some(*enabled)),
            Some(_) => bail!("computer_use.enabled must be a boolean"),
        }
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
        if section
            .get("enabled")
            .is_some_and(|value| !value.is_boolean())
        {
            bail!("computer_use.enabled must be a boolean");
        }
        section.insert("enabled".into(), Value::Bool(enabled));
        write_document(&self.settings_path, &document)?;
        self.status()
    }
}

fn parse_enabled(value: &str) -> Result<bool> {
    match value.trim() {
        "1" => Ok(true),
        "0" => Ok(false),
        value if value.eq_ignore_ascii_case("true") => Ok(true),
        value if value.eq_ignore_ascii_case("false") => Ok(false),
        _ => bail!("VADGR_COMPUTER_USE must be true, false, 1 or 0"),
    }
}

fn config_home() -> Result<PathBuf> {
    config_home_from(
        std::env::var_os("VADGR_CONFIG_HOME"),
        std::env::var_os("XDG_CONFIG_HOME"),
        std::env::var_os("HOME"),
        std::env::var_os("APPDATA"),
        std::env::var_os("USERPROFILE"),
        std::env::consts::OS,
    )
    .context("no platform configuration directory; set VADGR_CONFIG_HOME")
}

fn config_home_from(
    vadgr_home: Option<OsString>,
    xdg_home: Option<OsString>,
    home: Option<OsString>,
    app_data: Option<OsString>,
    user_profile: Option<OsString>,
    os: &str,
) -> Option<PathBuf> {
    if let Some(path) = vadgr_home {
        return Some(path.into());
    }

    match os {
        "windows" => absolute_path(app_data)
            .map(|path| path.join("vadgr"))
            .or_else(|| {
                absolute_path(user_profile)
                    .map(|path| path.join("AppData").join("Roaming").join("vadgr"))
            }),
        "macos" => absolute_path(home).map(|path| {
            path.join("Library")
                .join("Application Support")
                .join("vadgr")
        }),
        _ => absolute_path(xdg_home)
            .map(|path| path.join("vadgr"))
            .or_else(|| absolute_path(home).map(|path| path.join(".config").join("vadgr"))),
    }
}

fn absolute_path(value: Option<OsString>) -> Option<PathBuf> {
    value.map(PathBuf::from).filter(|path| path.is_absolute())
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
        .context("vadgr settings path has no file name")?;
    let mut temporary_name = OsString::from(".");
    temporary_name.push(file_name);
    temporary_name.push(format!(".{}.tmp", uuid::Uuid::new_v4()));
    let temporary = parent.join(temporary_name);
    let bytes = serde_json::to_vec_pretty(document)?;
    let mut file = std::fs::OpenOptions::new()
        .write(true)
        .create_new(true)
        .open(&temporary)
        .with_context(|| format!("creating {}", temporary.display()))?;
    file.write_all(&bytes)
        .with_context(|| format!("writing {}", temporary.display()))?;
    file.sync_all()
        .with_context(|| format!("syncing {}", temporary.display()))?;
    drop(file);
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
    use std::iter::once;
    use std::os::windows::ffi::OsStrExt;
    use windows_sys::Win32::Storage::FileSystem::{
        MOVEFILE_REPLACE_EXISTING, MOVEFILE_WRITE_THROUGH, MoveFileExW,
    };

    let source: Vec<u16> = source.as_os_str().encode_wide().chain(once(0)).collect();
    let destination: Vec<u16> = destination
        .as_os_str()
        .encode_wide()
        .chain(once(0))
        .collect();
    let result = unsafe {
        MoveFileExW(
            source.as_ptr(),
            destination.as_ptr(),
            MOVEFILE_REPLACE_EXISTING | MOVEFILE_WRITE_THROUGH,
        )
    };
    if result == 0 {
        Err(std::io::Error::last_os_error())
    } else {
        Ok(())
    }
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
        let service = SetupService::new(path.clone(), None, true);

        assert_eq!(service.disable().unwrap()["enabled"], false);
        let document: Value = serde_json::from_slice(&std::fs::read(path).unwrap()).unwrap();
        assert_eq!(document["transport"], "loopback");
        assert_eq!(document["computer_use"]["enabled"], false);
        assert_eq!(service.enable().unwrap()["enabled"], true);
    }

    #[test]
    fn status_reports_runtime_presence_without_starting_a_process() {
        let directory = tempfile::tempdir().unwrap();
        let runtime = crate::cua_payload::CuaRuntime::for_test(directory.path());
        let service =
            SetupService::new(directory.path().join("settings.json"), Some(runtime), true);

        let status = service.status().unwrap();
        assert_eq!(status["enabled"], true);
        assert_eq!(status["venv_ready"], true);
    }

    #[test]
    fn invalid_settings_are_not_overwritten_or_reported_as_defaults() {
        let directory = tempfile::tempdir().unwrap();
        for (index, contents) in [
            "not json",
            "[]",
            r#"{"computer_use":true}"#,
            r#"{"computer_use":{"enabled":"true"}}"#,
        ]
        .into_iter()
        .enumerate()
        {
            let path = directory.path().join(format!("settings-{index}.json"));
            std::fs::write(&path, contents).unwrap();
            let service = SetupService::new(path.clone(), None, true);

            assert!(service.status().is_err());
            assert!(service.disable().is_err());
            assert_eq!(std::fs::read_to_string(path).unwrap(), contents);
        }
    }

    #[test]
    fn the_environment_toggle_accepts_only_explicit_boolean_values() {
        use super::parse_enabled;

        assert!(parse_enabled("1").unwrap());
        assert!(parse_enabled("TRUE").unwrap());
        assert!(!parse_enabled("0").unwrap());
        assert!(!parse_enabled("false").unwrap());
        assert!(parse_enabled("enabled").is_err());
    }

    #[test]
    fn an_explicit_vadgr_config_home_wins_on_every_platform() {
        let expected = std::env::temp_dir().join("vadgr-explicit");
        let path = config_home_from(
            Some(expected.clone().into_os_string()),
            Some("ignored".into()),
            Some("ignored".into()),
            Some("ignored".into()),
            Some("ignored".into()),
            "windows",
        );

        assert_eq!(path, Some(expected));
    }

    #[test]
    fn linux_uses_xdg_then_the_home_config_directory() {
        let root = std::env::temp_dir().join("vadgr-linux-config");
        let xdg = root.join("xdg");
        assert_eq!(
            config_home_from(
                None,
                Some(xdg.clone().into_os_string()),
                Some(root.clone().into_os_string()),
                None,
                None,
                "linux",
            ),
            Some(xdg.join("vadgr"))
        );

        assert_eq!(
            config_home_from(
                None,
                Some("relative-xdg".into()),
                Some(root.clone().into_os_string()),
                None,
                None,
                "linux",
            ),
            Some(root.join(".config").join("vadgr"))
        );
    }

    #[test]
    fn macos_uses_application_support() {
        let home = std::env::temp_dir().join("vadgr-macos-home");
        let path = config_home_from(
            None,
            None,
            Some(home.clone().into_os_string()),
            None,
            None,
            "macos",
        );

        assert_eq!(
            path,
            Some(
                home.join("Library")
                    .join("Application Support")
                    .join("vadgr")
            )
        );
    }

    #[test]
    fn windows_uses_appdata_then_the_profile_roaming_directory() {
        let profile = std::env::temp_dir().join("vadgr-windows-profile");
        let app_data = profile.join("RoamingConfig");
        assert_eq!(
            config_home_from(
                None,
                None,
                None,
                Some(app_data.clone().into_os_string()),
                Some(profile.clone().into_os_string()),
                "windows",
            ),
            Some(app_data.join("vadgr"))
        );

        let path = config_home_from(
            None,
            None,
            None,
            None,
            Some(profile.clone().into_os_string()),
            "windows",
        );

        assert_eq!(
            path,
            Some(profile.join("AppData").join("Roaming").join("vadgr"))
        );
    }

    #[test]
    fn a_missing_platform_home_is_an_error_instead_of_a_working_directory_write() {
        assert_eq!(
            config_home_from(None, None, None, None, None, "linux"),
            None
        );
    }
}
