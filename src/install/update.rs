//! Signed update discovery and native vehicle handoff.

use super::{InstallReceipt, VerifiedManifest, current_target, require_receipt};
use anyhow::{Context, Result, anyhow, ensure};
use futures_util::StreamExt;
use serde::Serialize;
use std::path::{Path, PathBuf};

const LINUX_UPDATE_ORIGIN: &str = "https://github.com/MONTBRAIN/vadgr/releases/latest/download";
const DEVELOPMENT_UPDATE_REFUSAL: &str =
    "Signed updates cannot replace an unsigned development installation.";

#[derive(Clone, Debug, Serialize)]
pub struct UpdateCheck {
    pub current_version: String,
    pub available_version: String,
    pub update_available: bool,
    pub can_install: bool,
}

impl UpdateCheck {
    pub fn install_unavailable_reason(&self) -> Option<&'static str> {
        (!self.can_install).then_some(DEVELOPMENT_UPDATE_REFUSAL)
    }
}

pub fn check_for_updates() -> Result<UpdateCheck> {
    check_for_updates_from(None)
}

pub fn check_for_updates_from(source: Option<&str>) -> Result<UpdateCheck> {
    let receipt = require_receipt()?;
    let source = origin(&receipt, source)?;
    let staging = DownloadStaging::new()?;
    let verified = fetch_manifest(&source, &staging)?;
    let state = state_root()?;
    verified.ensure_sequence(&state)?;
    let _ = verified.artifact_for_target(&current_target()?)?;
    Ok(UpdateCheck {
        current_version: receipt.version.clone(),
        available_version: verified.manifest.version.clone(),
        update_available: version_parts(&verified.manifest.version)?
            > version_parts(&receipt.version)?,
        can_install: receipt.development_receipt_sha256.is_none(),
    })
}

pub fn apply_update() -> Result<UpdateCheck> {
    apply_update_from(None)
}

pub fn apply_update_from(source: Option<&str>) -> Result<UpdateCheck> {
    let receipt = require_receipt()?;
    ensure!(
        receipt.development_receipt_sha256.is_none(),
        DEVELOPMENT_UPDATE_REFUSAL
    );
    let source = origin(&receipt, source)?;
    let staging = DownloadStaging::new()?;
    let verified = fetch_manifest(&source, &staging)?;
    let state = state_root()?;
    verified.ensure_sequence(&state)?;
    let target = current_target()?;
    let artifact = verified.artifact_for_target(&target)?;
    ensure!(
        version_parts(&verified.manifest.version)? > version_parts(&receipt.version)?,
        "no newer signed release is available"
    );
    let artifact_path = staging.root.join(&artifact.name);
    fetch(&source, &artifact.name, &artifact_path, Some(artifact.size))?;
    verified.verify_bytes_at(&artifact_path, &artifact)?;
    native::verify(&artifact_path, &artifact.kind, receipt.publisher.as_deref())?;
    native::launch(&artifact_path, &artifact.kind)?;
    Ok(UpdateCheck {
        current_version: receipt.version,
        available_version: verified.manifest.version,
        update_available: true,
        can_install: true,
    })
}

#[cfg(target_os = "windows")]
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

fn fetch_manifest(origin: &str, staging: &DownloadStaging) -> Result<VerifiedManifest> {
    let manifest = staging.root.join("release-manifest.json");
    let signature = staging.root.join("release-manifest.json.bundle.jsonl");
    fetch(
        origin,
        "release-manifest.json",
        &manifest,
        Some(4 * 1024 * 1024),
    )?;
    fetch(
        origin,
        "release-manifest.json.bundle.jsonl",
        &signature,
        Some(64 * 1024),
    )?;
    VerifiedManifest::open(&manifest, &signature)
}

