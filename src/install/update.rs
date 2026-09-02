//! Signed update discovery and native vehicle handoff.

use super::{
    InstallReceipt, RELEASE_PUBLIC_KEY, VerifiedManifest, current_target, require_receipt,
};
use anyhow::{Context, Result, anyhow, ensure};
use futures_util::StreamExt;
use serde::Serialize;
use std::path::{Path, PathBuf};

#[derive(Clone, Debug, Serialize)]
pub struct UpdateCheck {
    pub current_version: String,
    pub available_version: String,
    pub update_available: bool,
}

pub fn check_for_updates() -> Result<UpdateCheck> {
    let receipt = require_receipt()?;
    let staging = DownloadStaging::new()?;
    let verified = fetch_manifest(&receipt, &staging)?;
    let state = state_root()?;
    verified.ensure_sequence(&state)?;
    let _ = verified.artifact_for_target(&current_target()?)?;
    Ok(UpdateCheck {
        current_version: receipt.version.clone(),
        available_version: verified.manifest.version.clone(),
        update_available: version_parts(&verified.manifest.version)?
            > version_parts(&receipt.version)?,
    })
}

pub fn apply_update() -> Result<UpdateCheck> {
    let receipt = require_receipt()?;
    let staging = DownloadStaging::new()?;
    let verified = fetch_manifest(&receipt, &staging)?;
    let state = state_root()?;
    verified.ensure_sequence(&state)?;
    let target = current_target()?;
    let artifact = verified.artifact_for_target(&target)?;
    ensure!(
        version_parts(&verified.manifest.version)? > version_parts(&receipt.version)?,
        "no newer signed release is available"
    );
    let artifact_path = staging.root.join(&artifact.name);
    fetch(
        &origin(&receipt)?,
        &artifact.name,
        &artifact_path,
        Some(artifact.size),
    )?;
    verified.verify_bytes_at(&artifact_path, &artifact)?;
    native::verify(&artifact_path, &artifact.kind, receipt.publisher.as_deref())?;
    native::launch(&artifact_path, &artifact.kind)?;
    Ok(UpdateCheck {
        current_version: receipt.version,
        available_version: verified.manifest.version,
        update_available: true,
    })
}

pub(super) fn launch_retained_native(receipt: &InstallReceipt) -> Result<()> {
    let relative = receipt
        .rollback_vehicle
        .as_deref()
        .ok_or_else(|| anyhow!("no retained rollback vehicle is available"))?;
    let relative_path = Path::new(relative);
    ensure!(
        relative_path
            .components()
            .all(|component| matches!(component, std::path::Component::Normal(_))),
        "the retained rollback path is unsafe"
    );
    let vehicle = receipt.install_root.join(relative_path);
    ensure!(
        vehicle.is_file(),
        "the retained rollback vehicle is missing"
    );
    let kind = match receipt.package_kind.as_str() {
        "msi" => "burn",
        "pkg" => "pkg",
        other => return Err(anyhow!("{other} has no native rollback vehicle")),
    };
    native::verify(&vehicle, kind, receipt.publisher.as_deref())?;
    native::launch(&vehicle, kind)
}

pub(super) fn verify_native_vehicle(
    path: &Path,
    kind: &str,
    publisher: Option<&str>,
) -> Result<()> {
    native::verify(path, kind, publisher)
}

fn fetch_manifest(receipt: &InstallReceipt, staging: &DownloadStaging) -> Result<VerifiedManifest> {
    let origin = origin(receipt)?;
    let manifest = staging.root.join("release-manifest.json");
    let signature = staging.root.join("release-manifest.json.minisig");
    fetch(
        &origin,
        "release-manifest.json",
        &manifest,
        Some(4 * 1024 * 1024),
    )?;
    fetch(
        &origin,
        "release-manifest.json.minisig",
        &signature,
        Some(64 * 1024),
    )?;
    VerifiedManifest::open(&manifest, &signature, RELEASE_PUBLIC_KEY)
}

fn origin(receipt: &InstallReceipt) -> Result<String> {
    receipt
        .update_origin
        .as_ref()
        .filter(|value| !value.trim().is_empty())
        .cloned()
        .ok_or_else(|| anyhow!("this installation has no update origin"))
}

