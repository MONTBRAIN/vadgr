//! Build-only wheelhouse and schema-2 private-runtime identities.

use anyhow::{Context, Result, ensure};
use serde::{Deserialize, Serialize};
use sha2::{Digest, Sha256};
use std::collections::{BTreeMap, BTreeSet};
use std::io::Read;
use std::path::Path;

const INVENTORY: &str = "installed-inventory.json";
const MAX_METADATA: u64 = 16 * 1024 * 1024;

#[derive(Debug, Deserialize, Serialize, PartialEq, Eq)]
#[serde(deny_unknown_fields)]
struct FileRecord {
    size: u64,
    sha256: String,
}

#[derive(Debug, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
struct Inventory {
    schema: u32,
    target: String,
    #[serde(deserialize_with = "unique_files")]
    files: BTreeMap<String, FileRecord>,
}

fn unique_files<'de, D: serde::Deserializer<'de>>(
    deserializer: D,
) -> std::result::Result<BTreeMap<String, FileRecord>, D::Error> {
    struct Files;
    impl<'de> serde::de::Visitor<'de> for Files {
        type Value = BTreeMap<String, FileRecord>;
        fn expecting(&self, formatter: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
            formatter.write_str("unique inventory members")
        }
        fn visit_map<A: serde::de::MapAccess<'de>>(
            self,
            mut map: A,
        ) -> std::result::Result<Self::Value, A::Error> {
            let mut files = BTreeMap::new();
            while let Some((key, value)) = map.next_entry::<String, FileRecord>()? {
                if files.insert(key, value).is_some() {
                    return Err(serde::de::Error::custom("duplicate inventory member"));
                }
            }
            Ok(files)
        }
    }
    deserializer.deserialize_map(Files)
}

pub(super) fn digest(bytes: &[u8]) -> String {
    Sha256::digest(bytes)
        .iter()
        .map(|byte| format!("{byte:02x}"))
        .collect()
}

fn metadata(path: &Path) -> Result<Vec<u8>> {
    let record = std::fs::symlink_metadata(path)?;
    ensure!(
        record.is_file() && !record.file_type().is_symlink() && record.len() <= MAX_METADATA,
        "CUA metadata is absent, linked or oversized"
    );
    Ok(std::fs::read(path)?)
}

fn fingerprint(root: &Path, path: &Path) -> Result<FileRecord> {
    let entry = std::fs::symlink_metadata(path)?;
    if entry.file_type().is_symlink() {
        ensure!(
            cfg!(unix) && !std::fs::read_link(path)?.is_absolute(),
            "CUA file link must be relative on a Unix target"
        );
    }
    let resolved = std::fs::canonicalize(path)?;
    ensure!(
        resolved.starts_with(std::fs::canonicalize(root)?) && resolved.is_file(),
        "CUA file escapes its private tree"
    );
    let mut input = std::fs::File::open(path)?;
    let before = input.metadata()?;
    let mut hasher = Sha256::new();
    let mut size = 0;
    let mut block = [0u8; 64 * 1024];
    loop {
        let count = input.read(&mut block)?;
        if count == 0 {
            break;
        }
        size += count as u64;
        hasher.update(&block[..count]);
    }
    let after = input.metadata()?;
    ensure!(
        size == before.len()
            && size == after.len()
            && before.modified()? == after.modified()?
            && std::fs::canonicalize(path)? == resolved,
        "CUA file changed during verification"
    );
    Ok(FileRecord {
        size,
        sha256: hasher
            .finalize()
            .iter()
            .map(|byte| format!("{byte:02x}"))
            .collect(),
    })
}

fn collect(root: &Path, directory: &Path, files: &mut BTreeMap<String, FileRecord>) -> Result<()> {
    for entry in std::fs::read_dir(directory)? {
        let path = entry?.path();
        let kind = std::fs::symlink_metadata(&path)?.file_type();
        if kind.is_dir() {
            collect(root, &path, files)?;
        } else {
            let name = path
                .strip_prefix(root)?
                .to_str()
                .context("non-UTF-8 CUA path")?
                .replace('\\', "/");
            if name == INVENTORY || name == "payload.json" {
                continue;
            }
            ensure!(
                kind.is_file() || kind.is_symlink(),
                "special CUA file refused"
            );
            ensure!(files.len() < 100_000, "CUA inventory is oversized");
            files.insert(name, fingerprint(root, &path)?);
        }
    }
    Ok(())
}

