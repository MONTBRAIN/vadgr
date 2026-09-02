//! Fail-closed release-manifest verification shared by every installer.

use super::{commit_file, sha256_file, valid_sha256};
use anyhow::{Context, Result, anyhow, ensure};
use minisign_verify::{PublicKey, Signature};
use serde::{Deserialize, Serialize};
use sha2::Digest;
use std::collections::HashSet;
use std::path::{Path, PathBuf};

const MAX_MANIFEST_BYTES: u64 = 4 * 1024 * 1024;
const SEQUENCE_FILE: &str = "release-sequence.json";
pub const RELEASE_PUBLIC_KEY: &str = include_str!("../../packaging/release-public-key.txt");

#[derive(Clone, Debug, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub struct ReleaseManifest {
    pub schema: u32,
    pub product: String,
    pub version: String,
    pub release_sequence: u64,
    pub tag: String,
    pub source_commit: String,
    pub terms_version: String,
    pub terms_sha256: String,
    pub cua_version: String,
    pub python_version: String,
    pub artifacts: Vec<Artifact>,
}

#[derive(Clone, Debug, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub struct Artifact {
    pub name: String,
    pub target: String,
    pub kind: String,
    pub size: u64,
    pub sha256: String,
    pub native_signature: String,
}

#[derive(Clone, Debug)]
pub struct VerifiedManifest {
    pub manifest: ReleaseManifest,
    bytes: Vec<u8>,
}

#[derive(Clone, Debug)]
pub struct VerifiedArtifact {
    pub manifest: VerifiedManifest,
    pub artifact: Artifact,
    pub path: PathBuf,
}

#[derive(Debug, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
struct AcceptedSequence {
    schema: u32,
    highest: u64,
    version: String,
    manifest_sha256: String,
}

impl VerifiedManifest {
    /// Verify the signature before parsing or trusting any manifest field.
    pub fn open(manifest_path: &Path, signature_path: &Path, public_key: &str) -> Result<Self> {
        let metadata =
            std::fs::metadata(manifest_path).context("reading release manifest metadata")?;
        ensure!(
            metadata.len() <= MAX_MANIFEST_BYTES,
            "the release manifest is larger than the supported limit"
        );
        let bytes = std::fs::read(manifest_path).context("reading the release manifest")?;
        verify_signature(&bytes, signature_path, public_key)?;
        let manifest: ReleaseManifest =
            serde_json::from_slice(&bytes).context("parsing the verified release manifest")?;
        validate_manifest(&manifest)?;
        Ok(Self { manifest, bytes })
    }

    pub fn verify_artifact(self, path: &Path, target: &str) -> Result<VerifiedArtifact> {
        ensure!(path.is_file(), "the release artifact is missing");
        let name = path
            .file_name()
            .and_then(|value| value.to_str())
            .ok_or_else(|| anyhow!("the release artifact name is not valid UTF-8"))?;
        let artifact = self
            .manifest
            .artifacts
            .iter()
            .find(|artifact| artifact.name == name && artifact.target == target)
            .cloned()
            .ok_or_else(|| {
                anyhow!("the signed manifest does not authorize this target artifact")
            })?;
        let size = std::fs::metadata(path)
            .context("reading release artifact metadata")?
            .len();
        ensure!(
            size == artifact.size,
            "the release artifact size does not match the signed manifest"
        );
        let digest = sha256_file(path)?;
        ensure!(
            digest == artifact.sha256,
            "the release artifact checksum does not match the signed manifest"
        );
        Ok(VerifiedArtifact {
            manifest: self,
            artifact,
            path: path.to_owned(),
        })
    }

    pub fn artifact_for_target(&self, target: &str) -> Result<Artifact> {
        let matches = self
            .manifest
            .artifacts
            .iter()
            .filter(|artifact| artifact.target == target)
            .cloned()
            .collect::<Vec<_>>();
        ensure!(
            matches.len() == 1,
            "the signed manifest must name exactly one artifact for this target"
        );
        Ok(matches.into_iter().next().expect("one matching artifact"))
    }

    pub fn verify_bytes_at(&self, path: &Path, artifact: &Artifact) -> Result<()> {
        ensure!(path.is_file(), "the release artifact is missing");
        let size = std::fs::metadata(path)
            .context("reading release artifact metadata")?
            .len();
        ensure!(
            size == artifact.size,
            "the release artifact size does not match the signed manifest"
        );
        ensure!(
            sha256_file(path)? == artifact.sha256,
            "the release artifact checksum does not match the signed manifest"
        );
        Ok(())
    }

    pub fn manifest_sha256(&self) -> String {
        sha256_bytes(&self.bytes)
    }

