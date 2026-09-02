//! Installed-package status and native lifecycle adapters.
//!
//! This module reads package-owned metadata. It does not infer installation
//! ownership from a checkout and it does not open daemon state.

use anyhow::{Context, Result, anyhow, ensure};
use serde::{Deserialize, Serialize};
use sha2::{Digest, Sha256};
use std::io::Read;
use std::path::{Path, PathBuf};

mod archive;
mod manifest;
pub use archive::validate_tar_gz;
mod update;
pub use manifest::{
    Artifact, RELEASE_PUBLIC_KEY, ReleaseManifest, VerifiedArtifact, VerifiedManifest,
    current_target,
};
pub use update::{UpdateCheck, apply_update, check_for_updates};
#[cfg(target_os = "linux")]
mod linux;
#[cfg(target_os = "linux")]
pub use linux::{
    InstallPhase, install_appimage, install_appimage_with_progress, rollback_appimage,
};

const RECEIPT_NAME: &str = "install-receipt.json";
const ACCEPTANCE_NAME: &str = "terms-acceptance.json";

#[derive(Clone, Debug, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub struct TermsAcceptance {
    pub schema: u32,
    pub terms_version: String,
    pub terms_sha256: String,
    pub accepted_at: String,
    pub installer_version: String,
    pub installer_artifact_sha256: String,
    pub install_scope: String,
    pub installation_id: String,
    pub assent_method: String,
}

#[derive(Clone, Debug, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub struct InstallReceipt {
    pub schema: u32,
    pub version: String,
    #[serde(skip)]
    pub install_root: PathBuf,
    pub package_kind: String,
    #[serde(default)]
    pub product_code: Option<String>,
    #[serde(default)]
    pub release_sequence: Option<u64>,
    #[serde(default)]
    pub manifest_sha256: Option<String>,
    #[serde(default)]
    pub update_origin: Option<String>,
    #[serde(default)]
    pub publisher: Option<String>,
    #[serde(default)]
    pub rollback_vehicle: Option<String>,
}

#[derive(Clone, Debug, Default, Serialize)]
pub struct InstallStatus {
    pub installed: bool,
    pub version: String,
    pub package_kind: Option<String>,
    pub install_root: Option<PathBuf>,
    pub launch_at_login: bool,
    pub update_state: String,
    pub lifecycle_available: bool,
    pub legal_available: bool,
    pub update_available: bool,
    pub rollback_available: bool,
}

pub fn status() -> Result<InstallStatus> {
    let Some(receipt) = read_receipt()? else {
        return Ok(InstallStatus {
            version: env!("CARGO_PKG_VERSION").to_owned(),
            update_state: "Development build".to_owned(),
            ..Default::default()
        });
    };
    let legal_available = platform::legal_path(&receipt).is_dir();
    Ok(InstallStatus {
        installed: true,
        version: receipt.version.clone(),
        package_kind: Some(receipt.package_kind.clone()),
        install_root: Some(receipt.install_root.clone()),
        launch_at_login: platform::launch_at_login()?,
        update_state: "No signed update was checked".to_owned(),
        lifecycle_available: matches!(receipt.package_kind.as_str(), "msi" | "pkg" | "appimage"),
        legal_available,
        update_available: receipt.update_origin.is_some(),
        rollback_available: platform::rollback_available(&receipt),
    })
}

pub fn set_launch_at_login(enabled: bool) -> Result<()> {
    let receipt = require_receipt()?;
    platform::set_launch_at_login(enabled, &receipt.install_root)
}

pub fn repair() -> Result<()> {
    let receipt = require_receipt()?;
    platform::repair(&receipt)
}

pub fn rollback() -> Result<()> {
    let receipt = require_receipt()?;
    platform::rollback(&receipt)
}

#[cfg(target_os = "windows")]
pub fn cache_install_vehicle(source: &Path) -> Result<()> {
    let receipt = require_receipt()?;
    platform::cache_install_vehicle(&receipt, source)
}

