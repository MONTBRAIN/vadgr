//! Integrity checks for explicitly compiled unsigned Linux qualification builds.
//! A matching unsigned receipt proves consistency, not publisher authenticity.

#![cfg(all(target_os = "linux", feature = "linux-unsigned-qualification"))]

use anyhow::{Context, Result, ensure};
use rustix::fs::{Mode, OFlags, ResolveFlags};
use serde::Deserialize;
use serde_json::Value;
use sha2::{Digest, Sha256};
use std::collections::BTreeMap;
use std::fs::File;
use std::io::Write;
use std::os::fd::AsRawFd;
use std::os::unix::fs::{FileExt, MetadataExt};
use std::path::{Path, PathBuf};

const MAX_RECEIPT: u64 = 16 * 1024 * 1024;
const MAX_METADATA: u64 = 16 * 1024 * 1024;
const MAX_MEMBERS: usize = 20_000;
const MAX_NODES: usize = 40_000;
const MAX_FILE: u64 = 4 * 1024 * 1024 * 1024;
const MAX_TOTAL: u64 = 16 * 1024 * 1024 * 1024;

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
    artifact: Artifact,
    appdir: Vec<Member>,
    preparation_sha256: String,
    appimage_runtime: Runtime,
    abi: Abi,
}

#[derive(Debug, Deserialize)]
#[serde(deny_unknown_fields)]
struct Artifact {
    filename: String,
    size: u64,
    sha256: String,
}

#[derive(Debug, Deserialize, PartialEq)]
#[serde(deny_unknown_fields)]
struct Runtime {
    asset_id: u64,
    filename: String,
    size: u64,
    sha256: String,
}

#[derive(Debug, Deserialize)]
#[serde(deny_unknown_fields)]
struct Abi {
    producer_runner: String,
    maximum_glibc: String,
    glibc_requirements: Vec<String>,
}

#[derive(Clone, Debug, Deserialize, PartialEq)]
#[serde(tag = "kind", deny_unknown_fields)]
enum Member {
    #[serde(rename = "file")]
    File {
        path: String,
        mode: u32,
        size: u64,
        sha256: String,
    },
    #[serde(rename = "symlink")]
    Symlink {
        path: String,
        mode: u32,
        target: String,
    },
}

impl Member {
    fn path(&self) -> &str {
        match self {
            Self::File { path, .. } | Self::Symlink { path, .. } => path,
        }
    }
}

/// Private construction prevents a parsed receipt from becoming authority.
#[derive(Debug)]
pub(super) struct VerifiedDevelopmentReceipt {
    receipt: Receipt,
    receipt_bytes: Vec<u8>,
    vehicle: StableFile,
    receipt_sha256: String,
    terms_version: Option<String>,
    terms_text: Option<String>,
}

struct Expected<'a> {
    version: &'a str,
    architecture: &'a str,
    source_commit: &'a str,
    source_tree: &'a str,
}

impl VerifiedDevelopmentReceipt {
    pub(super) fn open(vehicle: &Path, mounted_root: &Path) -> Result<Self> {
        let expected = compiled_identity()?;
        let executable = std::env::current_exe().context("resolving the running executable")?;
        verify(vehicle, mounted_root, &executable, &expected)
    }

    pub(super) fn receipt_sha256(&self) -> &str {
        &self.receipt_sha256
    }

    pub(super) fn receipt_bytes(&self) -> &[u8] {
        &self.receipt_bytes
    }

    pub(super) fn version(&self) -> &str {
        env!("CARGO_PKG_VERSION")
    }

    pub(super) fn terms_sha256(&self) -> &str {
        required_file_hash(&self.receipt, "legal/TERMS.txt").expect("validated required member")
    }

    /// Repair verifies the retained receipt and original vehicle without
    /// trusting possibly damaged installed files. It does not grant new assent.
    pub(super) fn open_retained(
        vehicle: &Path,
        receipt_path: &Path,
        expected_receipt_sha256: &str,
    ) -> Result<Self> {
        let expected = compiled_identity()?;
        let opened = open_bound(
            vehicle,
            receipt_path,
            Some(expected_receipt_sha256),
            &expected,
        )?;
        opened.recheck()?;
        Ok(opened.finish(None))
    }

