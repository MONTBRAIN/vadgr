//! Archive safety checks run before an installer extracts a signed payload.

use anyhow::{Result, bail, ensure};
use flate2::read::GzDecoder;
use std::collections::HashMap;
use std::path::{Component, Path, PathBuf};

pub fn validate_tar_gz(path: &Path) -> Result<()> {
    let file = std::fs::File::open(path)?;
    let mut archive = tar::Archive::new(GzDecoder::new(file));
    let mut members = HashMap::new();
    let mut folded = std::collections::HashSet::new();
    let mut links = Vec::new();
    for entry in archive.entries()? {
        let entry = entry?;
        let path = entry.path()?.into_owned();
        validate_path(&path)?;
        let path = normalized(&path)?;
        let kind = entry.header().entry_type();
        ensure!(
            kind.is_file() || kind.is_dir() || kind.is_symlink() || kind.is_hard_link(),
            "archive contains an unsupported special entry"
        );
        ensure!(
            !path.as_os_str().is_empty() || kind.is_dir(),
            "archive root entry is not a directory"
        );
        ensure!(
            members.insert(path.clone(), kind).is_none(),
            "archive contains a duplicate path"
        );
        let text = path
            .to_str()
            .ok_or_else(|| anyhow::anyhow!("archive path is not UTF-8"))?;
        ensure!(
            folded.insert(text.to_lowercase()),
            "archive contains a case-colliding path"
        );
        if let Some(link) = entry.link_name()? {
            ensure!(
                kind.is_symlink() || kind.is_hard_link(),
                "archive non-link entry has a link target"
            );
            validate_link(&path, &link, kind.is_hard_link())?;
            let base = if kind.is_hard_link() {
                Path::new("")
            } else {
                path.parent().unwrap_or(Path::new(""))
            };
            let target = normalized(&base.join(link.as_ref()))?;
            links.push((path, target, kind.is_hard_link()));
        } else {
            ensure!(
                !kind.is_symlink() && !kind.is_hard_link(),
                "archive link has no target"
            );
        }
    }
    // No archive entry may traverse another member that is a link or file,
    // regardless of extraction order. Link targets cannot traverse links either.
    for path in members.keys() {
        for parent in path.ancestors().skip(1) {
            if let Some(kind) = members.get(parent) {
                ensure!(
                    kind.is_dir(),
                    "archive entry traverses a non-directory member"
                );
            }
        }
    }
    for (_path, target, hard_link) in links {
        let target_kind = members
            .get(&target)
            .ok_or_else(|| anyhow::anyhow!("archive link target is missing"))?;
        ensure!(
            target_kind.is_file() || (!hard_link && target_kind.is_dir()),
            "archive link targets another link or special entry"
        );
        for ancestor in target.ancestors().skip(1) {
            if let Some(kind) = members.get(ancestor) {
                ensure!(
                    kind.is_dir(),
                    "archive link target traverses a non-directory member"
                );
            }
        }
    }
    Ok(())
}

fn normalized(path: &Path) -> Result<PathBuf> {
    let mut result = PathBuf::new();
    for component in path.components() {
        match component {
            Component::Normal(value) => {
                let value = value
                    .to_str()
                    .ok_or_else(|| anyhow::anyhow!("archive path is not UTF-8"))?;
                ensure!(
                    !value.contains('\\'),
                    "archive contains a platform-dependent path"
                );
                result.push(value);
            }
            Component::CurDir => {}
            Component::ParentDir => ensure!(result.pop(), "archive link escapes staging"),
            _ => bail!("archive contains an absolute or platform path"),
        }
    }
    Ok(result)
}

fn validate_path(path: &Path) -> Result<()> {
    ensure!(!path.is_absolute(), "archive contains an absolute path");
    ensure!(
        path.components()
            .all(|component| matches!(component, Component::Normal(_) | Component::CurDir)),
        "archive contains a parent or platform path: {}",
        path.display()
    );
    Ok(())
}