#[cfg(not(target_os = "windows"))]
pub fn cache_install_vehicle(_source: &Path) -> Result<()> {
    Err(anyhow!(
        "only the committed Windows MSI transaction retains a setup vehicle"
    ))
}

pub fn verify_install_vehicle(source: &Path) -> Result<()> {
    let receipt = require_receipt()?;
    ensure!(
        source.is_absolute() && source.is_file(),
        "the package vehicle is unavailable"
    );
    let kind = match receipt.package_kind.as_str() {
        "msi" => "burn",
        "pkg" => "pkg",
        other => return Err(anyhow!("{other} has no native package vehicle")),
    };
    update::verify_native_vehicle(source, kind, receipt.publisher.as_deref())
}

pub fn uninstall(purge_owner_state: bool) -> Result<()> {
    let receipt = require_receipt()?;
    platform::uninstall(&receipt, purge_owner_state)
}

/// Delete only the resolved default Vadgr owner-state root.
///
/// The public console owns the separate typed confirmation. These path checks
/// remain mandatory so a broken package cannot turn uninstall into a broad
/// recursive delete.
pub fn purge_owner_state() -> Result<()> {
    ensure!(
        std::env::var_os("VADGR_STATE_HOME").is_none(),
        "the package uninstaller refuses to delete an overridden state root"
    );
    let config = crate::config::Config::from_env()
        .map_err(|error| anyhow!("resolving Vadgr state: {error}"))?;
    let root = config
        .state_home
        .ok_or_else(|| anyhow!("the Vadgr state root is unavailable"))?;
    ensure!(
        safe_default_state_root(&root),
        "the resolved owner-state path is not a Vadgr default"
    );
    if !root.exists() {
        return Ok(());
    }
    ensure!(
        !std::fs::symlink_metadata(&root)?.file_type().is_symlink(),
        "the owner-state root is a link"
    );
    std::fs::remove_dir_all(&root).context("deleting the Vadgr owner-state root")
}

fn safe_default_state_root(path: &Path) -> bool {
    if !path.is_absolute() || path.parent().is_none() {
        return false;
    }
    let parts = path
        .components()
        .filter_map(|part| part.as_os_str().to_str())
        .collect::<Vec<_>>();
    if parts.len() < 3 {
        return false;
    }
    parts
        .last()
        .is_some_and(|part| part.eq_ignore_ascii_case("vadgr"))
        || parts.last().is_some_and(|part| *part == "state")
            && parts
                .get(parts.len().saturating_sub(2))
                .is_some_and(|part| part.eq_ignore_ascii_case("vadgr"))
}

pub fn open_legal() -> Result<()> {
    let receipt = require_receipt()?;
    let legal = platform::legal_path(&receipt);
    ensure!(legal.is_dir(), "the installed legal notices are missing");
    platform::open_path(&legal)
}

pub fn terms_acceptance() -> Result<Option<TermsAcceptance>> {
    read_acceptance(&acceptance_path()?)
}

pub fn terms_acceptance_in(state_root: &Path) -> Result<Option<TermsAcceptance>> {
    ensure!(
        state_root.is_absolute(),
        "the Vadgr state root must be absolute"
    );
    read_acceptance(&state_root.join(ACCEPTANCE_NAME))
}

fn read_acceptance(path: &Path) -> Result<Option<TermsAcceptance>> {
    if !path.is_file() {
        return Ok(None);
    }
    let record: TermsAcceptance = serde_json::from_slice(
        &std::fs::read(path).context("reading the terms acceptance record")?,
    )
    .context("parsing the terms acceptance record")?;
    ensure!(
        record.schema == 1,
        "the terms acceptance schema is unsupported"
    );
    ensure!(
        valid_sha256(&record.terms_sha256) && valid_sha256(&record.installer_artifact_sha256),
        "the terms acceptance record contains an invalid digest"
    );
    ensure!(
        record.install_scope == "user",
        "the terms acceptance scope is unsupported"
    );
    Ok(Some(record))
}

