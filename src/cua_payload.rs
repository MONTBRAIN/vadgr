//! The pinned, private computer-use payload carried by a vadgr installation.

mod release;

use crate::engine::mcp::ToolServer;
use crate::engine::mcp::cua::CuaServer;
use anyhow::{Context, Result, bail, ensure};
use flate2::read::GzDecoder;
use serde::{Deserialize, Serialize};
use sha2::{Digest, Sha256};
use std::ffi::OsString;
use std::fs::File;
use std::io::Write;
use std::path::{Component, Path, PathBuf};
use std::process::{Command, Output};
use std::sync::OnceLock;

pub const CUA_VERSION: &str = "0.7.8";
pub const PYTHON_VERSION: &str = "3.12.14";
pub const PYTHON_BUILD: &str = "20260825";
pub const UV_VERSION: &str = "0.12.7";
pub const REQUIREMENTS_SHA256: &str =
    "bee2f5d1d104d2b4782f8d185071acd4bf7f2fa14c388318e7c159e7a591727e";

const REQUIREMENTS: &[u8] = include_bytes!("../packaging/cua/requirements.lock");
const BOOTSTRAP: &[u8] = include_bytes!("../packaging/cua/bootstrap.py");
include!(concat!(env!("OUT_DIR"), "/cua_release_pins.rs"));

fn selected_requirements() -> &'static [u8] {
    RELEASE_REQUIREMENTS.unwrap_or(REQUIREMENTS)
}

fn selected_requirements_sha256() -> &'static str {
    static HASH: OnceLock<String> = OnceLock::new();
    HASH.get_or_init(|| hex_sha256(selected_requirements()))
}

fn selected_wheel_manifest_sha256() -> Option<&'static str> {
    static HASH: OnceLock<String> = OnceLock::new();
    RELEASE_WHEEL_MANIFEST.map(|bytes| HASH.get_or_init(|| hex_sha256(bytes)).as_str())
}

#[derive(Clone, Copy, Debug)]
pub struct CuaPins {
    pub cua: &'static str,
    pub python: &'static str,
    pub python_build: &'static str,
    pub uv: &'static str,
    pub requirements_sha256: &'static str,
    pub python_archive_sha256: &'static str,
    pub uv_archive_sha256: &'static str,
    pub wheel_manifest_sha256: Option<&'static str>,
}

#[derive(Clone, Debug, Eq, PartialEq)]
pub struct CuaCommand {
    pub program: PathBuf,
    pub args: Vec<OsString>,
}

#[derive(Clone, Debug, Eq, PartialEq)]
pub struct CuaRuntime {
    interpreter: PathBuf,
    bootstrap: PathBuf,
    environment: PathBuf,
    responsible_host: Option<PathBuf>,
}

#[derive(Debug, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
struct PayloadManifest {
    schema: u32,
    cua_version: String,
    python_version: String,
    python_build: String,
    requirements_sha256: String,
    python_archive_sha256: String,
    uv_archive_sha256: String,
    target: String,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    wheel_manifest_sha256: Option<String>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    installed_inventory_sha256: Option<String>,
}

impl CuaRuntime {
    #[cfg(test)]
    pub(crate) fn for_test(root: &Path) -> Self {
        Self {
            interpreter: root.join("bin/python"),
            bootstrap: root.join("bootstrap.py"),
            environment: root.to_path_buf(),
            responsible_host: None,
        }
    }

    pub fn below_install_root(root: &Path) -> Result<Self> {
        let pins = current_pins()?;
        let cua_root = root.join("lib").join("cua");
        let manifest_path = cua_root.join("payload.json");
        let manifest: PayloadManifest = serde_json::from_slice(
            &std::fs::read(&manifest_path)
                .with_context(|| format!("reading {}", manifest_path.display()))?,
        )
        .with_context(|| format!("parsing {}", manifest_path.display()))?;
        check_field(
            "schema",
            manifest.schema,
            if pins.wheel_manifest_sha256.is_some() {
                2
            } else {
                1
            },
        )?;
        ensure!(
            manifest.wheel_manifest_sha256.as_deref() == pins.wheel_manifest_sha256,
            "CUA wheel manifest differs from compiled release pins"
        );
        if pins.wheel_manifest_sha256.is_some() {
            release::validate_inventory(
                &cua_root,
                target_triple()?,
                manifest
                    .installed_inventory_sha256
                    .as_deref()
                    .context("CUA inventory pin is missing")?,
            )?;
        } else {
            ensure!(
                manifest.installed_inventory_sha256.is_none(),
                "development payload cannot claim release inventory"
            );
        }
        check_field("cua_version", manifest.cua_version.as_str(), pins.cua)?;
        check_field(
            "python_version",
            manifest.python_version.as_str(),
            pins.python,
        )?;
        check_field(
            "python_build",
            manifest.python_build.as_str(),
            pins.python_build,
        )?;
        check_field(
            "requirements_sha256",
            manifest.requirements_sha256.as_str(),
            pins.requirements_sha256,
        )?;
        check_field(
            "python_archive_sha256",
            manifest.python_archive_sha256.as_str(),
            pins.python_archive_sha256,
        )?;
        check_field(
            "uv_archive_sha256",
            manifest.uv_archive_sha256.as_str(),
            pins.uv_archive_sha256,
        )?;
        check_field("target", manifest.target.as_str(), target_triple()?)?;

        let environment = cua_root.join("environments").join(environment_generation());
        let runtime = Self {
            interpreter: environment_python(&environment),
            bootstrap: cua_root.join("bootstrap.py"),
            environment,
            responsible_host: responsible_host(root),
        };
        ensure!(
            runtime.interpreter.is_file(),
            "cua interpreter is missing: {}",
            runtime.interpreter.display()
        );
        #[cfg(unix)]
        {
            validate_payload_root(root, &cua_root)?;
            ensure!(
                std::fs::canonicalize(&runtime.interpreter)?
                    .starts_with(std::fs::canonicalize(&cua_root)?),
                "cua interpreter escapes its owned payload"
            );
            ensure!(
                !std::fs::read_link(&runtime.interpreter)?.is_absolute(),
                "cua interpreter retains an absolute assembly path"
            );
            ensure!(
                !std::fs::read_to_string(runtime.environment.join("pyvenv.cfg"))?
                    .lines()
                    .any(is_python_home_field),
                "cua environment retains assembly home metadata"
            );
        }
        ensure!(
            runtime.bootstrap.is_file(),
            "cua bootstrap is missing: {}",
            runtime.bootstrap.display()
        );
        #[cfg(target_os = "macos")]
        ensure!(
            runtime
                .responsible_host
                .as_ref()
                .is_some_and(|path| path.is_file()),
            "the signed Vadgr Computer Use host is missing"
        );
        Ok(runtime)
    }

    pub fn stdio_command(&self) -> CuaCommand {
        self.command(vec![
            "-I".into(),
            "-B".into(),
            self.bootstrap.as_os_str().to_owned(),
            "computer_use.mcp_server".into(),
            "--transport".into(),
            "stdio".into(),
        ])
    }

    pub fn setup_command(&self, apply: bool) -> CuaCommand {
        let mut args = vec![
            "-I".into(),
            "-B".into(),
            self.bootstrap.as_os_str().to_owned(),
            "computer_use.mcp_server".into(),
        ];
        if cfg!(target_os = "linux") && !is_wsl() {
            args.push("install-deps".into());
            if apply {
                args.push("--yes".into());
            }
        } else if cfg!(target_os = "macos") {
            // `doctor` only reports, and on macOS what it reports is the
            // responsible parent process's grants rather than this
            // interpreter's. Installed from a terminal that already holds
            // Accessibility and Screen Recording, it printed both as granted
            // while the interpreter had neither: the same binary answers false
            // under launchd. The owner was told computer use was ready, and it
            // then failed whenever the daemon started from anywhere else.
            //
            // `setup` fires the two prompts in the order macOS requires and
            // prints the state afterwards, so the owner grants the payload the
            // way every other macOS application asks, and the printed state is
            // the state after they answered.
            args.push("setup".into());
        } else {
            args.push("doctor".into());
        }
        self.command(args)
    }

    pub fn interpreter(&self) -> &Path {
        &self.interpreter
    }

    pub fn environment(&self) -> &Path {
        &self.environment
    }

    fn command(&self, args: Vec<OsString>) -> CuaCommand {
        if let Some(host) = &self.responsible_host {
            let mut hosted = vec![
                OsString::from("--python"),
                self.interpreter.as_os_str().to_owned(),
                OsString::from("--"),
            ];
            hosted.extend(args);
            CuaCommand {
                program: host.clone(),
                args: hosted,
            }
        } else {
            CuaCommand {
                program: self.interpreter.clone(),
                args,
            }
        }
    }
}