    /// Copy from the pinned verified inode, then recheck bytes and fstat. The
    /// caller supplies a new private staging path and must not commit after
    /// failure. A failed partial file remains for bounded staging cleanup.
    pub(super) fn copy_vehicle_to(&self, new_path: &Path) -> Result<()> {
        let parent = ConfinedRoot::open(new_path.parent().context("staging path has no parent")?)?;
        let name = new_path
            .file_name()
            .and_then(|name| name.to_str())
            .context("invalid staging filename")?;
        ensure!(safe_path(name), "unsafe staging filename");
        let mut destination = File::from(rustix::fs::openat2(
            &parent.file,
            name,
            OFlags::RDWR | OFlags::CREATE | OFlags::EXCL | OFlags::NOFOLLOW | OFlags::CLOEXEC,
            Mode::RUSR | Mode::WUSR,
            ResolveFlags::BENEATH
                | ResolveFlags::NO_SYMLINKS
                | ResolveFlags::NO_MAGICLINKS
                | ResolveFlags::NO_XDEV,
        )?);
        let observed = self.vehicle.scan(self.receipt.artifact.size, |chunk| {
            destination.write_all(chunk)?;
            Ok(())
        })?;
        ensure!(
            observed
                == (
                    self.receipt.artifact.size,
                    self.receipt.artifact.sha256.clone()
                ),
            "qualification vehicle changed before staging"
        );
        destination.sync_all()?;
        let staged = StableFile {
            stamp: Stamp::read(&destination)?,
            file: destination,
        };
        ensure!(
            staged.stamp.links == 1 && staged.stamp.mode & 0o077 == 0,
            "qualification staging file is not private and unlinked"
        );
        staged.verify(self.receipt.artifact.size, &self.receipt.artifact.sha256)?;
        parent.assert_bound(name, &staged.stamp)?;
        let current_parent = ConfinedRoot::open(&parent.path)?;
        ensure!(
            current_parent.stamp.device == parent.stamp.device
                && current_parent.stamp.inode == parent.stamp.inode,
            "staging parent identity changed"
        );
        Ok(())
    }
    pub(super) fn terms_version(&self) -> Option<&str> {
        self.terms_version.as_deref()
    }
    pub(super) fn terms_text(&self) -> Option<&str> {
        self.terms_text.as_deref()
    }

    /// Recheck copied legal and SBOM bytes before the caller commits staging.
    pub(super) fn verify_staged_metadata(&self, staging: &Path) -> Result<()> {
        let root = ConfinedRoot::open(staging)?;
        for name in ["legal", "sbom"] {
            let stamp = Stamp::read(&root.pin(name)?)?;
            let subtree = ConfinedRoot {
                file: root.directory(name, &stamp)?,
                path: root.path.join(name),
                stamp,
            };
            let first = mounted_inventory(&subtree)?;
            let second = mounted_inventory(&subtree)?;
            ensure!(
                first == second,
                "staged qualification metadata changed while reading"
            );
            let prefix = format!("{name}/");
            let actual = first.members.into_values().map(|mut member| {
                match &mut member {
                    Member::File { path, .. } | Member::Symlink { path, .. } => {
                        *path = format!("{prefix}{path}");
                    }
                }
                member
            });
            let expected = self
                .receipt
                .appdir
                .iter()
                .filter(|member| member.path().starts_with(&prefix))
                .cloned();
            ensure!(actual.eq(expected), "staged qualification metadata differs");
            root.assert_bound(name, &subtree.stamp)?;
        }
        root.assert_root()
    }
    pub(super) fn artifact_name(&self) -> &str {
        &self.receipt.artifact.filename
    }

    /// Retained copies use another basename, but must retain the exact bytes.
    pub(super) fn verify_vehicle_at(&self, path: &Path) -> Result<()> {
        verify_file(
            path,
            self.receipt.artifact.size,
            &self.receipt.artifact.sha256,
        )
    }
}

