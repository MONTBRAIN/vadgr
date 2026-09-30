//! Isolated fixtures only. No AppImage, daemon or host lifecycle is executed.

use super::*;
use serde_json::json;
use std::fs;
use std::os::unix::fs::{PermissionsExt, symlink};

const COMMIT: &str = "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa";
const TREE: &str = "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb";

struct Fixture {
    temporary: tempfile::TempDir,
    receipt: Value,
}

impl Fixture {
    fn new() -> Self {
        let temporary = tempfile::tempdir().unwrap();
        let root = temporary.path().join("mounted");
        let terms = b"Synthetic fixture terms\n";
        let inventory = json!({"schema":1,"version":"0.5.0","target":"x86_64-unknown-linux-gnu",
                               "terms_version":"1.0","terms_sha256":sha256_hex(terms)});
        for (path, bytes) in [
            ("AppRun", b"fixture launcher".to_vec()),
            ("usr/bin/vadgr", b"fixture executable".to_vec()),
            ("legal/TERMS.txt", terms.to_vec()),
            ("legal/empty.txt", Vec::new()),
            (
                "package-input-inventory.json",
                canonical(&inventory).unwrap(),
            ),
            ("package-input-review.json", b"{}\n".to_vec()),
            ("usr/lib/cua/payload.json", b"{}\n".to_vec()),
            ("usr/lib/cua/installed-inventory.json", b"{}\n".to_vec()),
            ("sbom/fixture.json", b"{}\n".to_vec()),
        ] {
            let destination = root.join(path);
            fs::create_dir_all(destination.parent().unwrap()).unwrap();
            fs::write(&destination, bytes).unwrap();
            fs::set_permissions(destination, fs::Permissions::from_mode(0o644)).unwrap();
        }
        symlink("vadgr", root.join("usr/bin/alias")).unwrap();
        let vehicle = temporary
            .path()
            .join("Vadgr-0.5.0-linux-x86_64-installer.AppImage");
        fs::write(&vehicle, b"synthetic vehicle bytes").unwrap();
        let pins: Value =
            serde_json::from_str(include_str!("../../packaging/linux/runtime.json")).unwrap();
        let (size, hash) = digest(&vehicle, MAX_FILE).unwrap();
        let mut fixture = Self {
            temporary,
            receipt: json!({
                "schema":1,"development":true,"publishable":false,
                "signing":"disabled","attestation":"absent",
                "source_commit":COMMIT,"source_tree":TREE,"platform":"linux","architecture":"x86_64",
                "artifact":{"filename":"Vadgr-0.5.0-linux-x86_64-installer.AppImage","size":size,"sha256":hash},
                "appdir":[],"preparation_sha256":"cccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc",
                "appimage_runtime":pins["targets"]["x86_64"],
                "abi":{"producer_runner":"ubuntu-24.04","maximum_glibc":"2.39","glibc_requirements":["GLIBC_2.17","GLIBC_2.39","GLIBC_ABI_DT_RELR"]}
            }),
        };
        fixture.refresh_inventory();
        fixture.save();
        fixture
    }

    fn root(&self) -> std::path::PathBuf {
        self.temporary.path().join("mounted")
    }
    fn vehicle(&self) -> std::path::PathBuf {
        self.temporary
            .path()
            .join("Vadgr-0.5.0-linux-x86_64-installer.AppImage")
    }
    fn sidecar(&self) -> std::path::PathBuf {
        self.vehicle().with_extension("development.json")
    }
    fn save(&self) {
        fs::write(self.sidecar(), canonical(&self.receipt).unwrap()).unwrap();
    }

