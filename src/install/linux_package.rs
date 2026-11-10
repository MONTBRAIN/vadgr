//! Mode-specific integrity for the shared native Linux transaction.

use super::InstallReceipt;
use anyhow::{Context, Result, ensure};
use std::path::Path;

#[cfg(feature = "linux-unsigned-qualification")]
use super::development::VerifiedDevelopmentReceipt;
#[cfg(not(feature = "linux-unsigned-qualification"))]
use super::{Artifact, VerifiedManifest};

pub(crate) struct VerifiedLinuxPackage {
    #[cfg(not(feature = "linux-unsigned-qualification"))]
    verified: VerifiedManifest,
    #[cfg(not(feature = "linux-unsigned-qualification"))]
    artifact: Artifact,
    #[cfg(feature = "linux-unsigned-qualification")]
    verified: VerifiedDevelopmentReceipt,
}

impl VerifiedLinuxPackage {
    pub(crate) fn open(
        vehicle: &Path,
        manifest: &Path,
        signature: &Path,
        bundle_root: &Path,
    ) -> Result<Self> {
        ensure!(
            vehicle.is_absolute() && bundle_root.is_absolute(),
            "the package paths must be absolute"
        );
        let target = super::current_target()?;
        ensure!(
            target.starts_with("linux-"),
            "the AppImage installer runs only on native Linux"
        );
        #[cfg(feature = "linux-unsigned-qualification")]
        {
            require_absent(manifest)?;
            require_absent(signature)?;
            Ok(Self {
                verified: VerifiedDevelopmentReceipt::open(vehicle, bundle_root)?,
            })
        }
        #[cfg(not(feature = "linux-unsigned-qualification"))]
        {
            let verified = VerifiedManifest::open(manifest, signature)?;
            let artifact = verified.artifact_for_target(&target)?;
            ensure!(
                artifact.kind == "appimage",
                "the selected release artifact is not an AppImage"
            );
            ensure!(
                vehicle.file_name().and_then(|name| name.to_str()) == Some(artifact.name.as_str()),
                "the AppImage file name does not match the signed manifest"
            );
            verified.verify_bytes_at(vehicle, &artifact)?;
            ensure!(
                super::sha256_file(&bundle_root.join("legal/TERMS.txt"))?
                    == verified.manifest.terms_sha256,
                "the displayed terms do not match the signed manifest"
            );
            Ok(Self { verified, artifact })
        }
    }

    pub(super) fn open_retained(receipt: &InstallReceipt) -> Result<Self> {
        ensure_receipt_mode(receipt)?;
        #[cfg(feature = "linux-unsigned-qualification")]
        let package = {
            require_absent(&receipt.install_root.join("release-manifest.json"))?;
            require_absent(
                &receipt
                    .install_root
                    .join("release-manifest.json.bundle.jsonl"),
            )?;
            let name = format!(
                "Vadgr-{}-linux-{}-installer.AppImage",
                env!("CARGO_PKG_VERSION"),
                std::env::consts::ARCH
            );
            Self {
                verified: VerifiedDevelopmentReceipt::open_retained(
                    &receipt.install_root.join("cache").join(name),
                    &receipt.install_root.join("development-receipt.json"),
                    receipt
                        .development_receipt_sha256
                        .as_deref()
                        .expect("mode check requires development digest"),
                )?,
            }
        };
        #[cfg(not(feature = "linux-unsigned-qualification"))]
        let package = {
            let verified = VerifiedManifest::open(
                &receipt.install_root.join("release-manifest.json"),
                &receipt
                    .install_root
                    .join("release-manifest.json.bundle.jsonl"),
            )?;
            let artifact = verified.artifact_for_target(&super::current_target()?)?;
            ensure!(
                artifact.kind == "appimage",
                "the retained artifact is not an AppImage"
            );
            Self { verified, artifact }
        };
        ensure!(
            package.version() == receipt.version,
            "the retained package version differs from its receipt"
        );
        package.verify_vehicle_at(
            &receipt
                .install_root
                .join("cache")
                .join(package.artifact_name()),
        )?;
        Ok(package)
    }

    pub(crate) fn version(&self) -> &str {
        #[cfg(feature = "linux-unsigned-qualification")]
        {
            self.verified.version()
        }
        #[cfg(not(feature = "linux-unsigned-qualification"))]
        {
            &self.verified.manifest.version
        }
    }

    pub(crate) fn terms_version(&self) -> Option<&str> {
        #[cfg(feature = "linux-unsigned-qualification")]
        {
            self.verified.terms_version()
        }
        #[cfg(not(feature = "linux-unsigned-qualification"))]
        {
            Some(&self.verified.manifest.terms_version)
        }
    }

