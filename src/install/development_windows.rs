//! Integrity checks for explicitly compiled unsigned Windows qualification
//! builds. A matching unsigned receipt proves consistency, not publisher
//! authenticity, and it grants no release trust.
//!
//! The receipt names no installation vehicle, which is the one way this differs
//! from the Linux admission. There, the installed AppImage is retained in the
//! install root, so the receipt's vehicle digest is checked against bytes that
//! are present. Here the MSI carries the receipt, so the receipt is sealed
//! before the vehicle it would name exists, and a development install caches no
//! vehicle to compare against either. Every field in this receipt is checkable
//! against the installed tree, because a claim nothing can check is worse than
//! an absent one.

#![cfg(all(target_os = "windows", feature = "windows-unsigned-qualification"))]

use anyhow::{Context, Result, ensure};
use serde::Deserialize;
use sha2::{Digest, Sha256};
use std::collections::BTreeSet;
use std::fs::{File, OpenOptions};
use std::os::windows::fs::{FileExt, OpenOptionsExt};
use std::os::windows::io::AsRawHandle;
use std::path::{Component, Path, PathBuf};
use windows_sys::Win32::Foundation::FILETIME;
use windows_sys::Win32::Storage::FileSystem::{
    BY_HANDLE_FILE_INFORMATION, FILE_ATTRIBUTE_DIRECTORY, FILE_ATTRIBUTE_REPARSE_POINT,
    FILE_FLAG_BACKUP_SEMANTICS, FILE_FLAG_OPEN_REPARSE_POINT, GetFileInformationByHandle,
};

const MAX_RECEIPT: u64 = 16 * 1024 * 1024;
const MAX_METADATA: u64 = 16 * 1024 * 1024;
const MAX_MEMBERS: usize = 20_000;
const MAX_NODES: usize = 40_000;
const MAX_FILE: u64 = 4 * 1024 * 1024 * 1024;
const MAX_TOTAL: u64 = 16 * 1024 * 1024 * 1024;

const RECEIPT_FILE: &str = "development-receipt.json";
const EXECUTABLE: &str = "vadgr.exe";

/// The daemon creates its virtual environment under the installed root after
/// the install, so that one subtree is the only place an uninventoried file may
/// appear. Everywhere else an extra file is a planted file.
const RUNTIME_SUBTREE: &str = "lib/cua/environments";

/// A development package must never carry release authority. These names are
/// what production admission reads, so their absence is what proves this path
/// cannot be mistaken for a signed install.
const FORBIDDEN: [&str; 4] = [
    "release-manifest.json",
    "release-manifest.json.bundle.jsonl",
    "cua-runtime-authorization.json",
    "cua-runtime-authorization.sigstore.json",
];

#[derive(Debug, Deserialize)]
#[serde(deny_unknown_fields)]
struct Receipt {
    schema: u32,
    development: bool,
    publishable: bool,
    signing: String,
    attestation: String,
    source_commit: String,
    source_tree: String,
    platform: String,
    architecture: String,
    payload: Vec<Member>,
}

#[derive(Clone, Debug, Deserialize, PartialEq, Eq, PartialOrd, Ord)]
#[serde(deny_unknown_fields)]
struct Member {
    path: String,
    size: u64,
    sha256: String,
}

struct Expected<'a> {
    version: &'a str,
    architecture: &'a str,
    source_commit: &'a str,
    source_tree: &'a str,
}

fn compiled_identity() -> Result<Expected<'static>> {
    ensure!(
        super::current_target()? == format!("windows-{}", std::env::consts::ARCH),
        "unsigned qualification requires native Windows"
    );
    Ok(Expected {
        version: env!("CARGO_PKG_VERSION"),
        architecture: std::env::consts::ARCH,
        source_commit: option_env!("VADGR_QUALIFICATION_SOURCE_COMMIT")
            .context("qualification source identity was not compiled")?,
        source_tree: option_env!("VADGR_QUALIFICATION_SOURCE_TREE")
            .context("qualification tree identity was not compiled")?,
    })
}

