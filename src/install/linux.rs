//! Native Linux AppImage installation and retained-generation lifecycle.

use super::{InstallReceipt, VerifiedLinuxPackage, record_terms_acceptance};
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
    let verified = VerifiedLinuxPackage::open(vehicle, manifest_path, signature_path, bundle_root)?;
    ensure!(
        verified.terms_version() == Some(terms_version),
        "the accepted terms version differs from the package"
    );
    let terms_file = bundle_root.join("legal/TERMS.txt");
    ensure!(
        bundle_root.is_absolute(),
        "the mounted AppImage root must be absolute"
    );
    ensure!(
        super::sha256_file(&terms_file)? == verified.terms_sha256(),
        "the displayed terms do not match the verified package"
    );

    let state_root = crate::config::Config::from_env()
        .map_err(|error| anyhow!("resolving Vadgr state: {error}"))?
        .state_home
        .ok_or_else(|| anyhow!("the Vadgr state root is unavailable"))?;
    verified.ensure_sequence(&state_root)?;

    let root = install_root()?;
    ensure_generation_modes(&root)?;
    let versions = root.join("versions");
    std::fs::create_dir_all(&versions).context("creating the Vadgr generation directory")?;
    let generation = versions.join(verified.version());
    ensure!(
        !generation.exists(),
        "this Vadgr version is already installed; use Repair"
    );
    let staging = root.join(format!(".stage-{}", uuid::Uuid::new_v4()));
    let previous = read_current(&root)?;
    let mut committed = false;
    let mut daemon_started = false;
    let mut startup_record_before = None;
    progress(InstallPhase::Staging);
    let result = stage_generation(
        &staging,
        vehicle,
        manifest_path,
        signature_path,
        bundle_root,
        &verified,
    )
    .and_then(|_| {
        progress(InstallPhase::Committing);
        std::fs::rename(&staging, &generation).context("committing the Vadgr generation")?;
        committed = true;
        switch_current(&root, verified.version())?;
        progress(InstallPhase::RegisteringLaunch);
        register_launch_entries(&root)?;
        progress(InstallPhase::HealthCheck);
        startup_record_before = Some(read_startup_record(&startup_record_path()?)?);
        start_and_probe(&root)?;
        daemon_started = true;
        record_terms_acceptance(
            terms_version,
            verified.version(),
            &generation.join("legal/TERMS.txt"),
            &generation.join("Vadgr.AppImage"),
        )?;
        verified.accept_sequence(&state_root)?;
        progress(InstallPhase::Complete);
        Ok(())
    });
    if let Err(error) = result {
        if !daemon_started
            && let Some(before) = startup_record_before
            && let Err(cleanup) = startup_record_path()
                .and_then(|path| verify_failed_start_cleanup(&path, before.as_ref()))
        {
            return Err(error).context(format!(
                "installation rollback was incomplete; the package was retained: {cleanup:#}"
            ));
        }
        let rollback = rollback_failed_installation(
            &root,
            previous.as_deref(),
            &staging,
            &generation,
            committed,
            daemon_started,
        );
        return match rollback {
            Ok(()) => Err(error),
            Err(rollback) => Err(error).context(format!(
                "installation rollback was incomplete: {rollback:#}"
            )),
        };
    }
    Ok(generation)
}

fn startup_record_path() -> Result<PathBuf> {
    let home = std::env::var_os("VADGR_HOME")
        .map(PathBuf::from)
        .or_else(|| std::env::var_os("HOME").map(|home| PathBuf::from(home).join(".vadgr")))
        .ok_or_else(|| anyhow!("the daemon service directory is unavailable"))?;
    ensure!(
        home.is_absolute(),
        "the daemon service directory is not absolute"
    );
    Ok(home.join("pids/api.pid"))
}

#[derive(PartialEq, Eq)]
struct StartupRecord {
    identity: (u64, u64, i64, i64),
    bytes: Vec<u8>,
}