fn responsible_host(install_root: &Path) -> Option<PathBuf> {
    if !cfg!(target_os = "macos") {
        return None;
    }
    install_root.ancestors().find_map(|ancestor| {
        (ancestor.file_name().is_some_and(|name| name == "Resources"))
            .then(|| ancestor.parent())
            .flatten()
            .map(|contents| {
                contents
                    .join("Library/LoginItems/Vadgr Computer Use.app/Contents/MacOS/vadgr-cua-host")
            })
    })
}

fn is_wsl() -> bool {
    cfg!(target_os = "linux")
        && std::fs::read_to_string("/proc/version")
            .map(|value| value.to_ascii_lowercase().contains("microsoft"))
            .unwrap_or(false)
}

pub struct CuaPayloadInstaller {
    install_root: PathBuf,
    pins: CuaPins,
    wheelhouse: Option<PathBuf>,
}

impl CuaPayloadInstaller {
    pub fn new(install_root: PathBuf) -> Result<Self> {
        validate_install_root(&install_root)?;
        Ok(Self {
            install_root,
            pins: current_pins()?,
            wheelhouse: None,
        })
    }

    /// Only the secret-free candidate builder supplies this already verified closure.
    pub fn with_wheelhouse(mut self, wheelhouse: Option<PathBuf>) -> Self {
        self.wheelhouse = wheelhouse;
        self
    }

    pub async fn assemble(&self) -> Result<CuaRuntime> {
        if let Ok(runtime) = CuaRuntime::below_install_root(&self.install_root) {
            return Ok(runtime);
        }
        validate_embedded_lock(self.pins.requirements_sha256)?;
        match (self.pins.wheel_manifest_sha256, self.wheelhouse.as_deref()) {
            (Some(hash), Some(wheelhouse)) => release::validate_wheelhouse(
                wheelhouse,
                target_triple()?,
                selected_requirements(),
                hash,
            )?,
            (None, None) => {}
            _ => bail!(
                "release payload assembly requires compiled reviewed pins and a closed wheelhouse"
            ),
        }
        let cua_root = self.install_root.join("lib").join("cua");
        std::fs::create_dir_all(&cua_root)?;
        validate_payload_root(&self.install_root, &cua_root)?;
        let staging = cua_root.join(format!(".staging-{}", uuid::Uuid::new_v4()));
        std::fs::create_dir(&staging).with_context(|| format!("creating {}", staging.display()))?;
        let result = self.assemble_in(&staging).await;
        safe_remove_staging(&self.install_root, &staging)?;
        let mut manifest = result?;
        if self.pins.wheel_manifest_sha256.is_some() {
            manifest.installed_inventory_sha256 =
                Some(release::write_inventory(&cua_root, target_triple()?)?);
        }
        write_manifest_last(&cua_root.join("payload.json"), &manifest)?;
        CuaRuntime::below_install_root(&self.install_root)
    }

    async fn assemble_in(&self, staging: &Path) -> Result<PayloadManifest> {
        let target = target_triple()?;
        let python_name = format!(
            "cpython-{}+{}-{}-install_only.tar.gz",
            self.pins.python, self.pins.python_build, target
        );
        let uv_extension = if cfg!(windows) { "zip" } else { "tar.gz" };
        let uv_name = format!("uv-{target}.{uv_extension}");
        let python_archive = staging.join(&python_name);
        let uv_archive = staging.join(&uv_name);
        download_verified(
            &format!(
                "https://github.com/astral-sh/python-build-standalone/releases/download/{}/{}",
                self.pins.python_build, python_name
            ),
            &python_archive,
            self.pins.python_archive_sha256,
        )
        .await?;
        download_verified(
            &format!(
                "https://github.com/astral-sh/uv/releases/download/{}/{}",
                self.pins.uv, uv_name
            ),
            &uv_archive,
            self.pins.uv_archive_sha256,
        )
        .await?;

        let python_extract = staging.join("python-extract");
        let uv_extract = staging.join("uv-extract");
        extract_archive(&python_archive, &python_extract)?;
        extract_archive(&uv_archive, &uv_extract)?;
        let extracted_python = python_extract.join("python");
        ensure!(
            extracted_python.is_dir(),
            "Python archive has no python directory"
        );
        prune_python_runtime(&extracted_python, target)?;
        let python_final = self
            .install_root
            .join("lib/cua/python")
            .join(self.pins.python);
        install_immutable_directory(&extracted_python, &python_final)?;
        let private_python = base_python(&python_final);
        verify_python(&private_python, self.pins.python)?;

        let uv = find_named_file(&uv_extract, if cfg!(windows) { "uv.exe" } else { "uv" })?
            .context("uv archive has no uv executable")?;
        let environment_staging = staging.join(environment_generation());
        let requirements = staging.join("requirements.lock");
        std::fs::write(&requirements, selected_requirements())?;
        let cache = staging.join("uv-cache");
        let output = clean_command(&uv)
            .args([
                OsString::from("venv"),
                OsString::from("--relocatable"),
                OsString::from("--python"),
                private_python.as_os_str().to_owned(),
                OsString::from("--no-config"),
                OsString::from("--no-project"),
                OsString::from("--no-python-downloads"),
                environment_staging.as_os_str().to_owned(),
            ])
            .env("UV_CACHE_DIR", &cache)
            .output()?;
        require_success("creating the private cua environment", output)?;
        let environment_interpreter = environment_python(&environment_staging);
        let mut sync = clean_command(&uv);
        sync.args([
            OsString::from("pip"),
            OsString::from("sync"),
            OsString::from("--python"),
            environment_interpreter.as_os_str().to_owned(),
            OsString::from("--require-hashes"),
            OsString::from("--only-binary"),
            OsString::from(":all:"),
            OsString::from("--no-config"),
            OsString::from("--no-cache"),
            OsString::from("--no-python-downloads"),
            requirements.as_os_str().to_owned(),
        ])
        .env("UV_CACHE_DIR", &cache);
        if let Some(wheelhouse) = &self.wheelhouse {
            sync.args(["--offline", "--no-index", "--find-links"])
                .arg(wheelhouse);
        }
        let output = sync.output()?;
        require_success("syncing the pinned cua packages", output)?;
        let output = clean_command(&uv)
            .args(["pip", "check", "--no-config", "--offline", "--python"])
            .arg(&environment_interpreter)
            .output()?;
        require_success("checking the complete cua dependency closure", output)?;
        if let (Some(hash), Some(wheelhouse)) = (self.pins.wheel_manifest_sha256, &self.wheelhouse)
        {
            release::validate_wheelhouse(wheelhouse, target, selected_requirements(), hash)?;
        }
        #[cfg(unix)]
        finalize_unix_environment(&environment_staging, &python_final)?;
        prune_python_runtime(&environment_staging, target)?;

        let bootstrap_staging = staging.join("bootstrap.py");
        std::fs::write(&bootstrap_staging, BOOTSTRAP)?;
        validate_environment(
            &environment_interpreter,
            &bootstrap_staging,
            self.pins.python,
            self.pins.cua,
        )?;
        let staged_runtime = CuaRuntime {
            interpreter: environment_interpreter,
            bootstrap: bootstrap_staging,
            environment: environment_staging.clone(),
            responsible_host: responsible_host(&self.install_root),
        };
        let probe_home = staging.join("probe-home");
        std::fs::create_dir(&probe_home)?;
        let probe_environment = vec![
            (
                OsString::from("VADGR_CUA_PAYLOAD_PROBE"),
                OsString::from("1"),
            ),
            (OsString::from("HOME"), probe_home.as_os_str().to_owned()),
            (
                OsString::from("USERPROFILE"),
                probe_home.as_os_str().to_owned(),
            ),
            (OsString::from("APPDATA"), probe_home.as_os_str().to_owned()),
            (
                OsString::from("XDG_CONFIG_HOME"),
                probe_home.as_os_str().to_owned(),
            ),
            (
                OsString::from("VADGR_CUA_BROWSER_DISCOVERY"),
                probe_home.join("browser.json").into_os_string(),
            ),
        ];
        let mut server =
            CuaServer::with_environment(staged_runtime.stdio_command(), probe_environment);
        let tools = tokio::time::timeout(std::time::Duration::from_secs(30), server.list_tools())
            .await
            .context("cua MCP tools/list timed out")??;
        server.close().await;
        ensure!(!tools.is_empty(), "cua MCP tools/list returned no tools");

        let cua_root = self.install_root.join("lib/cua");
        let environment_final = cua_root.join("environments").join(environment_generation());
        install_immutable_directory(&environment_staging, &environment_final)?;
        std::fs::write(cua_root.join("bootstrap.py"), BOOTSTRAP)?;
        install_licenses(
            &python_final,
            &environment_final,
            &cua_root.join("licenses"),
        )?;
        let manifest = PayloadManifest {
            schema: if self.pins.wheel_manifest_sha256.is_some() {
                2
            } else {
                1
            },
            cua_version: self.pins.cua.to_owned(),
            python_version: self.pins.python.to_owned(),
            python_build: self.pins.python_build.to_owned(),
            requirements_sha256: self.pins.requirements_sha256.to_owned(),
            python_archive_sha256: self.pins.python_archive_sha256.to_owned(),
            uv_archive_sha256: self.pins.uv_archive_sha256.to_owned(),
            target: target.to_owned(),
            wheel_manifest_sha256: self.pins.wheel_manifest_sha256.map(str::to_owned),
            installed_inventory_sha256: None,
        };
        Ok(manifest)
    }
}

