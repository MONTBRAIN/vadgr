//! Archive safety checks run before an installer extracts a signed payload.

use anyhow::{Result, bail, ensure};
use flate2::read::GzDecoder;
use std::path::{Component, Path, PathBuf};

pub fn validate_tar_gz(path: &Path) -> Result<()> {
    let file = std::fs::File::open(path)?;
    let mut archive = tar::Archive::new(GzDecoder::new(file));
    for entry in archive.entries()? {
        let entry = entry?;
        let path = entry.path()?.into_owned();
        validate_path(&path)?;
        if let Some(link) = entry.link_name()? {
            validate_link(&path, &link, entry.header().entry_type().is_hard_link())?;
        }
    }
    Ok(())
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
}