fn read_startup_record(path: &Path) -> Result<Option<StartupRecord>> {
    use std::io::Read;
    use std::os::unix::fs::{MetadataExt, OpenOptionsExt};
    let file = match std::fs::OpenOptions::new()
        .read(true)
        .custom_flags((rustix::fs::OFlags::NONBLOCK | rustix::fs::OFlags::NOFOLLOW).bits() as i32)
        .open(path)
    {
        Ok(file) => file,
        Err(error) if error.kind() == std::io::ErrorKind::NotFound => return Ok(None),
        Err(error) => return Err(error).context("reading daemon startup cleanup state"),
    };
    ensure!(
        file.metadata()?.is_file(),
        "daemon startup cleanup state is not a regular file"
    );
    let identity = |metadata: std::fs::Metadata| {
        (
            metadata.dev(),
            metadata.ino(),
            metadata.ctime(),
            metadata.ctime_nsec(),
        )
    };
    let before = identity(file.metadata()?);
    let mut bytes = Vec::new();
    (&file).take(4097).read_to_end(&mut bytes)?;
    ensure!(
        bytes.len() <= 4096,
        "daemon startup cleanup state is too large"
    );
    ensure!(
        identity(file.metadata()?) == before && identity(std::fs::metadata(path)?) == before,
        "daemon startup cleanup state changed while reading"
    );
    Ok(Some(StartupRecord {
        identity: before,
        bytes,
    }))
}

fn verify_failed_start_cleanup(path: &Path, before: Option<&StartupRecord>) -> Result<()> {
    let after = read_startup_record(path)?;
    // A failed packaged start retains its newly reserved record unless the
    // complete owned process tree is proved gone. Never delete those files.
    ensure!(
        after.is_none() || after.as_ref() == before,
        "the failed daemon's process-tree cleanup is not confirmed"
    );
    Ok(())
}

fn rollback_failed_installation(
    root: &Path,
    previous: Option<&str>,
    staging: &Path,
    generation: &Path,
    committed: bool,
    daemon_started: bool,
) -> Result<()> {
    rollback_failed_installation_with(
        root,
        previous,
        staging,
        generation,
        committed,
        daemon_started,
        |previous| {
            if previous.is_some() {
                register_launch_entries(root)?;
                start_and_probe(root).context("restoring the previous daemon")
            } else {
                unregister_launch_entries(root)
            }
        },
    )
}

fn rollback_failed_installation_with(
    root: &Path,
    previous: Option<&str>,
    staging: &Path,
    generation: &Path,
    committed: bool,
    daemon_started: bool,
    restore_launch: impl FnOnce(Option<&str>) -> Result<()>,
) -> Result<()> {
    // A failed start owns and reaps its child. If a later transaction step
    // fails, stop the successfully started generation before removing it.
    if daemon_started {
        let status = std::process::Command::new(generation.join("Vadgr.AppImage"))
            .arg("stop")
            .status()
            .context("stopping the failed installation")?;
        ensure!(status.success(), "the failed installation could not stop");
    }
    if committed {
        restore_current(root, previous)?;
        restore_launch(previous)?;
    }
    let owned_paths = [Some(staging), committed.then_some(generation)];
    for path in owned_paths.into_iter().flatten() {
        if path.exists() {
            std::fs::remove_dir_all(path).context("removing the failed package generation")?;
        }
    }
    Ok(())
}

/// The AppImage runtime gives this process a descriptor on its own mount
/// without close-on-exec. A child that inherits it, such as the installed
/// daemon started by `start_and_probe`, keeps that mount alive after this
/// process exits. Mark every inherited descriptor close-on-exec so that only
/// this process holds them.
pub fn keep_inherited_descriptors_from_children() -> Result<()> {
    use rustix::io::{FdFlags, fcntl_getfd, fcntl_setfd};
    for entry in std::fs::read_dir("/proc/self/fd").context("listing open descriptors")? {
        let Ok(fd) = entry?.file_name().to_string_lossy().parse::<i32>() else {
            continue;
        };
        if fd <= 2 {
            continue;
        }
        // SAFETY: the descriptor is borrowed only for these two fcntl calls.
        // One closed since the listing (including the listing's own) fails
        // with EBADF, which is ignored; a reused number only gains
        // close-on-exec, which every descriptor here should have.
        let fd = unsafe { std::os::fd::BorrowedFd::borrow_raw(fd) };
        if let Ok(flags) = fcntl_getfd(fd) {
            let _ = fcntl_setfd(fd, flags | FdFlags::CLOEXEC);
        }
    }
    Ok(())
}

