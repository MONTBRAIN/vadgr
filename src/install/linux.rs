//! Native Linux AppImage installation and retained-generation lifecycle.

use super::{InstallReceipt, RELEASE_PUBLIC_KEY, VerifiedManifest, record_terms_acceptance};
use anyhow::{Context, Result, anyhow, ensure};
use std::os::unix::fs::{PermissionsExt, symlink};
use std::path::{Path, PathBuf};

const DESKTOP_FILE: &str = "com.montbrain.vadgr.desktop";

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum InstallPhase {
    Verifying,
    Staging,
    Committing,
    RegisteringLaunch,
    HealthCheck,
    Complete,
}

pub fn install_appimage(
    vehicle: &Path,
    manifest_path: &Path,
    signature_path: &Path,
    bundle_root: &Path,
    terms_version: &str,
) -> Result<PathBuf> {
    install_appimage_with_progress(
        vehicle,
        manifest_path,
        signature_path,
        bundle_root,
        terms_version,
        |_| {},
    )
}

pub fn install_appimage_with_progress<F>(
    vehicle: &Path,
    manifest_path: &Path,
    signature_path: &Path,
    bundle_root: &Path,
    terms_version: &str,
    mut progress: F,
) -> Result<PathBuf>
where
    F: FnMut(InstallPhase),
{
    progress(InstallPhase::Verifying);
    ensure!(vehicle.is_absolute(), "the AppImage path must be absolute");
    let target = super::manifest::current_target()?;
    ensure!(
        target.starts_with("linux-"),
        "the AppImage installer runs only on native Linux"
    );
    let verified = VerifiedManifest::open(manifest_path, signature_path, RELEASE_PUBLIC_KEY)?;
    let artifact = verified.artifact_for_target(&target)?;
    ensure!(
        artifact.kind == "appimage",
        "the selected release artifact is not an AppImage"
    );
    ensure!(
        vehicle.file_name().and_then(|value| value.to_str()) == Some(artifact.name.as_str()),
        "the AppImage file name does not match the signed manifest"
    );
    verified.verify_bytes_at(vehicle, &artifact)?;
    let terms_file = bundle_root.join("legal/TERMS.txt");
    ensure!(
        bundle_root.is_absolute(),
        "the mounted AppImage root must be absolute"
    );
    ensure!(
        super::sha256_file(&terms_file)? == verified.manifest.terms_sha256,
        "the displayed terms do not match the signed manifest"
    );

    let state_root = crate::config::Config::from_env()
        .map_err(|error| anyhow!("resolving Vadgr state: {error}"))?
        .state_home
        .ok_or_else(|| anyhow!("the Vadgr state root is unavailable"))?;
    verified.ensure_sequence(&state_root)?;

    let root = install_root()?;
    let versions = root.join("versions");
    std::fs::create_dir_all(&versions).context("creating the Vadgr generation directory")?;
    let generation = versions.join(&verified.manifest.version);
    ensure!(
        !generation.exists(),
        "this Vadgr version is already installed; use Repair"
    );
    let staging = root.join(format!(".stage-{}", uuid::Uuid::new_v4()));
    let previous = read_current(&root)?;
    progress(InstallPhase::Staging);
    let result = stage_generation(
        &staging,
        vehicle,
        manifest_path,
        signature_path,
        bundle_root,
        &verified,
        &artifact,
    )
    .and_then(|_| {
        progress(InstallPhase::Committing);
        std::fs::rename(&staging, &generation).context("committing the Vadgr generation")?;
        switch_current(&root, &verified.manifest.version)?;
        progress(InstallPhase::RegisteringLaunch);
        register_launch_entries(&root)?;
        progress(InstallPhase::HealthCheck);
        start_and_probe(&root)?;
        record_terms_acceptance(
            terms_version,
            &verified.manifest.version,
            &terms_file,
            vehicle,
        )?;
        verified.accept_sequence(&state_root)?;
        progress(InstallPhase::Complete);
        Ok(())
    });
    if let Err(error) = result {
        let _ = restore_current(&root, previous.as_deref());
        let _ = start_and_probe(&root);
        let _ = std::fs::remove_dir_all(&staging);
        let _ = std::fs::remove_dir_all(&generation);
        return Err(error);
    }
    Ok(generation)
}

fn start_and_probe(root: &Path) -> Result<()> {
    let current = root.join("current/Vadgr.AppImage");
    ensure!(current.is_file(), "the active Vadgr AppImage is missing");
    let status = std::process::Command::new(current)
        .arg("start")
        .status()
        .context("starting the installed Vadgr daemon")?;
    ensure!(
        status.success(),
        "the installed Vadgr daemon did not become healthy"
    );
    Ok(())
}