    /// Persist anti-downgrade state only after the caller verified the artifact.
    pub fn accept_sequence(&self, state_root: &Path) -> Result<()> {
        ensure!(
            state_root.is_absolute(),
            "the Vadgr state root must be absolute"
        );
        self.ensure_sequence(state_root)?;
        let path = state_root.join(SEQUENCE_FILE);
        crate::private_fs::create_dir_all(state_root).context("creating the Vadgr state root")?;
        let record = AcceptedSequence {
            schema: 1,
            highest: self.manifest.release_sequence,
            version: self.manifest.version.clone(),
            manifest_sha256: self.manifest_sha256(),
        };
        let temporary = state_root.join(format!(".{SEQUENCE_FILE}.{}.tmp", uuid::Uuid::new_v4()));
        std::fs::write(&temporary, serde_json::to_vec_pretty(&record)?)
            .context("writing the release sequence candidate")?;
        crate::private_fs::harden(&temporary)
            .context("protecting the release sequence candidate")?;
        if let Err(error) = commit_file(&temporary, &path) {
            let _ = std::fs::remove_file(&temporary);
            return Err(error).context("committing the accepted release sequence");
        }
        crate::private_fs::harden(&path).context("protecting the accepted release sequence")
    }

    pub fn ensure_sequence(&self, state_root: &Path) -> Result<()> {
        ensure!(
            state_root.is_absolute(),
            "the Vadgr state root must be absolute"
        );
        let path = state_root.join(SEQUENCE_FILE);
        if !path.is_file() {
            return Ok(());
        }
        let previous: AcceptedSequence = serde_json::from_slice(
            &std::fs::read(&path).context("reading the accepted release sequence")?,
        )
        .context("parsing the accepted release sequence")?;
        ensure!(
            previous.schema == 1,
            "the release sequence schema is unsupported"
        );
        ensure!(
            self.manifest.release_sequence >= previous.highest,
            "the remote release sequence is lower than the accepted sequence"
        );
        Ok(())
    }
}

impl VerifiedArtifact {
    pub fn accept_sequence(&self, state_root: &Path) -> Result<()> {
        self.manifest.accept_sequence(state_root)
    }
}

pub fn current_target() -> Result<String> {
    let architecture = match std::env::consts::ARCH {
        "x86_64" => "x86_64",
        "aarch64" => "aarch64",
        other => return Err(anyhow!("unsupported architecture: {other}")),
    };
    let operating_system = match std::env::consts::OS {
        "windows" => "windows",
        "macos" => "macos",
        "linux" if is_wsl() => "wsl",
        "linux" => "linux",
        other => return Err(anyhow!("unsupported operating system: {other}")),
    };
    Ok(format!("{operating_system}-{architecture}"))
}

fn is_wsl() -> bool {
    cfg!(target_os = "linux")
        && std::fs::read_to_string("/proc/sys/kernel/osrelease")
            .map(|value| value.to_ascii_lowercase().contains("microsoft"))
            .unwrap_or(false)
}

fn verify_signature(bytes: &[u8], signature_path: &Path, public_key: &str) -> Result<()> {
    let public_key = public_key.trim();
    ensure!(
        !public_key.is_empty() && !public_key.eq_ignore_ascii_case("unconfigured"),
        "the release public key is not configured"
    );
    let public_key = PublicKey::from_base64(public_key)
        .map_err(|error| anyhow!("the release public key is invalid: {error}"))?;
    let encoded = std::fs::read_to_string(signature_path)
        .context("reading the release manifest signature")?;
    let signature = Signature::decode(&encoded)
        .map_err(|error| anyhow!("the release manifest signature is invalid: {error}"))?;
    public_key
        .verify(bytes, &signature, false)
        .map_err(|error| anyhow!("the release manifest signature did not verify: {error}"))
}

fn validate_manifest(manifest: &ReleaseManifest) -> Result<()> {
    ensure!(
        manifest.schema == 1,
        "the release manifest schema is unsupported"
    );
    ensure!(
        manifest.product == "vadgr",
        "the release manifest names another product"
    );
    ensure!(
        valid_version(&manifest.version),
        "the release version is invalid"
    );
    ensure!(
        manifest.tag == format!("v{}", manifest.version),
        "the release tag does not match the version"
    );
    ensure!(
        manifest.release_sequence > 0,
        "the release sequence must be positive"
    );
    ensure!(
        valid_commit(&manifest.source_commit),
        "the source commit is invalid"
    );
    ensure!(
        !manifest.terms_version.trim().is_empty(),
        "the terms version is empty"
    );
    ensure!(
        valid_sha256(&manifest.terms_sha256),
        "the terms checksum is invalid"
    );
    ensure!(
        !manifest.cua_version.trim().is_empty(),
        "the CUA version is empty"
    );
    ensure!(
        !manifest.python_version.trim().is_empty(),
        "the Python version is empty"
    );
    ensure!(
        !manifest.artifacts.is_empty(),
        "the release manifest has no artifacts"
    );
    let mut identities = HashSet::new();
    for artifact in &manifest.artifacts {
        ensure!(safe_file_name(&artifact.name), "an artifact name is unsafe");
        ensure!(
            valid_target(&artifact.target),
            "an artifact target is unsupported"
        );
        ensure!(
            valid_kind(&artifact.kind, &artifact.target),
            "an artifact kind is unsupported for its target"
        );
        ensure!(artifact.size > 0, "an artifact size must be positive");
        ensure!(
            valid_sha256(&artifact.sha256),
            "an artifact checksum is invalid"
        );
        ensure!(
            valid_native_signature(&artifact.native_signature, &artifact.target),
            "an artifact native-signature rule is invalid"
        );
        ensure!(
            identities.insert((artifact.name.clone(), artifact.target.clone())),
            "the release manifest repeats an artifact"
        );
    }
    Ok(())
}