fn start_and_probe(root: &Path) -> Result<()> {
    use std::io::Read;
    use std::process::Stdio;
    let current = root.join("current/Vadgr.AppImage");
    ensure!(current.is_file(), "the active Vadgr AppImage is missing");
    keep_inherited_descriptors_from_children()?;
    let mut child = std::process::Command::new(current)
        .arg("start")
        .stdout(Stdio::null())
        .stderr(Stdio::piped())
        .env("NO_COLOR", "1")
        .spawn()
        .context("starting the installed Vadgr daemon")?;
    let mut stderr = child.stderr.take().expect("startup stderr is piped");
    let mut diagnostic = Vec::new();
    let read_result = stderr
        .by_ref()
        .take(8192)
        .read_to_end(&mut diagnostic)
        .and_then(|_| std::io::copy(&mut stderr, &mut std::io::sink()));
    let status = child
        .wait()
        .context("waiting for the installed Vadgr daemon")?;
    if !status.success() && read_result.is_ok() && startup_cleanup_required(&diagnostic) {
        anyhow::bail!(
            "Startup records were retained because descendant cleanup is unproved. Verified cleanup is required; Repair alone does not prove it."
        );
    }
    ensure!(status.success(), "the installed Vadgr daemon is not ready");
    Ok(())
}

fn startup_cleanup_required(stderr: &[u8]) -> bool {
    const REASONS: &[&str] = &[
        "Startup records were retained because descendant cleanup is unproved. Verified cleanup is required; Repair alone does not prove it.",
        "The recorded daemon could not be verified. Startup records were retained; verified cleanup is required.",
        "Startup records could not be verified. Verified cleanup is required; Repair alone does not prove it.",
    ];
    // Forward only fixed product messages, never subprocess diagnostics or a
    // truncated line. Drain the rest without retaining or displaying it.
    String::from_utf8_lossy(stderr)
        .split_inclusive('\n')
        .filter(|line| line.ends_with('\n') || stderr.len() < 8192)
        .any(|line| REASONS.contains(&line.trim().strip_prefix("Error: ").unwrap_or(line.trim())))
}

pub fn repair(receipt: &InstallReceipt) -> Result<()> {
    ensure!(
        receipt.package_kind == "appimage",
        "this is not a Linux AppImage installation"
    );
    let verified = VerifiedLinuxPackage::open_retained(receipt)?;
    let cached = receipt
        .install_root
        .join("cache")
        .join(verified.artifact_name());
    let active = receipt.install_root.join("Vadgr.AppImage");
    if verified.verify_vehicle_at(&active).is_err() {
        let temporary = receipt
            .install_root
            .join(format!(".Vadgr.AppImage.{}.tmp", uuid::Uuid::new_v4()));
        verified.copy_vehicle_to(&cached, &temporary)?;
        executable(&temporary)?;
        super::commit_file(&temporary, &active).context("committing the repaired AppImage")?;
    }
    let root = install_root()?;
    register_launch_entries(&root)?;
    start_and_probe(&root)
}

pub fn rollback_appimage() -> Result<String> {
    let root = install_root()?;
    ensure_generation_modes(&root)?;
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
    ensure!(
        !cfg!(feature = "linux-unsigned-qualification"),
        "unsigned development builds cannot activate a different source generation"
    );
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
    let receipt = generation_receipt(generation)?;
    let verified = VerifiedLinuxPackage::open_retained(&receipt)?;
    let cached = generation.join("cache").join(verified.artifact_name());
    let active = generation.join("Vadgr.AppImage");
    if verified.verify_vehicle_at(&active).is_err() {
        let temporary = generation.join(format!(".Vadgr.AppImage.{}.tmp", uuid::Uuid::new_v4()));
        verified.copy_vehicle_to(&cached, &temporary)?;
        executable(&temporary)?;
        super::commit_file(&temporary, &active)
            .context("committing the restored retained AppImage")?;
    }
    Ok(())
}

pub fn rollback_available() -> Result<bool> {
    if cfg!(feature = "linux-unsigned-qualification") {
        return Ok(false);
    }
    let root = install_root()?;
    ensure_generation_modes(&root)?;
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
    ensure_generation_modes(&root)?;
    uninstall_with(
        &root,
        purge,
        unregister_launch_entries,
        super::purge_owner_state,
    )
}