    // Use an independent fixture traversal, not the verifier's inventory walker.
    fn refresh_inventory(&mut self) {
        let root = self.root();
        let mut pending = vec![root.clone()];
        let mut rows = Vec::new();
        while let Some(directory) = pending.pop() {
            for entry in fs::read_dir(directory).unwrap() {
                let path = entry.unwrap().path();
                let info = fs::symlink_metadata(&path).unwrap();
                if info.is_dir() {
                    pending.push(path);
                    continue;
                }
                let name = path.strip_prefix(&root).unwrap().to_str().unwrap();
                if info.file_type().is_symlink() {
                    rows.push(
                        json!({"path":name,"kind":"symlink","mode":info.mode() & 0o7777,
                        "target":fs::read_link(&path).unwrap().to_str().unwrap()}),
                    );
                } else {
                    let bytes = fs::read(&path).unwrap();
                    rows.push(
                        json!({"path":name,"kind":"file","mode":info.mode() & 0o7777,
                        "size":bytes.len(),"sha256":sha256_hex(&bytes)}),
                    );
                }
            }
        }
        rows.sort_by(|a, b| a["path"].as_str().cmp(&b["path"].as_str()));
        self.receipt["appdir"] = json!(rows);
    }

    fn check(&self) -> Result<VerifiedDevelopmentReceipt> {
        verify(
            &self.vehicle(),
            &self.root(),
            &self.root().join("usr/bin/vadgr"),
            &Expected {
                version: "0.5.0",
                architecture: "x86_64",
                source_commit: COMMIT,
                source_tree: TREE,
            },
        )
    }
}

#[test]
fn exact_fixture_verifies_without_claiming_a_signature() {
    let fixture = Fixture::new();
    let checked = fixture.check().unwrap();
    assert_eq!(checked.terms_version(), Some("1.0"));
    assert_eq!(checked.terms_text(), Some("Synthetic fixture terms\n"));
    assert_eq!(
        checked.artifact_name(),
        "Vadgr-0.5.0-linux-x86_64-installer.AppImage"
    );
    assert!(hex(checked.receipt_sha256(), 64));
    let renamed = fixture.temporary.path().join("Vadgr.AppImage");
    fs::copy(fixture.vehicle(), &renamed).unwrap();
    checked.verify_vehicle_at(&renamed).unwrap();
}

#[test]
fn public_unsigned_package_preflight_accepts_compiled_subject_without_release_manifest() {
    let identity = compiled_identity().unwrap();
    let mut fixture = Fixture::new();
    let filename = format!(
        "Vadgr-{}-linux-{}-installer.AppImage",
        identity.version, identity.architecture
    );
    let vehicle = fixture.temporary.path().join(&filename);
    if vehicle != fixture.vehicle() {
        fs::rename(fixture.vehicle(), &vehicle).unwrap();
        fs::remove_file(fixture.sidecar()).unwrap();
    }
    fixture.receipt["source_commit"] = json!(identity.source_commit);
    fixture.receipt["source_tree"] = json!(identity.source_tree);
    fixture.receipt["architecture"] = json!(identity.architecture);
    fixture.receipt["artifact"]["filename"] = json!(filename);
    let pins: Value =
        serde_json::from_str(include_str!("../../packaging/linux/runtime.json")).unwrap();
    fixture.receipt["appimage_runtime"] = pins["targets"][identity.architecture].clone();

    // Exercise the real executable-binding check without launching a process.
    fs::copy(
        std::env::current_exe().unwrap(),
        fixture.root().join("usr/bin/vadgr"),
    )
    .unwrap();
    let inventory_path = fixture.root().join("package-input-inventory.json");
    let mut inventory: Value = serde_json::from_slice(&fs::read(&inventory_path).unwrap()).unwrap();
    inventory["version"] = json!(identity.version);
    inventory["target"] = json!(format!("{}-unknown-linux-gnu", identity.architecture));
    fs::write(inventory_path, canonical(&inventory).unwrap()).unwrap();
    fixture.refresh_inventory();
    let sidecar = vehicle.with_extension("development.json");
    let receipt_bytes = canonical(&fixture.receipt).unwrap();
    fs::write(&sidecar, &receipt_bytes).unwrap();

    let manifest = fixture.temporary.path().join("release-manifest.json");
    let signature = fixture
        .temporary
        .path()
        .join("release-manifest.json.bundle.jsonl");
    assert!(!manifest.exists() && !signature.exists());
    assert_eq!(fixture.receipt["development"], true);
    assert_eq!(fixture.receipt["publishable"], false);
    assert_eq!(fixture.receipt["signing"], "disabled");
    assert_eq!(fixture.receipt["attestation"], "absent");

    let package = crate::install::VerifiedLinuxPackage::open(
        &vehicle,
        &manifest,
        &signature,
        &fixture.root(),
    )
    .expect("unsigned public preflight must not require a signed release manifest");
    assert_eq!(package.version(), identity.version);
    assert_eq!(package.artifact_name(), filename);
    assert_eq!(package.terms_version(), Some("1.0"));
    assert_eq!(
        package.terms_sha256(),
        sha256_hex(b"Synthetic fixture terms\n")
    );
    assert_eq!(
        package.terms_text(&fixture.root()).unwrap(),
        "Synthetic fixture terms\n"
    );
    package.verify_vehicle_at(&vehicle).unwrap();
    assert_eq!(fs::read(sidecar).unwrap(), receipt_bytes);
    assert!(!manifest.exists() && !signature.exists());
}