pub(super) fn origin(receipt: &InstallReceipt, explicit: Option<&str>) -> Result<String> {
    // A source locates bytes; it never grants release authority or changes the receipt.
    let source = explicit
        .or(receipt
            .update_origin
            .as_deref()
            .filter(|value| !value.trim().is_empty()))
        .or_else(|| {
            (cfg!(target_os = "linux") && receipt.package_kind == "appimage")
                .then_some(LINUX_UPDATE_ORIGIN)
        })
        .ok_or_else(|| anyhow!("this installation has no update origin; use --source"))?;
    validate_origin(source)?;
    Ok(source.to_owned())
}

fn validate_origin(source: &str) -> Result<()> {
    // Windows drive and UNC paths must not be interpreted as URL schemes.
    if Path::new(source).is_absolute() {
        return Ok(());
    }
    let url = url::Url::parse(source)
        .map_err(|_| anyhow!("an update source must be HTTPS or an absolute local directory"))?;
    ensure!(
        url.scheme() == "https"
            && url.has_host()
            && !url.cannot_be_a_base()
            && url.username().is_empty()
            && url.password().is_none()
            && url.query().is_none()
            && url.fragment().is_none(),
        "an update source must be HTTPS without credentials, query or fragment, or an absolute local directory"
    );
    Ok(())
}

fn download_failure(error: reqwest::Error) -> anyhow::Error {
    // Source URLs and underlying errors can contain private paths. Retain only
    // a failure category and public HTTP status, including in CLI error chains.
    let reason = if error.is_timeout() {
        "The request timed out. Try again later.".to_owned()
    } else if let Some(status) = error.status() {
        format!(
            "The update server returned HTTP {}. Try again later.",
            status.as_u16()
        )
    } else if error.is_connect() {
        "A connection to the update server could not be established. Try again after checking your connection."
            .to_owned()
    } else {
        "The network request could not be completed. Try again later.".to_owned()
    };
    anyhow!("The update download failed. {reason}")
}

