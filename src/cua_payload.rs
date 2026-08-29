//! The pinned, private computer-use payload carried by a vadgr installation.

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

pub const CUA_VERSION: &str = "0.7.4";
pub const PYTHON_VERSION: &str = "3.12.14";
pub const PYTHON_BUILD: &str = "20260825";
pub const UV_VERSION: &str = "0.12.7";
pub const REQUIREMENTS_SHA256: &str =
    "e5aafb05014332bfa46e53083bd4c6999e0114043799e82b51dbf4859c3b25b8";

const REQUIREMENTS: &[u8] = include_bytes!("../packaging/cua/requirements.lock");
const BOOTSTRAP: &[u8] = include_bytes!("../packaging/cua/bootstrap.py");

#[derive(Clone, Copy, Debug)]
pub struct CuaPins {
    pub cua: &'static str,
    pub python: &'static str,
    pub python_build: &'static str,
    pub uv: &'static str,
    pub requirements_sha256: &'static str,
    pub python_archive_sha256: &'static str,
    pub uv_archive_sha256: &'static str,
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
}

#[derive(Debug, Deserialize, Serialize)]
struct PayloadManifest {
    schema: u32,
    cua_version: String,
    python_version: String,
    python_build: String,
    requirements_sha256: String,
    python_archive_sha256: String,
    uv_archive_sha256: String,
    target: String,
}

impl CuaRuntime {
    #[cfg(test)]
    pub(crate) fn for_test(root: &Path) -> Self {
        Self {
            interpreter: root.join("bin/python"),
            bootstrap: root.join("bootstrap.py"),
            environment: root.to_path_buf(),
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
        check_field("schema", manifest.schema, 1)?;
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
        };
        ensure!(
            runtime.interpreter.is_file(),
            "cua interpreter is missing: {}",
            runtime.interpreter.display()
        );
        ensure!(
            runtime.bootstrap.is_file(),
            "cua bootstrap is missing: {}",
            runtime.bootstrap.display()
        );
        Ok(runtime)
    }

    pub fn stdio_command(&self) -> CuaCommand {
        CuaCommand {
            program: self.interpreter.clone(),
            args: vec![
                "-I".into(),
                self.bootstrap.as_os_str().to_owned(),
                "computer_use.mcp_server".into(),
                "--transport".into(),
                "stdio".into(),
            ],
        }
    }

    pub fn setup_command(&self, apply: bool) -> CuaCommand {
        let mut args = vec![
            "-I".into(),
            self.bootstrap.as_os_str().to_owned(),
            "computer_use.mcp_server".into(),
        ];
        if cfg!(target_os = "linux") && !is_wsl() {
            args.push("install-deps".into());
            if apply {
                args.push("--yes".into());
            }
        } else {
            args.push("doctor".into());
        }
        CuaCommand {
            program: self.interpreter.clone(),
            args,
        }
    }

    pub fn interpreter(&self) -> &Path {
        &self.interpreter
    }

    pub fn environment(&self) -> &Path {
        &self.environment
    }
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
}

impl CuaPayloadInstaller {
    pub fn new(install_root: PathBuf) -> Result<Self> {
        validate_install_root(&install_root)?;
        Ok(Self {
            install_root,
            pins: current_pins()?,
        })
    }

    pub async fn assemble(&self) -> Result<CuaRuntime> {
        if let Ok(runtime) = CuaRuntime::below_install_root(&self.install_root) {
            return Ok(runtime);
        }
        validate_embedded_lock(self.pins.requirements_sha256)?;
        let cua_root = self.install_root.join("lib").join("cua");
        std::fs::create_dir_all(&cua_root)?;
        validate_payload_root(&self.install_root, &cua_root)?;
        let staging = cua_root.join(format!(".staging-{}", uuid::Uuid::new_v4()));
        std::fs::create_dir(&staging).with_context(|| format!("creating {}", staging.display()))?;
        let result = self.assemble_in(&staging).await;
        safe_remove_staging(&self.install_root, &staging)?;
        result
    }