/// The caller names an installed root; it does not grant runtime admission.
pub(crate) fn verify_installed_runtime(install_root: &Path) -> Result<()> {
    verify_installed_runtime_at(
        install_root,
        &std::env::current_exe().context("resolving the running executable")?,
        &compiled_identity()?,
    )
}

fn verify_installed_runtime_at(
    install_root: &Path,
    executable: &Path,
    expected: &Expected<'_>,
) -> Result<()> {
    // This is package consistency, not publisher authenticity. The root is a
    // locator rather than an authority: the running image, the install receipt,
    // the development receipt and every inventoried byte must agree.
    let root = ConfinedRoot::open(install_root)?;
    ensure!(
        canonical(executable)? == root.path.join(EXECUTABLE),
        "development runtime is not executing its installed package"
    );
    for name in FORBIDDEN {
        root.require_absent(name)?;
    }
    let receipt_file = root.regular(super::RECEIPT_NAME, MAX_METADATA)?;
    let installed: super::InstallReceipt =
        serde_json::from_slice(&receipt_file.bytes(MAX_METADATA)?)?;
    ensure!(
        installed.schema == 1
            && installed.version == expected.version
            && installed.package_kind == "msi",
        "development installation receipt differs"
    );
    let digest = installed
        .development_receipt_sha256
        .as_deref()
        .context("installation receipt records no development receipt")?;
    ensure!(hex(digest, 64), "invalid development receipt digest");
    let development_file = root.regular(RECEIPT_FILE, MAX_RECEIPT)?;
    let bytes = development_file.bytes(MAX_RECEIPT)?;
    ensure!(
        sha256_hex(&bytes) == digest,
        "development receipt differs from the digest the installation recorded"
    );
    let receipt: Receipt = serde_json::from_slice(&bytes)?;
    validate_receipt(&receipt, expected)?;
    verify_inventory(&root, &receipt)?;
    // Nothing moved while the inventory was read, and the two records that
    // authorize the inventory are still the bytes that were read.
    ensure!(
        Stamp::read(&receipt_file.file)? == receipt_file.stamp
            && Stamp::read(&development_file.file)? == development_file.stamp,
        "development records changed during verification"
    );
    root.assert_bound(super::RECEIPT_NAME, &receipt_file.stamp)?;
    root.assert_bound(RECEIPT_FILE, &development_file.stamp)?;
    for name in FORBIDDEN {
        root.require_absent(name)?;
    }
    root.assert_root()
}

fn validate_receipt(receipt: &Receipt, expected: &Expected<'_>) -> Result<()> {
    ensure!(
        receipt.schema == 1
            && receipt.development
            && !receipt.publishable
            && receipt.signing == "disabled"
            && receipt.attestation == "absent",
        "development receipt does not declare an unsigned development package"
    );
    ensure!(
        receipt.platform == "windows" && receipt.architecture == expected.architecture,
        "development receipt names another platform"
    );
    ensure!(
        receipt.source_commit == expected.source_commit
            && receipt.source_tree == expected.source_tree,
        "development receipt names another source than the compiled identity"
    );
    ensure!(
        !receipt.payload.is_empty() && receipt.payload.len() <= MAX_MEMBERS,
        "development receipt inventories no payload"
    );
    let mut total = 0_u64;
    let mut previous: Option<&str> = None;
    for member in &receipt.payload {
        ensure!(
            safe_path(&member.path) && member.size <= MAX_FILE && hex(&member.sha256, 64),
            "invalid inventoried payload file"
        );
        // The producer writes one sorted inventory. Requiring that order here
        // makes a repeated or reordered entry a refusal instead of a race
        // between whichever copy is read first.
        ensure!(
            previous.is_none_or(|last| last < member.path.as_str()),
            "payload inventory is unordered or repeats a path"
        );
        previous = Some(&member.path);
        total = total
            .checked_add(member.size)
            .filter(|sum| *sum <= MAX_TOTAL)
            .context("inventoried payload exceeds its limit")?;
        ensure!(
            member.path != super::RECEIPT_NAME && member.path != RECEIPT_FILE,
            "the inventory must exclude the records that authorize it"
        );
    }
    Ok(())
}