pub fn install_root_from_executable(executable: &Path) -> Result<PathBuf> {
    let bin = executable
        .parent()
        .context("vadgr executable has no parent directory")?;
    if bin.file_name().is_some_and(|name| name == "bin") {
        return Ok(bin
            .parent()
            .context("vadgr bin directory has no install root")?
            .to_path_buf());
    }
    if cfg!(target_os = "macos")
        && bin.file_name().is_some_and(|name| name == "MacOS")
        && bin
            .parent()
            .is_some_and(|path| path.file_name().is_some_and(|name| name == "Contents"))
    {
        return Ok(bin.parent().expect("checked Contents").join("Resources"));
    }
    if bin.join("lib/cua").is_dir() || bin.join("install-receipt.json").is_file() {
        return Ok(bin.to_path_buf());
    }
    Err(anyhow::anyhow!(
        "vadgr is not running from a complete install root"
    ))
}

fn validate_install_root(root: &Path) -> Result<()> {
    let source_workspace = source_workspace_from_executable();
    validate_install_root_for_workspace(root, source_workspace.as_deref())
}

fn validate_install_root_for_workspace(root: &Path, source_workspace: Option<&Path>) -> Result<()> {
    ensure!(root.is_absolute(), "cua install root must be absolute");
    ensure!(
        root.parent().is_some(),
        "cua install root cannot be a filesystem root"
    );
    let home =
        std::env::var_os(if cfg!(windows) { "USERPROFILE" } else { "HOME" }).map(PathBuf::from);
    ensure!(
        home.as_deref() != Some(root),
        "cua install root cannot be the home directory"
    );
    if let Some(workspace) = source_workspace {
        ensure!(
            root != workspace && !root.starts_with(workspace),
            "cua install root cannot be the workspace or live below it"
        );
    }
    if root.exists() {
        let metadata = std::fs::symlink_metadata(root)?;
        ensure!(
            metadata.is_dir() && !metadata.file_type().is_symlink(),
            "cua install root must be a real directory"
        );
        ensure!(
            dunce::canonicalize(root)? == root,
            "cua install root cannot pass through a symlink"
        );
    }
    Ok(())
}

fn source_workspace_from_executable() -> Option<PathBuf> {
    let executable = dunce::canonicalize(std::env::current_exe().ok()?).ok()?;
    executable.ancestors().skip(1).find_map(|ancestor| {
        let manifest = ancestor.join("Cargo.toml");
        let payload_source = ancestor.join("src/cua_payload.rs");
        (manifest.is_file() && payload_source.is_file()).then(|| ancestor.to_path_buf())
    })
}

fn validate_payload_root(install_root: &Path, cua_root: &Path) -> Result<()> {
    let canonical_install = install_root.canonicalize()?;
    let canonical_cua = cua_root.canonicalize()?;
    ensure!(
        canonical_cua.starts_with(&canonical_install) && canonical_cua != canonical_install,
        "cua payload directory escapes the install root"
    );
    for path in [install_root.join("lib"), cua_root.to_path_buf()] {
        ensure!(
            !std::fs::symlink_metadata(&path)?.file_type().is_symlink(),
            "cua payload path cannot be a symlink: {}",
            path.display()
        );
    }
    Ok(())
}

fn current_pins() -> Result<CuaPins> {
    let (python_archive_sha256, uv_archive_sha256) = match target_triple()? {
        "x86_64-unknown-linux-gnu" => (
            "cbdd2f0cf02f941bc5c81e546f377275e322733abffe805ac29d2b7e8a58f7e3",
            "788f18abea7c5f55d6216e4f5613fd89d4d59b631efeec117b2b07fe72f1da21",
        ),
        "aarch64-unknown-linux-gnu" => (
            "70162d3fa61a7bf52a9f098ad6f46046f9813ab50e0d2b3cfeb81ee1bad78f1c",
            "66393193038dd7eb108abd7a218d9cec04ac70ab98242b0720fa94de19223b7c",
        ),
        "x86_64-apple-darwin" => (
            "65da7bc373ea36cb7e413f2a20bcced9eeb7e5a83fa554ce9f6ec79abb8d7e31",
            "06b8ae1da8c2661c5434507a66f8c2b0b835933bf955b5958a9ac357a37d1959",
        ),
        "aarch64-apple-darwin" => (
            "62eef3fcf48fa4f792d0d6d267c140b81aaea0edca4ae0641d8021854314f966",
            "127ebdda7ad953cdf198e964b570ea5771b85467ea93eb7cb6d6f8e6f55408f3",
        ),
        "x86_64-pc-windows-msvc" => (
            "15d25c455ea25d6b24d7e58eabdf744fd0db3cfb977934ae08fd2237acd8ccc1",
            "bf1518af459a3915511a11fdc6e2f43ef9a2afa138b9d498eeb9642fe9d85218",
        ),
        "aarch64-pc-windows-msvc" => (
            "57dd692b459609127d1b2d448e2033606da7089b9c5d3f9868a54899a87fad26",
            "1611d0f4be72b0a354ad9a6ae954093dd4c91e93e36b8b490326a05a039ffe14",
        ),
        target => bail!("cua payload does not support target {target}"),
    };
    Ok(CuaPins {
        cua: CUA_VERSION,
        python: PYTHON_VERSION,
        python_build: PYTHON_BUILD,
        uv: UV_VERSION,
        requirements_sha256: selected_requirements_sha256(),
        python_archive_sha256,
        uv_archive_sha256,
        wheel_manifest_sha256: selected_wheel_manifest_sha256(),
    })
}

fn target_triple() -> Result<&'static str> {
    match (std::env::consts::ARCH, std::env::consts::OS) {
        ("x86_64", "linux") => Ok("x86_64-unknown-linux-gnu"),
        ("aarch64", "linux") => Ok("aarch64-unknown-linux-gnu"),
        ("x86_64", "macos") => Ok("x86_64-apple-darwin"),
        ("aarch64", "macos") => Ok("aarch64-apple-darwin"),
        ("x86_64", "windows") => Ok("x86_64-pc-windows-msvc"),
        ("aarch64", "windows") => Ok("aarch64-pc-windows-msvc"),
        (arch, os) => bail!("cua payload does not support {arch}-{os}"),
    }
}

fn environment_generation() -> String {
    let generation = format!("{}-{}", CUA_VERSION, &selected_requirements_sha256()[..12]);
    if cfg!(unix) {
        format!("{generation}-unix-relative-v1")
    } else {
        generation
    }
}

#[cfg(unix)]
fn is_python_home_field(line: &str) -> bool {
    line.split_once('=')
        .is_some_and(|(key, _)| key.trim() == "home")
}

#[cfg(unix)]
fn finalize_unix_environment(environment: &Path, python_root: &Path) -> Result<()> {
    let container = environment
        .parent()
        .context("environment has no staging directory")?;
    ensure!(
        container
            .file_name()
            .is_some_and(|name| name.to_string_lossy().starts_with(".staging-")),
        "only a staged cua environment can be finalized"
    );
    let cua_root =
        std::fs::canonicalize(container.parent().context("staging has no payload root")?)?;
    let canonical_python_root = std::fs::canonicalize(python_root)?;
    let target = std::fs::canonicalize(base_python(python_root))?;
    ensure!(
        canonical_python_root.starts_with(&cua_root)
            && target.starts_with(&canonical_python_root)
            && target.is_file(),
        "base Python escapes its owned payload"
    );
    let relative_target = Path::new("../../..").join(target.strip_prefix(&cua_root)?);
    let interpreter = environment_python(environment);
    ensure!(
        std::fs::symlink_metadata(&interpreter)?
            .file_type()
            .is_symlink(),
        "staged cua interpreter is not a symbolic link"
    );
    ensure!(
        std::fs::canonicalize(
            interpreter
                .parent()
                .context("interpreter has no directory")?
                .join(&relative_target)
        )? == target,
        "relative cua interpreter does not resolve to its private Python"
    );
    let config_path = environment.join("pyvenv.cfg");
    let config = std::fs::read_to_string(&config_path)?;
    let config: String = config
        .split_inclusive('\n')
        .filter(|line| !is_python_home_field(line))
        .collect();
    let staged_link = interpreter.with_file_name(format!(".python-{}", uuid::Uuid::new_v4()));
    std::os::unix::fs::symlink(&relative_target, &staged_link)?;
    std::fs::write(config_path, config)?;
    std::fs::rename(staged_link, interpreter)?;
    Ok(())
}

