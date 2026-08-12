//! The computer-use setup service, ported from the Python daemon.
//!
//! This module owns the cua virtual environment and the three MCP client
//! configurations. The HTTP route returns what these files say now; it does
//! not echo the requested state.

use md5::{Digest, Md5};
use serde_json::{Value, json};
use std::path::{Path, PathBuf};
use std::process::{Command, Output, Stdio};
use std::time::Duration;
use toml_edit::{Array, DocumentMut, value};
use wait_timeout::ChildExt;

const PACKAGE_SPEC: &str = "vadgr-computer-use>=0.1.0,<0.2.0";
const DEPS_MARKER: &str = ".deps_installed";
const MCP_SERVER_NAME: &str = "vadgr-computer-use";

#[derive(Debug)]
pub struct SetupError(String);

impl std::fmt::Display for SetupError {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        f.write_str(&self.0)
    }
}

impl std::error::Error for SetupError {}

impl From<std::io::Error> for SetupError {
    fn from(error: std::io::Error) -> Self {
        Self(error.to_string())
    }
}

impl From<toml_edit::TomlError> for SetupError {
    fn from(error: toml_edit::TomlError) -> Self {
        Self(error.to_string())
    }
}

#[derive(Clone, Debug)]
pub struct SetupPaths {
    pub project_root: PathBuf,
    pub config_home: PathBuf,
}

impl SetupPaths {
    fn from_env() -> Self {
        let project_root = std::env::var_os("VADGR_PROJECT_ROOT")
            .map(PathBuf::from)
            .unwrap_or_else(|| {
                Path::new(env!("CARGO_MANIFEST_DIR"))
                    .parent()
                    .expect("the Rust crate has a repository parent")
                    .to_path_buf()
            });
        let config_home = std::env::var_os("VADGR_CONFIG_HOME")
            .or_else(|| std::env::var_os("HOME"))
            .or_else(|| std::env::var_os("USERPROFILE"))
            .map(PathBuf::from)
            .unwrap_or_else(|| project_root.clone());
        Self {
            project_root,
            config_home,
        }
    }

    fn venv(&self) -> PathBuf {
        self.project_root.join(".cu_venv")
    }

    fn mcp_json(&self) -> PathBuf {
        self.project_root.join(".mcp.json")
    }

    fn gemini_json(&self) -> PathBuf {
        self.project_root.join(".gemini/settings.json")
    }

    fn codex_toml(&self) -> PathBuf {
        self.config_home.join(".codex/config.toml")
    }
}

#[derive(Clone, Debug)]
pub struct SetupService {
    paths: SetupPaths,
    wsl2: bool,
}

impl SetupService {
    pub fn from_env() -> Self {
        Self {
            paths: SetupPaths::from_env(),
            wsl2: is_wsl2(),
        }
    }

    #[cfg(test)]
    fn new(paths: SetupPaths, wsl2: bool) -> Self {
        Self { paths, wsl2 }
    }

    pub fn status(&self) -> Value {
        let enabled = std::fs::read_to_string(self.paths.mcp_json())
            .ok()
            .and_then(|text| serde_json::from_str::<Value>(&text).ok())
            .and_then(|doc| {
                doc.get("mcpServers")?
                    .as_object()?
                    .get(MCP_SERVER_NAME)
                    .map(|_| true)
            })
            .unwrap_or(false);
        let daemon = if self.wsl2 && enabled {
            self.doctor_status()
        } else {
            None
        };
        json!({
            "enabled": enabled,
            "venv_ready": self.paths.venv().exists(),
            "daemon": daemon,
            "platform": if self.wsl2 { "wsl2" } else { "native" },
        })
    }

    pub fn enable(&self) -> Result<Value, SetupError> {
        if !self.venv_healthy() {
            self.create_venv()?;
        }
        if self.dependencies_need_install()? {
            self.install_package()?;
        }
        self.write_provider_configs()?;
        if self.wsl2 {
            self.run_cua("install-daemon", Duration::from_secs(60));
        }
        Ok(self.status())
    }

    pub fn disable(&self) -> Result<Value, SetupError> {
        if self.wsl2 {
            self.run_cua("stop-daemon", Duration::from_secs(15));
        }
        for path in [self.paths.mcp_json(), self.paths.gemini_json()] {
            match std::fs::remove_file(path) {
                Ok(()) => {}
                Err(error) if error.kind() == std::io::ErrorKind::NotFound => {}
                Err(error) => return Err(error.into()),
            }
        }
        self.remove_codex_section()?;
        Ok(self.status())
    }