pub fn record_terms_acceptance(
    terms_version: &str,
    installer_version: &str,
    terms_file: &Path,
    installer_file: &Path,
) -> Result<TermsAcceptance> {
    record_terms_acceptance_at(
        &acceptance_path()?,
        terms_version,
        installer_version,
        terms_file,
        installer_file,
    )
}

fn record_terms_acceptance_at(
    acceptance_path: &Path,
    terms_version: &str,
    installer_version: &str,
    terms_file: &Path,
    installer_file: &Path,
) -> Result<TermsAcceptance> {
    ensure!(
        !terms_version.trim().is_empty(),
        "the accepted terms version is empty"
    );
    ensure!(
        !installer_version.trim().is_empty(),
        "the installer version is empty"
    );
    ensure!(terms_file.is_file(), "the installed terms file is missing");
    ensure!(
        installer_file.is_file(),
        "the installation vehicle is missing"
    );
    let terms_sha256 = sha256_file(terms_file)?;
    let installer_artifact_sha256 = sha256_file(installer_file)?;
    let previous = read_acceptance(acceptance_path)?;
    if let Some(previous) = previous.as_ref()
        && previous.terms_version == terms_version
        && previous.terms_sha256 == terms_sha256
    {
        return Ok(previous.clone());
    }
    ensure!(
        previous.as_ref().is_none_or(|record| {
            record.terms_version != terms_version || record.terms_sha256 == terms_sha256
        }),
        "the accepted terms bytes changed without a new version"
    );
    let installation_id = previous
        .map(|record| record.installation_id)
        .unwrap_or_else(|| uuid::Uuid::new_v4().to_string());
    let record = TermsAcceptance {
        schema: 1,
        terms_version: terms_version.to_owned(),
        terms_sha256,
        accepted_at: time::OffsetDateTime::now_utc()
            .format(&time::format_description::well_known::Rfc3339)
            .expect("UTC time has an RFC 3339 representation"),
        installer_version: installer_version.to_owned(),
        installer_artifact_sha256,
        install_scope: "user".to_owned(),
        installation_id,
        assent_method: "unchecked_checkbox_then_install".to_owned(),
    };
    write_acceptance(acceptance_path, &record)?;
    Ok(record)
}

fn acceptance_path() -> Result<PathBuf> {
    let config = crate::config::Config::from_env()
        .map_err(|error| anyhow!("resolving Vadgr state: {error}"))?;
    let root = config
        .state_home
        .ok_or_else(|| anyhow!("the Vadgr state root is unavailable"))?;
    Ok(root.join(ACCEPTANCE_NAME))
}

fn write_acceptance(path: &Path, record: &TermsAcceptance) -> Result<()> {
    let parent = path
        .parent()
        .ok_or_else(|| anyhow!("the terms acceptance path has no parent"))?;
    crate::private_fs::create_dir_all(parent).context("creating the Vadgr state root")?;
    let temporary = parent.join(format!(".{ACCEPTANCE_NAME}.{}.tmp", uuid::Uuid::new_v4()));
    let bytes = serde_json::to_vec_pretty(record)?;
    std::fs::write(&temporary, bytes).context("writing the terms acceptance candidate")?;
    crate::private_fs::harden(&temporary).context("protecting the terms acceptance candidate")?;
    if let Err(error) = commit_file(&temporary, path) {
        let _ = std::fs::remove_file(&temporary);
        return Err(error).context("committing the terms acceptance record");
    }
    crate::private_fs::harden(path).context("protecting the terms acceptance record")
}

#[cfg(not(target_os = "windows"))]
fn commit_file(source: &Path, destination: &Path) -> std::io::Result<()> {
    std::fs::rename(source, destination)
}