    pub(crate) fn terms_sha256(&self) -> &str {
        #[cfg(feature = "linux-unsigned-qualification")]
        {
            self.verified.terms_sha256()
        }
        #[cfg(not(feature = "linux-unsigned-qualification"))]
        {
            &self.verified.manifest.terms_sha256
        }
    }

    pub(crate) fn terms_text(&self, bundle_root: &Path) -> Result<String> {
        #[cfg(feature = "linux-unsigned-qualification")]
        {
            let _ = bundle_root;
            self.verified
                .terms_text()
                .map(str::to_owned)
                .context("the original verified terms are unavailable")
        }
        #[cfg(not(feature = "linux-unsigned-qualification"))]
        {
            use sha2::{Digest, Sha256};
            let bytes = std::fs::read(bundle_root.join("legal/TERMS.txt"))
                .context("reading the verified installer terms")?;
            let digest: String = Sha256::digest(&bytes)
                .iter()
                .map(|byte| format!("{byte:02x}"))
                .collect();
            ensure!(digest == self.terms_sha256(), "the displayed terms changed");
            String::from_utf8(bytes).context("the installer terms are not UTF-8")
        }
    }

    pub(super) fn verify_staged_metadata(&self, staging: &Path) -> Result<()> {
        #[cfg(feature = "linux-unsigned-qualification")]
        self.verified.verify_staged_metadata(staging)?;
        ensure!(
            super::sha256_file(&staging.join("legal/TERMS.txt"))? == self.terms_sha256(),
            "the staged terms changed"
        );
        Ok(())
    }

    pub(super) fn artifact_name(&self) -> &str {
        #[cfg(feature = "linux-unsigned-qualification")]
        {
            self.verified.artifact_name()
        }
        #[cfg(not(feature = "linux-unsigned-qualification"))]
        {
            &self.artifact.name
        }
    }

    pub(super) fn verify_vehicle_at(&self, path: &Path) -> Result<()> {
        #[cfg(feature = "linux-unsigned-qualification")]
        {
            self.verified.verify_vehicle_at(path)
        }
        #[cfg(not(feature = "linux-unsigned-qualification"))]
        {
            self.verified.verify_bytes_at(path, &self.artifact)
        }
    }

    pub(super) fn copy_vehicle_to(&self, source: &Path, destination: &Path) -> Result<()> {
        #[cfg(feature = "linux-unsigned-qualification")]
        {
            let _ = source;
            self.verified.copy_vehicle_to(destination)?;
        }
        #[cfg(not(feature = "linux-unsigned-qualification"))]
        {
            std::fs::copy(source, destination).context("copying the verified AppImage")?;
        }
        self.verify_vehicle_at(destination)
    }

    pub(super) fn ensure_sequence(&self, state_root: &Path) -> Result<()> {
        #[cfg(feature = "linux-unsigned-qualification")]
        {
            require_absent(&state_root.join("release-sequence.json"))
        }
        #[cfg(not(feature = "linux-unsigned-qualification"))]
        {
            self.verified.ensure_sequence(state_root)
        }
    }

    pub(super) fn accept_sequence(&self, state_root: &Path) -> Result<()> {
        #[cfg(feature = "linux-unsigned-qualification")]
        {
            self.ensure_sequence(state_root)
        }
        #[cfg(not(feature = "linux-unsigned-qualification"))]
        {
            self.verified.accept_sequence(state_root)
        }
    }

    pub(super) fn stage_metadata(
        &self,
        staging: &Path,
        manifest: &Path,
        signature: &Path,
    ) -> Result<()> {
        #[cfg(feature = "linux-unsigned-qualification")]
        {
            let _ = (manifest, signature);
            std::fs::write(
                staging.join("development-receipt.json"),
                self.verified.receipt_bytes(),
            )
            .context("retaining development integrity metadata")?;
        }
        #[cfg(not(feature = "linux-unsigned-qualification"))]
        {
            std::fs::copy(manifest, staging.join("release-manifest.json"))?;
            std::fs::copy(
                signature,
                staging.join("release-manifest.json.bundle.jsonl"),
            )?;
            let retained = VerifiedManifest::open(
                &staging.join("release-manifest.json"),
                &staging.join("release-manifest.json.bundle.jsonl"),
            )?;
            ensure!(
                retained.manifest_sha256() == self.verified.manifest_sha256(),
                "the staged release manifest changed"
            );
        }
        Ok(())
    }

    pub(super) fn receipt(&self) -> InstallReceipt {
        InstallReceipt {
            schema: 1,
            version: self.version().to_owned(),
            install_root: Default::default(),
            package_kind: "appimage".to_owned(),
            product_code: None,
            #[cfg(not(feature = "linux-unsigned-qualification"))]
            release_sequence: Some(self.verified.manifest.release_sequence),
            #[cfg(feature = "linux-unsigned-qualification")]
            release_sequence: None,
            #[cfg(not(feature = "linux-unsigned-qualification"))]
            manifest_sha256: Some(self.verified.manifest_sha256()),
            #[cfg(feature = "linux-unsigned-qualification")]
            manifest_sha256: None,
            #[cfg(not(feature = "linux-unsigned-qualification"))]
            development_receipt_sha256: None,
            #[cfg(feature = "linux-unsigned-qualification")]
            development_receipt_sha256: Some(self.verified.receipt_sha256().to_owned()),
            update_origin: None,
            publisher: None,
            rollback_vehicle: None,
        }
    }
}

