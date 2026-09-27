//! Inspect pinned base-Python images before installing the immutable runtime.
//!
//! CPython copies vcruntime DLLs by glob, including optional foreign images.
//! A native ARM64 image has an ARM64 default header, also when it is ARM64X.
//! An AMD64 default header does not establish native ARM64 compatibility.

use anyhow::{Context, Result, bail, ensure};
use std::collections::{BTreeMap, BTreeSet};
use std::path::Path;

const ARM64: u16 = 0xaa64;
const AMD64: u16 = 0x8664;

pub(super) fn prune_arm64_base_python(root: &Path, target: &str) -> Result<BTreeSet<String>> {
    if target != "aarch64-pc-windows-msvc" {
        return Ok(BTreeSet::new());
    }
    let canonical_root = root.canonicalize()?;
    let mut files = Vec::new();
    super::collect_regular_files(root, &mut files)?;
    let mut images = Vec::new();
    let mut names = BTreeMap::<String, usize>::new();
    for path in files {
        let extension = path.extension().and_then(|x| x.to_str()).unwrap_or("");
        let bytes = std::fs::read(&path)?;
        if !bytes.starts_with(b"MZ")
            && !["exe", "dll", "pyd"]
                .iter()
                .any(|x| extension.eq_ignore_ascii_case(x))
        {
            continue;
        }
        let image = Image::parse(&bytes)
            .with_context(|| format!("invalid base Python image: {}", path.display()))?;
        let name = module_name(path.file_name().and_then(|x| x.to_str()).unwrap_or(""))?;
        *names.entry(name.clone()).or_default() += 1;
        let foreign = image.machine == AMD64;
        ensure!(
            image.machine == ARM64
                || (foreign
                    && image.characteristics & 0x2000 != 0
                    && extension.eq_ignore_ascii_case("dll")),
            "incompatible base Python executable: {}",
            path.display()
        );
        // Parse even unused foreign images. Malformed input never authorizes deletion.
        let dependencies = image.dependencies()?;
        images.push((path, name, foreign, dependencies));
    }
    let excluded: BTreeSet<_> = images.iter().filter(|x| x.2).map(|x| x.1.clone()).collect();
    for name in &excluded {
        ensure!(names[name] == 1, "ambiguous base Python DLL: {name}");
    }
    for (path, _, foreign, dependencies) in &images {
        if !foreign && let Some(name) = dependencies.intersection(&excluded).next() {
            bail!(
                "required incompatible base Python DLL {name}: {}",
                path.display()
            );
        }
        ensure!(
            path.canonicalize()?.starts_with(&canonical_root),
            "Python cleanup escaped staging"
        );
    }
    // Validate the entire retained dependency graph before removing any file.
    for (path, _, foreign, _) in images {
        if foreign {
            std::fs::remove_file(path)?;
        }
    }
    Ok(excluded)
}

pub(super) fn verify_retained_dependencies(
    root: &Path,
    target: &str,
    excluded: &BTreeSet<String>,
) -> Result<()> {
    if target != "aarch64-pc-windows-msvc" {
        return Ok(());
    }
    let mut files = Vec::new();
    super::collect_regular_files(root, &mut files)?;
    for path in files {
        let bytes = std::fs::read(&path)?;
        let extension = path.extension().and_then(|x| x.to_str()).unwrap_or("");
        if !bytes.starts_with(b"MZ")
            && !["exe", "dll", "pyd"]
                .iter()
                .any(|x| extension.eq_ignore_ascii_case(x))
        {
            continue;
        }
        let image = Image::parse(&bytes)
            .with_context(|| format!("invalid retained Python image: {}", path.display()))?;
        ensure!(
            image.machine == ARM64,
            "incompatible retained Python image: {}",
            path.display()
        );
        if let Some(name) = image.dependencies()?.intersection(excluded).next() {
            bail!(
                "required incompatible base Python DLL {name}: {}",
                path.display()
            );
        }
    }
    Ok(())
}

struct Section {
    rva: usize,
    extent: usize,
    raw: usize,
    size: usize,
}

struct Image<'a> {
    bytes: &'a [u8],
    machine: u16,
    characteristics: u16,
    directories: [(usize, usize); 16],
    sections: Vec<Section>,
}

fn slice(bytes: &[u8], offset: usize, size: usize) -> Result<&[u8]> {
    bytes
        .get(offset..offset.checked_add(size).context("PE range overflow")?)
        .context("PE range outside file")
}

