//! Fail-closed release-manifest verification shared by every installer.

use super::{commit_file, sha256_file, valid_sha256};
use anyhow::{Context, Result, anyhow, ensure};
use serde::{Deserialize, Serialize};
use sha2::Digest;
use sigstore_trust_root::TrustedRoot;
use sigstore_types::{Bundle, MediaType, SignatureContent};
use sigstore_verify::{VerificationPolicy, Verifier};
use std::collections::HashSet;
use std::path::{Path, PathBuf};
use x509_cert::der::{Decode, asn1::Utf8StringRef};

const MAX_MANIFEST_BYTES: u64 = 4 * 1024 * 1024;
const SEQUENCE_FILE: &str = "release-sequence.json";
const MAX_BUNDLE_BYTES: u64 = 4 * 1024 * 1024;
// Public Sigstore root obtained with `gh attestation trusted-root` on 2026-09-17.
// https://cli.github.com/manual/gh_attestation_trusted-root
// The GitHub private-instance root is deliberately excluded. Root rotation requires
// a reviewed verifier release; no bundle or command-line input can replace it.
const TRUSTED_ROOT: &str = include_str!("../../packaging/release-trusted-root.jsonl");
const RELEASE_IDENTITY: &str =
    "https://github.com/MONTBRAIN/vadgr/.github/workflows/candidate.yml@refs/heads/master";