#[test]
fn canonical_bytes_match_independent_python_fixture() {
    let value = json!({"z":[{},[],"é😀\u{7f}\n\t\"\\"],"a":1});
    let expected = include_bytes!("development-fixtures/canonical.json");
    assert_eq!(canonical(&value).unwrap(), expected);
}

#[test]
fn every_fixed_field_is_required_and_unknown_fields_are_refused() {
    let original = Fixture::new();
    for parent in ["", "/artifact", "/appimage_runtime", "/abi"] {
        let fields: Vec<_> = original
            .receipt
            .pointer(parent)
            .unwrap()
            .as_object()
            .unwrap()
            .keys()
            .cloned()
            .collect();
        for field in fields {
            let mut fixture = Fixture::new();
            fixture
                .receipt
                .pointer_mut(parent)
                .unwrap()
                .as_object_mut()
                .unwrap()
                .remove(&field);
            fixture.save();
            assert!(fixture.check().is_err(), "missing {parent}/{field}");
        }
        let mut fixture = Fixture::new();
        fixture.receipt.pointer_mut(parent).unwrap()["unknown"] = json!(true);
        fixture.save();
        assert!(fixture.check().is_err(), "unknown field at {parent}");
    }
}

#[test]
fn incorrect_identity_and_claims_are_refused() {
    for (pointer, replacement) in [
        ("/schema", json!(2)),
        ("/development", json!(false)),
        ("/publishable", json!(true)),
        ("/signing", json!("signed")),
        ("/attestation", json!("present")),
        ("/source_commit", json!(TREE)),
        ("/source_tree", json!(COMMIT)),
        ("/architecture", json!("aarch64")),
        ("/platform", json!("wsl")),
        ("/artifact/filename", json!("Vadgr.AppImage")),
        ("/artifact/size", json!(1)),
        ("/artifact/sha256", json!("0".repeat(64))),
        ("/preparation_sha256", json!("bad")),
        ("/appimage_runtime/asset_id", json!(1)),
        ("/appimage_runtime/sha256", json!("0".repeat(64))),
        ("/abi/producer_runner", json!("ubuntu-latest")),
        ("/abi/maximum_glibc", json!("2.43")),
        ("/abi/glibc_requirements", json!(["GLIBC_2.43"])),
        ("/appdir", json!([])),
    ] {
        let mut fixture = Fixture::new();
        *fixture.receipt.pointer_mut(pointer).unwrap() = replacement;
        fixture.save();
        assert!(fixture.check().is_err(), "accepted changed {pointer}");
    }
}