fn u16_at(bytes: &[u8], offset: usize) -> Result<u16> {
    Ok(u16::from_le_bytes(slice(bytes, offset, 2)?.try_into()?))
}

fn u32_at(bytes: &[u8], offset: usize) -> Result<usize> {
    Ok(u32::from_le_bytes(slice(bytes, offset, 4)?.try_into()?) as usize)
}

fn module_name(name: &str) -> Result<String> {
    ensure!(
        !name.is_empty()
            && name.len() <= 255
            && name
                .bytes()
                .all(|x| x.is_ascii_alphanumeric() || b"._-".contains(&x))
            && !name.starts_with('.')
            && !name.ends_with('.')
            && !name.contains(".."),
        "invalid PE dependency name"
    );
    Ok(name.to_ascii_lowercase())
}

impl<'a> Image<'a> {
    fn parse(bytes: &'a [u8]) -> Result<Self> {
        ensure!(slice(bytes, 0, 2)? == b"MZ", "missing DOS header");
        let pe = u32_at(bytes, 0x3c)?;
        ensure!(
            pe >= 64 && slice(bytes, pe, 4)? == b"PE\0\0",
            "invalid PE signature"
        );
        let machine = u16_at(bytes, pe + 4)?;
        let count = usize::from(u16_at(bytes, pe + 6)?);
        let optional_size = usize::from(u16_at(bytes, pe + 20)?);
        let characteristics = u16_at(bytes, pe + 22)?;
        ensure!(
            characteristics & 2 != 0 && (1..=96).contains(&count),
            "invalid PE image header"
        );
        let optional = slice(bytes, pe + 24, optional_size)?;
        ensure!(
            u16_at(optional, 0)? == 0x20b,
            "base Python image must be PE32+"
        );
        let directory_count = u32_at(optional, 108)?;
        ensure!(
            directory_count <= 16 && optional.len() >= 112 + directory_count * 8,
            "invalid PE directories"
        );
        let mut directories = [(0, 0); 16];
        for (index, entry) in directories.iter_mut().enumerate().take(directory_count) {
            *entry = (
                u32_at(optional, 112 + index * 8)?,
                u32_at(optional, 116 + index * 8)?,
            );
            ensure!((entry.0 == 0) == (entry.1 == 0), "incomplete PE directory");
        }
        let table = pe + 24 + optional_size;
        slice(bytes, table, count * 40)?;
        let headers = u32_at(optional, 60)?;
        ensure!(
            headers >= table + count * 40 && headers <= bytes.len(),
            "invalid PE header extent"
        );
        let mut sections: Vec<Section> = Vec::new();
        for index in 0..count {
            let offset = table + index * 40;
            let rva = u32_at(bytes, offset + 12)?;
            let size = u32_at(bytes, offset + 16)?;
            let raw = u32_at(bytes, offset + 20)?;
            let extent = u32_at(bytes, offset + 8)?.max(size);
            ensure!(
                rva >= headers
                    && rva
                        .checked_add(extent)
                        .is_some_and(|end| end <= u32::MAX as usize),
                "invalid PE section extent"
            );
            if size != 0 {
                ensure!(raw >= headers, "PE section overlaps headers");
                slice(bytes, raw, size)?;
            }
            for old in &sections {
                ensure!(
                    extent == 0
                        || old.extent == 0
                        || rva + extent <= old.rva
                        || old.rva + old.extent <= rva,
                    "overlapping PE virtual sections"
                );
                ensure!(
                    size == 0
                        || old.size == 0
                        || raw + size <= old.raw
                        || old.raw + old.size <= raw,
                    "overlapping PE file sections"
                );
            }
            sections.push(Section {
                rva,
                extent,
                raw,
                size,
            });
        }
        Ok(Self {
            bytes,
            machine,
            characteristics,
            directories,
            sections,
        })
    }

