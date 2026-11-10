//! Every case builds a complete installed development package and then changes
//! exactly one thing, so a refusal names the condition it came from.

use super::*;
use serde_json::{Value, json};

const COMMIT: &str = "1111111111111111111111111111111111111111";
const TREE: &str = "2222222222222222222222222222222222222222";

fn expected() -> Expected<'static> {
    Expected {
        version: env!("CARGO_PKG_VERSION"),
        architecture: std::env::consts::ARCH,
        source_commit: COMMIT,
        source_tree: TREE,
    }
}

/// The installed file set a development MSI produces, in the layout it installs.
fn payload() -> Vec<(&'static str, &'static [u8])> {
    vec![
        ("vadgr.exe", b"the backend image" as &[u8]),
        ("vadgr-app.exe", b"the windowless launcher"),
        ("README-OFFLINE.txt", b"offline notes"),
        ("legal/TERMS.txt", b"the accepted terms"),
        ("sbom/vadgr.spdx.json", b"{}"),
        ("lib/cua/payload.json", b"{\"cua_version\":\"0.0.0\"}"),
        ("lib/cua/bootstrap.py", b"print()"),
    ]
}

struct Fixture {
    _directory: tempfile::TempDir,
    root: PathBuf,
}

impl Fixture {
    /// A complete, consistent installed development package.
    fn new() -> Self {
        let directory = tempfile::tempdir().expect("temporary root");
        let root = directory.path().join("Vadgr");
        std::fs::create_dir(&root).expect("install root");
        for (relative, bytes) in payload() {
            write(&root, relative, bytes);
        }
        let fixture = Self {
            _directory: directory,
            root,
        };
        let receipt = fixture.development_receipt(|_| {});
        fixture.install_receipt(&sha256_hex(&receipt), |_| {});
        fixture
    }

    fn path(&self, relative: &str) -> PathBuf {
        self.root.join(relative.replace('/', "\\"))
    }

    fn executable(&self) -> PathBuf {
        self.path(EXECUTABLE)
    }

    /// Write the development receipt, after letting the caller change it. The
    /// returned bytes are what the install receipt must then record.
    fn development_receipt(&self, change: impl FnOnce(&mut Value)) -> Vec<u8> {
        let mut inventory: Vec<Value> = payload()
            .into_iter()
            .map(|(relative, bytes)| {
                json!({
                    "path": relative,
                    "size": bytes.len(),
                    "sha256": sha256_hex(bytes),
                })
            })
            .collect();
        inventory.sort_by(|a, b| a["path"].as_str().unwrap().cmp(b["path"].as_str().unwrap()));
        let mut receipt = json!({
            "schema": 1,
            "development": true,
            "publishable": false,
            "signing": "disabled",
            "attestation": "absent",
            "source_commit": COMMIT,
            "source_tree": TREE,
            "platform": "windows",
            "architecture": std::env::consts::ARCH,
            "payload": inventory,
        });
        change(&mut receipt);
        let bytes = serde_json::to_vec(&receipt).expect("receipt bytes");
        write(&self.root, RECEIPT_FILE, &bytes);
        bytes
    }

    fn install_receipt(&self, digest: &str, change: impl FnOnce(&mut Value)) {
        let mut receipt = json!({
            "schema": 1,
            "version": env!("CARGO_PKG_VERSION"),
            "package_kind": "msi",
            "development_receipt_sha256": digest,
        });
        change(&mut receipt);
        write(
            &self.root,
            super::super::RECEIPT_NAME,
            &serde_json::to_vec(&receipt).expect("install receipt bytes"),
        );
    }

    fn verify(&self) -> Result<()> {
        verify_installed_runtime_at(&self.root, &self.executable(), &expected())
    }

    fn refusal(&self) -> String {
        format!(
            "{:#}",
            self.verify()
                .expect_err("this installation must be refused")
        )
    }
}