const RELEASE_ISSUER: &str = "https://token.actions.githubusercontent.com";
const RELEASE_REPOSITORY: &str = "https://github.com/MONTBRAIN/vadgr";
const RELEASE_REF: &str = "refs/heads/master";

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
    pub fn open(manifest_path: &Path, bundle_path: &Path) -> Result<Self> {
        let metadata =
            std::fs::metadata(manifest_path).context("reading release manifest metadata")?;
        ensure!(
            metadata.len() <= MAX_MANIFEST_BYTES,
            "the release manifest is larger than the supported limit"
        );
        let bytes = std::fs::read(manifest_path).context("reading the release manifest")?;
        ensure!(
            bytes.len() as u64 <= MAX_MANIFEST_BYTES,
            "the release manifest is larger than the supported limit"
        );
        let metadata =
            std::fs::metadata(bundle_path).context("reading release attestation metadata")?;
        ensure!(
            metadata.len() <= MAX_BUNDLE_BYTES,
            "the release attestation is larger than the supported limit"
        );
        let bundle =
            std::fs::read_to_string(bundle_path).context("reading the release attestation")?;
        ensure!(
            bundle.len() as u64 <= MAX_BUNDLE_BYTES,
            "the release attestation is larger than the supported limit"
        );
        verify_attestation(&bytes, &bundle)?;
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

fn verify_attestation(bytes: &[u8], encoded: &str) -> Result<()> {
    // Parsing exactly one JSON value also rejects concatenated JSONL attestations.
    let bundle = Bundle::from_json(encoded).context("parsing the release attestation")?;
    ensure!(
        bundle.version()? == MediaType::Bundle0_3,
        "unsupported release attestation bundle version"
    );
    let SignatureContent::DsseEnvelope(envelope) = &bundle.content else {
        return Err(anyhow!(
            "the release attestation must contain a DSSE statement"
        ));
    };
    ensure!(
        envelope.signatures.len() == 1,
        "the release attestation must contain exactly one signature"
    );
    ensure!(
        envelope.payload_type == "application/vnd.in-toto+json",
        "unsupported release attestation payload type"
    );
    let root =
        TrustedRoot::from_json(TRUSTED_ROOT).context("loading the embedded release trust root")?;
    let policy = VerificationPolicy::default()
        .require_identity(RELEASE_IDENTITY)
        .require_issuer(RELEASE_ISSUER);
    // This synchronous API uses only the embedded root and bundle. Keep the
    // default certificate, SCT, log inclusion/checkpoint and time checks enabled.
    let verified = Verifier::new(&root)
        .verify(bytes, &bundle, &policy)
        .context("the release attestation did not verify")?;
    ensure!(
        verified.warnings.is_empty(),
        "the release attestation produced verification warnings"
    );
    let certificate = bundle
        .signing_certificate()
        .ok_or_else(|| anyhow!("the release attestation has no signing certificate"))?;
    let certificate = x509_cert::Certificate::from_der(certificate.as_bytes())
        .context("parsing the verified release certificate")?;
    verify_release_certificate(&certificate)?;
    verify_release_statement(envelope.payload.as_bytes(), bytes)
}

fn verify_release_certificate(certificate: &x509_cert::Certificate) -> Result<()> {
    // Fulcio OIDs .8 and later are DER UTF8String, not the legacy raw UTF-8.
    // https://github.com/sigstore/fulcio/blob/main/docs/oid-info.md
    for (oid, expected) in [
        ("1.3.6.1.4.1.57264.1.8", RELEASE_ISSUER),
        ("1.3.6.1.4.1.57264.1.9", RELEASE_IDENTITY),
        ("1.3.6.1.4.1.57264.1.11", "github-hosted"),
        ("1.3.6.1.4.1.57264.1.12", RELEASE_REPOSITORY),
        ("1.3.6.1.4.1.57264.1.14", RELEASE_REF),
    ] {
        let extensions = certificate
            .tbs_certificate
            .extensions
            .as_deref()
            .unwrap_or_default();
        let matching = extensions
            .iter()
            .filter(|extension| extension.extn_id.to_string() == oid)
            .collect::<Vec<_>>();
        ensure!(
            matching.len() == 1,
            "the release certificate must contain exactly one required identity claim: {oid}"
        );
        let value = Utf8StringRef::from_der(matching[0].extn_value.as_bytes())
            .context("the release certificate identity claim is malformed")?;
        ensure!(
            value.as_str() == expected,
            "the release certificate identity claim is not authorized: {oid}"
        );
    }
    Ok(())
}

fn verify_release_statement(payload: &[u8], manifest: &[u8]) -> Result<()> {
    let statement: serde_json::Value =
        serde_json::from_slice(payload).context("parsing the verified release statement")?;
    ensure!(
        statement["_type"] == "https://in-toto.io/Statement/v1",
        "unsupported release statement type"
    );
    ensure!(
        statement["predicateType"] == "https://slsa.dev/provenance/v1",
        "unsupported release provenance type"
    );
    let subjects = statement["subject"]
        .as_array()
        .ok_or_else(|| anyhow!("the release statement has no subjects"))?;
    ensure!(
        subjects.len() == 1,
        "the release statement must bind exactly one manifest"
    );
    ensure!(
        subjects[0]["name"] == "release-manifest.json",
        "the release statement names another artifact"
    );
    ensure!(
        subjects[0]["digest"]["sha256"] == sha256_bytes(manifest),
        "the release statement does not bind these manifest bytes"
    );
    Ok(())
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
            | (Some("linux"), "keyless-manifest")
            | (Some("wsl"), "keyless-manifest")
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
            cua_version: "0.7.8".to_owned(),
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
    fn linux_requires_keyless_manifest() {
        assert!(valid_native_signature("keyless-manifest", "linux-x86_64"));
        assert!(!valid_native_signature("minisign-manifest", "linux-x86_64"));
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
    fn embedded_root_is_reviewed_public_good_snapshot() {
        assert_eq!(
            sha256_bytes(TRUSTED_ROOT.as_bytes()),
            "3c2cc7f357dc064ec527fdcd78da6e9245c21a381e1abaa0f2b62b186bcac1a1"
        );
        TrustedRoot::from_json(TRUSTED_ROOT).unwrap();
    }

    #[test]
    fn public_github_attestations_verify_offline_but_are_not_vadgr_releases() {
        use base64::Engine as _;
        let artifact = base64::engine::general_purpose::STANDARD
            .decode(include_str!("../../tests/fixtures/sigstore/package.conda.base64").trim())
            .unwrap();
        let root = TrustedRoot::from_json(TRUSTED_ROOT).unwrap();
        let policy = VerificationPolicy::default()
            .require_identity("https://github.com/prefix-dev/sigstore-example/.github/workflows/action.yaml@refs/heads/main")
            .require_issuer(RELEASE_ISSUER);
        for encoded in [include_str!(
            "../../tests/fixtures/sigstore/conda-attestation.sigstore.json"
        )] {
            let bundle = Bundle::from_json(encoded).unwrap();
            let verified = Verifier::new(&root)
                .verify(artifact.as_slice(), &bundle, &policy)
                .unwrap_or_else(|error| {
                    panic!(
                        "log {:?}: {error}",
                        bundle.verification_material.tlog_entries[0].kind_version
                    )
                });
            assert!(verified.warnings.is_empty(), "{:?}", verified.warnings);
            assert!(
                Verifier::new(&root)
                    .verify(b"tampered".as_slice(), &bundle, &policy)
                    .is_err()
            );
            assert!(verify_attestation(&artifact, encoded).is_err());
            let certificate =
                x509_cert::Certificate::from_der(bundle.signing_certificate().unwrap().as_bytes())
                    .unwrap();
            assert!(verify_release_certificate(&certificate).is_err());
            let mut altered = serde_json::from_str::<serde_json::Value>(encoded).unwrap();
            altered["verificationMaterial"]["tlogEntries"] = serde_json::json!([]);
            let altered = Bundle::from_json(&altered.to_string()).unwrap();
            assert!(
                Verifier::new(&root)
                    .verify(artifact.as_slice(), &altered, &policy)
                    .is_err()
            );
        }
        let staging = Bundle::from_json(include_str!(
            "../../tests/fixtures/sigstore/conda-attestation-rekor2.sigstore.json"
        ))
        .unwrap();
        assert!(
            Verifier::new(&root)
                .verify(
                    artifact.as_slice(),
                    &staging,
                    &VerificationPolicy::default()
                )
                .is_err()
        );
    }

    #[test]
    fn certificate_policy_requires_every_authenticated_identity_claim() {
        use x509_cert::der::{Encode, asn1::OctetString};
        let bundle = Bundle::from_json(include_str!(
            "../../tests/fixtures/sigstore/conda-attestation.sigstore.json"
        ))
        .unwrap();
        let mut certificate =
            x509_cert::Certificate::from_der(bundle.signing_certificate().unwrap().as_bytes())
                .unwrap();
        let claims = [
            ("1.3.6.1.4.1.57264.1.8", RELEASE_ISSUER),
            ("1.3.6.1.4.1.57264.1.9", RELEASE_IDENTITY),
            ("1.3.6.1.4.1.57264.1.11", "github-hosted"),
            ("1.3.6.1.4.1.57264.1.12", RELEASE_REPOSITORY),
            ("1.3.6.1.4.1.57264.1.14", RELEASE_REF),
        ];
        // Synthetic claims test policy only. This modified certificate no longer
        // has a valid signature and is never accepted by verify_attestation.
        for (oid, expected) in claims {
            let extensions = certificate.tbs_certificate.extensions.as_mut().unwrap();
            extensions.retain(|extension| extension.extn_id.to_string() != oid);
            extensions.push(x509_cert::ext::Extension {
                extn_id: oid.parse().unwrap(),
                critical: false,
                extn_value: OctetString::new(
                    Utf8StringRef::new(expected).unwrap().to_der().unwrap(),
                )
                .unwrap(),
            });
        }
        verify_release_certificate(&certificate).unwrap();
        for (oid, _) in claims {
            for mode in 0..4 {
                let mut altered = certificate.clone();
                let extensions = altered.tbs_certificate.extensions.as_mut().unwrap();
                let index = extensions
                    .iter()
                    .position(|extension| extension.extn_id.to_string() == oid)
                    .unwrap();
                match mode {
                    0 => {
                        extensions.remove(index);
                    }
                    1 => extensions.push(extensions[index].clone()),
                    2 => {
                        extensions[index].extn_value = OctetString::new(
                            Utf8StringRef::new("unauthorized")
                                .unwrap()
                                .to_der()
                                .unwrap(),
                        )
                        .unwrap()
                    }
                    _ => {
                        extensions[index].extn_value =
                            OctetString::new(b"not DER".to_vec()).unwrap()
                    }
                }
                assert!(
                    verify_release_certificate(&altered).is_err(),
                    "accepted {oid} mutation {mode}"
                );
            }
        }
    }

    #[test]
    fn malformed_and_multiple_bundles_fail_closed() {
        for bundle in ["", "{}", "{}\n{}", "unconfigured"] {
            assert!(verify_attestation(b"manifest", bundle).is_err());
        }
    }

    #[test]
    fn statement_binds_exact_manifest_and_subject() {
        let bytes = b"manifest";
        let mut statement = serde_json::json!({
            "_type": "https://in-toto.io/Statement/v1",
            "predicateType": "https://slsa.dev/provenance/v1",
            "subject": [{"name": "release-manifest.json", "digest": {"sha256": sha256_bytes(bytes)}}]
        });
        let encode = |value: &serde_json::Value| serde_json::to_vec(value).unwrap();
        verify_release_statement(&encode(&statement), bytes).unwrap();
        assert!(verify_release_statement(&encode(&statement), b"tampered").is_err());
        statement["subject"][0]["name"] = "other.json".into();
        assert!(verify_release_statement(&encode(&statement), bytes).is_err());
        statement["subject"][0]["name"] = "release-manifest.json".into();
        let duplicate = statement["subject"][0].clone();
        statement["subject"].as_array_mut().unwrap().push(duplicate);
        assert!(verify_release_statement(&encode(&statement), bytes).is_err());
    }
}