fn fetch(origin: &str, name: &str, destination: &Path, limit: Option<u64>) -> Result<()> {
    ensure!(
        !name.contains('/') && !name.contains('\\'),
        "the update file name is unsafe"
    );
    validate_origin(origin)?;
    if !Path::new(origin).is_absolute() {
        let url = format!("{}/{}", origin.trim_end_matches('/'), name);
        return std::thread::scope(|scope| {
            scope
                .spawn(|| -> Result<()> {
                    let runtime = tokio::runtime::Builder::new_current_thread()
                        .enable_all()
                        .build()?;
                    runtime.block_on(async {
                        let response = reqwest::Client::builder()
                            .timeout(std::time::Duration::from_secs(120))
                            .build()
                            .map_err(download_failure)?
                            .get(&url)
                            .send()
                            .await
                            .map_err(download_failure)?
                            .error_for_status()
                            .map_err(download_failure)?;
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
                            let chunk = chunk.map_err(download_failure)?;
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
                    })
                })
                .join()
                .map_err(|_| anyhow!("the update download worker failed"))?
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
            std::fs::metadata(&source)
                .with_context(|| format!("reading local {name}"))?
                .len()
                <= maximum,
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
        );
        Ok(())
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

    fn receipt() -> InstallReceipt {
        InstallReceipt {
            schema: 1,
            version: "0.5.0".to_owned(),
            install_root: Default::default(),
            package_kind: "appimage".to_owned(),
            product_code: None,
            release_sequence: None,
            manifest_sha256: None,
            development_receipt_sha256: None,
            update_origin: None,
            publisher: None,
            rollback_vehicle: None,
        }
    }

    #[cfg(target_os = "linux")]
    #[test]
    fn linux_update_source_has_a_discovery_default_without_receipt_authority() {
        let mut installed = receipt();
        installed.development_receipt_sha256 = Some("b".repeat(64));
        let before = serde_json::to_vec(&installed).unwrap();
        assert_eq!(
            origin(&installed, None).unwrap(),
            "https://github.com/MONTBRAIN/vadgr/releases/latest/download"
        );
        assert_eq!(serde_json::to_vec(&installed).unwrap(), before);
        assert!(installed.update_origin.is_none());
        assert!(installed.release_sequence.is_none());
    }

    #[test]
    fn update_source_precedence_does_not_mutate_the_receipt() {
        let mut installed = receipt();
        installed.update_origin = Some("https://receipt.example/releases".to_owned());
        let before = serde_json::to_vec(&installed).unwrap();
        assert_eq!(
            origin(&installed, None).unwrap(),
            "https://receipt.example/releases"
        );
        assert_eq!(
            origin(&installed, Some("https://explicit.example/releases")).unwrap(),
            "https://explicit.example/releases"
        );
        let local = tempfile::tempdir().unwrap();
        assert_eq!(
            origin(&installed, local.path().to_str()).unwrap(),
            local.path().to_str().unwrap()
        );
        assert!(origin(&installed, Some("")).is_err());
        assert!(origin(&installed, Some("relative")).is_err());
        assert_eq!(serde_json::to_vec(&installed).unwrap(), before);
        installed.package_kind = "wsl-archive".to_owned();
        installed.update_origin = None;
        assert!(origin(&installed, None).is_err());
    }

    #[test]
    fn update_source_rejects_ambiguous_or_unsafe_urls_without_echoing_them() {
        for source in [
            "relative",
            "",
            "http://example.invalid",
            "file:///tmp/source",
            "https://person:private@example.invalid",
            "https://example.invalid?private=value",
            "https://example.invalid/#private",
        ] {
            let error = origin(&receipt(), Some(source)).unwrap_err().to_string();
            assert!(error.contains("update source"), "{error}");
            assert!(!error.contains("private"), "{error}");
            assert!(!error.contains("example.invalid"), "{error}");
        }
    }

    #[cfg(target_os = "windows")]
    #[test]
    fn update_source_accepts_absolute_drive_and_unc_directories_before_url_parsing() {
        for source in [r"C:\Vadgr releases", r"\\server\share\Vadgr"] {
            assert_eq!(origin(&receipt(), Some(source)).unwrap(), source);
        }
        assert!(origin(&receipt(), Some(r"C:relative")).is_err());
    }

    #[test]
    fn discovered_development_updates_name_the_installation_boundary() {
        let update = UpdateCheck {
            current_version: "0.5.0".to_owned(),
            available_version: "0.6.0".to_owned(),
            update_available: true,
            can_install: false,
        };
        assert_eq!(
            update.install_unavailable_reason(),
            Some(DEVELOPMENT_UPDATE_REFUSAL)
        );
        let signed = UpdateCheck {
            can_install: true,
            ..update
        };
        assert!(signed.install_unavailable_reason().is_none());
    }

    #[test]
    fn local_update_source_reads_absolute_paths_and_enforces_the_size_limit() {
        let source = tempfile::tempdir().unwrap();
        let destination = tempfile::tempdir().unwrap();
        std::fs::write(source.path().join("manifest.json"), b"fixture").unwrap();
        let copied = destination.path().join("manifest.json");
        fetch(
            source.path().to_str().unwrap(),
            "manifest.json",
            &copied,
            Some(7),
        )
        .unwrap();
        assert_eq!(std::fs::read(&copied).unwrap(), b"fixture");
        let refused = destination.path().join("refused.json");
        assert!(
            fetch(
                source.path().to_str().unwrap(),
                "manifest.json",
                &refused,
                Some(6)
            )
            .is_err()
        );
        assert!(!refused.exists());
        assert_eq!(
            std::fs::read(source.path().join("manifest.json")).unwrap(),
            b"fixture"
        );
    }

    #[test]
    fn version_order_is_numeric() {
        assert!(version_parts("0.10.0").unwrap() > version_parts("0.9.9").unwrap());
        assert!(version_parts("0.5").is_err());
    }

    #[test]
    fn network_fetch_does_not_start_a_nested_async_runtime() {
        let directory = tempfile::tempdir().unwrap();
        let destination = directory.path().join("manifest.json");
        let runtime = tokio::runtime::Builder::new_current_thread()
            .enable_all()
            .build()
            .unwrap();
        let outcome = std::panic::catch_unwind(|| {
            runtime.block_on(async {
                fetch(
                    "https://127.0.0.1:9",
                    "manifest.json",
                    &destination,
                    Some(1024),
                )
            })
        });
        assert!(outcome.is_ok(), "fetch started a runtime inside a runtime");
        assert!(outcome.unwrap().is_err());
    }

    #[test]
    fn failed_update_download_explains_failure_and_recovery_without_private_source() {
        let directory = tempfile::tempdir().unwrap();
        let destination = directory.path().join("manifest.json");
        let error = fetch(
            "https://127.0.0.1:9/private-source",
            "release-manifest.json",
            &destination,
            Some(1024),
        )
        .unwrap_err();
        let message = error.to_string();
        assert!(
            message.starts_with("The update download failed."),
            "{message}"
        );
        assert!(message.contains("Try again"), "{message}");
        assert!(
            message.contains("A connection to the update server could not be established."),
            "{message}"
        );
        for rendering in [message, format!("{error:#}"), format!("{error:?}")] {
            assert!(!rendering.contains("127.0.0.1"), "{rendering}");
            assert!(!rendering.contains("private-source"), "{rendering}");
        }
        assert!(!destination.exists());
    }

    #[test]
    fn update_download_http_failure_preserves_only_status_and_recovery() {
        for status in [404, 503] {
            let response = reqwest::Response::from(
                axum::http::Response::builder()
                    .status(status)
                    .body("private-response-body")
                    .unwrap(),
            );
            let error = download_failure(response.error_for_status().unwrap_err());
            assert_eq!(
                error.to_string(),
                format!(
                    "The update download failed. The update server returned HTTP {status}. Try again later."
                )
            );
            assert!(!format!("{error:?}").contains("private-response-body"));
            assert_eq!(error.chain().count(), 1);
        }
    }

    #[tokio::test]
    async fn update_download_timeout_is_specific_without_retaining_the_source() {
        // A local listener accepts TCP without sending an HTTP response. No
        // external service or host networking change is needed for this error.
        let listener = tokio::net::TcpListener::bind("127.0.0.1:0").await.unwrap();
        let address = listener.local_addr().unwrap();
        let client = reqwest::Client::builder()
            .no_proxy()
            .timeout(std::time::Duration::from_millis(100))
            .build()
            .unwrap();
        let error = client
            .get(format!("http://{address}/private-source"))
            .send()
            .await
            .unwrap_err();
        assert!(error.is_timeout());
        let safe = download_failure(error);
        assert_eq!(
            safe.to_string(),
            "The update download failed. The request timed out. Try again later."
        );
        assert!(!format!("{safe:#}").contains("private-source"));
        assert!(!format!("{safe:?}").contains("127.0.0.1"));
        assert_eq!(safe.chain().count(), 1);
    }

    #[test]
    fn update_download_builder_failure_has_a_safe_fallback() {
        let error = reqwest::Client::new()
            .get("private-source-not-a-url")
            .build()
            .unwrap_err();
        let safe = download_failure(error);
        assert_eq!(
            safe.to_string(),
            "The update download failed. The network request could not be completed. Try again later."
        );
        assert!(!format!("{safe:?}").contains("private-source"));
        assert_eq!(safe.chain().count(), 1);
    }

    #[cfg(target_os = "linux")]
    #[test]
    fn linux_update_verifier_accepts_only_appimages() {
        assert!(native::verify(Path::new("unused"), "appimage", None).is_ok());
        assert!(native::verify(Path::new("unused"), "archive", None).is_err());
    }
}