pub(super) fn write_inventory(root: &Path, target: &str) -> Result<String> {
    let mut files = BTreeMap::new();
    collect(root, root, &mut files)?;
    ensure!(!files.is_empty(), "CUA inventory is empty");
    let record = Inventory {
        schema: 1,
        target: target.to_owned(),
        files,
    };
    let mut bytes = serde_json::to_vec_pretty(&record)?;
    bytes.push(b'\n');
    let hash = digest(&bytes);
    std::fs::write(root.join(INVENTORY), bytes)?;
    Ok(hash)
}

pub(super) fn validate_inventory(root: &Path, target: &str, expected: &str) -> Result<()> {
    let bytes = metadata(&root.join(INVENTORY))?;
    ensure!(digest(&bytes) == expected, "CUA inventory digest differs");
    let record: Inventory = serde_json::from_slice(&bytes)?;
    ensure!(
        record.schema == 1 && record.target == target && !record.files.is_empty(),
        "CUA inventory target or schema differs"
    );
    let mut files = BTreeMap::new();
    collect(root, root, &mut files)?;
    ensure!(
        files == record.files,
        "CUA installed file set or bytes differ"
    );
    Ok(())
}

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct Wheel {
    filename: String,
    name: String,
    version: String,
    size: u64,
    sha256: String,
}

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct Wheelhouse {
    schema: u32,
    target: String,
    requirements_sha256: String,
    wheel_manifest_sha256: String,
    wheels: Vec<Wheel>,
}