fn fetch(origin: &str, name: &str, destination: &Path, limit: Option<u64>) -> Result<()> {
    ensure!(
        !name.contains('/') && !name.contains('\\'),
        "the update file name is unsafe"
    );
    if let Ok(url) = url::Url::parse(origin) {
        ensure!(
            url.scheme() == "https",
            "an update origin must use HTTPS or a local directory"
        );
        let url = format!("{}/{}", origin.trim_end_matches('/'), name);
        let runtime = tokio::runtime::Builder::new_current_thread()
            .enable_all()
            .build()?;
        return runtime.block_on(async {
            let response = reqwest::Client::builder()
                .timeout(std::time::Duration::from_secs(120))
                .build()?
                .get(&url)
                .send()
                .await
                .with_context(|| format!("downloading {name}"))?
                .error_for_status()
                .with_context(|| format!("downloading {name}"))?;
            if let (Some(maximum), Some(length)) = (limit, response.content_length()) {
                ensure!(
                    length <= maximum,
                    "the downloaded {name} is larger than its allowed bound"
                );
            }
            let mut file = std::fs::File::create(destination)
                .with_context(|| format!("creating staged {name}"))?;
            let mut total = 0_u64;
            let mut stream = response.bytes_stream();
            while let Some(chunk) = stream.next().await {
                let chunk = chunk.with_context(|| format!("reading downloaded {name}"))?;
                total = total
                    .checked_add(chunk.len() as u64)
                    .ok_or_else(|| anyhow!("the downloaded size overflowed"))?;
                if let Some(maximum) = limit {
                    ensure!(
                        total <= maximum,
                        "the downloaded {name} is larger than its allowed bound"
                    );
                }
                std::io::Write::write_all(&mut file, &chunk)?;
            }
            std::io::Write::flush(&mut file)?;
            Ok(())
        });
    }
    let root = PathBuf::from(origin);
    ensure!(
        root.is_absolute(),
        "a local update origin must be an absolute directory"
    );
    let source = root.join(name);
    ensure!(
        source.parent() == Some(root.as_path()),
        "the local update file escaped its origin"
    );
    if let Some(maximum) = limit {
        ensure!(
            std::fs::metadata(&source)?.len() <= maximum,
            "the local {name} is larger than its allowed bound"
        );
    }
    std::fs::copy(source, destination).with_context(|| format!("staging local {name}"))?;
    Ok(())
}

fn state_root() -> Result<PathBuf> {
    crate::config::Config::from_env()
        .map_err(|error| anyhow!("resolving Vadgr state: {error}"))?
        .state_home
        .ok_or_else(|| anyhow!("the Vadgr state root is unavailable"))
}

fn version_parts(value: &str) -> Result<(u64, u64, u64)> {
    let parts = value
        .split('.')
        .map(str::parse::<u64>)
        .collect::<std::result::Result<Vec<_>, _>>()?;
    ensure!(parts.len() == 3, "the release version is invalid");
    Ok((parts[0], parts[1], parts[2]))
}

struct DownloadStaging {
    root: PathBuf,
}

impl DownloadStaging {
    fn new() -> Result<Self> {
        let root = std::env::temp_dir().join(format!("vadgr-update-{}", uuid::Uuid::new_v4()));
        std::fs::create_dir(&root).context("creating isolated update staging")?;
        Ok(Self { root })
    }
}

impl Drop for DownloadStaging {
    fn drop(&mut self) {
        if self
            .root
            .file_name()
            .and_then(|value| value.to_str())
            .is_some_and(|value| value.starts_with("vadgr-update-"))
            && self.root.parent() == Some(std::env::temp_dir().as_path())
        {
            let _ = std::fs::remove_dir_all(&self.root);
        }
    }
}

#[cfg(target_os = "windows")]
mod native {
    use super::*;
    use std::process::{Command, Stdio};

