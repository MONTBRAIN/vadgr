//! Authenticated installed identity and a dedicated read-only launch channel.
//!
//! No owner environment digest/path is an authorization. Installation carries
//! an attested envelope outside the runtime inventory's self-hash domain.

use super::{CuaCommand, PayloadManifest, environment_generation, release};
use anyhow::{Context, Result, ensure};
use serde::Deserialize;
use serde_json::Value;
use std::io::Write;
use std::path::{Component, Path};

const MAX_RECORD: u64 = 4 * 1024 * 1024;
const ENVELOPE: &str = "cua-runtime-authorization.json";

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct Relay {
    path: String,
    size: u64,
    sha256: String,
}

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct Authorization {
    schema: u32,
    release_profile: String,
    cua_version: String,
    generation: String,
    payload_sha256: String,
    installed_inventory_sha256: String,
    broker_final_manifest_sha256: Option<String>,
    helper_closure_authorization_sha256: Option<String>,
    relay: Option<Relay>,
}

fn read(root: &Path, path: &str) -> Result<Vec<u8>> {
    ensure!(
        !path.contains('\\')
            && !path.contains(':')
            && !path.is_empty()
            && Path::new(path)
                .components()
                .all(|c| matches!(c, Component::Normal(_))),
        "unsafe installed authorization path"
    );
    let mut current = root.to_path_buf();
    for part in Path::new(path).components() {
        current.push(part);
        ensure!(
            !std::fs::symlink_metadata(&current)?
                .file_type()
                .is_symlink(),
            "linked installed authorization refused"
        );
    }
    ensure!(
        std::fs::metadata(&current)?.is_file()
            && dunce::canonicalize(&current)?.starts_with(dunce::canonicalize(root)?),
        "installed authorization escapes its root"
    );
    ensure!(
        std::fs::metadata(&current)?.len() <= MAX_RECORD,
        "installed authorization exceeds its limit"
    );
    Ok(std::fs::read(current)?)
}