#[cfg(target_os = "windows")]
fn commit_file(source: &Path, destination: &Path) -> std::io::Result<()> {
    use std::os::windows::ffi::OsStrExt;
    use windows_sys::Win32::Storage::FileSystem::{
        MOVEFILE_REPLACE_EXISTING, MOVEFILE_WRITE_THROUGH, MoveFileExW,
    };

    let source = source
        .as_os_str()
        .encode_wide()
        .chain(std::iter::once(0))
        .collect::<Vec<_>>();
    let destination = destination
        .as_os_str()
        .encode_wide()
        .chain(std::iter::once(0))
        .collect::<Vec<_>>();
    // SAFETY: both buffers are NUL-terminated and live for the call. The two
    // paths were built below the same resolved state directory.
    let moved = unsafe {
        MoveFileExW(
            source.as_ptr(),
            destination.as_ptr(),
            MOVEFILE_REPLACE_EXISTING | MOVEFILE_WRITE_THROUGH,
        )
    };
    if moved == 0 {
        Err(std::io::Error::last_os_error())
    } else {
        Ok(())
    }
}

pub(crate) fn sha256_file(path: &Path) -> Result<String> {
    let mut file = std::fs::File::open(path)
        .with_context(|| format!("opening {} for verification", path.display()))?;
    let mut digest = Sha256::new();
    let mut buffer = [0_u8; 64 * 1024];
    loop {
        let read = file
            .read(&mut buffer)
            .with_context(|| format!("reading {} for verification", path.display()))?;
        if read == 0 {
            break;
        }
        digest.update(&buffer[..read]);
    }
    let digest = digest.finalize();
    let mut encoded = String::with_capacity(64);
    for byte in digest {
        use std::fmt::Write as _;
        write!(&mut encoded, "{byte:02x}").expect("writing to a string cannot fail");
    }
    Ok(encoded)
}

fn valid_sha256(value: &str) -> bool {
    value.len() == 64 && value.chars().all(|character| character.is_ascii_hexdigit())
}

#[cfg(test)]
mod acceptance_tests {
    use super::*;

    #[test]
    fn acceptance_is_idempotent_and_a_new_version_keeps_the_installation_identity() {
        let root = tempfile::tempdir().unwrap();
        let acceptance = root.path().join(ACCEPTANCE_NAME);
        let terms = root.path().join("TERMS.txt");
        let installer = root.path().join("setup.exe");
        std::fs::write(&terms, "reviewed terms one").unwrap();
        std::fs::write(&installer, "installer one").unwrap();

        let first =
            record_terms_acceptance_at(&acceptance, "1.0", "0.5.0", &terms, &installer).unwrap();
        std::fs::write(&installer, "a later copy of the same vehicle").unwrap();
        let repeated =
            record_terms_acceptance_at(&acceptance, "1.0", "0.5.0", &terms, &installer).unwrap();
        assert_eq!(repeated.accepted_at, first.accepted_at);
        assert_eq!(
            repeated.installer_artifact_sha256,
            first.installer_artifact_sha256
        );

        std::fs::write(&terms, "reviewed terms two").unwrap();
        let next =
            record_terms_acceptance_at(&acceptance, "2.0", "0.6.0", &terms, &installer).unwrap();
        assert_eq!(next.installation_id, first.installation_id);
        assert_ne!(next.terms_sha256, first.terms_sha256);
        assert_eq!(
            read_acceptance(&acceptance).unwrap().unwrap().terms_version,
            "2.0"
        );
    }

    #[test]
    fn changed_terms_bytes_need_a_new_version() {
        let root = tempfile::tempdir().unwrap();
        let acceptance = root.path().join(ACCEPTANCE_NAME);
        let terms = root.path().join("TERMS.txt");
        let installer = root.path().join("setup.exe");
        std::fs::write(&terms, "first").unwrap();
        std::fs::write(&installer, "installer").unwrap();
        record_terms_acceptance_at(&acceptance, "1.0", "0.5.0", &terms, &installer).unwrap();

        std::fs::write(&terms, "silently changed").unwrap();
        let error = record_terms_acceptance_at(&acceptance, "1.0", "0.5.0", &terms, &installer)
            .unwrap_err();
        assert!(error.to_string().contains("without a new version"));
    }
}