fn write(root: &Path, relative: &str, bytes: &[u8]) {
    let path = root.join(relative.replace('/', "\\"));
    std::fs::create_dir_all(path.parent().expect("a parent")).expect("parent directory");
    std::fs::write(path, bytes).expect("fixture file");
}

#[test]
fn a_complete_development_installation_is_admitted() {
    Fixture::new().verify().expect("a consistent package");
}

#[test]
fn a_changed_payload_byte_is_refused() {
    let fixture = Fixture::new();
    // The same length, so the digest is the only thing that can catch it.
    write(&fixture.root, "lib/cua/bootstrap.py", b"PRINT()");
    assert!(
        fixture.refusal().contains("bytes differ"),
        "{}",
        fixture.refusal()
    );
}

#[test]
fn a_grown_payload_file_is_refused() {
    let fixture = Fixture::new();
    write(&fixture.root, "lib/cua/bootstrap.py", b"print(1)\n");
    assert!(
        fixture.refusal().contains("exceeds its limit"),
        "{}",
        fixture.refusal()
    );
}

#[test]
fn a_truncated_payload_file_is_refused() {
    let fixture = Fixture::new();
    write(&fixture.root, "legal/TERMS.txt", b"");
    assert!(
        fixture.refusal().contains("bytes differ"),
        "{}",
        fixture.refusal()
    );
}

#[test]
fn a_removed_payload_file_is_refused() {
    let fixture = Fixture::new();
    std::fs::remove_file(fixture.path("sbom/vadgr.spdx.json")).expect("remove");
    assert!(
        fixture.refusal().contains("resolving"),
        "{}",
        fixture.refusal()
    );
}

#[test]
fn a_file_the_inventory_does_not_name_is_refused() {
    let fixture = Fixture::new();
    write(&fixture.root, "lib/cua/planted.dll", b"loaded beside it");
    let refusal = fixture.refusal();
    assert!(
        refusal.contains("does not inventory") && refusal.contains("planted.dll"),
        "{refusal}"
    );
}

#[test]
fn the_runtime_subtree_the_daemon_writes_is_admitted() {
    let fixture = Fixture::new();
    // `computer-use enable` builds its environment inside the installed root
    // after the install, so this one subtree cannot be a closed inventory.
    write(
        &fixture.root,
        "lib/cua/environments/gen1/pyvenv.cfg",
        b"relocatable = true",
    );
    fixture
        .verify()
        .expect("the runtime environment is not a planted file");
}

#[test]
fn a_planted_release_attestation_is_refused() {
    for name in FORBIDDEN {
        let fixture = Fixture::new();
        write(&fixture.root, name, b"{}");
        let refusal = fixture.refusal();
        assert!(
            refusal.contains("no release authority"),
            "{name}: {refusal}"
        );
    }
}

#[test]
fn a_release_attestation_deeper_in_the_tree_is_refused() {
    let fixture = Fixture::new();
    // The root check alone would miss this one, and admission must not depend
    // on an attacker choosing the obvious directory.
    write(
        &fixture.root,
        "lib/cua/cua-runtime-authorization.json",
        b"{}",
    );
    assert!(
        fixture.refusal().contains("no release authority"),
        "{}",
        fixture.refusal()
    );
}

#[test]
fn a_receipt_the_installation_did_not_record_is_refused() {
    let fixture = Fixture::new();
    fixture.development_receipt(|receipt| {
        receipt["source_commit"] = json!(COMMIT.replace('1', "4"));
    });
    assert!(
        fixture.refusal().contains("differs from the digest"),
        "{}",
        fixture.refusal()
    );
}

#[test]
fn an_installation_recording_no_development_receipt_is_refused() {
    let fixture = Fixture::new();
    fixture.install_receipt("unused", |receipt| {
        receipt
            .as_object_mut()
            .expect("an object")
            .remove("development_receipt_sha256");
    });
    assert!(
        fixture.refusal().contains("records no development receipt"),
        "{}",
        fixture.refusal()
    );
}