fn environment_python(environment: &Path) -> PathBuf {
    if cfg!(windows) {
        environment.join("Scripts/python.exe")
    } else {
        environment.join("bin/python")
    }
}

fn base_python(runtime: &Path) -> PathBuf {
    if cfg!(windows) {
        runtime.join("python.exe")
    } else {
        runtime.join("bin/python3")
    }
}

fn check_field<T: std::fmt::Display + PartialEq>(name: &str, actual: T, expected: T) -> Result<()> {
    ensure!(
        actual == expected,
        "cua payload {name} mismatch: expected {expected}, found {actual}"
    );
    Ok(())
}

fn validate_embedded_lock(expected: &str) -> Result<()> {
    check_field(
        "requirements_sha256",
        hex_sha256(selected_requirements()),
        expected.to_owned(),
    )
}

async fn download_verified(url: &str, path: &Path, expected: &str) -> Result<()> {
    let response = reqwest::Client::new()
        .get(url)
        .send()
        .await
        .with_context(|| format!("downloading {url}"))?
        .error_for_status()
        .with_context(|| format!("downloading {url}"))?;
    let bytes = response
        .bytes()
        .await
        .with_context(|| format!("reading {url}"))?;
    check_field("archive sha256", hex_sha256(&bytes), expected.to_owned())?;
    std::fs::write(path, &bytes).with_context(|| format!("writing {}", path.display()))
}

fn hex_sha256(bytes: &[u8]) -> String {
    Sha256::digest(bytes)
        .iter()
        .map(|byte| format!("{byte:02x}"))
        .collect()
}

fn extract_archive(archive: &Path, destination: &Path) -> Result<()> {
    std::fs::create_dir(destination)?;
    if archive
        .extension()
        .is_some_and(|extension| extension == "zip")
    {
        extract_zip(archive, destination)
    } else {
        extract_tar_gz(archive, destination)
    }
}

fn extract_tar_gz(archive: &Path, destination: &Path) -> Result<()> {
    let mut archive = tar::Archive::new(GzDecoder::new(File::open(archive)?));
    for entry in archive.entries()? {
        let mut entry = entry?;
        let path = entry.path()?.into_owned();
        validate_archive_path(&path)?;
        if let Some(link) = entry.link_name()? {
            validate_archive_link(&path, &link, entry.header().entry_type().is_hard_link())?;
        }
        ensure!(
            entry.unpack_in(destination)?,
            "archive entry escaped staging: {}",
            path.display()
        );
    }
    Ok(())
}

fn extract_zip(archive: &Path, destination: &Path) -> Result<()> {
    let mut archive = zip::ZipArchive::new(File::open(archive)?)?;
    for index in 0..archive.len() {
        let mut entry = archive.by_index(index)?;
        let path = entry
            .enclosed_name()
            .context("zip entry has an unsafe path")?
            .to_path_buf();
        validate_archive_path(&path)?;
        let output = destination.join(path);
        if entry.is_dir() {
            std::fs::create_dir_all(&output)?;
        } else {
            std::fs::create_dir_all(output.parent().context("zip entry has no parent")?)?;
            let mut file = File::create(&output)?;
            std::io::copy(&mut entry, &mut file)?;
        }
    }
    Ok(())
}

fn validate_archive_path(path: &Path) -> Result<()> {
    ensure!(!path.is_absolute(), "archive contains an absolute path");
    ensure!(
        path.components()
            .all(|component| matches!(component, Component::Normal(_) | Component::CurDir)),
        "archive contains a parent or platform path: {}",
        path.display()
    );
    Ok(())
}

fn validate_archive_link(entry: &Path, link: &Path, hard_link: bool) -> Result<()> {
    ensure!(!link.is_absolute(), "archive contains an absolute link");
    let base = if hard_link {
        PathBuf::new()
    } else {
        entry
            .parent()
            .unwrap_or_else(|| Path::new(""))
            .to_path_buf()
    };
    let combined = base.join(link);
    let mut depth = 0usize;
    for component in combined.components() {
        match component {
            Component::Normal(_) => depth += 1,
            Component::CurDir => {}
            Component::ParentDir if depth > 0 => depth -= 1,
            Component::ParentDir => bail!("archive link escapes staging: {}", link.display()),
            Component::RootDir | Component::Prefix(_) => {
                bail!("archive contains an absolute or platform link")
            }
        }
    }
    Ok(())
}

fn find_named_file(root: &Path, name: &str) -> Result<Option<PathBuf>> {
    for entry in std::fs::read_dir(root)? {
        let path = entry?.path();
        if path.is_dir() {
            if let Some(found) = find_named_file(&path, name)? {
                return Ok(Some(found));
            }
        } else if path.file_name().is_some_and(|candidate| candidate == name) {
            return Ok(Some(path));
        }
    }
    Ok(None)
}

fn install_immutable_directory(source: &Path, destination: &Path) -> Result<()> {
    std::fs::create_dir_all(
        destination
            .parent()
            .context("payload directory has no parent")?,
    )?;
    if destination.exists() {
        let aside = destination.with_extension(format!("previous-{}", uuid::Uuid::new_v4()));
        std::fs::rename(destination, &aside)?;
        std::fs::rename(source, destination)?;
        std::fs::remove_dir_all(aside)?;
    } else {
        std::fs::rename(source, destination)?;
    }
    Ok(())
}

fn clean_command(program: &Path) -> Command {
    let mut command = Command::new(program);
    for (key, _) in std::env::vars_os() {
        if removes_owner_python_environment(&key.to_string_lossy()) {
            command.env_remove(key);
        }
    }
    command
}

fn removes_owner_python_environment(name: &str) -> bool {
    let name = name.to_ascii_uppercase();
    name == "VIRTUAL_ENV"
        || name.starts_with("PYTHON")
        || name.starts_with("PIP_")
        || name.starts_with("UV_")
}

fn require_success(action: &str, output: Output) -> Result<()> {
    if output.status.success() {
        return Ok(());
    }
    bail!(
        "failed while {action}: {}",
        String::from_utf8_lossy(&output.stderr).trim()
    )
}

fn verify_python(python: &Path, expected: &str) -> Result<()> {
    let output = Command::new(python).arg("--version").output()?;
    ensure!(
        output.status.success(),
        "failed while checking the private Python: {}",
        String::from_utf8_lossy(&output.stderr).trim()
    );
    let actual = format!(
        "{}{}",
        String::from_utf8_lossy(&output.stdout),
        String::from_utf8_lossy(&output.stderr)
    );
    ensure!(
        actual.trim() == format!("Python {expected}"),
        "private Python version mismatch: {}",
        actual.trim()
    );
    Ok(())
}

fn validate_environment(
    python: &Path,
    bootstrap: &Path,
    python_pin: &str,
    cua_pin: &str,
) -> Result<()> {
    let code = format!(
        "import importlib.metadata,sys; assert sys.version.split()[0] == {python_pin:?}; assert importlib.metadata.version('vadgr-computer-use') == {cua_pin:?}"
    );
    require_success(
        "validating private Python and cua versions",
        Command::new(python)
            .args(["-I", "-B", "-c", &code])
            .output()?,
    )?;
    require_success(
        "running cua doctor",
        Command::new(python)
            .arg("-I")
            .arg("-B")
            .arg(bootstrap)
            .arg("doctor")
            .output()?,
    )
}

fn install_licenses(python_root: &Path, environment: &Path, destination: &Path) -> Result<()> {
    let python_licenses = destination.join("python");
    let package_licenses = destination.join("python-packages");
    std::fs::create_dir_all(&python_licenses)?;
    std::fs::create_dir_all(&package_licenses)?;
    if let Some(license) = find_named_file(python_root, "LICENSE")? {
        std::fs::copy(license, python_licenses.join("LICENSE"))?;
    }
    copy_license_files(environment, environment, &package_licenses)?;
    Ok(())
}