fn require_receipt() -> Result<InstallReceipt> {
    read_receipt()?
        .ok_or_else(|| anyhow!("package lifecycle is unavailable in this development build"))
}

fn read_receipt() -> Result<Option<InstallReceipt>> {
    let path = receipt_path()?;
    let Some(parent) = path.parent() else {
        return Err(anyhow!("the install receipt path has no parent"));
    };
    if !path.exists() {
        return Ok(None);
    }
    let bytes = std::fs::read(&path).context("reading the install receipt")?;
    let mut receipt: InstallReceipt =
        serde_json::from_slice(&bytes).context("parsing the install receipt")?;
    ensure!(
        receipt.schema == 1,
        "the install receipt schema is unsupported"
    );
    let expected = dunce::canonicalize(parent).context("resolving the executable directory")?;
    ensure!(expected.is_absolute(), "the install root is not absolute");
    receipt.install_root = expected;
    Ok(Some(receipt))
}

fn receipt_path() -> Result<PathBuf> {
    if let Some(root) = std::env::var_os("VADGR_INSTALL_ROOT") {
        let root = PathBuf::from(root);
        ensure!(
            root.is_absolute(),
            "the declared install root is not absolute"
        );
        return Ok(root.join(RECEIPT_NAME));
    }
    let executable = std::env::current_exe().context("finding the Vadgr executable")?;
    let directory = executable
        .parent()
        .ok_or_else(|| anyhow!("the Vadgr executable has no parent directory"))?;
    Ok(directory.join(RECEIPT_NAME))
}

#[cfg(target_os = "windows")]
mod platform {
    use super::*;
    use std::process::{Command, Stdio};

    const RUN_KEY: &str = r"HKCU\Software\Microsoft\Windows\CurrentVersion\Run";
    const RUN_VALUE: &str = "Vadgr";

    pub fn legal_path(receipt: &InstallReceipt) -> PathBuf {
        receipt.install_root.join("legal")
    }

    pub fn rollback_available(receipt: &InstallReceipt) -> bool {
        receipt
            .rollback_vehicle
            .as_deref()
            .is_some_and(|relative| receipt.install_root.join(relative).is_file())
    }

    pub fn rollback(receipt: &InstallReceipt) -> Result<()> {
        super::update::launch_retained_native(receipt)
    }

    pub fn cache_install_vehicle(receipt: &InstallReceipt, source: &Path) -> Result<()> {
        ensure!(
            source.is_absolute() && source.is_file(),
            "the setup source is unavailable"
        );
        let publisher = receipt
            .publisher
            .as_deref()
            .filter(|value| !value.trim().is_empty())
            .ok_or_else(|| anyhow!("the expected Authenticode publisher is not configured"))?;
        super::update::verify_native_vehicle(source, "burn", Some(publisher))?;
        let cache = receipt.install_root.join("cache");
        std::fs::create_dir_all(&cache).context("creating the setup cache")?;
        let current = cache.join("current-setup.exe");
        let previous = cache.join("previous-setup.exe");
        if current.is_file() {
            let previous_candidate =
                cache.join(format!(".previous-setup.{}.tmp", uuid::Uuid::new_v4()));
            std::fs::copy(&current, &previous_candidate)
                .context("staging the prior setup for rollback")?;
            super::update::verify_native_vehicle(&previous_candidate, "burn", Some(publisher))?;
            commit_file(&previous_candidate, &previous)
                .context("retaining the prior setup for rollback")?;
        }
        let candidate = cache.join(format!(".current-setup.{}.tmp", uuid::Uuid::new_v4()));
        std::fs::copy(source, &candidate).context("staging the current setup cache")?;
        super::update::verify_native_vehicle(&candidate, "burn", Some(publisher))?;
        commit_file(&candidate, &current).context("committing the current setup cache")
    }