fn uninstall_with(
    root: &Path,
    purge: bool,
    unregister: impl FnOnce(&Path) -> Result<()>,
    purge_state: impl FnOnce() -> Result<()>,
) -> Result<()> {
    let active = root.join("current/Vadgr.AppImage");
    ensure!(
        active.is_file(),
        "The installed Vadgr app is missing. Nothing was uninstalled. Choose Repair to restore it, then retry Uninstall."
    );
    let status = std::process::Command::new(&active)
        .arg("stop")
        .status()
        .map_err(|error| match error.kind() {
            std::io::ErrorKind::PermissionDenied => anyhow!(
                "Permission to run the installed Vadgr app was denied. Nothing was uninstalled. Restore permission to run the app, then retry Uninstall."
            ),
            _ => anyhow!(
                "The installed Vadgr stop command could not run. Nothing was uninstalled. Check that the installed app can run, then retry Uninstall."
            ),
        })?;
    ensure!(
        status.success(),
        "Vadgr could not confirm that its daemon stopped. Nothing was uninstalled. Run 'vadgr status' and resolve any reported cleanup requirement before retrying Uninstall."
    );
    unregister(root)?;
    if root.exists() {
        std::fs::remove_dir_all(root).context("removing installed Vadgr package files")?;
    }
    if purge {
        purge_state()?;
    }
    Ok(())
}

fn stage_generation(
    staging: &Path,
    vehicle: &Path,
    manifest_path: &Path,
    signature_path: &Path,
    bundle_root: &Path,
    verified: &VerifiedLinuxPackage,
) -> Result<()> {
    std::fs::create_dir_all(staging.join("cache"))
        .context("creating the staged Vadgr generation")?;
    let active = staging.join("Vadgr.AppImage");
    verified.copy_vehicle_to(vehicle, &active)?;
    executable(&active)?;
    verified.copy_vehicle_to(
        vehicle,
        &staging.join("cache").join(verified.artifact_name()),
    )?;
    verified.stage_metadata(staging, manifest_path, signature_path)?;
    copy_tree(&bundle_root.join("legal"), &staging.join("legal"))
        .context("staging the offline legal bundle")?;
    copy_tree(&bundle_root.join("sbom"), &staging.join("sbom"))
        .context("staging the offline software bill of materials")?;
    verified.verify_staged_metadata(staging)?;
    let receipt = verified.receipt();
    std::fs::write(
        staging.join("install-receipt.json"),
        serde_json::to_vec_pretty(&receipt)?,
    )
    .context("writing the staged install receipt")?;
    Ok(())
}

fn generation_receipt(generation: &Path) -> Result<InstallReceipt> {
    let mut receipt: InstallReceipt =
        serde_json::from_slice(&std::fs::read(generation.join("install-receipt.json"))?)?;
    ensure!(
        receipt.schema == 1,
        "the retained install receipt schema is unsupported"
    );
    receipt.install_root = generation.to_owned();
    super::linux_package::ensure_receipt_mode(&receipt)?;
    Ok(receipt)
}