pub(super) fn installed_authorization(
    root: &Path,
    cua_root: &Path,
    payload: &PayloadManifest,
    profile: &str,
) -> Result<Option<Vec<u8>>> {
    #[cfg(windows)]
    {
        use windows_sys::Win32::System::SystemInformation::{
            GetNativeSystemInfo, PROCESSOR_ARCHITECTURE_AMD64, PROCESSOR_ARCHITECTURE_ARM64,
            SYSTEM_INFO,
        };
        let mut system: SYSTEM_INFO = unsafe { std::mem::zeroed() };
        // SAFETY: Windows fills the complete SDK structure at this valid pointer.
        unsafe { GetNativeSystemInfo(&mut system) };
        let native = match unsafe { system.Anonymous.Anonymous.wProcessorArchitecture } {
            PROCESSOR_ARCHITECTURE_AMD64 => "windows-x86_64",
            PROCESSOR_ARCHITECTURE_ARM64 => "windows-aarch64",
            _ => anyhow::bail!("unsupported native Windows architecture"),
        };
        ensure!(
            profile == native,
            "installed CUA profile cannot use architecture emulation"
        );
    }
    let observed = format!(
        "{}-{}",
        if super::is_wsl() {
            "wsl"
        } else {
            std::env::consts::OS
        },
        std::env::consts::ARCH
    );
    ensure!(
        profile == observed,
        "installed CUA profile differs from the execution environment"
    );
    let raw = read(root, ENVELOPE)?;
    let bundle = read(root, "cua-runtime-authorization.sigstore.json")?;
    crate::install::verify_cua_attestation(&raw, std::str::from_utf8(&bundle)?, false)?;
    let authorization: Authorization = serde_json::from_slice(&raw)?;
    ensure!(
        authorization.schema == 1
            && authorization.release_profile == profile
            && authorization.cua_version == payload.cua_version
            && authorization.generation == environment_generation()
            && authorization.payload_sha256 == release::digest(&read(cua_root, "payload.json")?)
            && Some(authorization.installed_inventory_sha256.as_str())
                == payload.installed_inventory_sha256.as_deref(),
        "installed CUA authorization differs from the validated runtime"
    );
    if !profile.starts_with("windows-") && !profile.starts_with("wsl-") {
        ensure!(
            authorization.broker_final_manifest_sha256.is_none()
                && authorization.helper_closure_authorization_sha256.is_none()
                && authorization.relay.is_none(),
            "native CUA profile cannot authorize Windows helpers"
        );
        return Ok(None);
    }
    let architecture = profile
        .split_once('-')
        .context("invalid compiled CUA profile")?
        .1;
    let directory = format!("managed-helpers/{architecture}");
    let manifest_raw = read(cua_root, &format!("{directory}/broker-final-manifest.json"))?;
    let helper_raw = read(
        cua_root,
        &format!("{directory}/helper-closure-authorization.json"),
    )?;
    let helper_bundle = read(
        cua_root,
        &format!("{directory}/authorization.sigstore.json"),
    )?;
    crate::install::verify_cua_attestation(
        &helper_raw,
        std::str::from_utf8(&helper_bundle)?,
        true,
    )?;
    ensure!(
        Some(release::digest(&manifest_raw)) == authorization.broker_final_manifest_sha256
            && Some(release::digest(&helper_raw))
                == authorization.helper_closure_authorization_sha256,
        "installed helper authorization changed"
    );
    let manifest: Value = serde_json::from_slice(&manifest_raw)?;
    let helper: Value = serde_json::from_slice(&helper_raw)?;
    let relay = authorization
        .relay
        .context("authorized installed relay missing")?;
    // The installed inventory already checked every file (including large
    // relay bytes); this lookup binds that checked file, not a new self-report.
    let inventory: Value = serde_json::from_slice(&read(cua_root, "installed-inventory.json")?)?;
    ensure!(
        inventory["files"][&relay.path]["size"] == relay.size
            && inventory["files"][&relay.path]["sha256"] == relay.sha256
            && helper["schema"] == 1
            && helper["architecture"] == architecture
            && helper["cua_version"] == payload.cua_version
            && helper["final_closure"]["manifest_sha256"] == release::digest(&manifest_raw)
            && helper["final_closure"]["relay_sha256"] == relay.sha256
            && helper["final_closure"]["archive_sha256"] == manifest["archive"]["sha256"]
            && manifest["schema"] == 1
            && manifest["mode"] == "managed-signed"
            && manifest["architecture"] == architecture
            && manifest["cua_version"] == payload.cua_version,
        "installed helper chain differs from its authenticated runtime"
    );
    ensure!(
        Path::new(&relay.path)
            .components()
            .all(|p| matches!(p, Component::Normal(_)))
            && !relay.path.contains(['\\', ':']),
        "unsafe installed relay path"
    );
    let root = dunce::canonicalize(cua_root)?;
    let relay_path = dunce::canonicalize(cua_root.join(&relay.path))?;
    ensure!(
        relay_path.starts_with(&root),
        "relay escapes its verified runtime"
    );
    let envelope = serde_json::json!({"schema":1,"generation":authorization.generation,"profile":profile,
        "inventory_sha256":authorization.installed_inventory_sha256,
        "broker_final_manifest_sha256":release::digest(&manifest_raw),"broker_final_manifest":manifest,
        "helper_closure_authorization_sha256":release::digest(&helper_raw),
        "relay":{"path":relay_path,"size":relay.size,"sha256":relay.sha256},"installed_root":root});
    let mut bytes = serde_json::to_vec(&envelope)?;
    bytes.push(b'\n');
    ensure!(
        bytes.len() as u64 <= MAX_RECORD,
        "managed launch authorization exceeds its limit"
    );
    Ok(Some(bytes))
}

/// The guard lives until the child is spawned, then closes the parent's read
/// endpoint. A background bounded writer cannot deadlock process creation.
pub struct LaunchChannel {
    _reader: std::io::PipeReader,
}