/// Every inventoried file is verified, and the installed tree carries no file
/// the inventory does not name, outside the runtime subtree the daemon writes.
fn verify_inventory(root: &ConfinedRoot, receipt: &Receipt) -> Result<()> {
    for member in &receipt.payload {
        let file = root.regular(&member.path, member.size)?;
        file.verify(member.size, &member.sha256)?;
        root.assert_bound(&member.path, &file.stamp)?;
    }
    let inventoried: BTreeSet<&str> = receipt.payload.iter().map(|m| m.path.as_str()).collect();
    let runtime = format!("{RUNTIME_SUBTREE}/");
    for path in walk(root)? {
        if path == super::RECEIPT_NAME || path == RECEIPT_FILE || path.starts_with(&runtime) {
            continue;
        }
        ensure!(
            inventoried.contains(path.as_str()),
            "the installed tree carries {path}, which the development receipt does not inventory"
        );
    }
    Ok(())
}

/// Relative paths of every regular file beneath the root. A link anywhere is a
/// refusal rather than a path to follow.
fn walk(root: &ConfinedRoot) -> Result<Vec<String>> {
    let mut found = Vec::new();
    let mut pending = vec![String::new()];
    let mut nodes = 0_usize;
    while let Some(relative) = pending.pop() {
        let directory = if relative.is_empty() {
            root.path.clone()
        } else {
            root.path.join(relative.replace('/', "\\"))
        };
        for entry in std::fs::read_dir(&directory)? {
            let entry = entry?;
            nodes += 1;
            ensure!(nodes <= MAX_NODES, "installed tree exceeds its node limit");
            let name = entry
                .file_name()
                .into_string()
                .map_err(|_| anyhow::anyhow!("the installed tree carries a non-Unicode name"))?;
            ensure!(
                !FORBIDDEN.contains(&name.as_str()),
                "a development installation must carry no release authority, and {name} is one"
            );
            let child = if relative.is_empty() {
                name
            } else {
                format!("{relative}/{name}")
            };
            ensure!(
                safe_path(&child),
                "the installed tree carries an unsafe name"
            );
            let metadata = entry.metadata()?;
            ensure!(
                !metadata.file_type().is_symlink(),
                "the installed tree carries a link, which verification never follows"
            );
            if metadata.is_dir() {
                pending.push(child);
            } else {
                ensure!(
                    metadata.is_file(),
                    "the installed tree carries a special file"
                );
                found.push(child);
            }
        }
    }
    Ok(found)
}

fn hex(value: &str, length: usize) -> bool {
    value.len() == length
        && value
            .bytes()
            .all(|b| b.is_ascii_digit() || (b'a'..=b'f').contains(&b))
}

fn lowercase_hex(bytes: &[u8]) -> String {
    const DIGITS: &[u8; 16] = b"0123456789abcdef";
    let mut result = String::with_capacity(bytes.len() * 2);
    for &byte in bytes {
        result.push(char::from(DIGITS[usize::from(byte >> 4)]));
        result.push(char::from(DIGITS[usize::from(byte & 15)]));
    }
    result
}

fn sha256_hex(bytes: &[u8]) -> String {
    lowercase_hex(Sha256::digest(bytes).as_ref())
}

/// Windows reserves more than POSIX does, and a receipt is not a place to be
/// generous: one plain relative path, no device name, no alternate stream.
fn safe_path(path: &str) -> bool {
    !path.is_empty()
        && path.len() <= 4096
        && path.split('/').count() <= 64
        && path.split('/').all(safe_name)
}