    fn venv_bin(&self) -> PathBuf {
        self.paths
            .venv()
            .join(if cfg!(windows) { "Scripts" } else { "bin" })
    }

    fn pip(&self) -> PathBuf {
        self.venv_bin()
            .join(if cfg!(windows) { "pip.exe" } else { "pip" })
    }

    fn cua(&self) -> PathBuf {
        self.venv_bin().join(if cfg!(windows) {
            "vadgr-cua.exe"
        } else {
            "vadgr-cua"
        })
    }

    fn venv_healthy(&self) -> bool {
        self.paths.venv().exists() && self.pip().exists()
    }

    fn dependencies_need_install(&self) -> Result<bool, SetupError> {
        let marker = self.paths.venv().join(DEPS_MARKER);
        match std::fs::read_to_string(marker) {
            Ok(value) => Ok(value.trim() != package_hash()),
            Err(error) if error.kind() == std::io::ErrorKind::NotFound => Ok(true),
            Err(error) => Err(error.into()),
        }
    }

    fn create_venv(&self) -> Result<(), SetupError> {
        let python = if cfg!(windows) { "python" } else { "python3" };
        checked_output(
            Command::new(python)
                .args(["-m", "venv", "--clear"])
                .arg(self.paths.venv()),
            "create the computer-use virtual environment",
        )?;
        Ok(())
    }

    fn install_package(&self) -> Result<(), SetupError> {
        checked_output(
            Command::new(self.pip()).args(["install", "-q", "--upgrade", PACKAGE_SPEC]),
            "install vadgr-computer-use",
        )?;
        std::fs::write(self.paths.venv().join(DEPS_MARKER), package_hash())?;
        Ok(())
    }

    fn doctor_status(&self) -> Option<&'static str> {
        let output = self.run_cua("doctor", Duration::from_secs(10))?;
        if !output.status.success() {
            return None;
        }
        let body: Value = serde_json::from_slice(&output.stdout).ok()?;
        Some(
            if body.get("daemon_running").and_then(Value::as_bool) == Some(true) {
                "running"
            } else {
                "stopped"
            },
        )
    }

    fn run_cua(&self, argument: &str, timeout: Duration) -> Option<Output> {
        let binary = self.cua();
        if !binary.exists() {
            return None;
        }
        let mut child = Command::new(binary)
            .arg(argument)
            .stdout(Stdio::piped())
            .stderr(Stdio::piped())
            .spawn()
            .ok()?;
        match child.wait_timeout(timeout).ok()? {
            Some(_) => child.wait_with_output().ok(),
            None => {
                let _ = child.kill();
                let _ = child.wait();
                None
            }
        }
    }

    fn mcp_document(&self) -> Value {
        json!({
            "mcpServers": {
                MCP_SERVER_NAME: {
                    "type": "stdio",
                    "command": self.cua().to_string_lossy(),
                    "args": ["--transport", "stdio"],
                }
            }
        })
    }

    fn write_provider_configs(&self) -> Result<(), SetupError> {
        write_json(self.paths.mcp_json(), &self.mcp_document())?;

        let mut gemini = self.mcp_document();
        gemini["context"] = json!({"fileFiltering": {"respectGitIgnore": false}});
        write_json(self.paths.gemini_json(), &gemini)?;

        let path = self.paths.codex_toml();
        if let Some(parent) = path.parent() {
            std::fs::create_dir_all(parent)?;
        }
        let existing = std::fs::read_to_string(&path).unwrap_or_default();
        let mut doc = if existing.trim().is_empty() {
            DocumentMut::new()
        } else {
            existing.parse::<DocumentMut>()?
        };
        remove_server_tables(&mut doc);
        doc["mcp_servers"][MCP_SERVER_NAME]["command"] =
            value(self.cua().to_string_lossy().to_string());
        let mut args = Array::new();
        args.push("--transport");
        args.push("stdio");
        doc["mcp_servers"][MCP_SERVER_NAME]["args"] = value(args);
        std::fs::write(path, doc.to_string())?;
        Ok(())
    }

    fn remove_codex_section(&self) -> Result<(), SetupError> {
        let path = self.paths.codex_toml();
        let existing = match std::fs::read_to_string(&path) {
            Ok(value) => value,
            Err(error) if error.kind() == std::io::ErrorKind::NotFound => return Ok(()),
            Err(error) => return Err(error.into()),
        };
        let mut doc = existing.parse::<DocumentMut>()?;
        remove_server_tables(&mut doc);
        std::fs::write(path, doc.to_string())?;
        Ok(())
    }
}