    pub fn verify(path: &Path, kind: &str, publisher: Option<&str>) -> Result<()> {
        ensure!(
            kind == "burn",
            "the Windows update vehicle is not a Burn setup"
        );
        let publisher = publisher
            .filter(|value| !value.is_empty())
            .ok_or_else(|| anyhow!("the expected Authenticode publisher is not configured"))?;
        let script = "$s=Get-AuthenticodeSignature -LiteralPath $args[0]; if($s.Status -ne 'Valid' -or $s.SignerCertificate.Subject -ne $args[1]){exit 1}";
        let status = Command::new("powershell.exe")
            .args([
                "-NoLogo",
                "-NoProfile",
                "-NonInteractive",
                "-Command",
                script,
            ])
            .arg(path)
            .arg(publisher)
            .stdout(Stdio::null())
            .stderr(Stdio::null())
            .status()
            .context("verifying the update Authenticode signature")?;
        ensure!(
            status.success(),
            "the update Authenticode signature or publisher is invalid"
        );
        Ok(())
    }

    pub fn launch(path: &Path, kind: &str) -> Result<()> {
        ensure!(
            kind == "burn",
            "the Windows update vehicle is not a Burn setup"
        );
        let status = Command::new(path)
            .status()
            .context("opening the verified Vadgr update")?;
        ensure!(
            status.success(),
            "the Vadgr update installer reported failure"
        );
        Ok(())
    }
}

#[cfg(target_os = "macos")]
mod native {
    use super::*;
    use std::process::{Command, Stdio};
    pub fn verify(path: &Path, kind: &str, publisher: Option<&str>) -> Result<()> {
        ensure!(kind == "pkg", "the macOS update vehicle is not a package");
        let publisher = publisher
            .filter(|value| !value.trim().is_empty())
            .ok_or_else(|| {
                anyhow!("the expected Developer ID Installer identity is not configured")
            })?;
        let signature = Command::new("pkgutil")
            .arg("--check-signature")
            .arg(path)
            .stderr(Stdio::null())
            .output()
            .context("checking the macOS package signature")?;
        ensure!(
            signature.status.success(),
            "macOS rejected the package signature"
        );
        let signature_text = String::from_utf8(signature.stdout)
            .context("the macOS package signature report was not UTF-8")?;
        ensure!(
            signature_text.lines().any(|line| line.trim() == publisher),
            "the macOS package publisher does not match the installed identity"
        );
        let status = Command::new("spctl")
            .args(["--assess", "--type", "install"])
            .arg(path)
            .stdout(Stdio::null())
            .stderr(Stdio::null())
            .status()
            .context("assessing the notarized macOS package")?;
        ensure!(status.success(), "macOS rejected the notarized package");
        Ok(())
    }
    pub fn launch(path: &Path, kind: &str) -> Result<()> {
        ensure!(kind == "pkg", "the macOS update vehicle is not a package");
        let status = Command::new("open")
            .arg("-W")
            .arg(path)
            .status()
            .context("opening the verified Vadgr update")?;
        ensure!(
            status.success(),
            "the Vadgr update installer reported failure"
        );
        Ok(())
    }
}

#[cfg(target_os = "linux")]
mod native {
    use super::*;
    use std::os::unix::fs::PermissionsExt;
    use std::process::Command;
    pub fn verify(_: &Path, kind: &str, _: Option<&str>) -> Result<()> {
        ensure!(
            kind == "appimage",
            "the Linux update vehicle is not an AppImage"
        )
    }
    pub fn launch(path: &Path, kind: &str) -> Result<()> {
        ensure!(
            kind == "appimage",
            "the Linux update vehicle is not an AppImage"
        );
        let mut permissions = std::fs::metadata(path)?.permissions();
        permissions.set_mode(0o755);
        std::fs::set_permissions(path, permissions)?;
        let status = Command::new(path)
            .status()
            .context("opening the verified Vadgr update")?;
        ensure!(
            status.success(),
            "the Vadgr update installer reported failure"
        );
        Ok(())
    }
}

#[cfg(not(any(target_os = "windows", target_os = "macos", target_os = "linux")))]
mod native {
    use super::*;
    pub fn verify(_: &Path, _: &str, _: Option<&str>) -> Result<()> {
        Err(anyhow!("this operating system is unsupported"))
    }
    pub fn launch(_: &Path, _: &str) -> Result<()> {
        Err(anyhow!("this operating system is unsupported"))
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn version_order_is_numeric() {
        assert!(version_parts("0.10.0").unwrap() > version_parts("0.9.9").unwrap());
        assert!(version_parts("0.5").is_err());
    }
}