    pub fn launch_at_login() -> Result<bool> {
        let status = Command::new("reg.exe")
            .args(["query", RUN_KEY, "/v", RUN_VALUE])
            .stdout(Stdio::null())
            .stderr(Stdio::null())
            .status()
            .context("reading the Vadgr Startup Apps entry")?;
        Ok(status.success())
    }

    pub fn set_launch_at_login(enabled: bool, install_root: &Path) -> Result<()> {
        let executable = install_root.join("vadgr-app.exe");
        ensure!(
            executable.is_file(),
            "the installed Vadgr executable is missing"
        );
        let status = if enabled {
            let command = format!("\"{}\" --daemon", executable.display());
            Command::new("reg.exe")
                .args(["add", RUN_KEY, "/v", RUN_VALUE, "/t", "REG_SZ", "/d"])
                .arg(command)
                .arg("/f")
                .status()
        } else {
            Command::new("reg.exe")
                .args(["delete", RUN_KEY, "/v", RUN_VALUE, "/f"])
                .status()
        }
        .context("changing the Vadgr Startup Apps entry")?;
        ensure!(status.success(), "Windows refused the Startup Apps change");
        Ok(())
    }

    pub fn repair(receipt: &InstallReceipt) -> Result<()> {
        run_msiexec(receipt, "/fa", false)
    }

    pub fn uninstall(receipt: &InstallReceipt, purge_owner_state: bool) -> Result<()> {
        run_msiexec(receipt, "/x", purge_owner_state)
    }

    fn run_msiexec(receipt: &InstallReceipt, verb: &str, purge_owner_state: bool) -> Result<()> {
        ensure!(
            receipt.package_kind == "msi",
            "this is not a Windows MSI installation"
        );
        let product_code = receipt
            .product_code
            .as_deref()
            .ok_or_else(|| anyhow!("the Windows product code is missing"))?;
        ensure!(
            valid_product_code(product_code),
            "the Windows product code is invalid"
        );
        let mut command = Command::new("msiexec.exe");
        command.args([verb, product_code, "/passive", "/norestart"]);
        if purge_owner_state {
            command.arg("PURGEOWNERDATA=1");
        }
        let status = command.status().context("starting Windows Installer")?;
        ensure!(status.success(), "Windows Installer returned {status}");
        Ok(())
    }

    fn valid_product_code(value: &str) -> bool {
        value.len() == 38
            && value.starts_with('{')
            && value.ends_with('}')
            && value[1..37].chars().enumerate().all(|(index, character)| {
                matches!(index, 8 | 13 | 18 | 23) && character == '-'
                    || !matches!(index, 8 | 13 | 18 | 23) && character.is_ascii_hexdigit()
            })
    }

    pub fn open_path(path: &Path) -> Result<()> {
        let status = Command::new("explorer.exe")
            .arg(path)
            .status()
            .context("opening the installed legal notices")?;
        ensure!(status.success(), "Windows could not open the legal notices");
        Ok(())
    }

    #[cfg(test)]
    mod tests {
        use super::*;

        #[test]
        fn only_a_guid_can_reach_windows_installer() {
            assert!(valid_product_code("{12345678-1234-1234-1234-123456789ABC}"));
            assert!(!valid_product_code("/quiet C:\\owner"));
            assert!(!valid_product_code("12345678-1234-1234-1234-123456789ABC"));
        }
    }
}

#[cfg(target_os = "linux")]
mod platform {
    use super::*;
    use std::process::{Command, Stdio};

    const AUTOSTART_FILE: &str = "com.montbrain.vadgr.desktop";

    pub fn legal_path(receipt: &InstallReceipt) -> PathBuf {
        receipt.install_root.join("legal")
    }

    pub fn rollback_available(_receipt: &InstallReceipt) -> bool {
        super::linux::rollback_available().unwrap_or(false)
    }