fn compiled_identity() -> Result<Expected<'static>> {
    ensure!(
        super::current_target()? == format!("linux-{}", std::env::consts::ARCH),
        "unsigned qualification requires native Linux"
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

fn safe_path(path: &str) -> bool {
    !path.is_empty()
        && path.len() <= 4096
        && !path.contains('\\')
        && !path.chars().any(char::is_control)
        && path.split('/').all(|part| !matches!(part, "" | "." | ".."))
        && path.split('/').count() <= 64
}

#[derive(Clone, Debug, PartialEq, Eq)]
struct Stamp {
    device: u64,
    inode: u64,
    mode: u32,
    links: u64,
    owner: u32,
    group: u32,
    size: u64,
    modified: (i64, i64),
    changed: (i64, i64),
}

impl Stamp {
    fn read(file: &File) -> Result<Self> {
        let m = file.metadata()?;
        Ok(Self {
            device: m.dev(),
            inode: m.ino(),
            mode: m.mode(),
            links: m.nlink(),
            owner: m.uid(),
            group: m.gid(),
            size: m.len(),
            modified: (m.mtime(), m.mtime_nsec()),
            changed: (m.ctime(), m.ctime_nsec()),
        })
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
            let count = self.file.read_at(&mut buffer[..maximum], offset)?;
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
            size > 0 && size <= MAX_FILE && hex(sha256, 64),
            "invalid qualification artifact"
        );
        ensure!(
            self.scan(size, |_| Ok(()))? == (size, sha256.to_owned()),
            "qualification artifact bytes differ"
        );
        Ok(())
    }
}

struct ConfinedRoot {
    file: File,
    path: PathBuf,
    stamp: Stamp,
}

impl ConfinedRoot {
    fn open(path: &Path) -> Result<Self> {
        ensure!(path.is_absolute(), "qualification root must be absolute");
        // There is deliberately no fallback on kernels without openat2.
        let file = File::from(rustix::fs::openat2(
            rustix::fs::CWD,
            path,
            OFlags::RDONLY | OFlags::DIRECTORY | OFlags::CLOEXEC,
            Mode::empty(),
            ResolveFlags::NO_SYMLINKS | ResolveFlags::NO_MAGICLINKS,
        )?);
        let stamp = Stamp::read(&file)?;
        Ok(Self {
            file,
            path: path.to_owned(),
            stamp,
        })
    }

    fn pin(&self, relative: &str) -> Result<File> {
        ensure!(safe_path(relative), "unsafe qualification member");
        // O_PATH avoids opening devices or blocking on FIFOs before their type
        // is known. NOFOLLOW permits pinning a final symlink, never following it.
        Ok(File::from(rustix::fs::openat2(
            &self.file,
            relative,
            OFlags::PATH | OFlags::NOFOLLOW | OFlags::CLOEXEC,
            Mode::empty(),
            ResolveFlags::BENEATH
                | ResolveFlags::NO_SYMLINKS
                | ResolveFlags::NO_MAGICLINKS
                | ResolveFlags::NO_XDEV,
        )?))
    }

    fn regular(&self, relative: &str, limit: u64) -> Result<StableFile> {
        let pinned = self.pin(relative)?;
        let metadata = pinned.metadata()?;
        let stamp = Stamp::read(&pinned)?;
        ensure!(
            metadata.is_file() && stamp.links == 1 && stamp.size <= limit,
            "qualification requires a bounded regular unlinked file"
        );
        // This one intentional procfs magic-link open addresses a descriptor
        // owned by this process, never a user-supplied path or descriptor number.
        // The pinned inode cannot turn into a device or another inode.
        let file = File::open(format!("/proc/self/fd/{}", pinned.as_raw_fd()))?;
        ensure!(
            Stamp::read(&file)? == stamp && Stamp::read(&pinned)? == stamp,
            "qualification file changed while opening"
        );
        self.assert_bound(relative, &stamp)?;
        Ok(StableFile { file, stamp })
    }

    fn directory(&self, relative: &str, stamp: &Stamp) -> Result<File> {
        let file = File::from(rustix::fs::openat2(
            &self.file,
            relative,
            OFlags::RDONLY | OFlags::DIRECTORY | OFlags::CLOEXEC,
            Mode::empty(),
            ResolveFlags::BENEATH
                | ResolveFlags::NO_SYMLINKS
                | ResolveFlags::NO_MAGICLINKS
                | ResolveFlags::NO_XDEV,
        )?);
        ensure!(
            Stamp::read(&file)? == *stamp,
            "qualification directory changed while opening"
        );
        Ok(file)
    }

    fn assert_bound(&self, relative: &str, stamp: &Stamp) -> Result<()> {
        let current = if relative.is_empty() {
            Stamp::read(&self.file)?
        } else {
            Stamp::read(&self.pin(relative)?)?
        };
        ensure!(current == *stamp, "qualification path binding changed");
        Ok(())
    }