#[test]
fn malformed_noncanonical_and_duplicate_key_receipts_are_refused() {
    for bytes in [
        b"{}".to_vec(),
        b"{\"schema\":1,\"schema\":1}\n".to_vec(),
        vec![0xff],
        vec![b' '; MAX_RECEIPT as usize + 1],
    ] {
        let fixture = Fixture::new();
        fs::write(fixture.sidecar(), bytes).unwrap();
        assert!(fixture.check().is_err());
    }
    let fixture = Fixture::new();
    fs::write(
        fixture.sidecar(),
        serde_json::to_vec(&fixture.receipt).unwrap(),
    )
    .unwrap();
    assert!(fixture.check().is_err());
}

#[test]
fn inventory_must_be_exact_including_modes_links_and_empty_files() {
    for change in ["extra", "missing", "bytes", "mode", "link", "hardlink"] {
        let fixture = Fixture::new();
        let file = fixture.root().join("sbom/fixture.json");
        match change {
            "extra" => fs::write(fixture.root().join("extra"), []).unwrap(),
            "missing" => fs::remove_file(file).unwrap(),
            "bytes" => fs::write(file, b"changed").unwrap(),
            "mode" => fs::set_permissions(file, fs::Permissions::from_mode(0o755)).unwrap(),
            "link" => {
                fs::remove_file(fixture.root().join("usr/bin/alias")).unwrap();
                symlink("../../AppRun", fixture.root().join("usr/bin/alias")).unwrap();
            }
            _ => fs::hard_link(file, fixture.root().join("hardlink")).unwrap(),
        }
        assert!(fixture.check().is_err(), "accepted {change}");
    }
}

#[test]
fn unsafe_members_and_link_escapes_are_refused() {
    for path in [
        "../outside",
        "/absolute",
        "a//b",
        "a/./b",
        "a/../b",
        "a\\b",
        "a\nb",
    ] {
        let mut fixture = Fixture::new();
        fixture.receipt["appdir"][0]["path"] = json!(path);
        fixture.save();
        assert!(fixture.check().is_err());
    }
    let fixture = Fixture::new();
    let alias = fixture.root().join("usr/bin/alias");
    fs::remove_file(&alias).unwrap();
    symlink("../../..", alias).unwrap();
    assert!(fixture.check().is_err());
    let fixture = Fixture::new();
    let alias = fixture.root().join("usr/bin/alias");
    fs::remove_file(&alias).unwrap();
    symlink("alias", alias).unwrap();
    assert!(fixture.check().is_err());
}

#[test]
fn member_fields_duplicates_and_order_are_strict() {
    for kind in ["file", "symlink"] {
        let original = Fixture::new();
        let index = original.receipt["appdir"]
            .as_array()
            .unwrap()
            .iter()
            .position(|row| row["kind"] == kind)
            .unwrap();
        let fields: Vec<_> = original.receipt["appdir"][index]
            .as_object()
            .unwrap()
            .keys()
            .cloned()
            .collect();
        for field in fields {
            let mut fixture = Fixture::new();
            fixture.receipt["appdir"][index]
                .as_object_mut()
                .unwrap()
                .remove(&field);
            fixture.save();
            assert!(fixture.check().is_err());
        }
        let mut fixture = Fixture::new();
        fixture.receipt["appdir"][index]["unknown"] = json!(true);
        fixture.save();
        assert!(fixture.check().is_err());
    }
    let mut fixture = Fixture::new();
    let duplicate = fixture.receipt["appdir"][0].clone();
    fixture.receipt["appdir"]
        .as_array_mut()
        .unwrap()
        .insert(0, duplicate);
    fixture.save();
    assert!(fixture.check().is_err());
    let mut fixture = Fixture::new();
    fixture.receipt["appdir"].as_array_mut().unwrap().reverse();
    fixture.save();
    assert!(fixture.check().is_err());
}