    pub fn rollback(_receipt: &InstallReceipt) -> Result<()> {
        super::linux::rollback_appimage().map(|_| ())
    }

    fn home() -> Result<PathBuf> {
        std::env::var_os("HOME")
            .map(PathBuf::from)
            .filter(|path| path.is_absolute())
            .ok_or_else(|| anyhow!("HOME is unavailable or not absolute"))
    }

    fn config_home() -> Result<PathBuf> {
        Ok(std::env::var_os("XDG_CONFIG_HOME")
            .map(PathBuf::from)
            .filter(|path| path.is_absolute())
            .unwrap_or(home()?.join(".config")))
    }

    fn autostart_path() -> Result<PathBuf> {
        Ok(config_home()?.join("autostart").join(AUTOSTART_FILE))
    }

    pub fn launch_at_login() -> Result<bool> {
        Ok(autostart_path()?.is_file())
    }

    pub fn set_launch_at_login(enabled: bool, install_root: &Path) -> Result<()> {
        let path = autostart_path()?;
        if !enabled {
            if path.exists() {
                std::fs::remove_file(path).context("removing the Vadgr XDG autostart entry")?;
            }
            return Ok(());
        }
        let app_image = install_root.join("Vadgr.AppImage");
        ensure!(
            app_image.is_file(),
            "the installed Vadgr AppImage is missing"
        );
        let command = desktop_exec(&app_image, "--daemon")?;
        let parent = path
            .parent()
            .ok_or_else(|| anyhow!("the XDG autostart path has no parent"))?;
        std::fs::create_dir_all(parent).context("creating the XDG autostart directory")?;
        write_atomic(
            &path,
            format!(
                "[Desktop Entry]\nType=Application\nVersion=1.5\nName=Vadgr\nComment=Start the Vadgr machine daemon\nExec={command}\nTerminal=false\nX-GNOME-Autostart-enabled=true\n"
            ),
        )
    }

    pub fn repair(receipt: &InstallReceipt) -> Result<()> {
        super::linux::repair(receipt)
    }

    pub fn uninstall(receipt: &InstallReceipt, purge_owner_state: bool) -> Result<()> {
        super::linux::uninstall(receipt, purge_owner_state)
    }

    pub fn open_path(path: &Path) -> Result<()> {
        let status = Command::new("xdg-open")
            .arg(path)
            .stdout(Stdio::null())
            .stderr(Stdio::null())
            .status()
            .context("opening the installed legal notices")?;
        ensure!(
            status.success(),
            "the desktop could not open the legal notices"
        );
        Ok(())
    }

    fn desktop_exec(path: &Path, argument: &str) -> Result<String> {
        let raw = path
            .to_str()
            .ok_or_else(|| anyhow!("the installed AppImage path is not valid UTF-8"))?;
        ensure!(
            !raw.chars().any(char::is_control),
            "the installed AppImage path contains a control character"
        );
        let escaped = raw
            .replace('\\', "\\\\")
            .replace('"', "\\\"")
            .replace('`', "\\`")
            .replace('$', "\\$");
        Ok(format!("\"{escaped}\" {argument}"))
    }

    fn write_atomic(path: &Path, contents: String) -> Result<()> {
        let parent = path
            .parent()
            .ok_or_else(|| anyhow!("the launch entry path has no parent"))?;
        let temporary = parent.join(format!(".{AUTOSTART_FILE}.{}.tmp", uuid::Uuid::new_v4()));
        std::fs::write(&temporary, contents).context("writing the XDG autostart candidate")?;
        commit_file(&temporary, path).context("committing the XDG autostart entry")
    }
}

#[cfg(target_os = "macos")]
mod platform {
    use super::*;
    use std::process::{Command, Stdio};

    fn helper(install_root: &Path) -> PathBuf {
        install_root.join("../Helpers/vadgr-login-item")
    }

    pub fn legal_path(receipt: &InstallReceipt) -> PathBuf {
        receipt.install_root.join("../Resources/legal")
    }