#[test]
fn a_receipt_claiming_release_and_development_standing_is_refused() {
    for field in ["manifest_sha256", "release_sequence"] {
        let fixture = Fixture::new();
        let bytes = fixture.development_receipt(|_| {});
        fixture.install_receipt(&sha256_hex(&bytes), |receipt| {
            receipt[field] = if field == "release_sequence" {
                json!(500)
            } else {
                json!("a".repeat(64))
            };
        });
        let refusal = fixture.refusal();
        assert!(
            refusal.contains("no release manifest or sequence"),
            "{field}: {refusal}"
        );
    }
}

#[test]
fn a_signed_package_kind_is_refused() {
    let fixture = Fixture::new();
    let bytes = fixture.development_receipt(|_| {});
    fixture.install_receipt(&sha256_hex(&bytes), |receipt| {
        receipt["package_kind"] = json!("appimage");
    });
    assert!(
        fixture.refusal().contains("installation receipt differs"),
        "{}",
        fixture.refusal()
    );
}

#[test]
fn a_receipt_claiming_release_standing_is_refused() {
    for (field, value) in [
        ("development", json!(false)),
        ("publishable", json!(true)),
        ("signing", json!("enabled")),
        ("attestation", json!("present")),
    ] {
        let fixture = Fixture::new();
        let bytes = fixture.development_receipt(|receipt| receipt[field] = value.clone());
        fixture.install_receipt(&sha256_hex(&bytes), |_| {});
        let refusal = fixture.refusal();
        assert!(
            refusal.contains("does not declare an unsigned development package"),
            "{field}: {refusal}"
        );
    }
}

#[test]
fn a_receipt_naming_another_source_is_refused() {
    for field in ["source_commit", "source_tree"] {
        let fixture = Fixture::new();
        let bytes = fixture.development_receipt(|receipt| {
            receipt[field] = json!("3333333333333333333333333333333333333333");
        });
        fixture.install_receipt(&sha256_hex(&bytes), |_| {});
        let refusal = fixture.refusal();
        assert!(
            refusal.contains("another source than the compiled identity"),
            "{field}: {refusal}"
        );
    }
}

#[test]
fn a_receipt_naming_another_platform_is_refused() {
    let fixture = Fixture::new();
    let bytes = fixture.development_receipt(|receipt| receipt["platform"] = json!("linux"));
    fixture.install_receipt(&sha256_hex(&bytes), |_| {});
    assert!(
        fixture.refusal().contains("names another platform"),
        "{}",
        fixture.refusal()
    );
}

#[test]
fn an_inventory_covering_its_own_records_is_refused() {
    for name in [super::super::RECEIPT_NAME, RECEIPT_FILE] {
        let fixture = Fixture::new();
        let bytes = fixture.development_receipt(|receipt| {
            // Inventorying either record is circular: the install receipt
            // records the development receipt's digest, so a receipt that
            // covers itself can never be consistent.
            receipt["payload"]
                .as_array_mut()
                .expect("an inventory")
                .insert(
                    0,
                    json!({"path": name, "size": 0, "sha256": sha256_hex(b"")}),
                );
        });
        fixture.install_receipt(&sha256_hex(&bytes), |_| {});
        let refusal = fixture.refusal();
        assert!(
            refusal.contains("must exclude the records that authorize it"),
            "{name}: {refusal}"
        );
    }
}

#[test]
fn an_unordered_or_repeated_inventory_is_refused() {
    let fixture = Fixture::new();
    let bytes = fixture.development_receipt(|receipt| {
        let inventory = receipt["payload"].as_array_mut().expect("an inventory");
        inventory.swap(0, 1);
    });
    fixture.install_receipt(&sha256_hex(&bytes), |_| {});
    assert!(
        fixture.refusal().contains("unordered or repeats a path"),
        "{}",
        fixture.refusal()
    );
}

