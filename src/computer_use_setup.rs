//! Daemon-owned computer-use state.
//!
//! The Python service configured external agent CLIs. The native loop owns its
//! MCP host, so this service writes only vadgr's settings and never edits a
//! project file or another program's global configuration.

use crate::platform;
use anyhow::{Context, Result, bail};
use serde_json::{Map, Value, json};
use std::ffi::{OsStr, OsString};
use std::io::Write;
use std::path::{Path, PathBuf};

const SETTINGS_FILE: &str = "settings.json";

#[derive(Clone)]
pub struct SetupService {
    settings_path: PathBuf,
    runtime_path: Option<PathBuf>,
    default_enabled: bool,
}

#[derive(Clone, Debug, Eq, PartialEq)]
pub struct ComputerUseEntry {
    pub enabled: bool,
    pub command: Option<PathBuf>,
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
        Ok(Self::new(
            config_home()?.join(SETTINGS_FILE),
            find_runtime(),
            default_enabled,
        ))
    }

    /// Construct the service with explicit dependencies. The daemon uses
    /// `from_env`; tests and embedders use this constructor without mutating the
    /// process environment.
    pub fn new(
        settings_path: PathBuf,
        runtime_path: Option<PathBuf>,
        default_enabled: bool,
    ) -> Self {
        Self {
            settings_path,
            runtime_path,
            default_enabled,
        }
    }

    pub fn status(&self) -> Result<Value> {
        Ok(json!({
            "enabled": self.read_enabled()?.unwrap_or(self.default_enabled),
            // This wire key is kept for the released CLI. It means that a cua
            // runtime can be mounted, not that vadgr owns a Python virtualenv.
            "venv_ready": self.runtime_path.is_some(),
            "daemon": Value::Null,
            "platform": platform::computer_use_platform(),
        }))
    }

    pub fn entry(&self) -> Result<ComputerUseEntry> {
        Ok(ComputerUseEntry {
            enabled: self.read_enabled()?.unwrap_or(self.default_enabled),
            command: self.runtime_path.clone(),
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

fn find_runtime() -> Option<PathBuf> {
    find_runtime_from(
        std::env::var_os("VADGR_CUA_BIN"),
        std::env::current_dir().ok(),
        std::env::var_os("PATH"),
        std::env::var_os("PATHEXT"),
        cfg!(windows),
    )
}

fn find_runtime_from(
    explicit: Option<OsString>,
    current_dir: Option<PathBuf>,
    path: Option<OsString>,
    path_ext: Option<OsString>,
    windows: bool,
) -> Option<PathBuf> {
    if let Some(explicit) = explicit {
        let explicit = PathBuf::from(explicit);
        return is_executable(&explicit).then_some(explicit);
    }

    if let Some(current_dir) = current_dir {
        let local = local_runtime_path(&current_dir, windows);
        if is_executable(&local) {
            return Some(local);
        }
    }

    find_on_path("vadgr-cua", path.as_deref(), path_ext.as_deref(), windows)
}

fn local_runtime_path(root: &Path, windows: bool) -> PathBuf {
    if windows {
        root.join(".cu_venv").join("Scripts").join("vadgr-cua.exe")
    } else {
        root.join(".cu_venv").join("bin").join("vadgr-cua")
    }
}

fn find_on_path(
    command: &str,
    path: Option<&OsStr>,
    path_ext: Option<&OsStr>,
    windows: bool,
) -> Option<PathBuf> {
    for directory in std::env::split_paths(path?) {
        for name in command_names(command, path_ext, windows) {
            let candidate = directory.join(name);
            if is_executable(&candidate) {
                return Some(candidate);
            }
        }
    }
    None
}

fn command_names(command: &str, path_ext: Option<&OsStr>, windows: bool) -> Vec<OsString> {
    if !windows || Path::new(command).extension().is_some() {
        return vec![command.into()];
    }
    path_ext
        .unwrap_or_else(|| OsStr::new(".COM;.EXE;.BAT;.CMD"))
        .to_string_lossy()
        .split(';')
        .filter_map(|extension| {
            let extension = extension.trim();
            if extension.is_empty() {
                return None;
            }
            let separator = if extension.starts_with('.') { "" } else { "." };
            Some(OsString::from(format!("{command}{separator}{extension}")))
        })
        .collect()
}

#[cfg(unix)]
fn is_executable(path: &Path) -> bool {
    use std::os::unix::fs::PermissionsExt;
    std::fs::metadata(path)
        .map(|metadata| metadata.is_file() && metadata.permissions().mode() & 0o111 != 0)
        .unwrap_or(false)
}

#[cfg(not(unix))]
fn is_executable(path: &Path) -> bool {
    path.is_file()
}

#[cfg(test)]
mod tests {
    use super::{SetupService, command_names, config_home_from, find_on_path, local_runtime_path};
    use serde_json::Value;
    use std::ffi::OsStr;
    use std::path::Path;

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
        let runtime = directory.path().join("vadgr-cua");
        std::fs::write(&runtime, "runtime").unwrap();
        let service =
            SetupService::new(directory.path().join("settings.json"), Some(runtime), true);

        let status = service.status().unwrap();
        assert_eq!(status["enabled"], true);
        assert_eq!(status["venv_ready"], true);
        assert!(status["daemon"].is_null());
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

    #[test]
    fn local_runtime_paths_use_native_components() {
        let root = Path::new("root");
        assert_eq!(
            local_runtime_path(root, false),
            root.join(".cu_venv").join("bin").join("vadgr-cua")
        );
        assert_eq!(
            local_runtime_path(root, true),
            root.join(".cu_venv").join("Scripts").join("vadgr-cua.exe")
        );
    }

    #[test]
    fn windows_command_names_follow_pathext_without_requiring_a_dot() {
        assert_eq!(
            command_names("vadgr-cua", Some(OsStr::new("EXE;.CMD")), true),
            vec!["vadgr-cua.EXE", "vadgr-cua.CMD"]
        );
        assert_eq!(
            command_names("vadgr-cua.exe", Some(OsStr::new(".EXE")), true),
            vec!["vadgr-cua.exe"]
        );
    }

    #[cfg(unix)]
    #[test]
    fn unix_path_discovery_rejects_a_file_without_an_execute_bit() {
        use std::os::unix::fs::PermissionsExt;

        let directory = tempfile::tempdir().unwrap();
        let runtime = directory.path().join("vadgr-cua");
        std::fs::write(&runtime, "runtime").unwrap();
        let path = std::env::join_paths([directory.path()]).unwrap();
        assert_eq!(find_on_path("vadgr-cua", Some(&path), None, false), None);

        std::fs::set_permissions(&runtime, std::fs::Permissions::from_mode(0o700)).unwrap();
        assert_eq!(
            find_on_path("vadgr-cua", Some(&path), None, false),
            Some(runtime)
        );
    }

    #[cfg(windows)]
    #[test]
    fn windows_path_discovery_uses_pathext() {
        let directory = tempfile::tempdir().unwrap();
        let runtime = directory.path().join("vadgr-cua.EXE");
        std::fs::write(&runtime, "runtime").unwrap();
        let path = std::env::join_paths([directory.path()]).unwrap();

        assert_eq!(
            find_on_path("vadgr-cua", Some(&path), Some(OsStr::new(".EXE")), true),
            Some(runtime)
        );
    }
}