#[test]
fn wrong_terms_running_executable_and_mixed_release_metadata_are_refused() {
    let mut fixture = Fixture::new();
    fs::write(fixture.root().join("legal/TERMS.txt"), b"changed").unwrap();
    fixture.refresh_inventory();
    fixture.save();
    assert!(fixture.check().is_err());
    let fixture = Fixture::new();
    assert!(
        verify(
            &fixture.vehicle(),
            &fixture.root(),
            &fixture.vehicle(),
            &Expected {
                version: "0.5.0",
                architecture: "x86_64",
                source_commit: COMMIT,
                source_tree: TREE,
            }
        )
        .is_err()
    );
    for name in [
        "release-manifest.json",
        "release-manifest.json.bundle.jsonl",
    ] {
        let fixture = Fixture::new();
        fs::write(fixture.temporary.path().join(name), b"not a real signature").unwrap();
        assert!(fixture.check().is_err());
    }
}

#[test]
fn linked_receipts_and_changed_vehicles_are_refused() {
    let fixture = Fixture::new();
    let original = fixture.temporary.path().join("receipt-original.json");
    fs::rename(fixture.sidecar(), &original).unwrap();
    symlink(original, fixture.sidecar()).unwrap();
    assert!(fixture.check().is_err());
    let fixture = Fixture::new();
    fs::write(fixture.vehicle(), b"changed").unwrap();
    assert!(fixture.check().is_err());
}

#[test]
fn swapped_ancestor_cannot_redirect_a_descriptor_relative_read() {
    let fixture = Fixture::new();
    let root = ConfinedRoot::open(&fixture.root()).unwrap();
    let outside = fixture.temporary.path().join("outside");
    fs::create_dir_all(outside.join("bin")).unwrap();
    fs::write(outside.join("bin/vadgr"), b"outside sentinel").unwrap();
    fs::rename(
        fixture.root().join("usr"),
        fixture.root().join("usr-original"),
    )
    .unwrap();
    symlink(outside, fixture.root().join("usr")).unwrap();
    assert!(root.regular("usr/bin/vadgr", MAX_FILE).is_err());
}

#[test]
fn ancestor_swap_during_enumeration_is_refused() {
    let fixture = Fixture::new();
    let root = ConfinedRoot::open(&fixture.root()).unwrap();
    let outside = fixture.temporary.path().join("outside");
    fs::create_dir(&outside).unwrap();
    fs::write(outside.join("vadgr"), b"outside sentinel").unwrap();
    let mut changed = false;
    let result = inventory_with_hook(&root, &mut |path| {
        if path == "usr/bin/vadgr" {
            fs::rename(
                fixture.root().join("usr/bin"),
                fixture.root().join("usr/bin-original"),
            )?;
            symlink(&outside, fixture.root().join("usr/bin"))?;
            changed = true;
        }
        Ok(())
    });
    assert!(changed && result.is_err());
}

#[test]
fn replaced_leaf_cannot_rebind_an_open_descriptor() {
    let fixture = Fixture::new();
    let root = ConfinedRoot::open(&fixture.root()).unwrap();
    let file = root.regular("usr/bin/vadgr", MAX_FILE).unwrap();
    let path = fixture.root().join("usr/bin/vadgr");
    fs::rename(&path, fixture.root().join("usr/bin/original")).unwrap();
    fs::write(&path, b"replacement").unwrap();
    assert!(root.assert_bound("usr/bin/vadgr", &file.stamp).is_err());
    // The pinned descriptor still refers to the old inode, never replacement.
    assert_eq!(file.file.metadata().unwrap().ino(), file.stamp.inode);
    assert_ne!(fs::metadata(path).unwrap().ino(), file.stamp.inode);
}

#[test]
fn in_place_write_during_hash_is_refused_without_sleep() {
    let fixture = Fixture::new();
    let root = ConfinedRoot::open(&fixture.root()).unwrap();
    let file = root.regular("usr/bin/vadgr", MAX_FILE).unwrap();
    let mut changed = false;
    let result = file.scan(MAX_FILE, |_| {
        if !changed {
            fs::write(fixture.root().join("usr/bin/vadgr"), b"changed")?;
            changed = true;
        }
        Ok(())
    });
    assert!(changed && result.is_err());
}