pub fn repair(receipt: &InstallReceipt) -> Result<()> {
    ensure!(
        receipt.package_kind == "appimage",
        "this is not a Linux AppImage installation"
    );
    let manifest_path = receipt.install_root.join("release-manifest.json");
    let signature_path = receipt.install_root.join("release-manifest.json.minisig");
    let verified = VerifiedManifest::open(&manifest_path, &signature_path, RELEASE_PUBLIC_KEY)?;
    let artifact = verified.artifact_for_target(&super::manifest::current_target()?)?;
    let cached = receipt.install_root.join("cache").join(&artifact.name);
    verified.verify_bytes_at(&cached, &artifact)?;
    let active = receipt.install_root.join("Vadgr.AppImage");
    if verified.verify_bytes_at(&active, &artifact).is_err() {
        let temporary = receipt
            .install_root
            .join(format!(".Vadgr.AppImage.{}.tmp", uuid::Uuid::new_v4()));
        std::fs::copy(&cached, &temporary).context("restoring the AppImage candidate")?;
        executable(&temporary)?;
        super::commit_file(&temporary, &active).context("committing the repaired AppImage")?;
    }
    let root = install_root()?;
    register_launch_entries(&root)?;
    start_and_probe(&root)
}

pub fn rollback_appimage() -> Result<String> {
    let root = install_root()?;
    let current =
        read_current(&root)?.ok_or_else(|| anyhow!("no active Vadgr generation was found"))?;
    let mut candidates = Vec::new();
    let versions = root.join("versions");
    for entry in std::fs::read_dir(&versions).context("reading retained Vadgr generations")? {
        let entry = entry?;
        if !entry.file_type()?.is_dir() || entry.file_name() == current.as_str() {
            continue;
        }
        let path = entry.path();
        let receipt: InstallReceipt = serde_json::from_slice(
            &std::fs::read(path.join("install-receipt.json"))
                .context("reading a retained generation receipt")?,
        )
        .context("parsing a retained generation receipt")?;
        candidates.push((
            receipt.release_sequence.unwrap_or(0),
            entry.file_name().to_string_lossy().into_owned(),
        ));
    }
    candidates.sort();
    let (_, version) = candidates
        .pop()
        .ok_or_else(|| anyhow!("no retained Vadgr generation is available"))?;
    verify_and_restore_generation(&versions.join(&version))?;
    switch_current(&root, &version)?;
    let activation = register_launch_entries(&root).and_then(|_| start_and_probe(&root));
    if let Err(error) = activation {
        let _ = switch_current(&root, &current);
        let _ = register_launch_entries(&root);
        let _ = start_and_probe(&root);
        return Err(error)
            .context("the retained generation failed; the prior generation was restored");
    }
    Ok(version)
}

fn verify_and_restore_generation(generation: &Path) -> Result<()> {
    let verified = VerifiedManifest::open(
        &generation.join("release-manifest.json"),
        &generation.join("release-manifest.json.minisig"),
        RELEASE_PUBLIC_KEY,
    )?;
    let artifact = verified.artifact_for_target(&super::manifest::current_target()?)?;
    ensure!(
        artifact.kind == "appimage",
        "the retained artifact is not an AppImage"
    );
    let cached = generation.join("cache").join(&artifact.name);
    verified.verify_bytes_at(&cached, &artifact)?;
    let active = generation.join("Vadgr.AppImage");
    if verified.verify_bytes_at(&active, &artifact).is_err() {
        let temporary = generation.join(format!(".Vadgr.AppImage.{}.tmp", uuid::Uuid::new_v4()));
        std::fs::copy(&cached, &temporary).context("restoring the retained AppImage candidate")?;
        executable(&temporary)?;
        super::commit_file(&temporary, &active)
            .context("committing the restored retained AppImage")?;
    }
    Ok(())
}

pub fn rollback_available() -> Result<bool> {
    let root = install_root()?;
    let Some(current) = read_current(&root)? else {
        return Ok(false);
    };
    let versions = root.join("versions");
    if !versions.is_dir() {
        return Ok(false);
    }
    for entry in std::fs::read_dir(versions)? {
        let entry = entry?;
        if entry.file_type()?.is_dir() && entry.file_name() != current.as_str() {
            return Ok(true);
        }
    }
    Ok(false)
}