pub(super) fn ensure_receipt_mode(receipt: &InstallReceipt) -> Result<()> {
    ensure!(
        receipt.package_kind == "appimage",
        "this is not a Linux AppImage installation"
    );
    let development = receipt.development_receipt_sha256.as_deref();
    ensure!(
        development.is_some() == cfg!(feature = "linux-unsigned-qualification"),
        "signed and unsigned development generations cannot be mixed"
    );
    if let Some(digest) = development {
        ensure!(
            super::valid_sha256(digest)
                && receipt.release_sequence.is_none()
                && receipt.manifest_sha256.is_none()
                && receipt.publisher.is_none()
                && receipt.update_origin.is_none(),
            "development metadata must not claim release authority"
        );
    }
    Ok(())
}

#[cfg(feature = "linux-unsigned-qualification")]
fn require_absent(path: &Path) -> Result<()> {
    match path.symlink_metadata() {
        Err(error) if error.kind() == std::io::ErrorKind::NotFound => Ok(()),
        Err(error) => Err(error).context("checking the development integrity boundary"),
        Ok(_) => {
            anyhow::bail!("unsigned development installation refuses production trust metadata")
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn receipt(development: bool) -> InstallReceipt {
        InstallReceipt {
            schema: 1,
            version: "0.5.0".to_owned(),
            install_root: Default::default(),
            package_kind: "appimage".to_owned(),
            product_code: None,
            release_sequence: (!development).then_some(1),
            manifest_sha256: (!development).then(|| "a".repeat(64)),
            development_receipt_sha256: development.then(|| "b".repeat(64)),
            update_origin: None,
            publisher: None,
            rollback_vehicle: None,
        }
    }

    #[test]
    fn generation_modes_are_compile_time_exclusive() {
        let development = cfg!(feature = "linux-unsigned-qualification");
        assert!(ensure_receipt_mode(&receipt(development)).is_ok());
        assert!(ensure_receipt_mode(&receipt(!development)).is_err());
    }

    #[test]
    fn development_metadata_cannot_claim_release_authority() {
        for field in 0..5 {
            let mut value = receipt(true);
            match field {
                0 => value.release_sequence = Some(1),
                1 => value.manifest_sha256 = Some("a".repeat(64)),
                2 => value.publisher = Some("publisher".to_owned()),
                3 => value.update_origin = Some("https://example.invalid".to_owned()),
                _ => value.development_receipt_sha256 = Some("invalid".to_owned()),
            }
            assert!(ensure_receipt_mode(&value).is_err());
        }
    }

    #[test]
    fn legacy_receipts_do_not_gain_development_metadata() {
        let encoded = serde_json::to_vec(&receipt(false)).unwrap();
        assert!(!String::from_utf8_lossy(&encoded).contains("development_receipt_sha256"));
        let decoded: InstallReceipt = serde_json::from_slice(&encoded).unwrap();
        assert!(decoded.development_receipt_sha256.is_none());
    }

    #[cfg(not(feature = "linux-unsigned-qualification"))]
    #[test]
    fn production_never_falls_back_to_a_development_receipt() {
        let root = tempfile::tempdir().unwrap();
        let vehicle = root
            .path()
            .join("Vadgr-0.5.0-linux-x86_64-installer.AppImage");
        std::fs::write(&vehicle, b"unsigned vehicle").unwrap();
        std::fs::write(vehicle.with_extension("development.json"), b"{}").unwrap();
        assert!(
            VerifiedLinuxPackage::open(
                &vehicle,
                &root.path().join("release-manifest.json"),
                &root.path().join("release-manifest.json.bundle.jsonl"),
                root.path()
            )
            .is_err()
        );
        assert_eq!(std::fs::read_dir(root.path()).unwrap().count(), 2);
    }

    #[cfg(feature = "linux-unsigned-qualification")]
    #[test]
    fn development_refuses_existing_production_sequence_and_broken_links() {
        let root = tempfile::tempdir().unwrap();
        let path = root.path().join("release-sequence.json");
        assert!(require_absent(&path).is_ok());
        std::fs::write(&path, b"{}").unwrap();
        assert!(require_absent(&path).is_err());
        let link = root.path().join("release-manifest.json");
        std::os::unix::fs::symlink(root.path().join("missing"), &link).unwrap();
        assert!(require_absent(&link).is_err());
    }
}