    pub fn rollback_available(receipt: &InstallReceipt) -> bool {
        receipt.rollback_vehicle.is_some()
            && std::env::var_os("HOME")
                .map(PathBuf::from)
                .filter(|path| path.is_absolute())
                .is_some_and(|home| {
                    home.join("Library/Application Support/vadgr/package-cache/previous.pkg")
                        .is_file()
                })
    }

    pub fn rollback(receipt: &InstallReceipt) -> Result<()> {
        run_lifecycle(receipt, "rollback", false)
    }

    pub fn launch_at_login() -> Result<bool> {
        let receipt = require_receipt()?;
        let output = Command::new(helper(&receipt.install_root))
            .arg("status")
            .output()
            .context("reading the Vadgr login-item state")?;
        Ok(output.status.success() && String::from_utf8_lossy(&output.stdout).trim() == "enabled")
    }

    pub fn set_launch_at_login(enabled: bool, install_root: &Path) -> Result<()> {
        let helper = helper(install_root);
        ensure!(
            helper.is_file(),
            "the signed Vadgr login-item helper is missing"
        );
        let status = Command::new(helper)
            .arg(if enabled { "enable" } else { "disable" })
            .status()
            .context("changing the Vadgr login item")?;
        ensure!(
            status.success(),
            "macOS did not accept the login-item change"
        );
        Ok(())
    }

    pub fn repair(receipt: &InstallReceipt) -> Result<()> {
        run_lifecycle(receipt, "repair", false)
    }

    pub fn uninstall(receipt: &InstallReceipt, purge_owner_state: bool) -> Result<()> {
        run_lifecycle(receipt, "uninstall", purge_owner_state)
    }

    pub fn open_path(path: &Path) -> Result<()> {
        let status = Command::new("open")
            .arg(path)
            .stdout(Stdio::null())
            .stderr(Stdio::null())
            .status()
            .context("opening the installed legal notices")?;
        ensure!(status.success(), "macOS could not open the legal notices");
        Ok(())
    }

    fn run_lifecycle(receipt: &InstallReceipt, action: &str, purge: bool) -> Result<()> {
        ensure!(
            receipt.package_kind == "pkg",
            "this is not a macOS package installation"
        );
        let helper = receipt.install_root.join("../Helpers/vadgr-lifecycle");
        ensure!(
            helper.is_file(),
            "the signed package lifecycle helper is missing"
        );
        let mut command = Command::new(helper);
        command.arg(action);
        if purge {
            command.arg("--purge-owner-state");
        }
        let status = command
            .status()
            .context("starting the macOS package lifecycle")?;
        ensure!(
            status.success(),
            "the macOS package lifecycle returned {status}"
        );
        Ok(())
    }
}

#[cfg(not(any(target_os = "windows", target_os = "linux", target_os = "macos")))]
mod platform {
    use super::*;
    pub fn legal_path(receipt: &InstallReceipt) -> PathBuf {
        receipt.install_root.join("legal")
    }
    pub fn rollback_available(_: &InstallReceipt) -> bool {
        false
    }
    pub fn rollback(_: &InstallReceipt) -> Result<()> {
        Err(anyhow!("this operating system is unsupported"))
    }
    pub fn launch_at_login() -> Result<bool> {
        Err(anyhow!("this operating system is unsupported"))
    }
    pub fn set_launch_at_login(_: bool, _: &Path) -> Result<()> {
        Err(anyhow!("this operating system is unsupported"))
    }
    pub fn repair(_: &InstallReceipt) -> Result<()> {
        Err(anyhow!("this operating system is unsupported"))
    }
    pub fn uninstall(_: &InstallReceipt, _: bool) -> Result<()> {
        Err(anyhow!("this operating system is unsupported"))
    }
    pub fn open_path(_: &Path) -> Result<()> {
        Err(anyhow!("this operating system is unsupported"))
    }
}