    fn assert_root(&self) -> Result<()> {
        ensure!(
            Stamp::read(&self.file)? == self.stamp && Self::open(&self.path)?.stamp == self.stamp,
            "qualification root identity changed"
        );
        Ok(())
    }

    fn require_absent(&self, name: &str) -> Result<()> {
        match rustix::fs::openat2(
            &self.file,
            name,
            OFlags::PATH | OFlags::NOFOLLOW | OFlags::CLOEXEC,
            Mode::empty(),
            ResolveFlags::BENEATH
                | ResolveFlags::NO_SYMLINKS
                | ResolveFlags::NO_MAGICLINKS
                | ResolveFlags::NO_XDEV,
        ) {
            Err(rustix::io::Errno::NOENT) => Ok(()),
            _ => anyhow::bail!("mixed release and development metadata refused"),
        }
    }

    fn link_target(&self, relative: &str, pinned: &File, stamp: &Stamp) -> Result<String> {
        let target = rustix::fs::readlinkat(pinned, "", Vec::new())?;
        let target = target.to_str()?.to_owned();
        ensure!(
            !target.is_empty()
                && target.len() <= 4096
                && !Path::new(&target).is_absolute()
                && !target.contains('\\')
                && !target.chars().any(char::is_control),
            "invalid qualification link"
        );
        // Validate chained relative links through the kernel, confined to this
        // pinned root. BENEATH rejects absolute targets and .. escapes.
        let _resolved = rustix::fs::openat2(
            &self.file,
            relative,
            OFlags::PATH | OFlags::CLOEXEC,
            Mode::empty(),
            ResolveFlags::BENEATH | ResolveFlags::NO_MAGICLINKS | ResolveFlags::NO_XDEV,
        )?;
        ensure!(Stamp::read(pinned)? == *stamp, "qualification link changed");
        self.assert_bound(relative, stamp)?;
        Ok(target)
    }
}

fn absolute_file(path: &Path, limit: u64) -> Result<(ConfinedRoot, String, StableFile)> {
    let root = ConfinedRoot::open(path.parent().context("qualification file has no parent")?)?;
    let name = path
        .file_name()
        .and_then(|name| name.to_str())
        .context("invalid qualification filename")?
        .to_owned();
    let file = root.regular(&name, limit)?;
    Ok((root, name, file))
}

#[cfg(test)]
fn digest(path: &Path, limit: u64) -> Result<(u64, String)> {
    let (root, name, file) = absolute_file(path, limit)?;
    let digest = file.scan(limit, |_| Ok(()))?;
    root.assert_bound(&name, &file.stamp)?;
    root.assert_root()?;
    Ok(digest)
}

fn verify_file(path: &Path, size: u64, sha256: &str) -> Result<()> {
    let (root, name, file) = absolute_file(path, MAX_FILE)?;
    file.verify(size, sha256)?;
    root.assert_bound(&name, &file.stamp)?;
    root.assert_root()
}

// JSON punctuation is ASCII. Escape the remaining string characters after
// serialization to match the existing producer's ensure_ascii=True policy.
fn canonical(value: &Value) -> Result<Vec<u8>> {
    let mut value = value.clone();
    value.sort_all_objects();
    let mut bytes = Vec::new();
    for character in serde_json::to_string_pretty(&value)?.chars() {
        if character < '\u{7f}' {
            bytes.push(character as u8);
        } else {
            for unit in character.encode_utf16(&mut [0; 2]) {
                write!(&mut bytes, "\\u{unit:04x}")?;
            }
        }
    }
    bytes.push(b'\n');
    Ok(bytes)
}

fn version(value: &str) -> Result<Vec<u32>> {
    ensure!(
        !value.is_empty() && value.split('.').count() >= 2,
        "invalid qualification version"
    );
    value
        .split('.')
        .map(|part| {
            ensure!(
                !part.is_empty() && part.bytes().all(|b| b.is_ascii_digit()),
                "invalid qualification version"
            );
            Ok(part.parse()?)
        })
        .collect()
}