fn safe_name(name: &str) -> bool {
    const RESERVED: [&str; 22] = [
        "con", "prn", "aux", "nul", "com1", "com2", "com3", "com4", "com5", "com6", "com7", "com8",
        "com9", "lpt1", "lpt2", "lpt3", "lpt4", "lpt5", "lpt6", "lpt7", "lpt8", "lpt9",
    ];
    let stem = name.split_once('.').map_or(name, |(stem, _)| stem);
    const FORBIDDEN_CHARS: [char; 8] = ['\\', '/', ':', '*', '?', '"', '<', '>'];
    !name.is_empty()
        && name.len() <= 255
        && !matches!(name, "." | "..")
        && !name.ends_with(' ')
        && !name.ends_with('.')
        && !name
            .chars()
            .any(|c| c.is_control() || c == '|' || FORBIDDEN_CHARS.contains(&c))
        && !RESERVED.contains(&stem.to_ascii_lowercase().as_str())
}

/// `dunce` keeps the plain form wherever Windows accepts one, which is what
/// makes a prefix comparison between two resolved paths mean anything.
fn canonical(path: &Path) -> Result<PathBuf> {
    let resolved =
        dunce::canonicalize(path).with_context(|| format!("resolving {}", path.display()))?;
    ensure!(
        resolved
            .components()
            .all(|part| !matches!(part, Component::CurDir | Component::ParentDir)),
        "a resolved path kept a relative component"
    );
    Ok(resolved)
}

/// Identity and mutation evidence for one open handle. Windows reports no change
/// time, so the size, the write time and the file's own index carry that proof.
#[derive(Clone, Debug, PartialEq, Eq)]
struct Stamp {
    volume: u32,
    index: u64,
    attributes: u32,
    links: u32,
    size: u64,
    created: u64,
    written: u64,
}

impl Stamp {
    fn read(file: &File) -> Result<Self> {
        let mut info: BY_HANDLE_FILE_INFORMATION = unsafe { std::mem::zeroed() };
        // SAFETY: the handle is open for reading and Windows fills the complete
        // SDK structure at this valid pointer.
        let ok = unsafe { GetFileInformationByHandle(file.as_raw_handle(), &mut info) };
        ensure!(ok != 0, "{}", std::io::Error::last_os_error());
        let pair = |high: u32, low: u32| (u64::from(high) << 32) | u64::from(low);
        let time = |value: FILETIME| pair(value.dwHighDateTime, value.dwLowDateTime);
        Ok(Self {
            volume: info.dwVolumeSerialNumber,
            index: pair(info.nFileIndexHigh, info.nFileIndexLow),
            attributes: info.dwFileAttributes,
            links: info.nNumberOfLinks,
            size: pair(info.nFileSizeHigh, info.nFileSizeLow),
            created: time(info.ftCreationTime),
            written: time(info.ftLastWriteTime),
        })
    }

    fn require_regular(&self) -> Result<()> {
        ensure!(
            self.attributes & FILE_ATTRIBUTE_DIRECTORY == 0
                && self.attributes & FILE_ATTRIBUTE_REPARSE_POINT == 0,
            "a qualification path is not a regular file"
        );
        // A second name for the same bytes is a second way to change them.
        ensure!(self.links == 1, "a qualification file carries another name");
        Ok(())
    }
}

#[derive(Debug)]
struct StableFile {
    file: File,
    stamp: Stamp,
}

impl StableFile {
    fn scan(
        &self,
        limit: u64,
        mut consume: impl FnMut(&[u8]) -> Result<()>,
    ) -> Result<(u64, String)> {
        ensure!(
            self.stamp.size <= limit && Stamp::read(&self.file)? == self.stamp,
            "qualification file changed before reading"
        );
        let mut hash = Sha256::new();
        let mut offset = 0_u64;
        let mut buffer = [0_u8; 64 * 1024];
        loop {
            let maximum = (limit + 1 - offset).min(buffer.len() as u64) as usize;
            let count = self.file.seek_read(&mut buffer[..maximum], offset)?;
            if count == 0 {
                break;
            }
            offset += count as u64;
            ensure!(offset <= limit, "qualification file exceeds its limit");
            hash.update(&buffer[..count]);
            consume(&buffer[..count])?;
        }
        ensure!(
            offset == self.stamp.size && Stamp::read(&self.file)? == self.stamp,
            "qualification file changed while reading"
        );
        Ok((offset, lowercase_hex(hash.finalize().as_ref())))
    }

