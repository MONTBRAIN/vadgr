//! Owner-only files that hold machine state or service output.

use std::fs::{File, OpenOptions};
use std::path::Path;

#[cfg(unix)]
pub fn create_dir_all(path: &Path) -> std::io::Result<()> {
    use std::os::unix::fs::{DirBuilderExt, PermissionsExt};

    std::fs::DirBuilder::new()
        .recursive(true)
        .mode(0o700)
        .create(path)?;
    std::fs::set_permissions(path, std::fs::Permissions::from_mode(0o700))
}

#[cfg(not(unix))]
pub fn create_dir_all(path: &Path) -> std::io::Result<()> {
    std::fs::create_dir_all(path)
}

#[cfg(unix)]
fn open(path: &Path, truncate: bool, append: bool) -> std::io::Result<File> {
    use std::os::unix::fs::{OpenOptionsExt, PermissionsExt};

    let file = OpenOptions::new()
        .write(true)
        .create(true)
        .truncate(truncate)
        .append(append)
        .mode(0o600)
        .open(path)?;
    file.set_permissions(std::fs::Permissions::from_mode(0o600))?;
    Ok(file)
}

#[cfg(not(unix))]
fn open(path: &Path, truncate: bool, append: bool) -> std::io::Result<File> {
    OpenOptions::new()
        .write(true)
        .create(true)
        .truncate(truncate)
        .append(append)
        .open(path)
}

pub fn touch(path: &Path) -> std::io::Result<File> {
    open(path, false, false)
}

pub fn append(path: &Path) -> std::io::Result<File> {
    open(path, false, true)
}

#[cfg(unix)]
pub fn harden(path: &Path) -> std::io::Result<()> {
    use std::os::unix::fs::PermissionsExt;

    if path.exists() {
        std::fs::set_permissions(path, std::fs::Permissions::from_mode(0o600))?;
    }
    Ok(())
}

#[cfg(not(unix))]
pub fn harden(_path: &Path) -> std::io::Result<()> {
    Ok(())
}