fn ensure_generation_modes(root: &Path) -> Result<()> {
    let versions = root.join("versions");
    if !versions.try_exists()? {
        return Ok(());
    }
    ensure!(
        !versions.symlink_metadata()?.file_type().is_symlink(),
        "the generation directory is a link"
    );
    for entry in std::fs::read_dir(versions)? {
        let entry = entry?;
        ensure!(
            entry.file_type()?.is_dir(),
            "the generation entry is not an owned directory"
        );
        generation_receipt(&entry.path())?;
    }
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

#[cfg(all(test, feature = "linux-unsigned-qualification"))]
mod development_lifecycle_tests {
    #[test]
    fn unsigned_builds_do_not_offer_cross_source_rollback() {
        assert!(!super::rollback_available().unwrap());
    }
}

#[cfg(test)]
mod inherited_descriptor_tests {
    use super::keep_inherited_descriptors_from_children;
    use std::os::fd::AsRawFd;

    /// Seen for real: after the installer closed, the installed daemon still
    /// held the installer's AppImage mount through the runtime's descriptor.
    #[test]
    fn children_do_not_inherit_descriptors_this_process_was_given() {
        let file = std::fs::File::open("/proc/self/stat").unwrap();
        // The AppImage runtime passes its descriptor without close-on-exec.
        rustix::io::fcntl_setfd(&file, rustix::io::FdFlags::empty()).unwrap();
        let fd = file.as_raw_fd();
        keep_inherited_descriptors_from_children().unwrap();
        let status = std::process::Command::new("/bin/sh")
            .arg("-c")
            .arg(format!("[ -e /proc/self/fd/{fd} ]"))
            .status()
            .unwrap();
        assert!(!status.success(), "descriptor {fd} reached the child");
    }
}

#[cfg(test)]
mod failed_install_tests {
    use super::*;
    use std::cell::Cell;

    #[test]
    fn uninstall_refuses_failed_or_unavailable_stop_before_any_mutation() {
        use std::os::unix::fs::PermissionsExt;
        for (failure, expected_message) in [
            (
                "not-executable",
                "Permission to run the installed Vadgr app was denied. Nothing was uninstalled. Restore permission to run the app, then retry Uninstall.",
            ),
            (
                "nonzero",
                "Vadgr could not confirm that its daemon stopped. Nothing was uninstalled. Run 'vadgr status' and resolve any reported cleanup requirement before retrying Uninstall.",
            ),
            (
                "missing",
                "The installed Vadgr app is missing. Nothing was uninstalled. Choose Repair to restore it, then retry Uninstall.",
            ),
            (
                "missing-interpreter",
                "The installed Vadgr stop command could not run. Nothing was uninstalled. Check that the installed app can run, then retry Uninstall.",
            ),
        ] {
            for purge in [false, true] {
                let temp = tempfile::tempdir().unwrap();
                let root = temp.path().join("package");
                let current = root.join("current");
                std::fs::create_dir_all(&current).unwrap();
                let active = current.join("Vadgr.AppImage");
                let script: &[u8] = if failure == "missing-interpreter" {
                    b"#!/nonexistent/private-uninstall-interpreter\n"
                } else {
                    b"#!/bin/sh\n[ \"$1\" = stop ] || exit 97\nexit 9\n"
                };
                if failure != "missing" {
                    std::fs::write(&active, script).unwrap();
                    let mode = if failure == "not-executable" {
                        0o644
                    } else {
                        0o755
                    };
                    std::fs::set_permissions(&active, std::fs::Permissions::from_mode(mode))
                        .unwrap();
                }
                let registration = temp.path().join("registration");
                let state = temp.path().join("owner-state");
                std::fs::write(&registration, b"registered").unwrap();
                std::fs::write(&state, b"preserved").unwrap();
                let result = uninstall_with(
                    &root,
                    purge,
                    |_| {
                        std::fs::remove_file(&registration)?;
                        Ok(())
                    },
                    || {
                        std::fs::remove_file(&state)?;
                        Ok(())
                    },
                );
                assert!(
                    result.is_err(),
                    "{failure}, purge={purge}: uninstall must report failure"
                );
                let error = result.unwrap_err();
                assert_eq!(error.to_string(), expected_message);
                assert_eq!(format!("{error:#}"), expected_message);
                assert_eq!(
                    error.chain().count(),
                    1,
                    "raw launch errors must stay private"
                );
                assert!(root.is_dir(), "a refused stop must retain the package");
                assert_eq!(std::fs::read(&registration).unwrap(), b"registered");
                assert_eq!(std::fs::read(&state).unwrap(), b"preserved");
                if failure != "missing" {
                    assert_eq!(std::fs::read(&active).unwrap(), script);
                }
            }
        }
    }

    #[test]
    fn uninstall_removes_package_and_optional_owner_state_only_after_confirmed_stop() {
        for purge in [false, true] {
            let temp = tempfile::tempdir().unwrap();
            let root = temp.path().join("package");
            let current = root.join("current");
            std::fs::create_dir_all(&current).unwrap();
            let active = current.join("Vadgr.AppImage");
            std::fs::write(&active, "#!/bin/sh\n[ \"$1\" = stop ] || exit 97\nprintf stopped > \"$0.stopped\" || exit 98\nexit 0\n").unwrap();
            executable(&active).unwrap();
            let registration = temp.path().join("registration");
            let state = temp.path().join("owner-state");
            std::fs::write(&registration, b"registered").unwrap();
            std::fs::write(&state, b"preserved").unwrap();
            let unregistered = Cell::new(false);
            let purged = Cell::new(false);
            uninstall_with(
                &root,
                purge,
                |actual| {
                    assert_eq!(actual, root);
                    assert!(active.is_file());
                    assert_eq!(
                        std::fs::read(current.join("Vadgr.AppImage.stopped"))?,
                        b"stopped"
                    );
                    std::fs::remove_file(&registration)?;
                    unregistered.set(true);
                    Ok(())
                },
                || {
                    assert!(unregistered.get());
                    assert!(
                        !root.exists(),
                        "purge must follow package removal and confirmed stop"
                    );
                    std::fs::remove_file(&state)?;
                    purged.set(true);
                    Ok(())
                },
            )
            .unwrap();
            assert!(unregistered.get());
            assert!(!root.exists());
            assert!(!registration.exists());
            assert_eq!(purged.get(), purge);
            assert_eq!(state.exists(), !purge);
            if !purge {
                assert_eq!(std::fs::read(state).unwrap(), b"preserved");
            }
        }
    }

    #[test]
    fn failed_install_retains_package_when_startup_cleanup_is_unproved() {
        let temp = tempfile::tempdir().unwrap();
        let record = temp.path().join("api.pid");
        assert!(verify_failed_start_cleanup(&record, None).is_ok());
        std::fs::write(&record, "older").unwrap();
        let older = read_startup_record(&record).unwrap();
        for bytes in [b"".as_slice(), b"1234".as_slice()] {
            std::fs::write(&record, bytes).unwrap();
            assert!(verify_failed_start_cleanup(&record, None).is_err());
            assert!(verify_failed_start_cleanup(&record, older.as_ref()).is_err());
            assert_eq!(std::fs::read(&record).unwrap(), bytes);
        }
        let same = read_startup_record(&record).unwrap();
        assert!(verify_failed_start_cleanup(&record, same.as_ref()).is_ok());
        std::fs::rename(&record, temp.path().join("previous-record")).unwrap();
        assert!(verify_failed_start_cleanup(&record, older.as_ref()).is_ok());
        std::fs::write(&record, "1234").unwrap();
        assert!(verify_failed_start_cleanup(&record, same.as_ref()).is_err());
        std::fs::remove_file(&record).unwrap();
        std::fs::create_dir(&record).unwrap();
        assert!(verify_failed_start_cleanup(&record, None).is_err());
        std::fs::remove_dir(&record).unwrap();
        symlink(temp.path().join("previous-record"), &record).unwrap();
        assert!(read_startup_record(&record).is_err());
    }

    #[test]
    fn failed_install_start_cannot_be_masked_by_a_successful_health_probe() {
        let temp = tempfile::tempdir().unwrap();
        let current = temp.path().join("current");
        std::fs::create_dir(&current).unwrap();
        let command = current.join("Vadgr.AppImage");
        std::fs::write(
            &command,
            "#!/bin/sh\ncase \"$1\" in start) exit 1;; health) exit 0;; *) exit 2;; esac\n",
        )
        .unwrap();
        executable(&command).unwrap();
        assert!(start_and_probe(temp.path()).is_err());
    }

    #[test]
    fn repair_start_preserves_the_verified_cleanup_refusal() {
        let temp = tempfile::tempdir().unwrap();
        let current = temp.path().join("current");
        std::fs::create_dir(&current).unwrap();
        let command = current.join("Vadgr.AppImage");
        std::fs::write(&command, "#!/bin/sh\nprintf '%s\\n' 'Startup records were retained because descendant cleanup is unproved. Verified cleanup is required; Repair alone does not prove it.' >&2\nexit 1\n").unwrap();
        executable(&command).unwrap();
        let error = start_and_probe(temp.path()).unwrap_err().to_string();
        assert!(error.contains("descendant cleanup is unproved"));
        assert!(error.contains("Verified cleanup is required"));
        assert!(error.contains("Repair alone does not prove it"));
        assert!(command.is_file());
    }

    #[test]
    fn repair_start_never_reflects_arbitrary_child_diagnostics() {
        let temp = tempfile::tempdir().unwrap();
        let current = temp.path().join("current");
        std::fs::create_dir(&current).unwrap();
        let command = current.join("Vadgr.AppImage");
        std::fs::write(&command, "#!/bin/sh\nprintf 'private-test-secret /private/owner/path \\033[31m\\n' >&2\ni=0\nwhile [ $i -lt 2000 ]; do printf 'oversized diagnostic\\n' >&2; i=$((i+1)); done\nexit 1\n").unwrap();
        executable(&command).unwrap();
        assert_eq!(
            start_and_probe(temp.path()).unwrap_err().to_string(),
            "the installed Vadgr daemon is not ready"
        );
        assert!(!startup_cleanup_required(b"Error: Startup records could not be verified. Verified cleanup is required; Repair alone does not prove it. /private/path\n"));
        assert!(!startup_cleanup_required(b"\x1b[31mStartup records could not be verified. Verified cleanup is required; Repair alone does not prove it.\n"));
    }

    #[test]
    fn uncommitted_attempt_does_not_remove_an_unowned_generation() {
        let temp = tempfile::tempdir().unwrap();
        let root = temp.path();
        let generation = root.join("versions/new");
        let staging = root.join("stage");
        std::fs::create_dir_all(&generation).unwrap();
        std::fs::create_dir(&staging).unwrap();
        rollback_failed_installation_with(root, None, &staging, &generation, false, false, |_| {
            panic!("an uncommitted attempt must not change registration")
        })
        .unwrap();
        assert!(generation.exists());
        assert!(!staging.exists());
    }

    #[test]
    fn clean_install_failure_removes_launch_registration_and_preserves_state() {
        let temp = tempfile::tempdir().unwrap();
        let root = temp.path();
        let generation = root.join("versions/new");
        let staging = root.join("stage");
        std::fs::create_dir_all(&generation).unwrap();
        std::fs::create_dir(&staging).unwrap();
        std::fs::write(root.join("owner-state"), "preserve").unwrap();
        switch_current(root, "new").unwrap();
        let unregistered = Cell::new(false);
        rollback_failed_installation_with(
            root,
            None,
            &staging,
            &generation,
            true,
            false,
            |previous| {
                assert!(previous.is_none());
                assert!(!root.join("current").is_symlink());
                unregistered.set(true);
                Ok(())
            },
        )
        .unwrap();
        assert!(unregistered.get());
        assert!(!generation.exists() && !staging.exists());
        assert_eq!(
            std::fs::read_to_string(root.join("owner-state")).unwrap(),
            "preserve"
        );
    }

    #[test]
    fn failed_stop_keeps_generation_and_selection_intact() {
        let temp = tempfile::tempdir().unwrap();
        let root = temp.path();
        let generation = root.join("versions/new");
        let staging = root.join("stage");
        std::fs::create_dir_all(&generation).unwrap();
        let command = generation.join("Vadgr.AppImage");
        std::fs::write(&command, "#!/bin/sh\nexit 1\n").unwrap();
        executable(&command).unwrap();
        switch_current(root, "new").unwrap();
        let result = rollback_failed_installation_with(
            root,
            None,
            &staging,
            &generation,
            true,
            true,
            |_| panic!("must not alter registration while the daemon can remain alive"),
        );
        assert!(result.is_err());
        assert!(generation.exists());
        assert_eq!(read_current(root).unwrap().as_deref(), Some("new"));
    }

    #[test]
    fn previous_generation_is_restored_before_failed_generation_removal() {
        let temp = tempfile::tempdir().unwrap();
        let root = temp.path();
        let generation = root.join("versions/new");
        let previous = root.join("versions/old");
        let staging = root.join("stage");
        std::fs::create_dir_all(&generation).unwrap();
        std::fs::create_dir_all(&previous).unwrap();
        switch_current(root, "new").unwrap();
        rollback_failed_installation_with(
            root,
            Some("old"),
            &staging,
            &generation,
            true,
            false,
            |selected| {
                assert_eq!(selected, Some("old"));
                assert_eq!(read_current(root)?.as_deref(), selected);
                assert!(generation.exists());
                Ok(())
            },
        )
        .unwrap();
        assert!(previous.exists() && !generation.exists());
    }
}