#[test]
fn an_inventoried_path_that_leaves_the_root_is_refused() {
    let fixture = Fixture::new();
    for escape in [
        "../outside.txt",
        "lib/../../outside.txt",
        "C:/Windows/py.exe",
    ] {
        let bytes = fixture.development_receipt(|receipt| {
            receipt["payload"].as_array_mut().expect("an inventory")[0] = json!({
                "path": escape, "size": 1, "sha256": sha256_hex(b"x"),
            });
        });
        fixture.install_receipt(&sha256_hex(&bytes), |_| {});
        let refusal = fixture.refusal();
        assert!(
            refusal.contains("invalid inventoried payload file"),
            "{escape}: {refusal}"
        );
    }
}

#[test]
fn an_empty_inventory_is_refused() {
    let fixture = Fixture::new();
    let bytes = fixture.development_receipt(|receipt| receipt["payload"] = json!([]));
    fixture.install_receipt(&sha256_hex(&bytes), |_| {});
    assert!(
        fixture.refusal().contains("inventories no payload"),
        "{}",
        fixture.refusal()
    );
}

#[test]
fn another_running_executable_is_refused() {
    let fixture = Fixture::new();
    let error =
        verify_installed_runtime_at(&fixture.root, &fixture.path("vadgr-app.exe"), &expected())
            .expect_err("the launcher is not the backend");
    assert!(
        format!("{error:#}").contains("not executing its installed package"),
        "{error:#}"
    );
}

#[test]
fn an_executable_outside_the_installation_is_refused() {
    let fixture = Fixture::new();
    let outside = fixture.root.parent().expect("a parent").join("vadgr.exe");
    std::fs::write(&outside, b"the backend image").expect("outside copy");
    let error = verify_installed_runtime_at(&fixture.root, &outside, &expected())
        .expect_err("an identical copy elsewhere is still elsewhere");
    assert!(
        format!("{error:#}").contains("not executing its installed package"),
        "{error:#}"
    );
}

#[test]
fn a_missing_development_receipt_is_refused() {
    let fixture = Fixture::new();
    std::fs::remove_file(fixture.path(RECEIPT_FILE)).expect("remove");
    assert!(
        fixture.refusal().contains("resolving"),
        "{}",
        fixture.refusal()
    );
}

#[test]
fn a_path_leaving_the_root_is_refused_before_it_is_opened() {
    let root = ConfinedRoot::open(Fixture::new().root.as_path()).expect("the root");
    for escape in ["..", "../..", "lib/../../elsewhere"] {
        let error = root
            .resolve(escape)
            .expect_err("a path leaving the root must be refused");
        let text = format!("{error:#}");
        assert!(
            text.contains("unsafe qualification path") || text.contains("leaves the installed"),
            "{escape}: {text}"
        );
    }
}

#[test]
fn a_windows_device_name_is_not_a_payload_path() {
    for reserved in ["nul", "CON", "lpt1.txt", "aux"] {
        assert!(!safe_name(reserved), "{reserved} must not be a safe name");
    }
    for ordinary in ["vadgr.exe", "payload.json", "console.log", "auxiliary.txt"] {
        assert!(safe_name(ordinary), "{ordinary} must be a safe name");
    }
}

#[test]
fn a_trailing_dot_or_space_is_not_a_payload_path() {
    // Windows strips both when it opens a name, so two different inventory
    // entries would reach the same file.
    for name in ["payload.json ", "payload.", "lib/cua ", ""] {
        assert!(!safe_path(name), "{name:?} must not be a safe path");
    }
}

#[test]
fn the_digest_helper_matches_the_receipt_format() {
    assert_eq!(
        sha256_hex(b""),
        "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
    );
    assert!(hex(&sha256_hex(b"vadgr"), 64));
    assert!(!hex("ABCDEF", 6), "uppercase is not the recorded format");
}