fn validate_receipt(receipt: &Receipt, expected: &Expected<'_>) -> Result<()> {
    ensure!(
        receipt.schema == 1
            && receipt.development
            && !receipt.publishable
            && receipt.signing == "disabled"
            && receipt.attestation == "absent"
            && receipt.platform == "linux"
            && receipt.architecture == expected.architecture
            && matches!(expected.architecture, "x86_64" | "aarch64"),
        "not a native unsigned qualification receipt"
    );
    ensure!(
        hex(expected.source_commit, 40)
            && hex(expected.source_tree, 40)
            && receipt.source_commit == expected.source_commit
            && receipt.source_tree == expected.source_tree,
        "qualification source identity differs"
    );
    ensure!(
        hex(&receipt.preparation_sha256, 64),
        "invalid preparation digest"
    );
    ensure!(
        receipt.artifact.filename
            == format!(
                "Vadgr-{}-linux-{}-installer.AppImage",
                expected.version, expected.architecture
            ),
        "qualification artifact name differs"
    );
    let pins: Value = serde_json::from_str(include_str!("../../packaging/linux/runtime.json"))?;
    let runtime: Runtime = serde_json::from_value(pins["targets"][expected.architecture].clone())?;
    ensure!(
        receipt.appimage_runtime == runtime,
        "qualification AppImage runtime differs"
    );
    ensure!(
        receipt.abi.producer_runner == "ubuntu-24.04",
        "qualification producer baseline differs"
    );
    let mut versions = Vec::new();
    let mut previous = None;
    for requirement in &receipt.abi.glibc_requirements {
        ensure!(
            previous.is_none_or(|last: &str| last < requirement.as_str()),
            "invalid ABI requirement ordering"
        );
        previous = Some(requirement);
        if requirement == "GLIBC_ABI_DT_RELR" {
            continue;
        }
        versions.push(version(
            requirement
                .strip_prefix("GLIBC_")
                .context("unknown ABI requirement")?,
        )?);
    }
    let maximum = version(&receipt.abi.maximum_glibc)?;
    ensure!(
        versions.iter().max() == Some(&maximum) && maximum <= vec![2, 39],
        "qualification ABI baseline differs"
    );
    ensure!(
        !receipt.appdir.is_empty() && receipt.appdir.len() <= MAX_MEMBERS,
        "invalid qualification inventory size"
    );
    let mut previous = "";
    for member in &receipt.appdir {
        ensure!(
            safe_path(member.path()) && member.path() > previous,
            "unsafe or unordered qualification member"
        );
        previous = member.path();
        match member {
            Member::File {
                mode, size, sha256, ..
            } => ensure!(
                *mode <= 0o777 && *size <= MAX_FILE && hex(sha256, 64),
                "invalid qualification file"
            ),
            Member::Symlink { mode, target, .. } => ensure!(
                *mode <= 0o777
                    && !target.is_empty()
                    && target.len() <= 4096
                    && !Path::new(target).is_absolute()
                    && !target.contains('\\')
                    && !target.chars().any(char::is_control),
                "invalid qualification link"
            ),
        }
    }
    for path in [
        "AppRun",
        "usr/bin/vadgr",
        "legal/TERMS.txt",
        "package-input-inventory.json",
        "package-input-review.json",
        "usr/lib/cua/payload.json",
        "usr/lib/cua/installed-inventory.json",
    ] {
        required_file_hash(receipt, path)?;
    }
    ensure!(
        receipt
            .appdir
            .iter()
            .any(|member| matches!(member, Member::File { path, .. } if path.starts_with("sbom/"))),
        "qualification SBOM is missing"
    );
    Ok(())
}

#[derive(Debug, PartialEq)]
struct Snapshot {
    members: BTreeMap<String, Member>,
    stamps: BTreeMap<String, Stamp>,
}

fn mounted_inventory(root: &ConfinedRoot) -> Result<Snapshot> {
    inventory_with_hook(root, &mut |_| Ok(()))
}