    async fn assemble_in(&self, staging: &Path) -> Result<CuaRuntime> {
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
        std::fs::write(&requirements, REQUIREMENTS)?;
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
        let output = clean_command(&uv)
            .args([
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
            .env("UV_CACHE_DIR", &cache)
            .output()?;
        require_success("syncing the pinned cua packages", output)?;

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
            schema: 1,
            cua_version: self.pins.cua.to_owned(),
            python_version: self.pins.python.to_owned(),
            python_build: self.pins.python_build.to_owned(),
            requirements_sha256: self.pins.requirements_sha256.to_owned(),
            python_archive_sha256: self.pins.python_archive_sha256.to_owned(),
            uv_archive_sha256: self.pins.uv_archive_sha256.to_owned(),
            target: target.to_owned(),
        };
        write_manifest_last(&cua_root.join("payload.json"), &manifest)?;
        CuaRuntime::below_install_root(&self.install_root)
    }
}

pub fn install_root_from_executable(executable: &Path) -> Result<PathBuf> {
    let bin = executable
        .parent()
        .context("vadgr executable has no parent directory")?;
    ensure!(
        bin.file_name().is_some_and(|name| name == "bin"),
        "vadgr must run from an install root bin directory"
    );
    Ok(bin
        .parent()
        .context("vadgr bin directory has no install root")?
        .to_path_buf())
}

fn validate_install_root(root: &Path) -> Result<()> {
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
    if let Ok(workspace) = std::env::current_dir() {
        ensure!(
            root != workspace && !root.starts_with(&workspace),
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
            root.canonicalize()? == root,
            "cua install root cannot pass through a symlink"
        );
    }
    Ok(())
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
        requirements_sha256: REQUIREMENTS_SHA256,
        python_archive_sha256,
        uv_archive_sha256,
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
    format!("{}-{}", CUA_VERSION, &REQUIREMENTS_SHA256[..12])
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
        hex_sha256(REQUIREMENTS),
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
        Command::new(python).args(["-I", "-c", &code]).output()?,
    )?;
    require_success(
        "running cua doctor",
        Command::new(python)
            .arg("-I")
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

    fn valid_payload(root: &Path) -> serde_json::Value {
        let pins = current_pins().unwrap();
        let cua_root = root.join("lib/cua");
        let environment = cua_root.join("environments").join(environment_generation());
        std::fs::create_dir_all(environment_python(&environment).parent().unwrap()).unwrap();
        std::fs::write(environment_python(&environment), b"private python").unwrap();
        std::fs::write(cua_root.join("bootstrap.py"), b"bootstrap").unwrap();
        serde_json::json!({
            "schema": 1,
            "cua_version": pins.cua,
            "python_version": pins.python,
            "python_build": pins.python_build,
            "requirements_sha256": pins.requirements_sha256,
            "python_archive_sha256": pins.python_archive_sha256,
            "uv_archive_sha256": pins.uv_archive_sha256,
            "target": target_triple().unwrap(),
        })
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
        validate_embedded_lock(REQUIREMENTS_SHA256).unwrap();
    }

    #[test]
    fn child_command_is_absolute_and_isolated() {
        let runtime = CuaRuntime {
            interpreter: PathBuf::from("/install/lib/cua/environments/current/bin/python"),
            bootstrap: PathBuf::from("/install/lib/cua/bootstrap.py"),
            environment: PathBuf::from("/install/lib/cua/environments/current"),
        };
        let command = runtime.stdio_command();
        assert!(command.program.is_absolute());
        assert_eq!(command.args[0], "-I");
        assert_eq!(command.args.last().unwrap(), "stdio");
    }

    #[test]
    fn a_valid_manifest_resolves_only_the_private_generation() {
        let root = tempfile::tempdir().unwrap();
        let manifest = valid_payload(root.path());
        write_manifest(root.path(), &manifest);

        let runtime = CuaRuntime::below_install_root(root.path()).unwrap();
        assert!(runtime.interpreter().starts_with(root.path()));
        assert!(runtime.environment().starts_with(root.path()));
        assert_eq!(
            runtime.stdio_command().program,
            environment_python(runtime.environment())
        );
    }

    #[test]
    fn every_manifest_mismatch_fails_closed_and_names_its_field() {
        let cases = [
            ("schema", serde_json::json!(2)),
            ("cua_version", serde_json::json!("wrong")),
            ("python_version", serde_json::json!("wrong")),
            ("python_build", serde_json::json!("wrong")),
            ("requirements_sha256", serde_json::json!("wrong")),
            ("python_archive_sha256", serde_json::json!("wrong")),
            ("uv_archive_sha256", serde_json::json!("wrong")),
            ("target", serde_json::json!("wrong")),
        ];
        for (field, wrong) in cases {
            let root = tempfile::tempdir().unwrap();
            let mut manifest = valid_payload(root.path());
            manifest[field] = wrong;
            write_manifest(root.path(), &manifest);
            let error = CuaRuntime::below_install_root(root.path()).unwrap_err();
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
    fn install_root_refuses_the_workspace_and_children_but_allows_its_parent() {
        let workspace = std::env::current_dir().unwrap();
        assert!(validate_install_root(&workspace).is_err());
        assert!(validate_install_root(&workspace.join("install")).is_err());
        assert!(validate_install_root(workspace.parent().unwrap()).is_ok());
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