pub fn uninstall(receipt: &InstallReceipt, purge: bool) -> Result<()> {
    ensure!(
        receipt.package_kind == "appimage",
        "this is not a Linux AppImage installation"
    );
    let root = install_root()?;
    let active = root.join("current/Vadgr.AppImage");
    if active.is_file() {
        let _ = std::process::Command::new(&active).arg("stop").status();
    }
    unregister_launch_entries(&root)?;
    if root.exists() {
        std::fs::remove_dir_all(&root).context("removing installed Vadgr package files")?;
    }
    if purge {
        super::purge_owner_state()?;
    }
    Ok(())
}

fn stage_generation(
    staging: &Path,
    vehicle: &Path,
    manifest_path: &Path,
    signature_path: &Path,
    bundle_root: &Path,
    verified: &VerifiedManifest,
    artifact: &super::Artifact,
) -> Result<()> {
    std::fs::create_dir_all(staging.join("cache"))
        .context("creating the staged Vadgr generation")?;
    let active = staging.join("Vadgr.AppImage");
    std::fs::copy(vehicle, &active).context("staging the Vadgr AppImage")?;
    executable(&active)?;
    std::fs::copy(vehicle, staging.join("cache").join(&artifact.name))
        .context("retaining the verified repair source")?;
    std::fs::copy(manifest_path, staging.join("release-manifest.json"))
        .context("staging the release manifest")?;
    std::fs::copy(
        signature_path,
        staging.join("release-manifest.json.minisig"),
    )
    .context("staging the manifest signature")?;
    copy_tree(&bundle_root.join("legal"), &staging.join("legal"))
        .context("staging the offline legal bundle")?;
    copy_tree(&bundle_root.join("sbom"), &staging.join("sbom"))
        .context("staging the offline software bill of materials")?;
    let receipt = InstallReceipt {
        schema: 1,
        version: verified.manifest.version.clone(),
        install_root: PathBuf::new(),
        package_kind: "appimage".to_owned(),
        product_code: None,
        release_sequence: Some(verified.manifest.release_sequence),
        manifest_sha256: Some(verified.manifest_sha256()),
        update_origin: None,
        publisher: None,
        rollback_vehicle: None,
    };
    std::fs::write(
        staging.join("install-receipt.json"),
        serde_json::to_vec_pretty(&receipt)?,
    )
    .context("writing the staged install receipt")?;
    Ok(())
}

fn copy_tree(source: &Path, destination: &Path) -> Result<()> {
    ensure!(
        source.is_dir(),
        "the package directory {} is missing",
        source.display()
    );
    ensure!(
        !std::fs::symlink_metadata(source)?.file_type().is_symlink(),
        "the package directory {} is a symbolic link",
        source.display()
    );
    std::fs::create_dir_all(destination)?;
    for entry in std::fs::read_dir(source)? {
        let entry = entry?;
        let file_type = entry.file_type()?;
        ensure!(
            !file_type.is_symlink(),
            "the package bundle contains a symbolic link"
        );
        let target = destination.join(entry.file_name());
        if file_type.is_dir() {
            copy_tree(&entry.path(), &target)?;
        } else {
            ensure!(
                file_type.is_file(),
                "the package bundle contains a special file"
            );
            std::fs::copy(entry.path(), target)?;
        }
    }
    Ok(())
}

fn install_root() -> Result<PathBuf> {
    let base = std::env::var_os("XDG_DATA_HOME")
        .map(PathBuf::from)
        .filter(|path| path.is_absolute())
        .or_else(|| {
            std::env::var_os("HOME")
                .map(PathBuf::from)
                .filter(|path| path.is_absolute())
                .map(|home| home.join(".local/share"))
        })
        .ok_or_else(|| anyhow!("the XDG data directory is unavailable"))?;
    Ok(base.join("vadgr"))
}

fn read_current(root: &Path) -> Result<Option<String>> {
    let current = root.join("current");
    if !current.exists() {
        return Ok(None);
    }
    let target = std::fs::read_link(&current).context("reading the active Vadgr generation")?;
    Ok(target
        .file_name()
        .and_then(|value| value.to_str())
        .map(str::to_owned))
}

fn switch_current(root: &Path, version: &str) -> Result<()> {
    ensure!(
        !version.contains('/') && !version.contains('\\'),
        "the generation version is unsafe"
    );
    let temporary = root.join(format!(".current-{}", uuid::Uuid::new_v4()));
    symlink(Path::new("versions").join(version), &temporary)
        .context("creating the active-generation candidate")?;
    super::commit_file(&temporary, &root.join("current"))
        .context("switching the active Vadgr generation")
}

fn restore_current(root: &Path, previous: Option<&str>) -> Result<()> {
    match previous {
        Some(version) => switch_current(root, version),
        None => {
            let current = root.join("current");
            if current.exists() {
                std::fs::remove_file(current)?;
            }
            Ok(())
        }
    }
}