    fn at(&self, rva: usize, size: usize) -> Result<&'a [u8]> {
        let end = rva.checked_add(size).context("PE RVA overflow")?;
        for section in &self.sections {
            if rva >= section.rva && end <= section.rva + section.size {
                return slice(self.bytes, section.raw + rva - section.rva, size);
            }
        }
        bail!("PE RVA outside raw section")
    }

    fn string(&self, rva: usize, limit: usize) -> Result<&'a str> {
        for length in 0..limit.min(4096) {
            if self.at(rva + length, 1)?[0] == 0 {
                return Ok(std::str::from_utf8(self.at(rva, length)?)?);
            }
        }
        bail!("unterminated PE string")
    }

    fn dependencies(&self) -> Result<BTreeSet<String>> {
        let mut result = BTreeSet::new();
        for (index, width, name_offset) in [(1, 20, 12), (13, 32, 4)] {
            let (rva, size) = self.directories[index];
            if size == 0 {
                continue;
            }
            let descriptors = self.at(rva, size)?;
            let mut terminated = false;
            for descriptor in descriptors.chunks_exact(width) {
                if descriptor.iter().all(|x| *x == 0) {
                    terminated = true;
                    break;
                }
                if index == 13 {
                    ensure!(
                        u32_at(descriptor, 0)? == 1,
                        "unsupported delay import addressing"
                    );
                }
                let name = self.string(u32_at(descriptor, name_offset)?, 256)?;
                let mut name = module_name(name)?;
                // The Windows loader appends .dll to an extensionless name.
                if !name.contains('.') {
                    name.push_str(".dll");
                }
                result.insert(name);
            }
            ensure!(terminated, "unterminated PE import directory");
        }
        let (rva, size) = self.directories[0];
        if size != 0 {
            self.at(rva, size)?;
            let exports = self.at(rva, 40)?;
            ensure!(size >= 40, "truncated PE export directory");
            let count = u32_at(exports, 20)?;
            let functions = if count == 0 {
                &[][..]
            } else {
                self.at(
                    u32_at(exports, 28)?,
                    count.checked_mul(4).context("PE export count overflow")?,
                )?
            };
            for function in functions.chunks_exact(4) {
                let address = u32_at(function, 0)?;
                if (rva..rva + size).contains(&address) {
                    let forwarder = self.string(address, rva + size - address)?;
                    let (module, symbol) = forwarder
                        .rsplit_once('.')
                        .context("invalid PE export forwarder")?;
                    ensure!(
                        !symbol.is_empty()
                            && symbol.is_ascii()
                            && !symbol.bytes().any(|x| x.is_ascii_control()),
                        "invalid PE forwarded symbol"
                    );
                    let mut name = module_name(module)?;
                    ensure!(
                        !name.contains('.')
                            || name
                                .strip_suffix(".dll")
                                .is_some_and(|stem| !stem.contains('.')),
                        "ambiguous PE export forwarder"
                    );
                    if !name.ends_with(".dll") {
                        name.push_str(".dll");
                    }
                    result.insert(name);
                }
            }
        }
        Ok(result)
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    const TARGET: &str = "aarch64-pc-windows-msvc";

    fn word(bytes: &mut [u8], offset: usize, value: u16) {
        bytes[offset..offset + 2].copy_from_slice(&value.to_le_bytes());
    }

    fn dword(bytes: &mut [u8], offset: usize, value: u32) {
        bytes[offset..offset + 4].copy_from_slice(&value.to_le_bytes());
    }

    fn image(machine: u16) -> Vec<u8> {
        let mut bytes = vec![0; 0x1200];
        bytes[..2].copy_from_slice(b"MZ");
        dword(&mut bytes, 0x3c, 0x80);
        bytes[0x80..0x84].copy_from_slice(b"PE\0\0");
        word(&mut bytes, 0x84, machine);
        word(&mut bytes, 0x86, 1);
        word(&mut bytes, 0x94, 240);
        word(&mut bytes, 0x96, 0x2022);
        word(&mut bytes, 0x98, 0x20b);
        dword(&mut bytes, 0x98 + 60, 0x200);
        dword(&mut bytes, 0x98 + 108, 16);
        dword(&mut bytes, 0x188 + 8, 0x1000);
        dword(&mut bytes, 0x188 + 12, 0x1000);
        dword(&mut bytes, 0x188 + 16, 0x1000);
        dword(&mut bytes, 0x188 + 20, 0x200);
        bytes
    }

    fn directory(bytes: &mut [u8], index: usize, rva: u32, size: u32) {
        dword(bytes, 0x98 + 112 + index * 8, rva);
        dword(bytes, 0x98 + 116 + index * 8, size);
    }

    fn dependency(bytes: &mut [u8], kind: usize, name: &str) {
        match kind {
            1 => {
                directory(bytes, 1, 0x1100, 40);
                dword(bytes, 0x300 + 12, 0x1200);
            }
            13 => {
                directory(bytes, 13, 0x1100, 64);
                dword(bytes, 0x300, 1);
                dword(bytes, 0x300 + 4, 0x1200);
            }
            0 => {
                directory(bytes, 0, 0x1100, 0x200);
                dword(bytes, 0x300 + 20, 1);
                dword(bytes, 0x300 + 28, 0x1140);
                dword(bytes, 0x340, 0x1200);
            }
            _ => unreachable!(),
        }
        bytes[0x400..0x400 + name.len()].copy_from_slice(name.as_bytes());
    }

    #[test]
    fn removes_unused_foreign_dll_without_a_filename_allowlist() {
        let root = tempfile::tempdir().unwrap();
        let mut native = image(ARM64);
        // Native-default ARM64X remains native. Hybrid metadata is not an
        // exemption for an AMD64-default image.
        directory(&mut native, 10, 0x1800, 320);
        dword(&mut native, 0xa00, 320);
        dword(&mut native, 0xa00 + 200, 0x1a00);
        std::fs::write(root.path().join("native.dll"), &native).unwrap();
        let mut foreign = native.clone();
        word(&mut foreign, 0x84, AMD64);
        std::fs::write(root.path().join("any-name.dll"), &foreign).unwrap();
        prune_arm64_base_python(root.path(), TARGET).unwrap();
        assert!(!root.path().join("any-name.dll").exists());
        assert_eq!(
            std::fs::read(root.path().join("native.dll")).unwrap(),
            native
        );
    }

    #[test]
    fn required_foreign_dll_refuses_before_any_deletion() {
        for (kind, name) in [
            (1, "FOREIGN.DLL"),
            (1, "FOREIGN"),
            (13, "Foreign.dll"),
            (13, "foreign"),
            (0, "FOREIGN.entry"),
            (0, "foreign.dll.#12"),
        ] {
            let root = tempfile::tempdir().unwrap();
            let mut native = image(ARM64);
            dependency(&mut native, kind, name);
            std::fs::write(root.path().join("python.exe"), native).unwrap();
            for name in ["foreign.dll", "unneeded.dll"] {
                std::fs::write(root.path().join(name), image(AMD64)).unwrap();
            }
            let error = prune_arm64_base_python(root.path(), TARGET).unwrap_err();
            assert!(
                error.to_string().contains("required incompatible"),
                "{error:#}"
            );
            assert!(root.path().join("foreign.dll").exists());
            assert!(root.path().join("unneeded.dll").exists());
        }
    }

    #[test]
    fn retained_wheel_dependencies_cannot_require_an_excluded_base_dll() {
        let excluded = BTreeSet::from(["foreign.dll".to_owned()]);
        for (kind, name) in [(1, "FOREIGN.DLL"), (13, "foreign"), (0, "foreign.entry")] {
            let root = tempfile::tempdir().unwrap();
            let mut bytes = image(ARM64);
            dependency(&mut bytes, kind, name);
            std::fs::write(root.path().join("extension.pyd"), &bytes).unwrap();
            assert!(verify_retained_dependencies(root.path(), TARGET, &excluded).is_err());
            assert_eq!(
                std::fs::read(root.path().join("extension.pyd")).unwrap(),
                bytes
            );
            verify_retained_dependencies(root.path(), TARGET, &BTreeSet::new()).unwrap();
        }
        let root = tempfile::tempdir().unwrap();
        std::fs::write(root.path().join("wheel.dll"), image(AMD64)).unwrap();
        assert!(verify_retained_dependencies(root.path(), TARGET, &BTreeSet::new()).is_err());
        assert!(root.path().join("wheel.dll").exists());
    }

    #[test]
    fn foreign_executables_extensions_and_intermediate_machines_are_not_pruned() {
        for (name, machine, characteristics) in [
            ("python.exe", AMD64, 0x22),
            ("extension.pyd", AMD64, 0x2022),
            ("renamed.dat", AMD64, 0x2022),
            ("not-a-dll.dll", AMD64, 0x22),
            ("intermediate.dll", 0xa641, 0x2022),
            ("x86.dll", 0x14c, 0x2022),
        ] {
            let root = tempfile::tempdir().unwrap();
            let mut bytes = image(machine);
            word(&mut bytes, 0x96, characteristics);
            std::fs::write(root.path().join(name), &bytes).unwrap();
            assert!(prune_arm64_base_python(root.path(), TARGET).is_err());
            assert_eq!(std::fs::read(root.path().join(name)).unwrap(), bytes);
        }
    }

    #[test]
    fn ambiguous_dll_names_refuse_even_in_different_directories() {
        let root = tempfile::tempdir().unwrap();
        std::fs::create_dir(root.path().join("DLLs")).unwrap();
        std::fs::write(root.path().join("foreign.dll"), image(AMD64)).unwrap();
        std::fs::write(root.path().join("DLLs/FOREIGN.dll"), image(ARM64)).unwrap();
        assert!(prune_arm64_base_python(root.path(), TARGET).is_err());
        assert!(root.path().join("foreign.dll").exists());
    }

    #[test]
    fn other_targets_are_unchanged() {
        for target in [
            "x86_64-pc-windows-msvc",
            "aarch64-apple-darwin",
            "aarch64-unknown-linux-gnu",
        ] {
            let root = tempfile::tempdir().unwrap();
            std::fs::write(root.path().join("foreign.dll"), b"not PE").unwrap();
            prune_arm64_base_python(root.path(), target).unwrap();
            assert_eq!(
                std::fs::read(root.path().join("foreign.dll")).unwrap(),
                b"not PE"
            );
        }
    }

    #[test]
    fn malformed_pe_dependency_tables_fail_closed() {
        let mut cases = Vec::new();
        let mut bytes = image(ARM64);
        dependency(&mut bytes, 1, "../foreign.dll");
        cases.push(bytes);
        let mut bytes = image(ARM64);
        dependency(&mut bytes, 1, "foreign.dll.");
        cases.push(bytes);
        let mut bytes = image(ARM64);
        dependency(&mut bytes, 1, "foreign.dll");
        directory(&mut bytes, 1, 0x1100, 20);
        cases.push(bytes);
        let mut bytes = image(ARM64);
        dependency(&mut bytes, 13, "foreign.dll");
        dword(&mut bytes, 0x300, 0);
        cases.push(bytes);
        let mut bytes = image(ARM64);
        dependency(&mut bytes, 0, "foreign");
        cases.push(bytes);
        let mut bytes = image(ARM64);
        dependency(&mut bytes, 0, "foreign.entry.extra");
        cases.push(bytes);
        let mut bytes = image(ARM64);
        dependency(&mut bytes, 0, "foreign.entry");
        directory(&mut bytes, 0, 0x1100, 0x10c);
        cases.push(bytes);
        let mut bytes = image(ARM64);
        dependency(&mut bytes, 0, "foreign.entry");
        dword(&mut bytes, 0x300 + 20, u32::MAX);
        cases.push(bytes);
        let mut bytes = image(ARM64);
        dependency(&mut bytes, 1, "foreign.dll");
        dword(&mut bytes, 0x300 + 12, 0xfffffff0);
        cases.push(bytes);
        let mut bytes = image(ARM64);
        directory(&mut bytes, 1, 0x1ff0, 40);
        cases.push(bytes);
        let mut bytes = image(ARM64);
        dependency(&mut bytes, 1, "foreign.dll");
        bytes[0x400..0x500].fill(b'a');
        cases.push(bytes);
        for bytes in cases {
            let root = tempfile::tempdir().unwrap();
            std::fs::write(root.path().join("python.exe"), bytes).unwrap();
            std::fs::write(root.path().join("foreign.dll"), image(AMD64)).unwrap();
            assert!(prune_arm64_base_python(root.path(), TARGET).is_err());
            assert!(root.path().join("foreign.dll").exists());
        }
    }

    #[test]
    fn overlapping_sections_and_truncated_images_fail_closed() {
        let bytes = image(ARM64);
        for length in 0..bytes.len() {
            assert!(Image::parse(&bytes[..length]).is_err(), "length {length}");
        }
        for file_overlap in [false, true] {
            let mut bytes = image(ARM64);
            word(&mut bytes, 0x86, 2);
            let original = bytes[0x188..0x188 + 40].to_vec();
            bytes[0x1b0..0x1b0 + 40].copy_from_slice(&original);
            if file_overlap {
                dword(&mut bytes, 0x1b0 + 12, 0x3000);
            }
            assert!(Image::parse(&bytes).is_err());
        }
    }
}