#[test]
fn same_length_change_and_metadata_change_invalidate_retained_stamp() {
    let fixture = Fixture::new();
    let root = ConfinedRoot::open(&fixture.root()).unwrap();
    let file = root.regular("usr/bin/vadgr", MAX_FILE).unwrap();
    let result = file.scan(MAX_FILE, |_| {
        fs::write(fixture.root().join("usr/bin/vadgr"), b"FIXTURE EXECUTABLE")?;
        fs::set_permissions(
            fixture.root().join("usr/bin/vadgr"),
            fs::Permissions::from_mode(0o755),
        )?;
        Ok(())
    });
    assert!(result.is_err());
}

#[test]
fn second_snapshot_detects_metadata_or_membership_changes() {
    let fixture = Fixture::new();
    let root = ConfinedRoot::open(&fixture.root()).unwrap();
    let first = mounted_inventory(&root).unwrap();
    fs::set_permissions(
        fixture.root().join("legal/empty.txt"),
        fs::Permissions::from_mode(0o755),
    )
    .unwrap();
    let second = mounted_inventory(&root).unwrap();
    assert_ne!(first, second);
    fs::write(fixture.root().join("legal/new"), b"unexpected").unwrap();
    let second = mounted_inventory(&root).unwrap();
    assert_ne!(first, second);
}

#[test]
fn root_replacement_and_symlink_replacement_are_refused() {
    let fixture = Fixture::new();
    let root = ConfinedRoot::open(&fixture.root()).unwrap();
    let link = root.pin("usr/bin/alias").unwrap();
    let stamp = Stamp::read(&link).unwrap();
    fs::remove_file(fixture.root().join("usr/bin/alias")).unwrap();
    symlink("../../..", fixture.root().join("usr/bin/alias")).unwrap();
    assert!(root.link_target("usr/bin/alias", &link, &stamp).is_err());
    fs::rename(fixture.root(), fixture.temporary.path().join("old-mounted")).unwrap();
    fs::create_dir(fixture.root()).unwrap();
    assert!(root.assert_root().is_err());
}

#[test]
fn retained_receipt_does_not_depend_on_damaged_installed_files_or_grant_assent() {
    let fixture = Fixture::new();
    let checked = fixture.check().unwrap();
    fs::write(fixture.root().join("legal/TERMS.txt"), b"damaged").unwrap();
    assert!(fixture.check().is_err());
    let expected = Expected {
        version: "0.5.0",
        architecture: "x86_64",
        source_commit: COMMIT,
        source_tree: TREE,
    };
    let reopened = open_bound(
        &fixture.vehicle(),
        &fixture.sidecar(),
        Some(checked.receipt_sha256()),
        &expected,
    )
    .unwrap()
    .finish(None);
    assert_eq!(reopened.terms_version(), None);
    assert_eq!(reopened.terms_text(), None);
    assert_eq!(reopened.terms_sha256(), checked.terms_sha256());
    assert_eq!(reopened.receipt_bytes(), checked.receipt_bytes());
    assert!(
        open_bound(
            &fixture.vehicle(),
            &fixture.sidecar(),
            Some(&"0".repeat(64)),
            &expected
        )
        .is_err()
    );
}

#[test]
fn staging_copies_verified_descriptor_bytes_and_never_overwrites() {
    let fixture = Fixture::new();
    let checked = fixture.check().unwrap();
    let destination = fixture.temporary.path().join("new-copy");
    checked.copy_vehicle_to(&destination).unwrap();
    assert_eq!(
        fs::read(&destination).unwrap(),
        fs::read(fixture.vehicle()).unwrap()
    );
    assert_eq!(fs::metadata(&destination).unwrap().mode() & 0o777, 0o600);
    assert!(checked.copy_vehicle_to(&destination).is_err());
    fs::write(fixture.vehicle(), b"changed").unwrap();
    assert!(
        checked
            .copy_vehicle_to(&fixture.temporary.path().join("refused-copy"))
            .is_err()
    );
}