fn validate_link(entry: &Path, link: &Path, hard_link: bool) -> Result<()> {
    ensure!(!link.is_absolute(), "archive contains an absolute link");
    let base = if hard_link {
        PathBuf::new()
    } else {
        entry
            .parent()
            .unwrap_or_else(|| Path::new(""))
            .to_path_buf()
    };
    let mut depth = 0usize;
    for component in base.join(link).components() {
        match component {
            Component::Normal(_) => depth += 1,
            Component::CurDir => {}
            Component::ParentDir if depth > 0 => depth -= 1,
            Component::ParentDir => bail!("archive link escapes staging: {}", link.display()),
            Component::RootDir | Component::Prefix(_) => {
                bail!("archive contains an absolute or platform link")
            }
        }
    }
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;
    fn archive_with(path: &str) -> tempfile::NamedTempFile {
        let file = tempfile::NamedTempFile::new().unwrap();
        let encoder =
            flate2::write::GzEncoder::new(file.reopen().unwrap(), flate2::Compression::default());
        let mut archive = tar::Builder::new(encoder);
        let bytes = b"payload";
        let mut header = tar::Header::new_gnu();
        header.set_size(bytes.len() as u64);
        header.set_mode(0o644);
        header.set_cksum();
        archive.append_data(&mut header, path, &bytes[..]).unwrap();
        let encoder = archive.into_inner().unwrap();
        encoder.finish().unwrap();
        file
    }

    #[test]
    fn a_normal_archive_is_accepted() {
        let file = archive_with("vadgr/bin/vadgr");
        validate_tar_gz(file.path()).unwrap();
    }

    #[test]
    fn path_validation_rejects_escape_and_absolute_entries() {
        assert!(validate_path(Path::new("../outside")).is_err());
        assert!(validate_path(Path::new("/outside")).is_err());
    }

    fn archive_entries(rows: &[(&str, u8, &str)]) -> tempfile::NamedTempFile {
        let file = tempfile::NamedTempFile::new().unwrap();
        let encoder =
            flate2::write::GzEncoder::new(file.reopen().unwrap(), flate2::Compression::default());
        let mut archive = tar::Builder::new(encoder);
        for (path, kind, link) in rows {
            let mut header = tar::Header::new_gnu();
            header.set_size(0);
            header.set_mode(0o644);
            header.set_entry_type(tar::EntryType::new(*kind));
            // Raw fields deliberately bypass the builder's own safety checks.
            header.as_mut_bytes()[..path.len()].copy_from_slice(path.as_bytes());
            header.as_mut_bytes()[157..157 + link.len()].copy_from_slice(link.as_bytes());
            header.set_cksum();
            archive.append(&header, std::io::empty()).unwrap();
        }
        archive.into_inner().unwrap().finish().unwrap();
        file
    }

    #[test]
    fn malicious_archive_members_fail_before_extraction() {
        for rows in [
            vec![("../outside", b'0', "")],
            vec![("/outside", b'0', "")],
            vec![("link", b'2', "../outside")],
            vec![("link", b'1', "../outside")],
            vec![("file", b'0', ""), ("./file", b'0', "")],
            vec![("FILE", b'0', ""), ("file", b'0', "")],
            vec![("link", b'2', "safe"), ("link/child", b'0', "")],
            vec![("link/child", b'0', ""), ("link", b'2', "safe")],
            vec![("fifo", b'6', "")],
            vec![("a", b'2', "b"), ("b", b'2', "a")],
        ] {
            let file = archive_entries(&rows);
            assert!(validate_tar_gz(file.path()).is_err(), "accepted {rows:?}");
        }
    }

    #[test]
    fn safe_python_links_and_directory_members_are_accepted() {
        let file = archive_entries(&[
            ("./", b'5', ""),
            ("bin", b'5', ""),
            ("bin/python3.12", b'0', ""),
            ("bin/python3", b'2', "python3.12"),
            ("python", b'1', "bin/python3.12"),
        ]);
        validate_tar_gz(file.path()).unwrap();
    }
}