fn valid_version(value: &str) -> bool {
    let parts = value.split('.').collect::<Vec<_>>();
    parts.len() == 3
        && parts.iter().all(|part| {
            !part.is_empty() && part.chars().all(|character| character.is_ascii_digit())
        })
}

fn valid_commit(value: &str) -> bool {
    value.len() == 40 && value.chars().all(|character| character.is_ascii_hexdigit())
}

fn safe_file_name(value: &str) -> bool {
    !value.is_empty()
        && value != "."
        && value != ".."
        && !value.contains('/')
        && !value.contains('\\')
        && Path::new(value).file_name().and_then(|name| name.to_str()) == Some(value)
}

fn valid_target(value: &str) -> bool {
    matches!(
        value,
        "windows-x86_64"
            | "windows-aarch64"
            | "macos-x86_64"
            | "macos-aarch64"
            | "linux-x86_64"
            | "linux-aarch64"
            | "wsl-x86_64"
            | "wsl-aarch64"
    )
}

fn valid_kind(kind: &str, target: &str) -> bool {
    matches!(
        (target.split('-').next(), kind),
        (Some("windows"), "burn")
            | (Some("macos"), "pkg")
            | (Some("linux"), "appimage")
            | (Some("wsl"), "tar.gz")
    )
}

fn valid_native_signature(rule: &str, target: &str) -> bool {
    matches!(
        (target.split('-').next(), rule),
        (Some("windows"), "authenticode")
            | (Some("macos"), "developer-id-notarized")
            | (Some("linux"), "minisign-manifest")
            | (Some("wsl"), "minisign-manifest")
    )
}

fn sha256_bytes(bytes: &[u8]) -> String {
    use std::fmt::Write as _;
    let digest = sha2::Sha256::digest(bytes);
    let mut encoded = String::with_capacity(64);
    for byte in digest {
        write!(&mut encoded, "{byte:02x}").expect("writing to a string cannot fail");
    }
    encoded
}

#[cfg(test)]
mod tests {
    use super::*;

    fn manifest() -> ReleaseManifest {
        ReleaseManifest {
            schema: 1,
            product: "vadgr".to_owned(),
            version: "0.5.0".to_owned(),
            release_sequence: 500,
            tag: "v0.5.0".to_owned(),
            source_commit: "a".repeat(40),
            terms_version: "1.0".to_owned(),
            terms_sha256: "b".repeat(64),
            cua_version: "0.7.6".to_owned(),
            python_version: "3.12.14".to_owned(),
            artifacts: vec![Artifact {
                name: "Vadgr-0.5.0-windows-x86_64-setup.exe".to_owned(),
                target: "windows-x86_64".to_owned(),
                kind: "burn".to_owned(),
                size: 1,
                sha256: "c".repeat(64),
                native_signature: "authenticode".to_owned(),
            }],
        }
    }

    #[test]
    fn validates_the_exact_release_shape() {
        validate_manifest(&manifest()).unwrap();
        let mut row = manifest();
        row.artifacts[0].name = "../setup.exe".to_owned();
        assert!(validate_manifest(&row).is_err());
    }

    #[test]
    fn accepted_sequence_refuses_a_remote_downgrade() {
        let root = tempfile::tempdir().unwrap();
        let mut current = manifest();
        let verified = VerifiedManifest {
            manifest: current.clone(),
            bytes: b"current".to_vec(),
        };
        let absolute = dunce::canonicalize(root.path()).unwrap();
        verified.accept_sequence(&absolute).unwrap();
        current.release_sequence -= 1;
        let older = VerifiedManifest {
            manifest: current,
            bytes: b"older".to_vec(),
        };
        assert!(
            older
                .accept_sequence(&absolute)
                .unwrap_err()
                .to_string()
                .contains("lower")
        );
    }

    #[test]
    fn known_minisign_vector_verifies_and_tampering_fails() {
        let root = tempfile::tempdir().unwrap();
        let signature = root.path().join("manifest.minisig");
        std::fs::write(&signature, "untrusted comment: signature from minisign secret key\nRUQf6LRCGA9i559r3g7V1qNyJDApGip8MfqcadIgT9CuhV3EMhHoN1mGTkUidF/z7SrlQgXdy8ofjb7bNJJylDOocrCo8KLzZwo=\ntrusted comment: timestamp:1556193335\tfile:test\ny/rUw2y8/hOUYjZU71eHp/Wo1KZ40fGy2VJEDl34XMJM+TX48Ss/17u3IvIfbVR1FkZZSNCisQbuQY+bHwhEBg==\n").unwrap();
        let key = "RWQf6LRCGA9i53mlYecO4IzT51TGPpvWucNSCh1CBM0QTaLn73Y7GFO3";
        verify_signature(b"test", &signature, key).unwrap();
        assert!(verify_signature(b"tampered", &signature, key).is_err());
    }
}