fn inventory_with_hook(
    root: &ConfinedRoot,
    hook: &mut impl FnMut(&str) -> Result<()>,
) -> Result<Snapshot> {
    fn visit(
        root: &ConfinedRoot,
        relative: &str,
        directory: &File,
        initial: &Stamp,
        result: &mut Snapshot,
        total: &mut u64,
        hook: &mut impl FnMut(&str) -> Result<()>,
    ) -> Result<()> {
        root.assert_bound(relative, initial)?;
        ensure!(
            Stamp::read(directory)? == *initial,
            "qualification directory changed"
        );
        for entry in rustix::fs::Dir::read_from(directory)? {
            let entry = entry?;
            let name = entry.file_name().to_str()?;
            if matches!(name, "." | "..") {
                continue;
            }
            ensure!(safe_path(name), "unsafe qualification directory entry");
            let path = if relative.is_empty() {
                name.to_owned()
            } else {
                format!("{relative}/{name}")
            };
            ensure!(safe_path(&path), "unsafe qualification member");
            hook(&path)?;
            root.assert_bound(relative, initial)?;
            let pinned = root.pin(&path)?;
            let stamp = Stamp::read(&pinned)?;
            let metadata = pinned.metadata()?;
            ensure!(
                result.stamps.insert(path.clone(), stamp.clone()).is_none(),
                "duplicate qualification entry"
            );
            ensure!(
                result.stamps.len() <= MAX_NODES,
                "qualification tree exceeds its limit"
            );
            if metadata.is_dir() {
                let child = root.directory(&path, &stamp)?;
                visit(root, &path, &child, &stamp, result, total, hook)?;
            } else {
                let mode = stamp.mode & 0o7777;
                let member = if metadata.file_type().is_symlink() {
                    Member::Symlink {
                        path: path.clone(),
                        mode,
                        target: root.link_target(&path, &pinned, &stamp)?,
                    }
                } else {
                    ensure!(metadata.is_file(), "special qualification member refused");
                    let file = root.regular(&path, MAX_FILE)?;
                    ensure!(
                        file.stamp == stamp,
                        "qualification member changed while opening"
                    );
                    let (size, sha256) = file.scan(MAX_FILE, |_| Ok(()))?;
                    *total = total
                        .checked_add(size)
                        .context("qualification inventory size overflow")?;
                    ensure!(
                        *total <= MAX_TOTAL,
                        "qualification inventory exceeds its limit"
                    );
                    Member::File {
                        path: path.clone(),
                        mode,
                        size,
                        sha256,
                    }
                };
                result.members.insert(path.clone(), member);
                ensure!(
                    result.members.len() <= MAX_MEMBERS,
                    "qualification inventory exceeds its limit"
                );
            }
            ensure!(
                Stamp::read(&pinned)? == stamp,
                "qualification member changed while reading"
            );
            root.assert_bound(&path, &stamp)?;
        }
        ensure!(
            Stamp::read(directory)? == *initial,
            "qualification directory changed while reading"
        );
        root.assert_bound(relative, initial)?;
        Ok(())
    }
    let mut result = Snapshot {
        members: BTreeMap::new(),
        stamps: BTreeMap::new(),
    };
    let mut total = 0;
    visit(
        root,
        "",
        &root.file,
        &root.stamp,
        &mut result,
        &mut total,
        hook,
    )?;
    root.assert_root()?;
    Ok(result)
}

struct OpenedReceipt {
    receipt: Receipt,
    bytes: Vec<u8>,
    vehicle: StableFile,
    vehicle_root: ConfinedRoot,
    vehicle_name: String,
    sidecar: StableFile,
    sidecar_root: ConfinedRoot,
    sidecar_name: String,
}

impl OpenedReceipt {
    fn recheck(&self) -> Result<()> {
        ensure!(
            Stamp::read(&self.sidecar.file)? == self.sidecar.stamp,
            "qualification receipt changed"
        );
        self.vehicle
            .verify(self.receipt.artifact.size, &self.receipt.artifact.sha256)?;
        self.sidecar_root
            .assert_bound(&self.sidecar_name, &self.sidecar.stamp)?;
        self.vehicle_root
            .assert_bound(&self.vehicle_name, &self.vehicle.stamp)?;
        self.sidecar_root.assert_root()?;
        self.vehicle_root.assert_root()?;
        Ok(())
    }

    fn finish(self, terms: Option<(String, String)>) -> VerifiedDevelopmentReceipt {
        let (terms_version, terms_text) =
            terms.map_or((None, None), |(version, text)| (Some(version), Some(text)));
        VerifiedDevelopmentReceipt {
            receipt: self.receipt,
            receipt_sha256: sha256_hex(&self.bytes),
            receipt_bytes: self.bytes,
            vehicle: self.vehicle,
            terms_version,
            terms_text,
        }
    }
}