fn copy_license_files(root: &Path, current: &Path, destination: &Path) -> Result<()> {
    for entry in std::fs::read_dir(current)? {
        let path = entry?.path();
        if path.is_dir() {
            copy_license_files(root, &path, destination)?;
        } else if path
            .file_name()
            .and_then(|name| name.to_str())
            .is_some_and(|name| name.to_ascii_lowercase().starts_with("license"))
        {
            let relative = path.strip_prefix(root)?;
            let flattened = relative.to_string_lossy().replace(['/', '\\'], "__");
            std::fs::copy(&path, destination.join(flattened))?;
        }
    }
    Ok(())
}

fn write_manifest_last(path: &Path, manifest: &PayloadManifest) -> Result<()> {
    let temporary = path.with_extension(format!("tmp-{}", uuid::Uuid::new_v4()));
    let mut file = File::create(&temporary)?;
    file.write_all(&serde_json::to_vec_pretty(manifest)?)?;
    file.sync_all()?;
    #[cfg(windows)]
    if path.exists() {
        std::fs::remove_file(path)?;
    }
    std::fs::rename(temporary, path)?;
    Ok(())
}

fn collect_regular_files(root: &Path, files: &mut Vec<PathBuf>) -> Result<()> {
    for entry in std::fs::read_dir(root)? {
        let path = entry?.path();
        let metadata = std::fs::symlink_metadata(&path)?;
        if metadata.file_type().is_symlink() {
            // The standalone Unix runtime uses relative executable links.
            ensure!(
                !cfg!(windows) && !path.is_dir(),
                "linked Python directory refused"
            );
            continue;
        }
        if metadata.is_dir() {
            collect_regular_files(&path, files)?;
        } else {
            ensure!(metadata.is_file(), "special Python file refused");
            files.push(path);
        }
    }
    Ok(())
}

fn prune_python_runtime(root: &Path, target: &str) -> Result<()> {
    let canonical_root = root.canonicalize()?;
    let mut files = Vec::new();
    collect_regular_files(root, &mut files)?;
    for path in files {
        let relative = path
            .strip_prefix(root)?
            .to_string_lossy()
            .replace('\\', "/");
        let lower = relative.to_ascii_lowercase();
        let name = lower.rsplit('/').next().unwrap_or("");
        let development = lower.ends_with(".pdb")
            || lower.ends_with(".pyc")
            || lower.ends_with(".pyo")
            || lower
                .split('/')
                .any(|part| matches!(part, "test" | "tests" | "__pycache__" | "idle_test"))
            || (lower.starts_with("dlls/")
                && (name.starts_with("_test") || name.starts_with("_ctypes_test")));
        let launcher = lower.contains("/pip/_vendor/distlib/") && lower.ends_with(".exe");
        let allowed_launcher = match target {
            "x86_64-pc-windows-msvc" => matches!(name, "t64.exe" | "w64.exe"),
            "aarch64-pc-windows-msvc" => matches!(name, "t64-arm.exe" | "w64-arm.exe"),
            _ => false,
        };
        if development || (launcher && !allowed_launcher) {
            ensure!(
                path.canonicalize()?.starts_with(&canonical_root),
                "Python cleanup escaped staging"
            );
            std::fs::remove_file(path)?;
        }
    }
    Ok(())
}