    fn bytes(&self, limit: u64) -> Result<Vec<u8>> {
        let mut bytes = Vec::new();
        self.scan(limit, |chunk| {
            bytes.extend_from_slice(chunk);
            Ok(())
        })?;
        Ok(bytes)
    }

    fn verify(&self, size: u64, sha256: &str) -> Result<()> {
        ensure!(
            size <= MAX_FILE && hex(sha256, 64),
            "invalid qualification artifact"
        );
        ensure!(
            self.scan(size, |_| Ok(()))? == (size, sha256.to_owned()),
            "qualification artifact bytes differ"
        );
        Ok(())
    }
}

/// An installed root that every later path is resolved against and confined to.
/// Linux gets confinement from `openat2` with `RESOLVE_BENEATH`; Windows gets it
/// from resolving each candidate, refusing one that leaves this root, and
/// opening it without following a reparse point.
struct ConfinedRoot {
    file: File,
    path: PathBuf,
    stamp: Stamp,
}

impl ConfinedRoot {
    fn open(path: &Path) -> Result<Self> {
        let resolved = canonical(path)?;
        let file = OpenOptions::new()
            .read(true)
            .custom_flags(FILE_FLAG_BACKUP_SEMANTICS | FILE_FLAG_OPEN_REPARSE_POINT)
            .open(&resolved)
            .with_context(|| format!("opening {}", resolved.display()))?;
        let stamp = Stamp::read(&file)?;
        ensure!(
            stamp.attributes & FILE_ATTRIBUTE_DIRECTORY != 0
                && stamp.attributes & FILE_ATTRIBUTE_REPARSE_POINT == 0,
            "the installed root is not a plain directory"
        );
        Ok(Self {
            file,
            path: resolved,
            stamp,
        })
    }

    /// Resolve one relative path and refuse it unless it stays beneath the root.
    fn resolve(&self, relative: &str) -> Result<PathBuf> {
        ensure!(safe_path(relative), "unsafe qualification path");
        let candidate = canonical(&self.path.join(relative.replace('/', "\\")))?;
        ensure!(
            candidate.starts_with(&self.path) && candidate != self.path,
            "qualification path {relative} leaves the installed root"
        );
        Ok(candidate)
    }

    fn regular(&self, relative: &str, limit: u64) -> Result<StableFile> {
        let path = self.resolve(relative)?;
        let file = OpenOptions::new()
            .read(true)
            .custom_flags(FILE_FLAG_OPEN_REPARSE_POINT)
            .open(&path)
            .with_context(|| format!("opening {relative}"))?;
        let stamp = Stamp::read(&file)?;
        stamp.require_regular()?;
        ensure!(
            stamp.volume == self.stamp.volume,
            "qualification path {relative} crosses a volume"
        );
        ensure!(
            stamp.size <= limit,
            "qualification path {relative} exceeds its limit"
        );
        Ok(StableFile { file, stamp })
    }

    fn require_absent(&self, relative: &str) -> Result<()> {
        ensure!(safe_path(relative), "unsafe qualification path");
        let candidate = self.path.join(relative.replace('/', "\\"));
        ensure!(
            std::fs::symlink_metadata(&candidate).is_err(),
            "a development installation must carry no release authority, and {relative} is one"
        );
        Ok(())
    }

    /// The name still resolves to the same bytes that were verified.
    fn assert_bound(&self, relative: &str, stamp: &Stamp) -> Result<()> {
        let reopened = self.regular(relative, stamp.size)?;
        ensure!(
            reopened.stamp == *stamp,
            "qualification path {relative} no longer names the verified bytes"
        );
        Ok(())
    }

    /// The root itself was never swapped under the verification.
    fn assert_root(&self) -> Result<()> {
        let current = Stamp::read(&self.file)?;
        ensure!(
            current.volume == self.stamp.volume && current.index == self.stamp.index,
            "the installed root changed during verification"
        );
        ensure!(
            canonical(&self.path)? == self.path,
            "the installed root no longer resolves to itself"
        );
        Ok(())
    }
}

#[cfg(test)]
mod tests;