fn open_bound(
    vehicle: &Path,
    sidecar: &Path,
    expected_hash: Option<&str>,
    expected: &Expected<'_>,
) -> Result<OpenedReceipt> {
    let (sidecar_root, sidecar_name, sidecar_file) = absolute_file(sidecar, MAX_RECEIPT)?;
    let bytes = sidecar_file.bytes(MAX_RECEIPT)?;
    if let Some(hash) = expected_hash {
        ensure!(
            hex(hash, 64) && sha256_hex(&bytes) == hash,
            "retained qualification receipt digest differs"
        );
    }
    let value: Value = serde_json::from_slice(&bytes).context("invalid qualification JSON")?;
    ensure!(
        canonical(&value)? == bytes,
        "noncanonical qualification receipt"
    );
    let receipt: Receipt =
        serde_json::from_value(value).context("invalid qualification receipt fields")?;
    validate_receipt(&receipt, expected)?;
    ensure!(
        vehicle.file_name().and_then(|name| name.to_str())
            == Some(receipt.artifact.filename.as_str()),
        "qualification vehicle name differs"
    );
    let (vehicle_root, vehicle_name, vehicle_file) = absolute_file(vehicle, MAX_FILE)?;
    for name in [
        "release-manifest.json",
        "release-manifest.json.bundle.jsonl",
    ] {
        sidecar_root.require_absent(name)?;
        vehicle_root.require_absent(name)?;
    }
    vehicle_file.verify(receipt.artifact.size, &receipt.artifact.sha256)?;
    let opened = OpenedReceipt {
        receipt,
        bytes,
        vehicle: vehicle_file,
        vehicle_root,
        vehicle_name,
        sidecar: sidecar_file,
        sidecar_root,
        sidecar_name,
    };
    opened.recheck()?;
    Ok(opened)
}

fn verify(
    vehicle: &Path,
    root: &Path,
    executable: &Path,
    expected: &Expected<'_>,
) -> Result<VerifiedDevelopmentReceipt> {
    let opened = open_bound(
        vehicle,
        &vehicle.with_extension("development.json"),
        None,
        expected,
    )?;
    let mounted = ConfinedRoot::open(root)?;
    let first = mounted_inventory(&mounted)?;
    ensure!(
        first.members.values().eq(opened.receipt.appdir.iter()),
        "mounted qualification inventory differs"
    );
    if let Some(Member::File { size, sha256, .. }) = first.members.get("usr/bin/vadgr") {
        verify_file(executable, *size, sha256)?;
    }
    let inventory_file = mounted.regular("package-input-inventory.json", MAX_METADATA)?;
    let inventory_bytes = inventory_file.bytes(MAX_METADATA)?;
    if let Some(Member::File { size, sha256, .. }) =
        first.members.get("package-input-inventory.json")
    {
        ensure!(
            inventory_bytes.len() as u64 == *size && sha256_hex(&inventory_bytes) == *sha256,
            "qualification terms inventory changed"
        );
    }
    let inventory: Value = serde_json::from_slice(&inventory_bytes)?;
    let terms_version = inventory["terms_version"]
        .as_str()
        .context("missing terms version")?
        .to_owned();
    version(&terms_version)?;
    let terms_hash = required_file_hash(&opened.receipt, "legal/TERMS.txt")?;
    let terms_file = mounted.regular("legal/TERMS.txt", MAX_METADATA)?;
    let terms_bytes = terms_file.bytes(MAX_METADATA)?;
    ensure!(
        sha256_hex(&terms_bytes) == terms_hash,
        "qualification terms text differs"
    );
    let terms_text = String::from_utf8(terms_bytes).context("qualification terms are not UTF-8")?;
    ensure!(
        inventory["schema"] == 1
            && inventory["version"] == expected.version
            && inventory["target"] == format!("{}-unknown-linux-gnu", expected.architecture)
            && inventory["terms_sha256"] == terms_hash,
        "qualification terms inventory differs"
    );
    let second = mounted_inventory(&mounted)?;
    ensure!(
        first == second,
        "qualification inventory changed between scans"
    );
    mounted.assert_bound("package-input-inventory.json", &inventory_file.stamp)?;
    mounted.assert_bound("legal/TERMS.txt", &terms_file.stamp)?;
    mounted.assert_root()?;
    opened.recheck()?;
    Ok(opened.finish(Some((terms_version, terms_text))))
}

fn required_file_hash<'a>(receipt: &'a Receipt, path: &str) -> Result<&'a str> {
    receipt
        .appdir
        .iter()
        .find_map(|member| match member {
            Member::File {
                path: name, sha256, ..
            } if name == path => Some(sha256.as_str()),
            _ => None,
        })
        .context("required qualification regular member is missing")
}

#[cfg(test)]
#[path = "development_tests.rs"]
mod tests;