pub(super) fn validate_wheelhouse(
    root: &Path,
    target: &str,
    lock: &[u8],
    manifest_hash: &str,
) -> Result<()> {
    ensure!(
        root.is_absolute() && dunce::canonicalize(root)? == root,
        "wheelhouse must be an absolute unlinked build directory"
    );
    let receipt: Wheelhouse = serde_json::from_slice(&metadata(&root.join("wheelhouse.json"))?)?;
    ensure!(
        receipt.schema == 1
            && receipt.target == target
            && receipt.requirements_sha256 == digest(lock)
            && receipt.wheel_manifest_sha256 == manifest_hash,
        "wheelhouse differs from compiled release pins"
    );
    let lock = std::str::from_utf8(lock)?
        .replace("\\\r\n", " ")
        .replace("\\\n", " ");
    let row = regex::Regex::new(
        r"^([A-Za-z0-9][A-Za-z0-9._-]*)==([A-Za-z0-9][A-Za-z0-9.!+_-]*)\s+--hash=sha256:([0-9a-f]{64})$",
    )?;
    let normalizer = regex::Regex::new(r"[-_.]+")?;
    let mut expected = BTreeMap::new();
    for line in lock.lines() {
        let line = line.split('#').next().unwrap_or_default().trim();
        if line.is_empty() {
            continue;
        }
        let fields = row
            .captures(line)
            .context("target lock must select one exact wheel")?;
        let name = normalizer.replace_all(&fields[1], "-").to_ascii_lowercase();
        ensure!(
            expected
                .insert(name, (fields[2].to_owned(), fields[3].to_owned()))
                .is_none(),
            "target lock repeats a package"
        );
    }
    ensure!(!expected.is_empty(), "target lock is empty");
    let filename = regex::Regex::new(r"^[A-Za-z0-9_.-]+\.whl$")?;
    let mut selected = BTreeMap::new();
    let mut names = BTreeSet::from(["wheelhouse.json".to_owned()]);
    for wheel in receipt.wheels {
        ensure!(
            filename.is_match(&wheel.filename) && names.insert(wheel.filename.clone()),
            "unsafe or duplicate wheelhouse member"
        );
        let path = root.join(&wheel.filename);
        ensure!(
            !std::fs::symlink_metadata(&path)?.file_type().is_symlink(),
            "linked wheel refused"
        );
        let actual = fingerprint(root, &path)?;
        ensure!(
            actual.size == wheel.size && actual.sha256 == wheel.sha256,
            "wheel bytes differ from reviewed input"
        );
        let name = normalizer
            .replace_all(&wheel.name, "-")
            .to_ascii_lowercase();
        ensure!(
            name == wheel.name
                && selected
                    .insert(name, (wheel.version, wheel.sha256))
                    .is_none(),
            "wheelhouse repeats a package"
        );
    }
    ensure!(
        expected == selected,
        "wheelhouse does not contain the exact selected closure"
    );
    let actual = std::fs::read_dir(root)?
        .map(|entry| {
            let entry = entry?;
            ensure!(
                entry.file_type()?.is_file(),
                "wheelhouse contains a directory or link"
            );
            entry
                .file_name()
                .into_string()
                .map_err(|_| anyhow::anyhow!("non-UTF-8 wheelhouse member"))
        })
        .collect::<Result<BTreeSet<_>>>()?;
    ensure!(actual == names, "wheelhouse contains unreviewed files");
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn inventory_detects_changed_extra_and_missing_files() {
        let temp = tempfile::tempdir().unwrap();
        std::fs::write(temp.path().join("python.exe"), b"synthetic runtime").unwrap();
        let hash = write_inventory(temp.path(), "x86_64-pc-windows-msvc").unwrap();
        validate_inventory(temp.path(), "x86_64-pc-windows-msvc", &hash).unwrap();
        std::fs::write(temp.path().join("extra.dll"), b"extra").unwrap();
        assert!(validate_inventory(temp.path(), "x86_64-pc-windows-msvc", &hash).is_err());
        std::fs::remove_file(temp.path().join("extra.dll")).unwrap();
        std::fs::write(temp.path().join("python.exe"), b"modified runtime").unwrap();
        assert!(validate_inventory(temp.path(), "x86_64-pc-windows-msvc", &hash).is_err());
        std::fs::remove_file(temp.path().join("python.exe")).unwrap();
        assert!(validate_inventory(temp.path(), "x86_64-pc-windows-msvc", &hash).is_err());
    }

    #[test]
    fn inventory_never_contains_itself_or_the_payload_manifest() {
        let temp = tempfile::tempdir().unwrap();
        std::fs::write(temp.path().join("python.exe"), b"synthetic runtime").unwrap();
        std::fs::write(temp.path().join("payload.json"), b"old manifest").unwrap();
        let hash = write_inventory(temp.path(), "x86_64-pc-windows-msvc").unwrap();
        std::fs::write(temp.path().join("payload.json"), b"new manifest").unwrap();
        validate_inventory(temp.path(), "x86_64-pc-windows-msvc", &hash).unwrap();
        assert!(validate_inventory(temp.path(), "aarch64-pc-windows-msvc", &hash).is_err());
        assert!(
            validate_inventory(temp.path(), "x86_64-pc-windows-msvc", &"0".repeat(64)).is_err()
        );
    }

    #[test]
    fn duplicate_inventory_members_are_not_silently_overwritten() {
        let raw = br#"{"schema":1,"target":"x86_64-pc-windows-msvc","files":{"one":{"size":1,"sha256":"a"},"one":{"size":1,"sha256":"a"}}}"#;
        assert!(serde_json::from_slice::<Inventory>(raw).is_err());
    }

    #[test]
    fn closed_wheelhouse_binds_exact_target_lock_and_every_wheel() {
        let temp = tempfile::tempdir().unwrap();
        let name = "synthetic-1.0-py3-none-any.whl";
        let wheel = b"synthetic fixture, not a real wheel";
        let hash = digest(wheel);
        let lock = format!("synthetic==1.0 --hash=sha256:{hash}\n");
        std::fs::write(temp.path().join(name), wheel).unwrap();
        let receipt = serde_json::json!({"schema":1,"target":"x86_64-pc-windows-msvc",
            "requirements_sha256":digest(lock.as_bytes()), "wheel_manifest_sha256":"a".repeat(64),
            "wheels":[{"filename":name,"name":"synthetic","version":"1.0",
                       "size":wheel.len(),"sha256":hash}]});
        std::fs::write(
            temp.path().join("wheelhouse.json"),
            serde_json::to_vec(&receipt).unwrap(),
        )
        .unwrap();
        validate_wheelhouse(
            temp.path(),
            "x86_64-pc-windows-msvc",
            lock.as_bytes(),
            &"a".repeat(64),
        )
        .unwrap();
        std::fs::write(temp.path().join("unexpected.whl"), b"extra").unwrap();
        assert!(
            validate_wheelhouse(
                temp.path(),
                "x86_64-pc-windows-msvc",
                lock.as_bytes(),
                &"a".repeat(64)
            )
            .is_err()
        );
    }

    #[cfg(unix)]
    #[test]
    fn inventory_accepts_internal_relative_file_links_but_not_external_links() {
        let temp = tempfile::tempdir().unwrap();
        std::fs::write(temp.path().join("python3"), b"synthetic runtime").unwrap();
        std::os::unix::fs::symlink("python3", temp.path().join("python")).unwrap();
        let hash = write_inventory(temp.path(), "x86_64-unknown-linux-gnu").unwrap();
        validate_inventory(temp.path(), "x86_64-unknown-linux-gnu", &hash).unwrap();
        std::fs::remove_file(temp.path().join("python")).unwrap();
        std::os::unix::fs::symlink("/etc/passwd", temp.path().join("python")).unwrap();
        assert!(validate_inventory(temp.path(), "x86_64-unknown-linux-gnu", &hash).is_err());
    }
}