fn remove_server_tables(doc: &mut DocumentMut) {
    if let Some(servers) = doc
        .get_mut("mcp_servers")
        .and_then(toml_edit::Item::as_table_like_mut)
    {
        servers.remove("computer-use");
        servers.remove(MCP_SERVER_NAME);
    }
}

fn write_json(path: PathBuf, value: &Value) -> Result<(), SetupError> {
    if let Some(parent) = path.parent() {
        std::fs::create_dir_all(parent)?;
    }
    let mut encoded = serde_json::to_string_pretty(value).map_err(|e| SetupError(e.to_string()))?;
    encoded.push('\n');
    std::fs::write(path, encoded)?;
    Ok(())
}

fn checked_output(command: &mut Command, operation: &str) -> Result<Output, SetupError> {
    let output = command.output()?;
    if output.status.success() {
        Ok(output)
    } else {
        Err(SetupError(format!(
            "failed to {operation}: {}",
            String::from_utf8_lossy(&output.stderr).trim()
        )))
    }
}

fn package_hash() -> String {
    Md5::digest(PACKAGE_SPEC.as_bytes())
        .iter()
        .map(|byte| format!("{byte:02x}"))
        .collect()
}

fn is_wsl2() -> bool {
    std::fs::read_to_string("/proc/version")
        .map(|value| value.to_lowercase().contains("microsoft"))
        .unwrap_or(false)
}

#[cfg(test)]
mod tests {
    use super::*;

    fn service() -> (tempfile::TempDir, SetupService) {
        let root = tempfile::tempdir().unwrap();
        let paths = SetupPaths {
            project_root: root.path().join("project"),
            config_home: root.path().join("home"),
        };
        std::fs::create_dir_all(&paths.project_root).unwrap();
        (root, SetupService::new(paths, false))
    }

    fn healthy_venv(service: &SetupService) {
        std::fs::create_dir_all(service.venv_bin()).unwrap();
        std::fs::write(service.pip(), "").unwrap();
        std::fs::write(service.cua(), "").unwrap();
        std::fs::write(service.paths.venv().join(DEPS_MARKER), package_hash()).unwrap();
    }

    #[test]
    fn status_matches_the_python_four_field_shape() {
        let (_root, service) = service();
        assert_eq!(
            service.status(),
            json!({
                "enabled": false,
                "venv_ready": false,
                "daemon": null,
                "platform": "native",
            })
        );
    }

    #[test]
    fn enable_writes_all_three_configs_and_returns_the_resulting_state() {
        let (_root, service) = service();
        healthy_venv(&service);
        let status = service.enable().unwrap();
        assert_eq!(status["enabled"], true);
        assert_eq!(status["venv_ready"], true);
        assert!(service.paths.mcp_json().exists());
        assert!(service.paths.gemini_json().exists());
        let codex = std::fs::read_to_string(service.paths.codex_toml()).unwrap();
        assert!(codex.contains("vadgr-computer-use"), "{codex}");
    }

    #[test]
    fn disable_removes_only_the_cua_codex_table_and_preserves_other_settings() {
        let (_root, service) = service();
        healthy_venv(&service);
        std::fs::create_dir_all(service.paths.codex_toml().parent().unwrap()).unwrap();
        std::fs::write(
            service.paths.codex_toml(),
            "model = \"gpt-5.5\"\n\n[mcp_servers.vadgr-computer-use]\ncommand = \"old\"\n",
        )
        .unwrap();
        std::fs::write(
            service.paths.mcp_json(),
            serde_json::to_string(&service.mcp_document()).unwrap(),
        )
        .unwrap();
        let status = service.disable().unwrap();
        assert_eq!(status["enabled"], false);
        let codex = std::fs::read_to_string(service.paths.codex_toml()).unwrap();
        assert!(codex.contains("model = \"gpt-5.5\""));
        assert!(!codex.contains(MCP_SERVER_NAME));
    }
}