impl CuaCommand {
    pub fn authorize_process(
        &self,
        command: &mut std::process::Command,
    ) -> Result<Option<LaunchChannel>> {
        if let Some(root) = &self.authorization_root {
            let current = super::CuaRuntime::below_install_root(root)?;
            ensure!(
                current.authorization == self.authorization,
                "installed CUA authorization changed before launch; restart the daemon"
            );
        }
        command
            .env_remove("VADGR_CUA_LAUNCH_AUTHORIZATION_FD")
            .env_remove("VADGR_CUA_LAUNCH_AUTHORIZATION_HANDLE");
        let Some(bytes) = self.authorization.clone() else {
            return Ok(None);
        };
        ensure!(
            bytes.len() as u64 <= MAX_RECORD,
            "managed launch authorization exceeds its limit"
        );
        let (reader, mut writer) = std::io::pipe()?;
        #[cfg(windows)]
        {
            use std::os::windows::io::AsRawHandle;
            use windows_sys::Win32::Foundation::{HANDLE_FLAG_INHERIT, SetHandleInformation};
            let handle = reader.as_raw_handle();
            // SAFETY: reader owns a live anonymous pipe handle. Only its read
            // endpoint is inherited; the write endpoint remains parent-only.
            ensure!(
                unsafe { SetHandleInformation(handle, HANDLE_FLAG_INHERIT, HANDLE_FLAG_INHERIT) }
                    != 0,
                "cannot inherit the managed authorization channel"
            );
            command.env(
                "VADGR_CUA_LAUNCH_AUTHORIZATION_HANDLE",
                (handle as usize).to_string(),
            );
        }
        #[cfg(unix)]
        {
            use std::os::fd::AsRawFd;
            use std::os::unix::process::CommandExt;
            let descriptor = reader.as_raw_fd();
            command.env("VADGR_CUA_LAUNCH_AUTHORIZATION_FD", descriptor.to_string());
            // SAFETY: the guard retains this descriptor through spawn. Only
            // async-signal-safe fcntl runs between fork and exec.
            unsafe {
                command.pre_exec(move || {
                    use std::os::fd::BorrowedFd;
                    rustix::io::fcntl_setfd(
                        BorrowedFd::borrow_raw(descriptor),
                        rustix::io::FdFlags::empty(),
                    )?;
                    Ok(())
                });
            }
        }
        std::thread::Builder::new()
            .name("cua-launch-authorization".to_owned())
            .spawn(move || {
                let _ = writer.write_all(&bytes);
            })?;
        Ok(Some(LaunchChannel { _reader: reader }))
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn inherited_environment_is_not_authority() {
        let spec = CuaCommand {
            program: "unused".into(),
            args: vec![],
            authorization: None,
            authorization_root: None,
        };
        let mut process = std::process::Command::new("unused");
        process.env("VADGR_CUA_LAUNCH_AUTHORIZATION_FD", "42");
        assert!(spec.authorize_process(&mut process).unwrap().is_none());
        assert!(process.get_envs().any(|(name, value)| name == "VADGR_CUA_LAUNCH_AUTHORIZATION_FD" && value.is_none()));
    }

    #[test]
    fn arbitrary_owner_file_is_not_an_attestation() {
        assert!(crate::install::verify_cua_attestation(b"{}", "{}", false).is_err());
    }

    #[test]
    fn authorization_pipe_child() {
        if std::env::var_os("VADGR_SYNTHETIC_PIPE_CHILD").is_none() {
            return;
        }
        use std::io::Read;
        #[cfg(windows)]
        let mut reader = {
            use std::os::windows::io::FromRawHandle;
            let value: usize = std::env::var("VADGR_CUA_LAUNCH_AUTHORIZATION_HANDLE")
                .unwrap()
                .parse()
                .unwrap();
            // SAFETY: only the parent test supplies this owned inherited read handle.
            unsafe { std::fs::File::from_raw_handle(value as *mut std::ffi::c_void) }
        };
        #[cfg(unix)]
        let mut reader = {
            use std::os::fd::FromRawFd;
            let value = std::env::var("VADGR_CUA_LAUNCH_AUTHORIZATION_FD")
                .unwrap()
                .parse()
                .unwrap();
            // SAFETY: only the parent test supplies this inherited read descriptor.
            unsafe { std::fs::File::from_raw_fd(value) }
        };
        let mut bytes = Vec::new();
        reader.read_to_end(&mut bytes).unwrap();
        assert_eq!(
            bytes,
            b"synthetic launch record, not signed authorization\n"
        );
    }

    #[test]
    fn read_only_authorization_channel_reaches_only_the_spawned_child() {
        let executable = std::env::current_exe().unwrap();
        let specification = CuaCommand {
            program: executable.clone(),
            args: vec![],
            authorization: Some(b"synthetic launch record, not signed authorization\n".to_vec()),
            authorization_root: None,
        };
        let mut process = std::process::Command::new(executable);
        process
            .args([
                "--exact",
                "cua_payload::managed::tests::authorization_pipe_child",
                "--nocapture",
            ])
            .env("VADGR_SYNTHETIC_PIPE_CHILD", "1")
            .stdout(std::process::Stdio::piped())
            .stderr(std::process::Stdio::piped());
        #[cfg(windows)]
        {
            use std::os::windows::process::CommandExt;
            process.creation_flags(0x08000000);
        }
        let channel = specification.authorize_process(&mut process).unwrap();
        let child = process.spawn().unwrap();
        drop(channel);
        let output = child.wait_with_output().unwrap();
        assert!(
            output.status.success(),
            "inherited authorization pipe child failed"
        );
    }
}