fn safe_remove_staging(root: &Path, staging: &Path) -> Result<()> {
    let expected_parent = root.join("lib/cua");
    ensure!(
        staging.parent() == Some(expected_parent.as_path())
            && staging
                .file_name()
                .is_some_and(|name| name.to_string_lossy().starts_with(".staging-")),
        "refusing to clean a path outside cua staging"
    );
    if staging.exists() {
        validate_payload_root(root, &expected_parent)?;
        ensure!(
            !std::fs::symlink_metadata(staging)?.file_type().is_symlink(),
            "refusing to clean a staging symlink"
        );
        ensure!(
            staging
                .canonicalize()?
                .starts_with(expected_parent.canonicalize()?),
            "refusing to clean a staging path outside the install root"
        );
        std::fs::remove_dir_all(staging)?;
    }
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn release_runtime_excludes_debug_cache_tests_and_foreign_launcher_templates() {
        let root = tempfile::tempdir().unwrap();
        for name in [
            "DLLs/_ssl.pdb",
            "DLLs/_testcapi.pyd",
            "DLLs/_ctypes_test.pyd",
            "Lib/test/test_ssl.py",
            "Lib/json/tests/test_decode.py",
            "Lib/site-packages/example/test/helper.py",
            "Lib/json/__pycache__/decoder.cpython-312.pyc",
            "Lib/site-packages/pip/_vendor/distlib/t32.exe",
            "Lib/site-packages/pip/_vendor/distlib/t64-arm.exe",
            "Lib/site-packages/pip/_vendor/distlib/w32.exe",
            "Lib/site-packages/pip/_vendor/distlib/w64-arm.exe",
            "DLLs/_ssl.pyd",
            "Lib/json/decoder.py",
            "Lib/site-packages/pip/_vendor/distlib/t64.exe",
            "LICENSE.txt",
        ] {
            let path = root.path().join(name);
            std::fs::create_dir_all(path.parent().unwrap()).unwrap();
            std::fs::write(path, b"fixture").unwrap();
        }
        prune_python_runtime(root.path(), "x86_64-pc-windows-msvc").unwrap();
        let remaining = [
            "DLLs/_ssl.pyd",
            "Lib/json/decoder.py",
            "Lib/site-packages/pip/_vendor/distlib/t64.exe",
            "LICENSE.txt",
        ];
        for name in remaining {
            assert!(root.path().join(name).is_file(), "{name}");
        }
        let mut files = Vec::new();
        collect_regular_files(root.path(), &mut files).unwrap();
        assert_eq!(files.len(), remaining.len());
    }

    #[test]
    fn runtime_launcher_templates_are_selected_for_the_actual_target() {
        for (target, retained) in [
            ("x86_64-pc-windows-msvc", vec!["t64.exe", "w64.exe"]),
            (
                "aarch64-pc-windows-msvc",
                vec!["t64-arm.exe", "w64-arm.exe"],
            ),
            ("x86_64-unknown-linux-gnu", vec![]),
        ] {
            let root = tempfile::tempdir().unwrap();
            let launchers = root.path().join("Lib/site-packages/pip/_vendor/distlib");
            std::fs::create_dir_all(&launchers).unwrap();
            for name in [
                "t32.exe",
                "w32.exe",
                "t64.exe",
                "w64.exe",
                "t64-arm.exe",
                "w64-arm.exe",
            ] {
                std::fs::write(launchers.join(name), b"fixture").unwrap();
            }
            prune_python_runtime(root.path(), target).unwrap();
            let mut names = std::fs::read_dir(launchers)
                .unwrap()
                .map(|entry| entry.unwrap().file_name().to_string_lossy().into_owned())
                .collect::<Vec<_>>();
            names.sort();
            assert_eq!(names, retained);
        }
    }

    #[cfg(unix)]
    fn unix_environment_fixture(root: &Path, container: &str) -> (PathBuf, PathBuf) {
        let python = root.join("python").join(PYTHON_VERSION);
        let environment = root.join(container).join(environment_generation());
        std::fs::create_dir_all(python.join("bin")).unwrap();
        std::fs::create_dir_all(environment.join("bin")).unwrap();
        std::fs::write(python.join("bin/python3.12"), b"private python").unwrap();
        std::os::unix::fs::symlink("python3.12", python.join("bin/python3")).unwrap();
        std::os::unix::fs::symlink(base_python(&python), environment_python(&environment)).unwrap();
        std::fs::write(environment.join("pyvenv.cfg"), format!(
            "home = {}\nimplementation = CPython\nversion_info = {PYTHON_VERSION}\ninclude-system-site-packages = false\nrelocatable = true\n", python.join("bin").display()
        )).unwrap();
        (environment, python)
    }

    #[cfg(unix)]
    #[test]
    fn unix_generation_does_not_reuse_the_legacy_recipe() {
        assert!(environment_generation().ends_with("-unix-relative-v1"));
    }

    #[cfg(unix)]
    #[test]
    fn unix_finalization_never_patches_a_committed_generation() {
        let temporary = tempfile::tempdir().unwrap();
        let (environment, python) = unix_environment_fixture(temporary.path(), "environments");
        let before = std::fs::read(environment.join("pyvenv.cfg")).unwrap();
        assert!(finalize_unix_environment(&environment, &python).is_err());
        assert_eq!(
            std::fs::read(environment.join("pyvenv.cfg")).unwrap(),
            before
        );
        assert!(
            std::fs::read_link(environment_python(&environment))
                .unwrap()
                .is_absolute()
        );
    }

    #[cfg(unix)]
    #[test]
    fn unix_finalization_preserves_metadata_and_survives_generation_moves() {
        let temporary = tempfile::tempdir().unwrap();
        let root = temporary.path().join("original/lib/cua");
        let (environment, python) = unix_environment_fixture(&root, ".staging-test");
        let legacy = root
            .join("environments")
            .join(format!("{CUA_VERSION}-{}", &REQUIREMENTS_SHA256[..12]));
        std::fs::create_dir_all(&legacy).unwrap();
        std::fs::write(legacy.join("unchanged"), b"legacy generation").unwrap();
        finalize_unix_environment(&environment, &python).unwrap();
        let link = std::fs::read_link(environment_python(&environment)).unwrap();
        assert!(
            !link.is_absolute(),
            "the interpreter must not retain the assembly root"
        );
        assert_eq!(link, Path::new("../../../python/3.12.14/bin/python3.12"));
        let config = std::fs::read_to_string(environment.join("pyvenv.cfg")).unwrap();
        assert_eq!(
            config,
            "implementation = CPython\nversion_info = 3.12.14\ninclude-system-site-packages = false\nrelocatable = true\n"
        );
        let final_environment = root.join("environments").join(environment_generation());
        std::fs::rename(&environment, &final_environment).unwrap();
        assert_eq!(
            std::fs::read(legacy.join("unchanged")).unwrap(),
            b"legacy generation"
        );
        let moved = temporary
            .path()
            .join("moved app/Contents/Resources/lib/cua");
        std::fs::create_dir_all(moved.parent().unwrap()).unwrap();
        std::fs::rename(&root, &moved).unwrap();
        assert!(!root.exists());
        assert_eq!(
            std::fs::canonicalize(environment_python(
                &moved.join("environments").join(environment_generation())
            ))
            .unwrap(),
            std::fs::canonicalize(moved.join("python/3.12.14/bin/python3.12")).unwrap()
        );
    }

    #[cfg(unix)]
    #[test]
    fn unix_finalization_refuses_an_external_base_before_mutation() {
        let temporary = tempfile::tempdir().unwrap();
        let (environment, python) =
            unix_environment_fixture(&temporary.path().join("cua"), ".staging-test");
        let outside = temporary.path().join("outside-python");
        std::fs::write(&outside, b"foreign python").unwrap();
        std::fs::remove_file(python.join("bin/python3.12")).unwrap();
        std::os::unix::fs::symlink(&outside, python.join("bin/python3.12")).unwrap();
        let before = std::fs::read(environment.join("pyvenv.cfg")).unwrap();
        assert!(
            finalize_unix_environment(&environment, &python).is_err(),
            "external base must be refused"
        );
        assert_eq!(
            std::fs::read(environment.join("pyvenv.cfg")).unwrap(),
            before
        );
        assert!(
            std::fs::read_link(environment_python(&environment))
                .unwrap()
                .is_absolute()
        );
    }

    #[cfg(unix)]
    #[test]
    fn unix_runtime_refuses_an_existing_external_interpreter() {
        let temporary = tempfile::tempdir().unwrap();
        let root = test_install_root(temporary.path());
        let manifest = valid_payload(&root);
        write_manifest(&root, &manifest);
        let interpreter = environment_python(
            &root
                .join("lib/cua/environments")
                .join(environment_generation()),
        );
        let outside = temporary.path().join("outside-python");
        std::fs::write(&outside, b"foreign python").unwrap();
        std::fs::remove_file(&interpreter).unwrap();
        std::os::unix::fs::symlink(outside, &interpreter).unwrap();
        assert!(
            CuaRuntime::below_install_root(&root).is_err(),
            "a live external interpreter must not satisfy readiness"
        );
    }

    #[cfg(unix)]
    #[test]
    fn unix_runtime_refuses_unrelocatable_metadata_without_modifying_it() {
        let temporary = tempfile::tempdir().unwrap();
        let root = test_install_root(temporary.path());
        let manifest = valid_payload(&root);
        write_manifest(&root, &manifest);
        let environment = root
            .join("lib/cua/environments")
            .join(environment_generation());
        let interpreter = environment_python(&environment);
        let target = std::fs::canonicalize(&interpreter).unwrap();
        std::fs::remove_file(&interpreter).unwrap();
        std::os::unix::fs::symlink(&target, &interpreter).unwrap();
        assert!(
            CuaRuntime::below_install_root(&root)
                .unwrap_err()
                .to_string()
                .contains("absolute assembly path")
        );
        assert_eq!(std::fs::read_link(&interpreter).unwrap(), target);
        std::fs::remove_file(&interpreter).unwrap();
        std::os::unix::fs::symlink("../../../python/3.12.14/bin/python3.12", &interpreter).unwrap();
        std::fs::write(
            environment.join("pyvenv.cfg"),
            "home = obsolete\ninclude-system-site-packages = false\n",
        )
        .unwrap();
        assert!(
            CuaRuntime::below_install_root(&root)
                .unwrap_err()
                .to_string()
                .contains("assembly home metadata")
        );
        assert!(
            std::fs::read_to_string(environment.join("pyvenv.cfg"))
                .unwrap()
                .starts_with("home = obsolete")
        );
    }

    #[cfg(unix)]
    fn copy_unix_fixture(source: &Path, destination: &Path) {
        let metadata = std::fs::symlink_metadata(source).unwrap();
        if metadata.file_type().is_symlink() {
            std::os::unix::fs::symlink(std::fs::read_link(source).unwrap(), destination).unwrap();
        } else if metadata.is_dir() {
            std::fs::create_dir_all(destination).unwrap();
            for entry in std::fs::read_dir(source).unwrap() {
                let entry = entry.unwrap();
                copy_unix_fixture(&entry.path(), &destination.join(entry.file_name()));
            }
        } else {
            std::fs::copy(source, destination).unwrap();
        }
    }

    /// Explicit fixtures: VADGR_TEST_CUA_PAYLOAD is an assembled lib/cua directory;
    /// VADGR_TEST_UV is the pinned uv executable. Runs on macOS and Linux without
    /// downloading packages, importing computer use, or changing either fixture.
    #[cfg(unix)]
    #[test]
    #[ignore = "requires explicit pinned standalone Python, wheel and uv fixtures"]
    fn unix_cold_runtime_closure_with_pinned_fixtures() {
        let fixture = PathBuf::from(
            std::env::var_os("VADGR_TEST_CUA_PAYLOAD").expect("set VADGR_TEST_CUA_PAYLOAD"),
        );
        let uv = PathBuf::from(std::env::var_os("VADGR_TEST_UV").expect("set VADGR_TEST_UV"));
        let pins = current_pins().unwrap();
        let manifest: PayloadManifest =
            serde_json::from_slice(&std::fs::read(fixture.join("payload.json")).unwrap()).unwrap();
        assert_eq!(manifest.python_version, PYTHON_VERSION);
        assert_eq!(manifest.python_build, PYTHON_BUILD);
        assert_eq!(manifest.python_archive_sha256, pins.python_archive_sha256);
        assert_eq!(manifest.requirements_sha256, REQUIREMENTS_SHA256);
        assert_eq!(manifest.uv_archive_sha256, pins.uv_archive_sha256);
        assert_eq!(manifest.target, target_triple().unwrap());
        let version = clean_command(&uv).arg("--version").output().unwrap();
        assert!(version.status.success());
        assert!(String::from_utf8_lossy(&version.stdout).starts_with(&format!("uv {UV_VERSION} ")));
        let temporary = tempfile::tempdir().unwrap();
        let origin = temporary.path().join("assembly origin/lib/cua");
        let python = origin.join("python").join(PYTHON_VERSION);
        copy_unix_fixture(&fixture.join("python").join(PYTHON_VERSION), &python);
        let environment = origin.join(".staging-test").join(environment_generation());
        let home = temporary.path().join("isolated-home");
        std::fs::create_dir(&home).unwrap();
        let output = Command::new(&uv)
            .env_clear()
            .env("HOME", &home)
            .env("PATH", "")
            .env("UV_OFFLINE", "true")
            .env("UV_CACHE_DIR", temporary.path().join("cache"))
            .args([
                "venv",
                "--relocatable",
                "--no-config",
                "--no-project",
                "--no-python-downloads",
                "--python",
            ])
            .arg(base_python(&python))
            .arg(&environment)
            .output()
            .unwrap();
        println!(
            "{}",
            serde_json::json!({"phase":"fresh_venv", "exit_code": output.status.code(), "stdout":String::from_utf8_lossy(&output.stdout), "stderr":String::from_utf8_lossy(&output.stderr)})
        );
        assert!(output.status.success());
        let source_environment = fixture
            .join("environments")
            .join(format!("{CUA_VERSION}-{}", &REQUIREMENTS_SHA256[..12]));
        let source_environment = if source_environment.is_dir() {
            source_environment
        } else {
            fixture.join("environments").join(environment_generation())
        };
        copy_unix_fixture(
            &source_environment.join("lib/python3.12/site-packages"),
            &environment.join("lib/python3.12/site-packages"),
        );
        finalize_unix_environment(&environment, &python).unwrap();
        let final_environment = origin.join("environments").join(environment_generation());
        std::fs::create_dir(origin.join("environments")).unwrap();
        std::fs::rename(environment, final_environment).unwrap();
        let copied = temporary
            .path()
            .join("copied app/Contents/Resources/lib/cua");
        copy_unix_fixture(&origin, &copied);
        std::fs::rename(&origin, temporary.path().join("hidden-origin")).unwrap();
        assert!(!origin.exists());
        let probe = r#"import ctypes, encodings, importlib.metadata, json, pathlib, sqlite3, ssl, sys
root = pathlib.Path(sys.argv[1]).resolve()
paths = [sys.executable, sys.prefix, sys.base_prefix, encodings.__file__, ssl.__file__, sqlite3.__file__, ctypes.__file__, *sys.path]
distributions = sorted((d.metadata['Name'], d.version, str(d.locate_file('').resolve())) for d in importlib.metadata.distributions())
outside = [p for p in paths + [d[2] for d in distributions] if not pathlib.Path(p).resolve().is_relative_to(root)]
print(json.dumps({'python':sys.version.split()[0], 'paths':paths, 'distributions':[(d[0], d[1]) for d in distributions], 'outside':outside}))
assert sys.version.split()[0] == '3.12.14'
assert importlib.metadata.version('vadgr-computer-use') == '0.7.8'
assert not outside
"#;
        let result = Command::new(environment_python(
            &copied.join("environments").join(environment_generation()),
        ))
        .env_clear()
        .env("HOME", &home)
        .env("PATH", "")
        .current_dir(&home)
        .args(["-I", "-B", "-c", probe])
        .arg(&copied)
        .output();
        match result {
            Ok(output) => {
                println!(
                    "{}",
                    serde_json::json!({"phase":"cold_closure", "exit_code":output.status.code(), "stdout":String::from_utf8_lossy(&output.stdout), "stderr":String::from_utf8_lossy(&output.stderr)})
                );
                assert!(output.status.success(), "cold interpreter closure failed");
            }
            Err(error) => {
                println!(
                    "{}",
                    serde_json::json!({"phase":"cold_closure", "exit_code":null, "launch_error":error.to_string(), "raw_os_error":error.raw_os_error()})
                );
                panic!("cold interpreter could not launch: {error}");
            }
        }
    }

    fn valid_payload(root: &Path) -> serde_json::Value {
        let pins = current_pins().unwrap();
        let cua_root = root.join("lib/cua");
        let environment = cua_root.join("environments").join(environment_generation());
        std::fs::create_dir_all(environment_python(&environment).parent().unwrap()).unwrap();
        #[cfg(not(unix))]
        std::fs::write(environment_python(&environment), b"private python").unwrap();
        #[cfg(unix)]
        {
            let (staged, python) = unix_environment_fixture(&cua_root, ".staging-test");
            finalize_unix_environment(&staged, &python).unwrap();
            std::fs::rename(
                environment_python(&staged),
                environment_python(&environment),
            )
            .unwrap();
            std::fs::rename(staged.join("pyvenv.cfg"), environment.join("pyvenv.cfg")).unwrap();
        }
        std::fs::write(cua_root.join("bootstrap.py"), b"bootstrap").unwrap();
        let mut manifest = serde_json::json!({
            "schema": if pins.wheel_manifest_sha256.is_some() { 2 } else { 1 },
            "cua_version": pins.cua,
            "python_version": pins.python,
            "python_build": pins.python_build,
            "requirements_sha256": pins.requirements_sha256,
            "python_archive_sha256": pins.python_archive_sha256,
            "uv_archive_sha256": pins.uv_archive_sha256,
            "target": target_triple().unwrap(),
        });
        if let Some(hash) = pins.wheel_manifest_sha256 {
            manifest["wheel_manifest_sha256"] = hash.into();
            manifest["installed_inventory_sha256"] =
                release::write_inventory(&cua_root, target_triple().unwrap())
                    .unwrap()
                    .into();
        }
        manifest
    }

    fn test_install_root(temporary: &Path) -> PathBuf {
        #[cfg(target_os = "macos")]
        {
            let root = temporary.join("Vadgr.app/Contents/Resources");
            let host = temporary.join("Vadgr.app/Contents/Library/LoginItems/Vadgr Computer Use.app/Contents/MacOS/vadgr-cua-host");
            std::fs::create_dir_all(host.parent().unwrap()).unwrap();
            std::fs::write(host, b"test host").unwrap();
            root
        }
        #[cfg(not(target_os = "macos"))]
        {
            temporary.to_path_buf()
        }
    }

    fn write_manifest(root: &Path, manifest: &serde_json::Value) {
        std::fs::write(
            root.join("lib/cua/payload.json"),
            serde_json::to_vec(manifest).unwrap(),
        )
        .unwrap();
    }

    #[test]
    fn embedded_lock_matches_the_compiled_pin() {
        assert_eq!(hex_sha256(REQUIREMENTS), REQUIREMENTS_SHA256);
        validate_embedded_lock(current_pins().unwrap().requirements_sha256).unwrap();
    }

    #[test]
    fn child_command_is_absolute_and_isolated() {
        let install = tempfile::tempdir().unwrap();
        let runtime = CuaRuntime {
            interpreter: install.path().join("environments/current/bin/python"),
            bootstrap: install.path().join("bootstrap.py"),
            environment: install.path().join("environments/current"),
            responsible_host: None,
        };
        let command = runtime.stdio_command();
        assert!(command.program.is_absolute());
        assert_eq!(command.args[0], "-I");
        assert_eq!(command.args.last().unwrap(), "stdio");
    }

    /// macOS asks the owner for Accessibility and Screen Recording the way
    /// every other application does, by firing the prompts. `doctor` only
    /// reports, and what it reports on macOS is the responsible parent
    /// process's grants: run from a terminal that already holds them it printed
    /// both as granted while this interpreter had neither.
    #[cfg(target_os = "macos")]
    #[test]
    fn macos_setup_asks_the_owner_rather_than_reporting_the_parent() {
        let install = tempfile::tempdir().unwrap();
        let runtime = CuaRuntime {
            interpreter: install.path().join("environments/current/bin/python"),
            bootstrap: install.path().join("bootstrap.py"),
            environment: install.path().join("environments/current"),
            responsible_host: None,
        };
        let command = runtime.setup_command(false);
        assert_eq!(
            command.args.last().unwrap(),
            "setup",
            "macOS must fire the permission prompts, not only report state"
        );
        assert!(
            !command.args.iter().any(|a| a == "doctor"),
            "doctor reports the parent's grants on macOS, so it must not be the setup path"
        );
    }

    /// Windows and WSL keep the reporting path, so their recorded setup output
    /// does not change under this fix.
    #[cfg(any(
        target_os = "windows",
        all(target_os = "linux", not(target_os = "macos"))
    ))]
    #[test]
    fn only_macos_switches_to_the_prompting_setup() {
        let install = tempfile::tempdir().unwrap();
        let runtime = CuaRuntime {
            interpreter: install.path().join("environments/current/bin/python"),
            bootstrap: install.path().join("bootstrap.py"),
            environment: install.path().join("environments/current"),
            responsible_host: None,
        };
        let command = runtime.setup_command(false);
        assert!(
            !command.args.iter().any(|a| a == "setup"),
            "the prompting setup is macOS only"
        );
    }

    #[test]
    fn a_valid_manifest_resolves_only_the_private_generation() {
        let temporary = tempfile::tempdir().unwrap();
        let root = test_install_root(temporary.path());
        let manifest = valid_payload(&root);
        write_manifest(&root, &manifest);

        let runtime = CuaRuntime::below_install_root(&root).unwrap();
        assert!(runtime.interpreter().starts_with(&root));
        assert!(runtime.environment().starts_with(&root));
        #[cfg(not(target_os = "macos"))]
        assert_eq!(
            runtime.stdio_command().program,
            environment_python(runtime.environment())
        );
        #[cfg(target_os = "macos")]
        assert!(
            runtime
                .stdio_command()
                .program
                .ends_with("Vadgr Computer Use.app/Contents/MacOS/vadgr-cua-host")
        );
    }

    #[cfg(target_os = "macos")]
    #[test]
    fn macos_flat_or_hostless_payload_refuses_at_the_host_guard() {
        let temporary = tempfile::tempdir().unwrap();
        for root in [
            temporary.path().join("flat"),
            temporary.path().join("Vadgr.app/Contents/Resources"),
        ] {
            let manifest = valid_payload(&root);
            write_manifest(&root, &manifest);
            let error = CuaRuntime::below_install_root(&root).unwrap_err();
            assert_eq!(
                error.to_string(),
                "the signed Vadgr Computer Use host is missing"
            );
        }
    }

    #[cfg(target_os = "macos")]
    #[test]
    fn macos_ci_staging_resolves_the_same_payload_from_the_installed_cli() {
        let temporary = tempfile::tempdir().unwrap();
        let checkout = temporary.path().join("checkout");
        let binaries = checkout.join("target/release");
        std::fs::create_dir_all(&binaries).unwrap();
        // This fixture checks paths without starting Python or requesting grants.
        for name in ["vadgr", "vadgr-cua-host"] {
            std::fs::write(binaries.join(name), b"fixture executable").unwrap();
        }
        let packaging = checkout.join("packaging/macos");
        std::fs::create_dir_all(&packaging).unwrap();
        for name in ["Vadgr-Info.plist", "CuaHost-Info.plist"] {
            std::fs::copy(
                Path::new(env!("CARGO_MANIFEST_DIR"))
                    .join("packaging/macos")
                    .join(name),
                packaging.join(name),
            )
            .unwrap();
        }
        let workflow = std::fs::read_to_string(
            Path::new(env!("CARGO_MANIFEST_DIR")).join(".github/workflows/ci.yml"),
        )
        .unwrap();
        let step = workflow
            .split_once("- name: Assemble the macOS app without Python tools\n")
            .or_else(|| {
                workflow.split_once(
                    "- name: Assemble the complete clean install on Unix without Python tools\n",
                )
            })
            .unwrap()
            .1;
        let prefix = step
            .split_once("        run: |\n")
            .unwrap()
            .1
            .split_once("          env PATH=")
            .unwrap()
            .0;
        let runner = temporary.path().join("runner");
        std::fs::create_dir(&runner).unwrap();
        let output = Command::new("bash")
            .args(["-euc", &format!("{prefix}\nprintf '%s' \"$install_root\"")])
            .env_clear()
            .env("HOME", temporary.path())
            .env("PATH", "/usr/bin:/bin")
            .env("RUNNER_TEMP", &runner)
            .current_dir(&checkout)
            .output()
            .unwrap();
        assert!(
            output.status.success(),
            "{}",
            String::from_utf8_lossy(&output.stderr)
        );
        let root = PathBuf::from(String::from_utf8(output.stdout).unwrap());
        let manifest = valid_payload(&root);
        write_manifest(&root, &manifest);
        let runtime = CuaRuntime::below_install_root(&root).unwrap();
        let executable = runner.join("vadgr-clean-install/Vadgr.app/Contents/MacOS/vadgr");
        assert!(executable.is_file());
        assert_eq!(install_root_from_executable(&executable).unwrap(), root);
        assert_eq!(
            runtime.stdio_command().program,
            responsible_host(&root).unwrap()
        );
    }

    #[test]
    fn every_manifest_mismatch_fails_closed_and_names_its_field() {
        let cases = [
            (
                "schema",
                serde_json::json!(if current_pins().unwrap().wheel_manifest_sha256.is_some() {
                    1
                } else {
                    2
                }),
            ),
            ("cua_version", serde_json::json!("wrong")),
            ("python_version", serde_json::json!("wrong")),
            ("python_build", serde_json::json!("wrong")),
            ("requirements_sha256", serde_json::json!("wrong")),
            ("python_archive_sha256", serde_json::json!("wrong")),
            ("uv_archive_sha256", serde_json::json!("wrong")),
            ("target", serde_json::json!("wrong")),
        ];
        for (field, wrong) in cases {
            let temporary = tempfile::tempdir().unwrap();
            let root = test_install_root(temporary.path());
            let mut manifest = valid_payload(&root);
            manifest[field] = wrong;
            write_manifest(&root, &manifest);
            let error = CuaRuntime::below_install_root(&root).unwrap_err();
            assert!(
                error.to_string().contains(field),
                "{field} mismatch was reported as {error:#}"
            );
        }
    }

    #[test]
    fn the_committed_pin_record_matches_every_compiled_pin() {
        let pins = current_pins().unwrap();
        let record = include_str!("../packaging/cua/pins.toml");
        for expected in [
            format!("cua = {:?}", pins.cua),
            format!("python = {:?}", pins.python),
            format!("python_build = {:?}", pins.python_build),
            format!("uv = {:?}", pins.uv),
            format!("python_sha256 = {:?}", pins.python_archive_sha256),
            format!("uv_sha256 = {:?}", pins.uv_archive_sha256),
        ] {
            assert!(record.contains(&expected), "pin record lacks {expected}");
        }
    }

    #[test]
    fn the_universal_lock_pins_and_hashes_every_requirement() {
        let lock = String::from_utf8(REQUIREMENTS.to_vec()).unwrap();
        assert!(lock.contains(&format!("vadgr-computer-use=={CUA_VERSION}")));
        assert!(!lock.contains(" @ "));
        let mut stanzas: Vec<Vec<&str>> = Vec::new();
        for line in lock
            .lines()
            .filter(|line| !line.is_empty() && !line.starts_with('#'))
        {
            if line.chars().next().is_some_and(char::is_whitespace) {
                stanzas.last_mut().unwrap().push(line);
            } else {
                stanzas.push(vec![line]);
            }
        }
        for stanza in &stanzas {
            assert!(
                stanza[0].contains("=="),
                "unfixed requirement: {}",
                stanza[0]
            );
            assert!(
                stanza.iter().any(|line| line.contains("--hash=sha256:")),
                "requirement has no hash: {stanza:?}"
            );
        }
        assert!(
            stanzas.len() > 40,
            "lock parsed only {} requirements",
            stanzas.len()
        );
    }

    #[test]
    fn owner_python_and_uv_configuration_is_removed_but_proxy_state_survives() {
        for name in [
            "VIRTUAL_ENV",
            "PYTHONPATH",
            "pythonhome",
            "PIP_INDEX_URL",
            "uv_cache_dir",
        ] {
            assert!(removes_owner_python_environment(name), "kept {name}");
        }
        for name in ["PATH", "HOME", "HTTPS_PROXY", "NO_PROXY", "DISPLAY"] {
            assert!(!removes_owner_python_environment(name), "removed {name}");
        }
    }

    #[test]
    fn unsafe_archive_paths_are_rejected() {
        assert!(validate_archive_path(Path::new("../escape")).is_err());
        assert!(validate_archive_path(Path::new("/escape")).is_err());
        assert!(validate_archive_path(Path::new("safe/file")).is_ok());
    }

    #[test]
    fn cleanup_refuses_the_install_root_and_home() {
        let root = Path::new("/tmp/vadgr-install");
        assert!(safe_remove_staging(root, root).is_err());
        assert!(safe_remove_staging(root, Path::new("/tmp/elsewhere")).is_err());
    }

    #[test]
    fn install_root_refuses_the_workspace_and_children_but_allows_an_external_directory() {
        let workspace = dunce::canonicalize(env!("CARGO_MANIFEST_DIR")).unwrap();
        let outside = tempfile::tempdir().unwrap();
        let outside = dunce::canonicalize(outside.path()).unwrap();
        assert!(validate_install_root_for_workspace(&workspace, Some(&workspace)).is_err());
        assert!(
            validate_install_root_for_workspace(&workspace.join("install"), Some(&workspace))
                .is_err()
        );
        assert!(validate_install_root_for_workspace(&outside, Some(&workspace)).is_ok());
    }

    #[test]
    fn install_root_workspace_is_the_candidate_source_checkout() {
        let expected = dunce::canonicalize(env!("CARGO_MANIFEST_DIR")).unwrap();
        assert_eq!(source_workspace_from_executable(), Some(expected));
    }

    #[cfg(unix)]
    #[test]
    fn payload_and_cleanup_refuse_symlink_escapes() {
        use std::os::unix::fs::symlink;

        let install = tempfile::tempdir().unwrap();
        let outside = tempfile::tempdir().unwrap();
        std::fs::create_dir(install.path().join("lib")).unwrap();
        symlink(outside.path(), install.path().join("lib/cua")).unwrap();
        assert!(validate_payload_root(install.path(), &install.path().join("lib/cua")).is_err());

        std::fs::remove_file(install.path().join("lib/cua")).unwrap();
        std::fs::create_dir(install.path().join("lib/cua")).unwrap();
        let staging = install.path().join("lib/cua/.staging-linked");
        symlink(outside.path(), &staging).unwrap();
        assert!(safe_remove_staging(install.path(), &staging).is_err());
        assert!(outside.path().exists(), "cleanup followed the symlink");
    }
}