#[test]
fn staging_refuses_a_symlinked_parent() {
    let fixture = Fixture::new();
    let checked = fixture.check().unwrap();
    let outside = fixture.temporary.path().join("outside");
    fs::create_dir(&outside).unwrap();
    symlink(&outside, fixture.temporary.path().join("stage")).unwrap();
    assert!(
        checked
            .copy_vehicle_to(&fixture.temporary.path().join("stage/copy"))
            .is_err()
    );
    assert!(!outside.join("copy").exists());
}

#[test]
fn bytewise_hex_matches_known_digest() {
    assert_eq!(
        lowercase_hex(&[0, 1, 15, 16, 127, 128, 255]),
        "00010f107f80ff"
    );
    assert_eq!(
        sha256_hex(b"abc"),
        "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"
    );
}

#[test]
fn displayed_terms_remain_the_verified_bytes_after_path_changes() {
    let fixture = Fixture::new();
    let checked = fixture.check().unwrap();
    fs::write(
        fixture.root().join("legal/TERMS.txt"),
        b"unverified replacement",
    )
    .unwrap();
    assert_eq!(checked.terms_text(), Some("Synthetic fixture terms\n"));
    assert!(fixture.check().is_err());
}

#[test]
fn invalid_utf8_terms_are_refused_even_when_their_hash_matches() {
    let mut fixture = Fixture::new();
    fs::write(fixture.root().join("legal/TERMS.txt"), [0xff]).unwrap();
    let inventory_path = fixture.root().join("package-input-inventory.json");
    let mut inventory: Value = serde_json::from_slice(&fs::read(&inventory_path).unwrap()).unwrap();
    inventory["terms_sha256"] = json!(sha256_hex(&[0xff]));
    fs::write(inventory_path, canonical(&inventory).unwrap()).unwrap();
    fixture.refresh_inventory();
    fixture.save();
    assert!(fixture.check().is_err());
}

#[test]
fn staged_metadata_requires_exact_nonterms_members_modes_and_types() {
    for directory in ["legal", "sbom"] {
        for change in ["bytes", "missing", "extra", "mode", "link"] {
            let fixture = Fixture::new();
            let checked = fixture.check().unwrap();
            checked.verify_staged_metadata(&fixture.root()).unwrap();
            let member = fixture.root().join(if directory == "legal" {
                "legal/empty.txt"
            } else {
                "sbom/fixture.json"
            });
            match change {
                "bytes" => fs::write(&member, b"changed owned metadata").unwrap(),
                "missing" => fs::remove_file(&member).unwrap(),
                "extra" => {
                    fs::write(fixture.root().join(directory).join("extra"), b"unexpected").unwrap()
                }
                "mode" => fs::set_permissions(&member, fs::Permissions::from_mode(0o755)).unwrap(),
                _ => {
                    fs::remove_file(&member).unwrap();
                    symlink("../legal/TERMS.txt", &member).unwrap();
                }
            }
            assert!(
                checked.verify_staged_metadata(&fixture.root()).is_err(),
                "accepted {directory} {change}"
            );
        }
    }
}

#[test]
fn staged_metadata_rejects_linked_subtree_and_ignores_nonmetadata_cache() {
    let fixture = Fixture::new();
    let checked = fixture.check().unwrap();
    fs::create_dir(fixture.root().join("cache")).unwrap();
    fs::write(
        fixture.root().join("cache/vehicle"),
        b"separately verified vehicle",
    )
    .unwrap();
    checked.verify_staged_metadata(&fixture.root()).unwrap();
    fs::rename(
        fixture.root().join("legal"),
        fixture.root().join("legal-original"),
    )
    .unwrap();
    symlink("legal-original", fixture.root().join("legal")).unwrap();
    assert!(checked.verify_staged_metadata(&fixture.root()).is_err());
}