fn register_launch_entries(root: &Path) -> Result<()> {
    let home = std::env::var_os("HOME")
        .map(PathBuf::from)
        .filter(|path| path.is_absolute())
        .ok_or_else(|| anyhow!("HOME is unavailable"))?;
    let bin = home.join(".local/bin");
    std::fs::create_dir_all(&bin).context("creating the user binary directory")?;
    replace_symlink(&bin.join("vadgr"), &root.join("current/Vadgr.AppImage"))?;
    let applications = std::env::var_os("XDG_DATA_HOME")
        .map(PathBuf::from)
        .filter(|path| path.is_absolute())
        .unwrap_or(home.join(".local/share"))
        .join("applications");
    std::fs::create_dir_all(&applications).context("creating the desktop application directory")?;
    let executable = desktop_quote(&root.join("current/Vadgr.AppImage"))?;
    let entry = format!(
        "[Desktop Entry]\nType=Application\nVersion=1.5\nName=Vadgr\nComment=Manage this Vadgr machine\nExec={executable} --console\nTerminal=false\nCategories=Utility;\n"
    );
    std::fs::write(applications.join(DESKTOP_FILE), entry)
        .context("registering the Vadgr desktop application")?;
    let config = std::env::var_os("XDG_CONFIG_HOME")
        .map(PathBuf::from)
        .filter(|path| path.is_absolute())
        .unwrap_or(home.join(".config"));
    let autostart = config.join("autostart");
    std::fs::create_dir_all(&autostart).context("creating the XDG autostart directory")?;
    std::fs::write(
        autostart.join(DESKTOP_FILE),
        format!("[Desktop Entry]\nType=Application\nVersion=1.5\nName=Vadgr\nComment=Start the Vadgr machine daemon\nExec={executable} --daemon\nTerminal=false\nX-GNOME-Autostart-enabled=true\n"),
    )
    .context("registering the Vadgr XDG autostart entry")
}

fn unregister_launch_entries(root: &Path) -> Result<()> {
    if let Some(home) = std::env::var_os("HOME")
        .map(PathBuf::from)
        .filter(|path| path.is_absolute())
    {
        remove_if_points_to(&home.join(".local/bin/vadgr"), root)?;
        let data = std::env::var_os("XDG_DATA_HOME")
            .map(PathBuf::from)
            .filter(|path| path.is_absolute())
            .unwrap_or(home.join(".local/share"));
        let desktop = data.join("applications").join(DESKTOP_FILE);
        if desktop.is_file() {
            std::fs::remove_file(desktop).context("removing the Vadgr desktop entry")?;
        }
        let config = std::env::var_os("XDG_CONFIG_HOME")
            .map(PathBuf::from)
            .filter(|path| path.is_absolute())
            .unwrap_or(home.join(".config"));
        let autostart = config.join("autostart").join(DESKTOP_FILE);
        if autostart.is_file() {
            std::fs::remove_file(autostart).context("removing the Vadgr autostart entry")?;
        }
    }
    Ok(())
}

fn replace_symlink(path: &Path, target: &Path) -> Result<()> {
    let temporary = path.with_file_name(format!(".vadgr-{}", uuid::Uuid::new_v4()));
    symlink(target, &temporary).context("creating the Vadgr command link candidate")?;
    super::commit_file(&temporary, path).context("committing the Vadgr command link")
}

fn desktop_quote(path: &Path) -> Result<String> {
    let raw = path
        .to_str()
        .ok_or_else(|| anyhow!("an installed path is not valid UTF-8"))?;
    ensure!(
        !raw.chars().any(char::is_control),
        "an installed path contains a control character"
    );
    Ok(format!(
        "\"{}\"",
        raw.replace('\\', "\\\\")
            .replace('"', "\\\"")
            .replace('`', "\\`")
            .replace('$', "\\$")
    ))
}

fn remove_if_points_to(path: &Path, root: &Path) -> Result<()> {
    if path.symlink_metadata().is_ok() {
        let target =
            std::fs::read_link(path).context("reading the installed Vadgr command link")?;
        ensure!(
            target.starts_with(root),
            "the vadgr command link is not owned by this installation"
        );
        std::fs::remove_file(path).context("removing the Vadgr command link")?;
    }
    Ok(())
}

fn executable(path: &Path) -> Result<()> {
    let mut permissions = std::fs::metadata(path)?.permissions();
    permissions.set_mode(0o755);
    std::fs::set_permissions(path, permissions).context("making the installed AppImage executable")
}
