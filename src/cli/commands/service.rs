//! `vadgr start`, `stop`, `restart`, `status`, `logs` and `update`.
//!
//! **Until the `0.4.9` cutover, `start` launches the still-shipped daemon rather
//! than the one in this crate.** The default flips once, in a release that
//! contains nothing else, so a defect found afterwards has one candidate cause.
//! Everything here that computes an address, writes a pid file or waits for
//! health is therefore supervising a separate process, on purpose.

use std::io::{BufRead, Read, Seek, SeekFrom, Write};
use std::net::{TcpListener, TcpStream, ToSocketAddrs};
use std::path::{Path, PathBuf};
use std::process::{Child, Command, Stdio};
use std::time::Duration;

use crate::client::Client;
use crate::error::CliError;
use crate::output;

#[cfg(unix)]
fn create_service_home(path: &Path) -> std::io::Result<()> {
    use std::os::unix::fs::{DirBuilderExt, PermissionsExt};

    std::fs::DirBuilder::new()
        .recursive(true)
        .mode(0o700)
        .create(path)?;
    std::fs::set_permissions(path, std::fs::Permissions::from_mode(0o700))
}

#[cfg(not(unix))]
fn create_service_home(path: &Path) -> std::io::Result<()> {
    std::fs::create_dir_all(path)
}

#[cfg(unix)]
fn open_service_log(path: &Path) -> std::io::Result<std::fs::File> {
    use std::os::unix::fs::{OpenOptionsExt, PermissionsExt};

    let file = std::fs::OpenOptions::new()
        .write(true)
        .create(true)
        .truncate(true)
        .mode(0o600)
        .open(path)?;
    file.set_permissions(std::fs::Permissions::from_mode(0o600))?;
    Ok(file)
}

#[cfg(not(unix))]
fn open_service_log(path: &Path) -> std::io::Result<std::fs::File> {
    std::fs::File::create(path)
}

/// How long the CLI waits for the daemon to answer health after spawning it.
const API_STARTUP_TIMEOUT: Duration = Duration::from_secs(30);

fn packaged_startup() -> Result<bool, CliError> {
    #[cfg(target_os = "linux")]
    {
        let executable = std::env::current_exe().ok();
        let appdir = std::env::var_os("APPDIR").map(PathBuf::from);
        let installed = std::env::var_os("VADGR_INSTALL_ROOT").map(PathBuf::from);
        let vehicle = std::env::var_os("APPIMAGE").map(PathBuf::from);
        if vadgr_daemon::platform::machine_platform() != "linux" {
            return Ok(false);
        }
        let intent = appdir.is_some() || installed.is_some() || vehicle.is_some();
        classify_installed_startup(
            intent,
            installed_startup_layout(
                cfg!(feature = "linux-unsigned-qualification"),
                vadgr_daemon::platform::machine_platform(),
                executable.as_deref(),
                appdir.as_deref(),
                installed.as_deref(),
                vehicle.as_deref(),
            ),
        )
    }
    #[cfg(not(target_os = "linux"))]
    Ok(false)
}

#[cfg(any(test, target_os = "linux"))]
fn classify_installed_startup(intent: bool, valid_layout: bool) -> Result<bool, CliError> {
    if intent && !valid_layout {
        return Err(CliError::Failed("The installed package metadata is missing or does not match this build. Repair the installation before starting Vadgr.".to_owned()));
    }
    Ok(intent)
}

#[cfg(any(test, target_os = "linux"))]
fn bounded_process_record(path: &Path, limit: u64) -> Option<Vec<u8>> {
    let mut bytes = Vec::new();
    std::fs::File::open(path)
        .ok()?
        .take(limit + 1)
        .read_to_end(&mut bytes)
        .ok()?;
    (bytes.len() as u64 <= limit).then_some(bytes)
}

#[cfg(target_os = "linux")]
fn stable_executable_hash(path: &Path) -> Option<String> {
    use sha2::{Digest, Sha256};
    use std::os::unix::fs::MetadataExt;
    let mut file = std::fs::File::open(path).ok()?;
    let stamp = |metadata: std::fs::Metadata| {
        (
            metadata.dev(),
            metadata.ino(),
            metadata.len(),
            metadata.mtime(),
            metadata.mtime_nsec(),
            metadata.ctime(),
            metadata.ctime_nsec(),
        )
    };
    let before = file.metadata().ok()?;
    if !before.is_file() || before.len() == 0 || before.len() > 256 * 1024 * 1024 {
        return None;
    }
    let before = stamp(before);
    let deadline = std::time::Instant::now() + Duration::from_secs(5);
    let mut hash = Sha256::new();
    let mut buffer = [0; 64 * 1024];
    let mut bytes = 0;
    loop {
        if std::time::Instant::now() >= deadline {
            return None;
        }
        let count = file.read(&mut buffer).ok()?;
        if count == 0 {
            break;
        }
        bytes += count as u64;
        if bytes > before.2 {
            return None;
        }
        hash.update(&buffer[..count]);
    }
    (bytes == before.2
        && stamp(file.metadata().ok()?) == before
        && stamp(std::fs::metadata(path).ok()?) == before)
        .then(|| {
            hash.finalize()
                .iter()
                .map(|byte| format!("{byte:02x}"))
                .collect()
        })
}

#[cfg(target_os = "linux")]
fn same_generation_process(
    process: &Path,
    executable: &Path,
    installed: &Path,
    vehicle: &Path,
) -> Option<(String, String)> {
    use std::os::unix::{ffi::OsStrExt, fs::MetadataExt};
    if std::fs::metadata(process).ok()?.uid() != std::fs::metadata("/proc/self").ok()?.uid() {
        return None;
    }
    let identity = || {
        let bytes = bounded_process_record(&process.join("stat"), 4096)?;
        let stat = std::str::from_utf8(&bytes).ok()?;
        Some(
            stat.rsplit_once(") ")?
                .1
                .split_whitespace()
                .nth(19)?
                .to_owned(),
        )
    };
    let before = identity()?;
    let argv = bounded_process_record(&process.join("cmdline"), 64 * 1024)?;
    if argv.split(|byte| *byte == 0).nth(1) != Some(b"serve".as_slice()) {
        return None;
    }
    let environment = bounded_process_record(&process.join("environ"), 1024 * 1024)?;
    for (name, expected) in [
        (b"VADGR_INSTALL_ROOT=".as_slice(), installed),
        (b"APPIMAGE=".as_slice(), vehicle),
    ] {
        let values: Vec<_> = environment
            .split(|byte| *byte == 0)
            .filter_map(|value| value.strip_prefix(name))
            .collect();
        if values.as_slice() != [expected.as_os_str().as_bytes()] {
            return None;
        }
    }
    let expected = stable_executable_hash(executable)?;
    let observed = stable_executable_hash(&process.join("exe"))?;
    (observed == expected && identity()? == before).then_some((before, observed))
}

#[cfg(target_os = "linux")]
fn process_state_matches(
    environment: &[u8],
    expected: &[(String, Option<Vec<u8>>)],
    port: u16,
) -> bool {
    let value_matches = |name: &str, expected: Option<&[u8]>| {
        let prefix = format!("{name}=");
        let values: Vec<_> = environment
            .split(|byte| *byte == 0)
            .filter_map(|value| value.strip_prefix(prefix.as_bytes()))
            .collect();
        match expected {
            Some(value) => values.as_slice() == [value],
            None => values.is_empty(),
        }
    };
    expected
        .iter()
        .all(|(name, value)| value_matches(name, value.as_deref()))
        && value_matches("VADGR_PORT", Some(port.to_string().as_bytes()))
}

#[cfg(target_os = "linux")]
fn owns_api_listener(process: &Path, port: u16) -> bool {
    let Some(bytes) = bounded_process_record(&process.join("net/tcp"), 1024 * 1024) else {
        return false;
    };
    let Ok(table) = std::str::from_utf8(&bytes) else {
        return false;
    };
    let sockets: Vec<_> = table
        .lines()
        .skip(1)
        .filter_map(|line| {
            let fields: Vec<_> = line.split_whitespace().collect();
            let (address, actual_port) = fields.get(1)?.split_once(':')?;
            (fields.get(3) == Some(&"0A")
                && matches!(address, "0100007F" | "00000000")
                && u16::from_str_radix(actual_port, 16).ok() == Some(port))
            .then(|| fields.get(9).map(|inode| format!("socket:[{inode}]")))
            .flatten()
        })
        .collect();
    if sockets.is_empty() {
        return false;
    }
    let (Ok(ours), Ok(theirs)) = (
        std::fs::read_link("/proc/self/ns/net"),
        std::fs::read_link(process.join("ns/net")),
    ) else {
        return false;
    };
    if ours != theirs {
        return false;
    }
    let Ok(entries) = std::fs::read_dir(process.join("fd")) else {
        return false;
    };
    entries
        .flatten()
        .filter_map(|entry| std::fs::read_link(entry.path()).ok())
        .any(|link| {
            sockets
                .iter()
                .any(|socket| link.as_os_str() == std::ffi::OsStr::new(socket))
        })
}

#[cfg(target_os = "linux")]
fn packaged_binding(pid: u32, port: u16, listener: bool) -> Option<(String, String)> {
    use std::os::unix::ffi::OsStrExt;
    let (Some(executable), Some(installed), Some(vehicle)) = (
        std::env::current_exe().ok(),
        std::env::var_os("VADGR_INSTALL_ROOT").map(PathBuf::from),
        std::env::var_os("APPIMAGE").map(PathBuf::from),
    ) else {
        return None;
    };
    let process = PathBuf::from(format!("/proc/{pid}"));
    let expected_state: Vec<_> = [
        "HOME",
        "VADGR_HOME",
        "XDG_STATE_HOME",
        "VADGR_STATE_HOME",
        "VADGR_DB",
        "VADGR_RUNS_DIR",
        "XDG_CONFIG_HOME",
        "VADGR_CONFIG_HOME",
        "XDG_DATA_HOME",
    ]
    .into_iter()
    .map(|name| {
        (
            name.to_owned(),
            std::env::var_os(name).map(|value| value.as_os_str().as_bytes().to_vec()),
        )
    })
    .collect();
    let binding = || {
        if std::fs::read_to_string(pid_dir().join("api.pid"))
            .ok()?
            .trim()
            .parse::<u32>()
            .ok()?
            != pid
            || std::fs::read_to_string(pid_dir().join("api.port"))
                .ok()?
                .trim()
                .parse::<u16>()
                .ok()?
                != port
            || !process_state_matches(
                &bounded_process_record(&process.join("environ"), 1024 * 1024)?,
                &expected_state,
                port,
            )
            || (listener && !owns_api_listener(&process, port))
        {
            return None;
        }
        same_generation_process(&process, &executable, &installed, &vehicle)
    };
    binding()
}

#[cfg(target_os = "linux")]
async fn packaged_existing_ready(pid: u32) -> bool {
    let port = read_active_port("api", default_port());
    let Some(before) = packaged_binding(pid, port, true) else {
        return false;
    };
    let Ok(client) = Client::new(format!("http://127.0.0.1:{port}")) else {
        return false;
    };
    let ready = tokio::time::timeout(API_STARTUP_TIMEOUT, async {
        client.is_running().await
            && client
                .get("/api/settings/computer-use")
                .await
                .is_ok_and(|status| status["venv_ready"] == true)
    })
    .await
    .unwrap_or(false);
    ready && packaged_binding(pid, port, true).as_ref() == Some(&before)
}

fn startup_timeout(packaged: bool) -> Duration {
    if packaged {
        // Mounted package inventories are verified before the API binds.
        // This changes only the wait budget, never runtime authorization.
        Duration::from_secs(300)
    } else {
        API_STARTUP_TIMEOUT
    }
}

#[cfg(any(test, target_os = "linux"))]
fn installed_startup_layout(
    development: bool,
    platform: &str,
    executable: Option<&Path>,
    appdir: Option<&Path>,
    installed: Option<&Path>,
    vehicle: Option<&Path>,
) -> bool {
    let (Some(executable), Some(appdir), Some(installed), Some(vehicle)) =
        (executable, appdir, installed, vehicle)
    else {
        return false;
    };
    let Some(bytes) = bounded_process_record(&installed.join("install-receipt.json"), 1024 * 1024)
    else {
        return false;
    };
    let Ok(receipt) = serde_json::from_slice::<vadgr_daemon::install::InstallReceipt>(&bytes)
    else {
        return false;
    };
    let mode_matches = if development {
        receipt.development_receipt_sha256.is_some()
            && receipt.manifest_sha256.is_none()
            && receipt.release_sequence.is_none()
            && installed.join("development-receipt.json").is_file()
            && !installed.join("release-manifest.json").exists()
            && !installed
                .join("release-manifest.json.bundle.jsonl")
                .exists()
    } else {
        receipt.development_receipt_sha256.is_none()
            && receipt.manifest_sha256.is_some()
            && receipt.release_sequence.is_some()
            && !installed.join("development-receipt.json").exists()
            && installed.join("release-manifest.json").is_file()
            && installed
                .join("release-manifest.json.bundle.jsonl")
                .is_file()
    };
    platform == "linux"
        && receipt.schema == 1
        && receipt.package_kind == "appimage"
        && mode_matches
        && appdir.is_absolute()
        && installed.is_absolute()
        && executable == appdir.join("usr/bin/vadgr")
        && vehicle == installed.join("Vadgr.AppImage")
        && vehicle.is_file()
}

/// A failed or cancelled startup must not become a daemon after rollback.
struct StartingDaemon {
    child: Child,
    records: PathBuf,
    port: u16,
    ready: bool,
    #[cfg(target_os = "linux")]
    packaged: bool,
}

impl Drop for StartingDaemon {
    fn drop(&mut self) {
        if self.ready {
            return;
        }
        #[cfg(target_os = "linux")]
        if self.packaged && !self.stop_failed_packaged_start(Duration::from_secs(30)) {
            // A retained startup record is the installer's rollback fence. Do
            // not erase it or kill the parent if its children remain unproved.
            return;
        }
        // The retained child handle identifies our process, not a port owner.
        let _ = self.child.kill();
        let _ = self.child.wait();
        let pid = self.records.join("api.pid");
        let port = self.records.join("api.port");
        let recorded = std::fs::read_to_string(&pid).ok();
        let matches_child = recorded.as_deref() == Some(self.child.id().to_string().as_str());
        #[cfg(target_os = "linux")]
        let matches_reservation = self.packaged && recorded.as_deref() == Some("");
        #[cfg(not(target_os = "linux"))]
        let matches_reservation = false;
        if matches_child || matches_reservation {
            if std::fs::read_to_string(&port).ok().as_deref()
                == Some(self.port.to_string().as_str())
            {
                let _ = std::fs::remove_file(port);
            }
            let _ = std::fs::remove_file(pid);
        }
    }
}

#[cfg(target_os = "linux")]
impl StartingDaemon {
    fn stop_failed_packaged_start(&mut self, timeout: Duration) -> bool {
        // Once the parent has exited its descendants may have been reparented.
        // Keep the rollback fence rather than inventing an ownership claim.
        if !matches!(self.child.try_wait(), Ok(None)) {
            return false;
        }
        let pid = self.child.id();
        let Ok(identity) = stop_snapshot(pid) else {
            return false;
        };
        stop_owned_process_tree(pid, &identity.start, timeout, || {
            stop_snapshot(pid)
                .is_ok_and(|current| current.start == identity.start && current.uid == identity.uid)
        })
        .is_ok()
    }
}
/// How long a port probe waits before calling the port closed.
const PORT_PROBE_TIMEOUT: Duration = Duration::from_secs(1);
/// The port this daemon has always taken.
pub const DEFAULT_PORT: u16 = 8000;
/// How far `start` will walk up from a busy port before giving up.
const PORT_SEARCH_ATTEMPTS: u16 = 20;

fn user_home() -> PathBuf {
    let key = if cfg!(windows) { "USERPROFILE" } else { "HOME" };
    std::env::var_os(key).map(PathBuf::from).unwrap_or_default()
}

/// Where the installation keeps its pid files, its log and its clone.
///
/// This is the product's own directory, and it is the one the installer
/// creates. Durable state does not live here: the database, the run journals
/// and the credentials resolve below the platform's local-state directory.
pub fn vadgr_home() -> PathBuf {
    std::env::var_os("VADGR_HOME")
        .map(PathBuf::from)
        .unwrap_or_else(|| user_home().join(".vadgr"))
}

/// The checkout the daemon runs from.
///
/// The installer puts it at `~/.vadgr/src`, and `vadgr update` rebuilds from
/// exactly that tree. The two must name the same directory or an update reports
/// a checkout that is not there. A checkout anywhere else sets `VADGR_REPO`,
/// which is how a development tree runs.
pub fn vadgr_repo() -> PathBuf {
    std::env::var_os("VADGR_REPO")
        .map(PathBuf::from)
        .unwrap_or_else(|| vadgr_home().join("src"))
}

fn pid_dir() -> PathBuf {
    vadgr_home().join("pids")
}

/// The port to use when nothing else says otherwise.
pub fn default_port() -> u16 {
    std::env::var("VADGR_PORT")
        .ok()
        .and_then(|v| v.parse().ok())
        .unwrap_or(DEFAULT_PORT)
}

fn pid_alive(pid: u32) -> bool {
    #[cfg(unix)]
    {
        let Ok(pid) = rustix::process::Pid::from_raw(pid as i32).ok_or(()) else {
            return false;
        };
        rustix::process::test_kill_process(pid).is_ok()
    }
    #[cfg(windows)]
    {
        Command::new("tasklist")
            .args(["/FI", &format!("PID eq {pid}"), "/NH"])
            .output()
            .map(|out| String::from_utf8_lossy(&out.stdout).contains(&pid.to_string()))
            .unwrap_or(false)
    }
}

/// The pid of a running service, clearing the file when it names a dead one.
///
/// A stale pid file is the difference between "already running, refusing to
/// start" and a machine nobody can start any more, so reading one is also what
/// removes it.
pub fn read_pid(service: &str) -> Option<u32> {
    let pidfile = pid_dir().join(format!("{service}.pid"));
    let text = std::fs::read_to_string(&pidfile).ok()?;
    let Ok(pid) = text.trim().parse::<u32>() else {
        let _ = std::fs::remove_file(&pidfile);
        return None;
    };
    if pid_alive(pid) {
        return Some(pid);
    }
    let _ = std::fs::remove_file(&pidfile);
    None
}

fn write_pid(service: &str, pid: u32) -> std::io::Result<()> {
    std::fs::create_dir_all(pid_dir())?;
    std::fs::write(pid_dir().join(format!("{service}.pid")), pid.to_string())
}

fn write_port(service: &str, port: u16) -> std::io::Result<()> {
    std::fs::create_dir_all(pid_dir())?;
    std::fs::write(pid_dir().join(format!("{service}.port")), port.to_string())
}

/// The port a running service actually took.
///
/// `start` walks up from a busy port, so the port the CLI should call is not
/// always the default. The pid is what makes the file trustworthy: a port file
/// with no live process behind it is stale and is removed rather than believed.
pub fn read_active_port(service: &str, default: u16) -> u16 {
    let portfile = pid_dir().join(format!("{service}.port"));
    let Ok(text) = std::fs::read_to_string(&portfile) else {
        return default;
    };
    let Ok(port) = text.trim().parse::<u16>() else {
        let _ = std::fs::remove_file(&portfile);
        return default;
    };
    if read_pid(service).is_none() {
        let _ = std::fs::remove_file(&portfile);
        return default;
    }
    port
}

/// Whether anything is listening on a loopback port.
///
/// Both families, because a listener may hold `::1` alone and checking only
/// `127.0.0.1` would report a running daemon as stopped.
pub fn port_in_use(port: u16) -> bool {
    ["127.0.0.1", "::1"].iter().any(|host| {
        (*host, port)
            .to_socket_addrs()
            .map(|addrs| {
                addrs
                    .into_iter()
                    .any(|a| TcpStream::connect_timeout(&a, PORT_PROBE_TIMEOUT).is_ok())
            })
            .unwrap_or(false)
    })
}

/// Whether this process could actually take the port.
///
/// `port_in_use` asks a different question, and asks it by connecting: it says
/// whether something answers, which is right for "is a daemon alive" and wrong
/// for "can I bind this". A listener whose backlog is full refuses the probe, so
/// two connects in a row disagree and the port reads free while it is held.
/// Binding is the question being asked here, and its answer does not depend on
/// what the other process is doing with its accept queue.
///
/// **Every host the daemon will bind, not just loopback.** Checking one address
/// and binding another is the same mistake as checking liveness and binding: the
/// daemon binds the transport's address too, so a port free on `127.0.0.1` and
/// taken on the tailnet address would pass this check and still die.
fn port_bindable(port: u16, hosts: &[String]) -> bool {
    hosts
        .iter()
        .all(|host| match TcpListener::bind((host.as_str(), port)) {
            Ok(listener) => {
                drop(listener);
                true
            }
            Err(_) => false,
        })
}

/// The port to start on, given the one asked for.
///
/// Separated from the sockets so the decision itself is testable on every
/// operating system. The socket-level tests below can only run where a held
/// port can be simulated; this one runs everywhere, which matters because the
/// defect it guards was found on Windows.
fn choose_port(requested: u16, mut bindable: impl FnMut(u16) -> bool) -> Option<u16> {
    (0..PORT_SEARCH_ATTEMPTS)
        .filter_map(|offset| requested.checked_add(offset))
        .find(|candidate| bindable(*candidate))
}

/// The first port at or above `default` that this process can bind on every host.
fn find_free_port(default: u16, hosts: &[String]) -> Option<u16> {
    choose_port(default, |candidate| port_bindable(candidate, hosts))
}

/// The reason the daemon gave for stopping, read from the tail of its log.
///
/// **Only a line the daemon wrote as its own failure**, so a stray warning
/// earlier in the file is never reported as the cause. The daemon prints its
/// refusals as `Error: ...` on the last line before it exits, which is what a
/// person needs and what the CLI otherwise replaces with a guess.
fn daemon_failure_reason(log_path: &Path) -> Option<String> {
    let text = std::fs::read_to_string(log_path).ok()?;
    text.lines()
        .rev()
        .map(str::trim)
        .find(|line| line.starts_with("Error: "))
        .map(|line| line.trim_start_matches("Error: ").to_owned())
}

fn kill_tree(pid: u32) {
    #[cfg(windows)]
    {
        let _ = Command::new("taskkill")
            .args(["/PID", &pid.to_string(), "/T", "/F"])
            .output();
    }
    #[cfg(unix)]
    {
        if let Ok(out) = Command::new("pgrep")
            .args(["-P", &pid.to_string()])
            .output()
        {
            for child in String::from_utf8_lossy(&out.stdout).split_whitespace() {
                if let Ok(child) = child.parse::<u32>() {
                    kill_tree(child);
                }
            }
        }
        if let Some(pid) = rustix::process::Pid::from_raw(pid as i32) {
            let _ = rustix::process::kill_process(pid, rustix::process::Signal::TERM);
        }
    }
}

fn kill_port(port: u16) {
    #[cfg(windows)]
    {
        let script = format!(
            "Get-NetTCPConnection -LocalPort {port} -ErrorAction SilentlyContinue | \
             ForEach-Object {{ Stop-Process -Id $_.OwningProcess -Force }}"
        );
        let _ = Command::new("powershell")
            .args(["-Command", &script])
            .output();
    }
    #[cfg(unix)]
    {
        let _ = Command::new("fuser")
            .args(["-k", &format!("{port}/tcp")])
            .output();
    }
}

async fn wait_for_api(
    child: &mut Child,
    port: u16,
    timeout: Duration,
    packaged: bool,
) -> Result<bool, CliError> {
    let client = Client::new(format!("http://127.0.0.1:{port}")).map_err(CliError::Failed)?;
    let deadline = tokio::time::Instant::now() + timeout;
    while tokio::time::Instant::now() < deadline {
        if child
            .try_wait()
            .map_err(|error| CliError::Failed(error.to_string()))?
            .is_some()
        {
            return Ok(false);
        }
        if tokio::time::timeout_at(deadline, client.is_running())
            .await
            .unwrap_or(false)
        {
            if packaged {
                #[cfg(target_os = "linux")]
                if !owns_api_listener(&PathBuf::from(format!("/proc/{}", child.id())), port) {
                    return Ok(false);
                }
                // An owner may disable computer use without invalidating its
                // installed runtime. Read admission, not the enabled flag.
                let ready =
                    tokio::time::timeout_at(deadline, client.get("/api/settings/computer-use"))
                        .await
                        .ok()
                        .and_then(Result::ok)
                        .is_some_and(|status| status["venv_ready"] == true);
                if child
                    .try_wait()
                    .map_err(|error| CliError::Failed(error.to_string()))?
                    .is_some()
                {
                    return Ok(false);
                }
                #[cfg(target_os = "linux")]
                return Ok(ready
                    && owns_api_listener(&PathBuf::from(format!("/proc/{}", child.id())), port));
                #[cfg(not(target_os = "linux"))]
                return Ok(ready);
            }
            return Ok(true);
        }
        tokio::time::sleep_until(
            (tokio::time::Instant::now() + Duration::from_millis(100)).min(deadline),
        )
        .await;
    }
    Ok(false)
}
/// The executable that serves, which is this one.
///
/// The product is a single file: the daemon is this binary invoked with
/// `serve`. `VADGR_DAEMON` still names another executable for a test or a
/// managed deployment that wants one, and it is the only way to point
/// somewhere else.
///
/// It used to resolve a sibling `vadgr-daemon` beside this binary, then fall
/// back to `PATH`. That fallback once started a daemon from an entirely
/// different installation when the expected file was missing, which took a
/// while to see, because the product appeared to work.
fn daemon_binary() -> Result<PathBuf, CliError> {
    if let Some(explicit) = std::env::var_os("VADGR_DAEMON") {
        let path = PathBuf::from(explicit);
        if !path.exists() {
            return Err(CliError::Failed(format!(
                "VADGR_DAEMON names {}, which does not exist.",
                path.display()
            )));
        }
        return Ok(path);
    }
    std::env::current_exe()
        .map_err(|e| CliError::Failed(format!("Could not work out which binary is running: {e}")))
}
/// The addresses the daemon binds.
///
/// **The address `vadgr start` binds and the address `vadgr pair` advertises can
/// never be two different answers**, because both come from this crate's own
/// transport registry rather than from two separate computations: the union of
/// every supported transport's bind hosts. A transport that is down listens on
/// nothing and says so through its own reach, so it never fails the probe for
/// the others; the built-in transport binds its own UDP socket and contributes
/// no host here.
///
/// Computed here rather than left to the child, because `start` writes a pid
/// file and prints success, and it must know the address resolves before it
/// does either. A refused configuration (an illegal `VADGR_TRANSPORT` value,
/// a malformed relay list) stops `start` before anything spawns, with the
/// daemon's own boot refusal as the message.
fn resolve_bind_hosts() -> Result<Vec<String>, CliError> {
    let config = vadgr_daemon::config::Config::from_env()
        .map_err(|error| CliError::Failed(error.to_string()))?;
    let registry = vadgr_daemon::transport::Transports::from_config(&config, config.port, None);
    let mut hosts = registry.bind_hosts();
    if !hosts.iter().any(|h| h == "127.0.0.1") {
        hosts.push("127.0.0.1".to_owned());
    }
    Ok(hosts)
}

pub async fn start(api_port: Option<u16>) -> Result<(), CliError> {
    let packaged = packaged_startup()?;
    let mut port = api_port.unwrap_or_else(default_port);
    std::fs::create_dir_all(pid_dir())
        .map_err(|e| CliError::Failed(format!("Could not create {}: {e}", pid_dir().display())))?;

    if let Some(pid) = read_pid("api") {
        #[cfg(target_os = "linux")]
        if packaged && packaged_existing_ready(pid).await {
            anstream::println!("{}", output::success("vadgr is running!"));
            return Ok(());
        }
        #[cfg(not(target_os = "linux"))]
        let _ = pid;
        anstream::println!(
            "{}",
            output::warning("vadgr is already running. Use 'vadgr stop' first.")
        );
        return Err(CliError::Failed(String::new()));
    }

    // The hosts come first because the port decision depends on them: the search
    // must try to bind exactly what the daemon will bind.
    let bind_hosts = resolve_bind_hosts()?;

    // **One question, asked once.** This used to gate on `port_in_use`, which
    // answers by connecting, and then search by binding. A port that nothing is
    // listening on but nothing can bind either failed the gate, so the search
    // never ran and the daemon died on bind under a message naming a port that
    // looked free. Windows reserves ports exactly that way, with no listener at
    // all, so no probe that connects can ever see them: `VADGR_PORT=8861` on a
    // host with Hyper-V reservations killed the daemon every time.
    let requested = port;
    let Some(chosen) = find_free_port(port, &bind_hosts) else {
        anstream::println!(
            "{}",
            output::warning(&format!("No free port found starting from {requested}."))
        );
        return Err(CliError::Failed(String::new()));
    };
    port = chosen;
    if port != requested {
        anstream::println!(
            "{}",
            output::info(&format!("Port {requested} busy, using {port}"))
        );
    }

    anstream::println!(
        "{}",
        output::info(&format!(
            "Starting API server ({} on port {port})...",
            bind_hosts.join(", ")
        ))
    );

    let log_path = vadgr_home().join("api.log");
    create_service_home(&vadgr_home()).map_err(|e| {
        CliError::Failed(format!("Could not create {}: {e}", vadgr_home().display()))
    })?;
    let log = open_service_log(&log_path)
        .map_err(|e| CliError::Failed(format!("Could not open {}: {e}", log_path.display())))?;
    let errors = log
        .try_clone()
        .map_err(|e| CliError::Failed(format!("Could not open {}: {e}", log_path.display())))?;

    // The product is one executable, so the daemon is this binary again with
    // `serve`. There is no sibling file to find, which also removes the way a
    // stale daemon from an older installation used to be picked up off PATH.
    let mut command = Command::new(daemon_binary()?);
    command.arg("serve");
    for host in &bind_hosts {
        command.args(["--host", host]);
    }
    // **No working directory is set on purpose.** The daemon resolves its state
    // from the platform root, so where it is started from decides nothing, and
    // passing a directory here would suggest otherwise.
    command
        .args(["--port", &port.to_string()])
        .env("VADGR_PORT", port.to_string())
        .stdin(Stdio::null())
        .stdout(Stdio::from(log))
        .stderr(Stdio::from(errors));
    detach(&mut command);

    #[cfg(target_os = "linux")]
    if packaged {
        // The installer can detect a failed cleanup even if writing the actual
        // child PID fails. Never spawn without this durable rollback fence.
        std::fs::create_dir_all(pid_dir()).map_err(|e| CliError::Failed(e.to_string()))?;
        std::fs::OpenOptions::new()
            .write(true)
            .create_new(true)
            .open(pid_dir().join("api.pid"))
            .and_then(|file| file.sync_all())
            .map_err(|e| {
                CliError::Failed(format!("Could not reserve daemon startup record: {e}"))
            })?;
    }
    let child = command.spawn().map_err(|e| {
        #[cfg(target_os = "linux")]
        if packaged && std::fs::read(pid_dir().join("api.pid")).is_ok_and(|bytes| bytes.is_empty())
        {
            let _ = std::fs::remove_file(pid_dir().join("api.pid"));
        }
        CliError::Failed(format!("Could not start the API: {e}"))
    })?;
    let mut starting = StartingDaemon {
        child,
        records: pid_dir(),
        port,
        ready: false,
        #[cfg(target_os = "linux")]
        packaged,
    };
    write_pid("api", starting.child.id()).map_err(|e| CliError::Failed(e.to_string()))?;
    write_port("api", port).map_err(|e| CliError::Failed(e.to_string()))?;

    tokio::time::sleep(Duration::from_secs(1)).await;
    if matches!(starting.child.try_wait(), Ok(Some(_))) {
        // **Say why it died, not what usually kills it.** Guessing at the port
        // sent someone hunting a conflict that did not exist while the daemon
        // had written a precise reason to its log: it had refused to merge two
        // histories that shared a run id, named the id and both files, and said
        // nothing had been moved. The daemon knows the cause and the log has
        // it, so the operator gets it rather than a plausible story.
        let reported = daemon_failure_reason(&log_path)
            .unwrap_or_else(|| format!("Port {port} may be in use. Check {}", log_path.display()));
        anstream::println!(
            "{}",
            output::warning(&format!("The daemon stopped before it served. {reported}"))
        );
        return Err(CliError::Failed(String::new()));
    }

    if !wait_for_api(
        &mut starting.child,
        port,
        startup_timeout(packaged),
        packaged,
    )
    .await?
    {
        anstream::println!(
            "{}",
            output::warning(&format!(
                "API failed to start. Check {}",
                log_path.display()
            ))
        );
        return Err(CliError::Failed(String::new()));
    }
    starting.ready = true;

    anstream::println!("{}", output::success("vadgr is running!"));
    anstream::println!(
        "{}",
        output::success(&format!("  API: http://localhost:{port}"))
    );
    anstream::println!();
    anstream::println!(
        "{}",
        output::info(
            "Run 'vadgr pair' to pair your phone, 'vadgr stop' to stop, 'vadgr logs' for the log."
        )
    );
    Ok(())
}

/// Detach the daemon from the terminal that started it.
///
/// Without this the child inherits the terminal and competes with the shell for
/// input, which corrupts typing and paste in the session that started it.
fn detach(command: &mut Command) {
    #[cfg(unix)]
    {
        use std::os::unix::process::CommandExt;
        // Safety: `setsid` after fork and before exec is async-signal-safe, which
        // is the whole contract of `pre_exec`.
        unsafe {
            command.pre_exec(|| rustix::process::setsid().map(|_| ()).map_err(|e| e.into()));
        }
    }
    #[cfg(windows)]
    {
        use std::os::windows::process::CommandExt;
        const CREATE_NO_WINDOW: u32 = 0x0800_0000;
        command.creation_flags(CREATE_NO_WINDOW);
    }
}

pub fn stop() -> Result<(), CliError> {
    #[cfg(target_os = "linux")]
    if packaged_startup()? {
        return stop_installed_linux();
    }
    let port = read_active_port("api", default_port());
    let mut stopped = false;

    if let Some(pid) = read_pid("api") {
        kill_tree(pid);
        anstream::println!("{}", output::info(&format!("Stopped api (PID {pid})")));
        stopped = true;
    } else if port_in_use(port) {
        kill_port(port);
        anstream::println!("{}", output::info(&format!("Stopped api on port {port}")));
        stopped = true;
    }

    if stopped {
        let _ = std::fs::remove_file(pid_dir().join("api.pid"));
        let _ = std::fs::remove_file(pid_dir().join("api.port"));
        anstream::println!("{}", output::success("vadgr stopped."));
    } else {
        anstream::println!("{}", output::warning("vadgr is not running."));
    }
    Ok(())
}

#[cfg(target_os = "linux")]
#[derive(Clone)]
struct StopSnapshot {
    start: String,
    parent: u32,
    state: String,
    uid: u32,
}

#[cfg(target_os = "linux")]
fn stop_snapshot(pid: u32) -> anyhow::Result<StopSnapshot> {
    use std::os::unix::fs::MetadataExt;
    let root = PathBuf::from(format!("/proc/{pid}"));
    let bytes = bounded_process_record(&root.join("stat"), 4096)
        .ok_or_else(|| anyhow::anyhow!("process identity is unavailable"))?;
    let text = std::str::from_utf8(&bytes)?;
    let fields: Vec<_> = text
        .rsplit_once(") ")
        .ok_or_else(|| anyhow::anyhow!("invalid process identity"))?
        .1
        .split_whitespace()
        .collect();
    anyhow::ensure!(fields.len() >= 20, "incomplete process identity");
    Ok(StopSnapshot {
        start: fields[19].to_owned(),
        parent: fields[1].parse()?,
        state: fields[0].to_owned(),
        uid: std::fs::metadata(root)?.uid(),
    })
}

#[cfg(target_os = "linux")]
struct StoppingProcess {
    pid: u32,
    identity: StopSnapshot,
    handle: rustix::fd::OwnedFd,
    paused: bool,
}

#[cfg(target_os = "linux")]
impl StoppingProcess {
    fn open(pid: u32) -> anyhow::Result<Self> {
        let identity = stop_snapshot(pid)?;
        let handle = rustix::process::pidfd_open(
            rustix::process::Pid::from_raw(pid as i32)
                .ok_or_else(|| anyhow::anyhow!("invalid process id"))?,
            rustix::process::PidfdFlags::empty(),
        )?;
        let after = stop_snapshot(pid)?;
        anyhow::ensure!(
            identity.start == after.start && identity.uid == after.uid,
            "process identity changed before stop"
        );
        Ok(Self {
            pid,
            identity,
            handle,
            paused: false,
        })
    }

    fn exited(&self) -> anyhow::Result<bool> {
        use std::os::fd::AsRawFd;
        let path = PathBuf::from(format!("/proc/self/fdinfo/{}", self.handle.as_raw_fd()));
        let bytes = bounded_process_record(&path, 4096)
            .ok_or_else(|| anyhow::anyhow!("process handle status is unavailable"))?;
        let text = std::str::from_utf8(&bytes)?;
        let value = text
            .lines()
            .find_map(|line| line.strip_prefix("Pid:"))
            .ok_or_else(|| anyhow::anyhow!("process handle has no identity"))?
            .trim()
            .parse::<i64>()?;
        if value == -1 {
            return Ok(true);
        }
        anyhow::ensure!(
            value == i64::from(self.pid),
            "process handle identity differs"
        );
        let status = match stop_snapshot(self.pid) {
            Ok(status) => status,
            Err(error) => {
                // The process may be reaped between the handle and stat reads.
                // Only this same pidfd can prove that its original task is gone.
                let repeated = bounded_process_record(&path, 4096)
                    .ok_or_else(|| anyhow::anyhow!("process handle status is unavailable"))?;
                let gone = std::str::from_utf8(&repeated)?
                    .lines()
                    .find_map(|line| line.strip_prefix("Pid:"))
                    .is_some_and(|value| value.trim() == "-1");
                if gone {
                    return Ok(true);
                }
                return Err(error);
            }
        };
        anyhow::ensure!(
            status.start == self.identity.start,
            "process identity changed while stopping"
        );
        Ok(matches!(status.state.as_str(), "Z" | "X"))
    }

    fn signal(&self, signal: rustix::process::Signal) -> anyhow::Result<()> {
        if !self.exited()? {
            rustix::process::pidfd_send_signal(&self.handle, signal)?;
        }
        Ok(())
    }
}

#[cfg(target_os = "linux")]
struct FrozenProcessTree(Vec<StoppingProcess>);

#[cfg(target_os = "linux")]
impl Drop for FrozenProcessTree {
    fn drop(&mut self) {
        for process in self.0.iter_mut().rev() {
            if process.paused {
                let _ = process.signal(rustix::process::Signal::CONT);
                process.paused = false;
            }
        }
    }
}

#[cfg(target_os = "linux")]
fn stop_owned_process_tree(
    pid: u32,
    expected_start: &str,
    timeout: Duration,
    still_owned: impl Fn() -> bool,
) -> anyhow::Result<()> {
    anyhow::ensure!(still_owned(), "daemon ownership changed before stop");
    let deadline = std::time::Instant::now() + timeout;
    let root = StoppingProcess::open(pid)?;
    anyhow::ensure!(
        root.identity.start == expected_start,
        "daemon identity changed before stop"
    );
    let uid = root.identity.uid;
    let mut tree = FrozenProcessTree(vec![root]);
    let mut index = 0;
    while index < tree.0.len() {
        anyhow::ensure!(
            std::time::Instant::now() < deadline,
            "daemon stop timed out before termination"
        );
        let process = &mut tree.0[index];
        if process.exited()? {
            index += 1;
            continue;
        }
        let status = stop_snapshot(process.pid)?;
        anyhow::ensure!(
            !matches!(status.state.as_str(), "T" | "t"),
            "a daemon process is already stopped externally; its state was preserved"
        );
        process.signal(rustix::process::Signal::STOP)?;
        process.paused = true;
        while !process.exited()? && !matches!(stop_snapshot(process.pid)?.state.as_str(), "T" | "t")
        {
            anyhow::ensure!(
                std::time::Instant::now() < deadline,
                "daemon stop timed out while pausing"
            );
            std::thread::sleep(Duration::from_millis(2));
        }
        if process.exited()? {
            index += 1;
            continue;
        }
        let parent = process.pid;
        let mut children = std::collections::BTreeSet::new();
        for task in std::fs::read_dir(format!("/proc/{parent}/task"))? {
            let bytes = bounded_process_record(&task?.path().join("children"), 64 * 1024)
                .ok_or_else(|| anyhow::anyhow!("daemon child inventory is unavailable"))?;
            for child in std::str::from_utf8(&bytes)?.split_whitespace() {
                children.insert(child.parse::<u32>()?);
            }
        }
        for child in children {
            anyhow::ensure!(
                tree.0.len() < 256,
                "daemon child inventory exceeds its bound"
            );
            let child = StoppingProcess::open(child)?;
            anyhow::ensure!(
                child.identity.parent == parent && child.identity.uid == uid,
                "daemon child ownership differs"
            );
            anyhow::ensure!(
                !tree.0.iter().any(|existing| existing.pid == child.pid),
                "daemon child inventory changed"
            );
            tree.0.push(child);
        }
        index += 1;
    }
    anyhow::ensure!(still_owned(), "daemon ownership changed before termination");
    for process in tree.0.iter_mut().rev() {
        anyhow::ensure!(
            std::time::Instant::now() < deadline,
            "daemon stop timed out before termination"
        );
        if process.exited()? {
            process.paused = false;
            continue;
        }
        process.signal(rustix::process::Signal::TERM)?;
        process.signal(rustix::process::Signal::CONT)?;
        process.paused = false;
        while !process.exited()? {
            anyhow::ensure!(
                std::time::Instant::now() < deadline,
                "daemon did not stop before the deadline"
            );
            std::thread::sleep(Duration::from_millis(5));
        }
    }
    Ok(())
}

#[cfg(target_os = "linux")]
fn stop_installed_linux() -> Result<(), CliError> {
    let operation = || -> anyhow::Result<()> {
        let records = pid_dir();
        let pid_path = records.join("api.pid");
        let port_path = records.join("api.port");
        let pid_text = match std::fs::read_to_string(&pid_path) {
            Ok(value) => value,
            Err(error) if error.kind() == std::io::ErrorKind::NotFound => {
                let retained_port = match std::fs::read_to_string(&port_path) {
                    Ok(value) => value.trim().parse::<u16>()?,
                    Err(error) if error.kind() == std::io::ErrorKind::NotFound => default_port(),
                    Err(error) => return Err(error.into()),
                };
                anyhow::ensure!(
                    port_bindable(retained_port, &["127.0.0.1".to_owned()]),
                    "an unowned listener is present; nothing was stopped"
                );
                return Ok(());
            }
            Err(error) => return Err(error.into()),
        };
        let pid = pid_text.trim().parse::<u32>()?;
        let port_text = std::fs::read_to_string(&port_path)?;
        let port = port_text.trim().parse::<u16>()?;
        if matches!(std::fs::metadata(format!("/proc/{pid}")), Err(error) if error.kind() == std::io::ErrorKind::NotFound)
        {
            anyhow::ensure!(
                port_bindable(port, &["127.0.0.1".to_owned()]),
                "an unowned listener is present; nothing was stopped"
            );
        } else {
            let identity = packaged_binding(pid, port, false).ok_or_else(|| anyhow::anyhow!("the recorded process does not belong to this installed generation and state; nothing was stopped"))?;
            stop_owned_process_tree(pid, &identity.0, Duration::from_secs(30), || {
                packaged_binding(pid, port, false).as_ref() == Some(&identity)
            })?;
        }
        if std::fs::read_to_string(&pid_path).ok().as_deref() == Some(pid_text.as_str())
            && std::fs::read_to_string(&port_path).ok().as_deref() == Some(port_text.as_str())
        {
            std::fs::remove_file(port_path)?;
            std::fs::remove_file(pid_path)?;
        }
        Ok(())
    };
    operation().map_err(|error| CliError::Failed(error.to_string()))?;
    anstream::println!("{}", output::success("vadgr stopped."));
    Ok(())
}

pub async fn restart(api_port: Option<u16>) -> Result<(), CliError> {
    stop()?;
    tokio::time::sleep(Duration::from_secs(1)).await;
    start(api_port).await
}

/// The service table, read from the pid files this CLI writes.
///
/// It asks the daemon nothing. It used to, for one extra row carrying the
/// state of the computer-use bridge, and that row never appeared because the
/// field behind it has answered null on every platform since the Rust daemon
/// began serving it.
pub fn status() -> Result<(), CliError> {
    let mut rows: Vec<Vec<String>> = Vec::new();
    match read_pid("api") {
        Some(pid) => rows.push(vec![
            "api".to_owned(),
            pid.to_string(),
            output::format_status("running"),
        ]),
        None => rows.push(vec![
            "api".to_owned(),
            "-".to_owned(),
            output::format_status("stopped"),
        ]),
    }

    // The daemon's own view, and only when it answers. A stopped daemon is not
    // an error here: the table is the answer to "what is running".

    anstream::println!(
        "{}",
        output::render_table(&["Service", "PID", "Status"], &rows)
    );
    Ok(())
}

/// The last `lines` lines of a file, without reading the whole file.
fn tail_lines(path: &Path, lines: usize) -> std::io::Result<(Vec<String>, u64)> {
    let file = std::fs::File::open(path)?;
    let end = file.metadata()?.len();
    let mut reader = std::io::BufReader::new(file);
    let mut kept: std::collections::VecDeque<String> = std::collections::VecDeque::new();
    let mut line = String::new();
    loop {
        line.clear();
        let mut raw = Vec::new();
        let read = reader.read_until(b'\n', &mut raw)?;
        if read == 0 {
            break;
        }
        let text = String::from_utf8_lossy(&raw)
            .trim_end_matches('\n')
            .to_owned();
        if kept.len() == lines {
            kept.pop_front();
        }
        kept.push_back(text);
    }
    Ok((kept.into_iter().collect(), end))
}

/// `vadgr logs`, following the file itself rather than shelling out.
///
/// **A fixed defect, not an invented feature.** Before `0.4.8` this shelled out
/// to `tail -f`, which does not exist on Windows, so `vadgr logs` there failed
/// with a missing-executable error instead of showing a log. Following the file
/// directly works on all four platforms and removes a process.
pub async fn logs(service: &str, follow: bool, lines: usize) -> Result<(), CliError> {
    let path = vadgr_home().join(format!("{service}.log"));
    if !path.exists() {
        anstream::println!(
            "{}",
            output::warning(&format!("No logs found for {service}. Is vadgr running?"))
        );
        return Err(CliError::Failed(String::new()));
    }

    let (tail, mut offset) = tail_lines(&path, lines)
        .map_err(|e| CliError::Failed(format!("Could not read {}: {e}", path.display())))?;
    for line in tail {
        anstream::println!("{line}");
    }
    if !follow {
        return Ok(());
    }

    // Ctrl-C ends the follow, which is what a person expects from a tail.
    let mut file = std::fs::File::open(&path)
        .map_err(|e| CliError::Failed(format!("Could not read {}: {e}", path.display())))?;
    loop {
        let len = file
            .metadata()
            .map(|m| m.len())
            .map_err(|e| CliError::Failed(e.to_string()))?;
        // A rotated or truncated file starts again from its own beginning
        // rather than seeking past its end and printing nothing for ever.
        if len < offset {
            offset = 0;
        }
        if len > offset {
            file.seek(SeekFrom::Start(offset))
                .map_err(|e| CliError::Failed(e.to_string()))?;
            let mut fresh = Vec::new();
            file.read_to_end(&mut fresh)
                .map_err(|e| CliError::Failed(e.to_string()))?;
            offset = len;
            let mut out = anstream::stdout();
            let _ = out.write_all(&fresh);
            let _ = out.flush();
        }
        tokio::select! {
            _ = tokio::signal::ctrl_c() => return Ok(()),
            _ = tokio::time::sleep(Duration::from_millis(400)) => {}
        }
    }
}
fn git(repo: &Path, args: &[&str]) -> Result<std::process::Output, CliError> {
    Command::new("git")
        .args(args)
        .current_dir(repo)
        .output()
        .map_err(|e| CliError::Failed(format!("Could not run git: {e}")))
}

/// Installed packages discover and verify signed updates from the selected source.
/// Source checkouts retain their fast-forward and rebuild path without `--source`.
pub async fn update(check: bool, source: Option<&str>) -> Result<(), CliError> {
    let package =
        vadgr_daemon::install::status().map_err(|error| CliError::Failed(error.to_string()))?;
    if package.installed {
        if check {
            let update = vadgr_daemon::install::check_for_updates_from(source)
                .map_err(|error| CliError::Failed(error.to_string()))?;
            if update.update_available {
                anstream::println!(
                    "{}",
                    output::info(&format!("Vadgr {} is available.", update.available_version))
                );
                if let Some(reason) = update.install_unavailable_reason() {
                    anstream::println!("{}", output::info(reason));
                }
            } else {
                anstream::println!("{}", output::success("vadgr is up to date."));
            }
            return Ok(());
        }
        let update = vadgr_daemon::install::apply_update_from(source)
            .map_err(|error| CliError::Failed(error.to_string()))?;
        anstream::println!(
            "{}",
            output::success(&format!(
                "The signed Vadgr {} installer completed.",
                update.available_version
            ))
        );
        return Ok(());
    }

    if source.is_some() {
        return Err(CliError::Usage(
            "--source requires an installed Vadgr package.".to_owned(),
        ));
    }
    let repo = vadgr_repo();
    if !repo.join(".git").exists() {
        return Err(CliError::Failed(format!(
            "{} is not a git checkout, so it cannot be updated. Reinstall with the \
             installer instead.",
            repo.display()
        )));
    }

    if check {
        let fetched = git(&repo, &["fetch", "--quiet", "origin", "master"])?;
        if !fetched.status.success() {
            anstream::println!(
                "{}",
                output::warning(&format!(
                    "Could not reach the remote: {}",
                    String::from_utf8_lossy(&fetched.stderr).trim()
                ))
            );
            return Err(CliError::Failed(String::new()));
        }
        let behind = git(&repo, &["rev-list", "--count", "HEAD..origin/master"])?;
        let count: usize = String::from_utf8_lossy(&behind.stdout)
            .trim()
            .parse()
            .unwrap_or(0);
        if count == 0 {
            anstream::println!("{}", output::success("vadgr is up to date."));
            return Ok(());
        }
        anstream::println!(
            "{}",
            output::info(&format!(
                "{count} commit(s) available. Run 'vadgr update' to apply them."
            ))
        );
        // What a person actually wants to know before rebuilding: whether the
        // dependency set moves, because that is the slow half of the build.
        let names = git(
            &repo,
            &[
                "diff",
                "--name-only",
                "HEAD..origin/master",
                "--",
                "Cargo.lock",
            ],
        )?;
        if !String::from_utf8_lossy(&names.stdout).trim().is_empty() {
            anstream::println!("  dependencies change: Cargo.lock");
        }
        return Ok(());
    }

    anstream::println!("{}", output::info("Updating vadgr..."));
    let pulled = git(&repo, &["pull", "--ff-only", "origin", "master"])?;
    if !pulled.status.success() {
        anstream::println!(
            "{}",
            output::warning(&format!(
                "Could not pull: {}",
                String::from_utf8_lossy(&pulled.stderr).trim()
            ))
        );
        return Ok(());
    }
    anstream::println!("{}", String::from_utf8_lossy(&pulled.stdout).trim());

    anstream::println!("{}", output::info("Building the release binaries..."));
    let mut build = Command::new("cargo");
    build.args(["build", "--locked", "--release", "--bins"]);
    // Windows links the C runtime in rather than importing it, so the binary
    // does not need the Visual C++ redistributable to start. The installer
    // builds the same way, and an update that built differently would quietly
    // replace a standalone binary with one that has a dependency.
    if cfg!(windows) {
        build.args(["--target", WINDOWS_TARGET]);
        build.env("RUSTFLAGS", "-C target-feature=+crt-static");
    }
    let built = build.current_dir(&repo).status().map_err(|e| {
        CliError::Failed(format!(
            "Could not run cargo: {e}. An update from a checkout needs the Rust \
                 toolchain the installer set up."
        ))
    })?;
    if !built.success() {
        return Err(CliError::Failed(
            "The build failed, so nothing was replaced. The installation you had is \
             still the one on PATH."
                .to_owned(),
        ));
    }

    // The matching private runtime is ready before the new executable moves.
    // A payload failure leaves the currently installed binary untouched.
    let current = std::env::current_exe().map_err(|error| {
        CliError::Failed(format!(
            "Could not locate the installed vadgr binary: {error}"
        ))
    })?;
    let install_root = vadgr_daemon::cua_payload::install_root_from_executable(&current)
        .map_err(|error| CliError::Failed(error.to_string()))?;
    let suffix = if cfg!(windows) { ".exe" } else { "" };
    let candidate = release_dir(&repo).join(format!("vadgr{suffix}"));
    let payload = Command::new(&candidate)
        .arg("__payload-setup")
        .arg("--install-root")
        .arg(&install_root)
        .arg("--payload-only")
        .status()
        .map_err(|error| {
            CliError::Failed(format!(
                "Could not run the built candidate at {}: {error}",
                candidate.display()
            ))
        })?;
    if !payload.success() {
        return Err(CliError::Failed(
            "The matching computer-use payload failed, so nothing was replaced.".to_owned(),
        ));
    }

    // **Nothing is copied over the running installation until the build passed.**
    // A half-replaced binary is an installation that neither starts nor rolls
    // back.
    let installed = install_binaries(&repo)?;
    anstream::println!(
        "{}",
        output::success(&format!("Updated {installed} binary/binaries."))
    );

    if read_pid("api").is_some() {
        anstream::println!("{}", output::info("The daemon is running the old build."));
        anstream::println!("Run 'vadgr restart' to apply changes.");
    } else {
        anstream::println!(
            "{}",
            output::success("Update complete. Run 'vadgr start' to start.")
        );
    }
    Ok(())
}

/// Copy the freshly built binaries beside the command that is running.
///
/// Beside, rather than to a remembered install path: the command a person typed
/// is by definition the installation they are updating.
/// The triple the Windows build is named with, so its flags reach the binary
/// and not the build scripts and proc macros that run on the host.
const WINDOWS_TARGET: &str = "x86_64-pc-windows-msvc";

/// Where the release binaries land, which the explicit Windows target moves.
fn release_dir(repo: &Path) -> std::path::PathBuf {
    let target = repo.join("target");
    if cfg!(windows) {
        target.join(WINDOWS_TARGET).join("release")
    } else {
        target.join("release")
    }
}

fn install_binaries(repo: &Path) -> Result<usize, CliError> {
    let target = std::env::current_exe()
        .ok()
        .and_then(|exe| exe.parent().map(Path::to_path_buf))
        .ok_or_else(|| {
            CliError::Failed("Could not work out where this command is installed.".to_owned())
        })?;
    let suffix = if cfg!(windows) { ".exe" } else { "" };
    let mut installed = 0;
    for name in ["vadgr"] {
        let built = release_dir(repo).join(format!("{name}{suffix}"));
        if !built.exists() {
            continue;
        }
        // A running binary cannot be overwritten on Windows, and can be on Unix,
        // so the old one is moved aside first on both. One code path, and the
        // aside copy is what a failed update is rolled back from.
        let destination = target.join(format!("{name}{suffix}"));
        if destination.exists() {
            let aside = target.join(format!("{name}{suffix}.previous"));
            let _ = std::fs::remove_file(&aside);
            std::fs::rename(&destination, &aside).map_err(|e| {
                CliError::Failed(format!(
                    "Could not move {} aside: {e}. Nothing was replaced.",
                    destination.display()
                ))
            })?;
        }
        std::fs::copy(&built, &destination).map_err(|e| {
            CliError::Failed(format!(
                "Could not install {}: {e}. The previous binary is beside it as \
                 {name}{suffix}.previous.",
                destination.display()
            ))
        })?;
        installed += 1;
    }
    Ok(installed)
}

#[cfg(test)]
mod startup_tests {
    use super::*;

    #[cfg(target_os = "linux")]
    #[test]
    fn stopped_tree_fixture() {
        let Some(root) = std::env::var_os("VADGR_STOP_FIXTURE") else {
            return;
        };
        let root = PathBuf::from(root);
        let depth: u32 = std::env::var("VADGR_STOP_DEPTH").unwrap().parse().unwrap();
        if root.join("ignore-term").exists() {
            // Only this isolated test child changes its signal disposition.
            unsafe {
                libc::signal(libc::SIGTERM, libc::SIG_IGN);
            }
        }
        let mut child = (depth < 2).then(|| {
            Command::new(std::env::current_exe().unwrap())
                .args([
                    "--exact",
                    "commands::service::startup_tests::stopped_tree_fixture",
                ])
                .env("VADGR_STOP_DEPTH", (depth + 1).to_string())
                .stdin(Stdio::null())
                .stdout(Stdio::null())
                .stderr(Stdio::null())
                .spawn()
                .unwrap()
        });
        std::fs::write(
            root.join(format!("pid-{depth}")),
            std::process::id().to_string(),
        )
        .unwrap();
        std::thread::sleep(Duration::from_secs(10));
        if let Some(child) = child.as_mut() {
            let _ = child.kill();
            let _ = child.wait();
        }
    }

    #[cfg(target_os = "linux")]
    struct StopFixture {
        _root: tempfile::TempDir,
        child: Option<Child>,
        processes: Vec<StoppingProcess>,
    }

    #[cfg(target_os = "linux")]
    impl Drop for StopFixture {
        fn drop(&mut self) {
            for process in self.processes.iter().rev() {
                let _ = process.signal(rustix::process::Signal::KILL);
            }
            if let Some(child) = self.child.as_mut() {
                let _ = child.kill();
                let _ = child.wait();
            } else if let Some(root) = self.processes.first() {
                // This fixture spawned the root; waitpid never selects another
                // process and simply returns ECHILD if StartingDaemon reaped it.
                unsafe {
                    libc::waitpid(root.pid as i32, std::ptr::null_mut(), 0);
                }
            }
        }
    }

    #[cfg(target_os = "linux")]
    fn stop_fixture(ignore_term: bool) -> StopFixture {
        let root = tempfile::tempdir().unwrap();
        if ignore_term {
            std::fs::write(root.path().join("ignore-term"), []).unwrap();
        }
        let child = Command::new(std::env::current_exe().unwrap())
            .args([
                "--exact",
                "commands::service::startup_tests::stopped_tree_fixture",
            ])
            .env("VADGR_STOP_FIXTURE", root.path())
            .env("VADGR_STOP_DEPTH", "0")
            .stdin(Stdio::null())
            .stdout(Stdio::null())
            .stderr(Stdio::null())
            .spawn()
            .unwrap();
        let mut fixture = StopFixture {
            _root: root,
            child: Some(child),
            processes: Vec::new(),
        };
        let deadline = std::time::Instant::now() + Duration::from_secs(5);
        for depth in 0..3 {
            let path = fixture._root.path().join(format!("pid-{depth}"));
            while !path.exists() {
                assert!(
                    std::time::Instant::now() < deadline,
                    "test process failed to reach its barrier"
                );
                std::thread::sleep(Duration::from_millis(5));
            }
            let pid = std::fs::read_to_string(path).unwrap().parse().unwrap();
            fixture.processes.push(StoppingProcess::open(pid).unwrap());
        }
        fixture
    }

    #[cfg(target_os = "linux")]
    #[test]
    fn installed_stop_waits_for_owned_children_and_grandchildren() {
        let fixture = stop_fixture(false);
        let root = &fixture.processes[0];
        stop_owned_process_tree(
            root.pid,
            &root.identity.start,
            Duration::from_secs(3),
            || true,
        )
        .unwrap();
        assert!(
            fixture
                .processes
                .iter()
                .all(|process| process.exited().unwrap()),
            "stop returned before the owned tree exited"
        );
    }

    #[cfg(target_os = "linux")]
    #[test]
    fn failed_packaged_start_reaps_descendants_before_clearing_rollback_fence() {
        let mut fixture = stop_fixture(false);
        let records = fixture._root.path().to_path_buf();
        let child = fixture.child.take().unwrap();
        std::fs::write(records.join("api.pid"), child.id().to_string()).unwrap();
        std::fs::write(records.join("api.port"), "18890").unwrap();
        let starting = StartingDaemon {
            child,
            records: records.clone(),
            port: 18890,
            ready: false,
            packaged: true,
        };
        drop(starting);
        assert!(
            fixture
                .processes
                .iter()
                .all(|process| process.exited().unwrap())
        );
        assert!(!records.join("api.pid").exists());
        assert!(!records.join("api.port").exists());
    }

    #[cfg(target_os = "linux")]
    #[test]
    fn failed_packaged_start_drop_retains_empty_fence_when_child_is_externally_stopped() {
        let mut fixture = stop_fixture(false);
        let records = fixture._root.path().to_path_buf();
        std::fs::write(records.join("api.pid"), []).unwrap();
        let leaf = &fixture.processes[2];
        leaf.signal(rustix::process::Signal::STOP).unwrap();
        let deadline = std::time::Instant::now() + Duration::from_secs(1);
        while stop_snapshot(leaf.pid).unwrap().state != "T" {
            assert!(std::time::Instant::now() < deadline);
            std::thread::sleep(Duration::from_millis(2));
        }
        drop(StartingDaemon {
            child: fixture.child.take().unwrap(),
            records: records.clone(),
            port: 18890,
            ready: false,
            packaged: true,
        });
        assert_eq!(std::fs::read(records.join("api.pid")).unwrap(), b"");
        assert!(
            fixture
                .processes
                .iter()
                .all(|process| !process.exited().unwrap())
        );
        assert_eq!(stop_snapshot(leaf.pid).unwrap().state, "T");
    }

    #[cfg(target_os = "linux")]
    #[test]
    fn failed_packaged_start_preserves_fence_and_live_parent_on_unproved_cleanup() {
        let mut fixture = stop_fixture(true);
        let records = fixture._root.path().to_path_buf();
        let child = fixture.child.take().unwrap();
        let pid = child.id().to_string();
        std::fs::write(records.join("api.pid"), &pid).unwrap();
        std::fs::write(records.join("api.port"), "18890").unwrap();
        let mut starting = StartingDaemon {
            child,
            records: records.clone(),
            port: 18890,
            ready: false,
            packaged: true,
        };
        assert!(!starting.stop_failed_packaged_start(Duration::from_millis(100)));
        assert_eq!(
            std::fs::read_to_string(records.join("api.pid")).unwrap(),
            pid
        );
        assert_eq!(
            std::fs::read_to_string(records.join("api.port")).unwrap(),
            "18890"
        );
        assert!(
            fixture
                .processes
                .iter()
                .all(|process| !process.exited().unwrap())
        );
        // Test-owned cleanup retains the handles; do not repeat a 30-second
        // production deadline after this deliberately short timeout proof.
        starting.ready = true;
        for process in fixture.processes.iter().rev() {
            process.signal(rustix::process::Signal::KILL).unwrap();
        }
        starting.child.wait().unwrap();
    }

    #[cfg(target_os = "linux")]
    #[test]
    fn installed_stop_timeout_is_not_success_and_resumes_only_its_pauses() {
        let fixture = stop_fixture(true);
        let root = &fixture.processes[0];
        let result = stop_owned_process_tree(
            root.pid,
            &root.identity.start,
            Duration::from_millis(100),
            || true,
        );
        assert!(
            result.is_err(),
            "ignored TERM must not report successful stop"
        );
        for process in &fixture.processes {
            assert!(!process.exited().unwrap());
            assert!(!matches!(
                stop_snapshot(process.pid).unwrap().state.as_str(),
                "T" | "t"
            ));
        }
    }

    #[cfg(target_os = "linux")]
    #[test]
    fn installed_stop_refuses_foreign_and_preserves_external_stop() {
        let fixture = stop_fixture(false);
        let root = &fixture.processes[0];
        assert!(
            stop_owned_process_tree(
                root.pid,
                &root.identity.start,
                Duration::from_secs(1),
                || false
            )
            .is_err()
        );
        assert!(
            fixture
                .processes
                .iter()
                .all(|process| !process.exited().unwrap())
        );
        let leaf = &fixture.processes[2];
        leaf.signal(rustix::process::Signal::STOP).unwrap();
        let deadline = std::time::Instant::now() + Duration::from_secs(1);
        while stop_snapshot(leaf.pid).unwrap().state != "T" {
            assert!(std::time::Instant::now() < deadline);
            std::thread::sleep(Duration::from_millis(2));
        }
        assert!(
            stop_owned_process_tree(
                root.pid,
                &root.identity.start,
                Duration::from_secs(1),
                || true
            )
            .is_err()
        );
        assert_eq!(
            stop_snapshot(leaf.pid).unwrap().state,
            "T",
            "an external stop must not be resumed"
        );
        for process in &fixture.processes[..2] {
            assert!(!matches!(
                stop_snapshot(process.pid).unwrap().state.as_str(),
                "T" | "t"
            ));
        }
    }

    #[test]
    fn delayed_service_fixture() {
        let Some(root) = std::env::var_os("VADGR_STARTUP_FIXTURE") else {
            return;
        };
        let root = PathBuf::from(root);
        std::fs::write(root.join("entered"), []).unwrap();
        let deadline = std::time::Instant::now() + Duration::from_secs(10);
        while !root.join("release").exists() {
            if std::time::Instant::now() >= deadline {
                return;
            }
            std::thread::sleep(Duration::from_millis(5));
        }
        if root.join("exit").exists() {
            return;
        }
        let port: u16 = std::fs::read_to_string(root.join("port"))
            .unwrap()
            .parse()
            .unwrap();
        let listener = TcpListener::bind(("127.0.0.1", port)).unwrap();
        for connection in listener.incoming() {
            let mut connection = connection.unwrap();
            let mut request = [0; 2048];
            let count = connection.read(&mut request).unwrap_or(0);
            let body = if request[..count].starts_with(b"GET /api/settings/computer-use ") {
                if root.join("runtime-ready").exists() {
                    r#"{"venv_ready":true,"enabled":false}"#
                } else {
                    r#"{"venv_ready":false,"enabled":true}"#
                }
            } else {
                "{}"
            };
            let reply = format!(
                "HTTP/1.1 200 OK\r\nContent-Length: {}\r\nConnection: close\r\n\r\n{body}",
                body.len()
            );
            let _ = connection.write_all(reply.as_bytes());
        }
    }

    async fn fixture() -> (tempfile::TempDir, StartingDaemon) {
        let root = tempfile::tempdir().unwrap();
        let listener = TcpListener::bind(("127.0.0.1", 0)).unwrap();
        let port = listener.local_addr().unwrap().port();
        drop(listener);
        std::fs::write(root.path().join("port"), port.to_string()).unwrap();
        let child = Command::new(std::env::current_exe().unwrap())
            .args([
                "--exact",
                "commands::service::startup_tests::delayed_service_fixture",
                "--nocapture",
            ])
            .env("VADGR_STARTUP_FIXTURE", root.path())
            .stdin(Stdio::null())
            .stdout(Stdio::null())
            .stderr(Stdio::null())
            .spawn()
            .unwrap();
        let starting = StartingDaemon {
            child,
            records: root.path().to_path_buf(),
            port,
            ready: false,
            #[cfg(target_os = "linux")]
            packaged: false,
        };
        std::fs::write(root.path().join("api.pid"), starting.child.id().to_string()).unwrap();
        std::fs::write(root.path().join("api.port"), port.to_string()).unwrap();
        tokio::time::timeout(Duration::from_secs(10), async {
            while !root.path().join("entered").is_file() {
                tokio::time::sleep(Duration::from_millis(5)).await;
            }
        })
        .await
        .expect("the real child reached the explicit startup barrier");
        (root, starting)
    }

    #[tokio::test]
    async fn timed_out_child_is_reaped_before_rollback_and_cannot_bind_later() {
        let (root, mut starting) = fixture().await;
        let port = starting.port;
        assert!(
            !wait_for_api(&mut starting.child, port, Duration::from_millis(30), false)
                .await
                .unwrap()
        );
        let pid = starting.child.id();
        drop(starting);
        assert!(!pid_alive(pid), "timed-out child remains alive");
        assert!(!root.path().join("api.pid").exists());
        assert!(!root.path().join("api.port").exists());
        std::fs::write(root.path().join("release"), []).unwrap();
        assert!(TcpListener::bind(("127.0.0.1", port)).is_ok());
    }

    #[tokio::test]
    async fn failed_start_does_not_remove_replacement_records_or_stop_another_child() {
        let (root, starting) = fixture().await;
        let (_other_root, other) = fixture().await;
        std::fs::write(root.path().join("api.pid"), other.child.id().to_string()).unwrap();
        std::fs::write(root.path().join("api.port"), other.port.to_string()).unwrap();
        drop(starting);
        assert!(pid_alive(other.child.id()));
        assert_eq!(
            std::fs::read_to_string(root.path().join("api.pid")).unwrap(),
            other.child.id().to_string()
        );
        assert_eq!(
            std::fs::read_to_string(root.path().join("api.port")).unwrap(),
            other.port.to_string()
        );
    }

    #[tokio::test]
    async fn startup_wait_stops_when_the_child_exits_and_keeps_changed_port_record() {
        let (root, mut starting) = fixture().await;
        std::fs::write(root.path().join("exit"), []).unwrap();
        std::fs::write(root.path().join("release"), []).unwrap();
        let result = tokio::time::timeout(
            Duration::from_secs(2),
            wait_for_api(
                &mut starting.child,
                starting.port,
                Duration::from_secs(30),
                false,
            ),
        )
        .await;
        assert!(
            !result
                .expect("child exit must not wait for the startup deadline")
                .unwrap()
        );
        std::fs::write(root.path().join("api.port"), "different").unwrap();
        drop(starting);
        assert!(!root.path().join("api.pid").exists());
        assert_eq!(
            std::fs::read_to_string(root.path().join("api.port")).unwrap(),
            "different"
        );
    }

    #[tokio::test]
    async fn successful_readiness_releases_the_child_and_preserves_service_records() {
        let (root, mut starting) = fixture().await;
        std::fs::write(root.path().join("release"), []).unwrap();
        assert!(
            wait_for_api(
                &mut starting.child,
                starting.port,
                Duration::from_secs(5),
                false
            )
            .await
            .unwrap()
        );
        starting.ready = true;
        assert!(pid_alive(starting.child.id()));
        assert!(root.path().join("api.pid").exists());
        // Restore fixture ownership so teardown stops only this test child.
        starting.ready = false;
    }

    #[test]
    fn extended_budget_layout_excludes_wsl_and_uninstalled_or_unrelated_executables() {
        assert!(!classify_installed_startup(false, false).unwrap());
        assert!(classify_installed_startup(true, true).unwrap());
        assert_eq!(startup_timeout(false), Duration::from_secs(30));
        assert_eq!(startup_timeout(true), Duration::from_secs(300));
        let root = tempfile::tempdir().unwrap();
        let appdir = root.path().join("mount");
        let installed = root.path().join("generation");
        std::fs::create_dir(&installed).unwrap();
        for name in [
            "Vadgr.AppImage",
            "install-receipt.json",
            "development-receipt.json",
        ] {
            std::fs::write(installed.join(name), []).unwrap();
        }
        std::fs::write(installed.join("install-receipt.json"), r#"{"schema":1,"version":"0.5.0","package_kind":"appimage","development_receipt_sha256":"fixture"}"#).unwrap();
        let exe = appdir.join("usr/bin/vadgr");
        let vehicle = installed.join("Vadgr.AppImage");
        assert!(installed_startup_layout(
            true,
            "linux",
            Some(&exe),
            Some(&appdir),
            Some(&installed),
            Some(&vehicle)
        ));
        assert!(!installed_startup_layout(
            true,
            "wsl",
            Some(&exe),
            Some(&appdir),
            Some(&installed),
            Some(&vehicle)
        ));
        assert!(!installed_startup_layout(
            true,
            "linux",
            Some(Path::new("/other/vadgr")),
            Some(&appdir),
            Some(&installed),
            Some(&vehicle)
        ));
        assert!(!installed_startup_layout(
            true,
            "linux",
            Some(&exe),
            Some(&appdir),
            Some(&installed),
            None
        ));
        assert!(!installed_startup_layout(
            false,
            "linux",
            Some(&exe),
            Some(&appdir),
            Some(&installed),
            Some(&vehicle)
        ));
        std::fs::remove_file(installed.join("development-receipt.json")).unwrap();
        assert!(
            classify_installed_startup(
                true,
                installed_startup_layout(
                    true,
                    "linux",
                    Some(&exe),
                    Some(&appdir),
                    Some(&installed),
                    Some(&vehicle)
                )
            )
            .is_err()
        );
        std::fs::write(installed.join("install-receipt.json"), r#"{"schema":1,"version":"0.5.0","package_kind":"appimage","manifest_sha256":"fixture","release_sequence":1}"#).unwrap();
        for name in [
            "release-manifest.json",
            "release-manifest.json.bundle.jsonl",
        ] {
            std::fs::write(installed.join(name), []).unwrap();
        }
        assert!(installed_startup_layout(
            false,
            "linux",
            Some(&exe),
            Some(&appdir),
            Some(&installed),
            Some(&vehicle)
        ));
        assert!(!installed_startup_layout(
            true,
            "linux",
            Some(&exe),
            Some(&appdir),
            Some(&installed),
            Some(&vehicle)
        ));
        assert!(
            classify_installed_startup(
                true,
                installed_startup_layout(
                    true,
                    "linux",
                    Some(&exe),
                    Some(&appdir),
                    Some(&installed),
                    Some(&vehicle)
                )
            )
            .is_err()
        );
        std::fs::remove_file(installed.join("install-receipt.json")).unwrap();
        assert!(
            classify_installed_startup(
                true,
                installed_startup_layout(
                    false,
                    "linux",
                    Some(&exe),
                    Some(&appdir),
                    Some(&installed),
                    Some(&vehicle)
                )
            )
            .is_err()
        );
        assert!(!installed_startup_layout(
            false,
            "linux",
            Some(&exe),
            Some(&appdir),
            Some(&installed),
            Some(&vehicle)
        ));
    }

    #[cfg(target_os = "linux")]
    #[test]
    fn existing_process_binding_requires_role_generation_bytes_and_stable_start_identity() {
        let root = tempfile::tempdir().unwrap();
        let process = root.path().join("process");
        std::fs::create_dir(&process).unwrap();
        let installed = root.path().join("generation");
        let vehicle = installed.join("Vadgr.AppImage");
        let executable = root.path().join("current-executable");
        std::fs::write(&executable, b"exact executable bytes").unwrap();
        std::fs::write(process.join("exe"), b"exact executable bytes").unwrap();
        std::fs::write(process.join("cmdline"), b"vadgr\0serve\0").unwrap();
        let environment = format!(
            "VADGR_INSTALL_ROOT={}\0APPIMAGE={}\0",
            installed.display(),
            vehicle.display()
        );
        std::fs::write(process.join("environ"), &environment).unwrap();
        let stat = |start| format!("7 (vadgr) S {} {start}", ["0"; 18].join(" "));
        std::fs::write(process.join("stat"), stat(123)).unwrap();
        let bind = || same_generation_process(&process, &executable, &installed, &vehicle);
        let first = bind().expect("same source and generation");
        assert_eq!(first.0, "123");
        std::fs::write(process.join("stat"), stat(124)).unwrap();
        assert_ne!(bind(), Some(first));
        std::fs::write(process.join("cmdline"), b"vadgr\0--console\0").unwrap();
        assert!(bind().is_none());
        std::fs::write(process.join("cmdline"), b"vadgr\0serve\0").unwrap();
        std::fs::write(
            process.join("environ"),
            b"VADGR_INSTALL_ROOT=/different\0APPIMAGE=/different/Vadgr.AppImage\0",
        )
        .unwrap();
        assert!(bind().is_none());
        std::fs::write(process.join("environ"), environment).unwrap();
        std::fs::write(process.join("exe"), b"different executable bytes").unwrap();
        assert!(bind().is_none());
        std::fs::write(process.join("exe"), b"exact executable bytes").unwrap();
        std::fs::write(process.join("cmdline"), vec![b'x'; 64 * 1024 + 1]).unwrap();
        assert!(bind().is_none());
    }

    #[cfg(target_os = "linux")]
    #[tokio::test]
    async fn another_listener_cannot_satisfy_a_new_packaged_child_readiness() {
        let (_waiting_root, mut waiting) = fixture().await;
        let (other_root, mut other) = fixture().await;
        std::fs::write(other_root.path().join("runtime-ready"), []).unwrap();
        std::fs::write(other_root.path().join("release"), []).unwrap();
        assert!(
            wait_for_api(&mut other.child, other.port, Duration::from_secs(5), true)
                .await
                .unwrap()
        );
        assert!(
            !wait_for_api(&mut waiting.child, other.port, Duration::from_secs(5), true)
                .await
                .unwrap()
        );
        assert!(
            pid_alive(other.child.id()),
            "refusing another listener must not kill it"
        );
    }

    #[cfg(target_os = "linux")]
    #[tokio::test]
    async fn readiness_listener_must_belong_to_the_exact_child() {
        let (root, mut starting) = fixture().await;
        let process = PathBuf::from(format!("/proc/{}", starting.child.id()));
        assert!(!owns_api_listener(&process, starting.port));
        std::fs::write(root.path().join("release"), []).unwrap();
        assert!(
            wait_for_api(
                &mut starting.child,
                starting.port,
                Duration::from_secs(5),
                false
            )
            .await
            .unwrap()
        );
        assert!(owns_api_listener(&process, starting.port));
        assert!(!owns_api_listener(Path::new("/proc/self"), starting.port));
        let port = starting.port;
        drop(starting);
        assert!(!owns_api_listener(&process, port));
    }

    #[cfg(target_os = "linux")]
    #[test]
    fn process_state_binding_distinguishes_absent_empty_other_root_and_port() {
        let expected = vec![
            ("HOME".to_owned(), Some(b"/isolated".to_vec())),
            ("VADGR_HOME".to_owned(), None),
            ("XDG_STATE_HOME".to_owned(), Some(b"/state".to_vec())),
        ];
        let correct = b"HOME=/isolated\0XDG_STATE_HOME=/state\0VADGR_PORT=18878\0";
        assert!(process_state_matches(correct, &expected, 18878));
        assert!(!process_state_matches(correct, &expected, 18890));
        assert!(!process_state_matches(
            b"HOME=/owner\0XDG_STATE_HOME=/state\0VADGR_PORT=18878\0",
            &expected,
            18878
        ));
        assert!(!process_state_matches(
            b"HOME=/isolated\0XDG_STATE_HOME=/state\0VADGR_HOME=\0VADGR_PORT=18878\0",
            &expected,
            18878
        ));
        assert!(!process_state_matches(
            b"HOME=/isolated\0HOME=/isolated\0XDG_STATE_HOME=/state\0VADGR_PORT=18878\0",
            &expected,
            18878
        ));
    }

    #[cfg(target_os = "linux")]
    #[tokio::test]
    async fn real_unrelated_child_is_not_accepted_as_the_installed_daemon() {
        let (root, starting) = fixture().await;
        assert!(
            same_generation_process(
                &PathBuf::from(format!("/proc/{}", starting.child.id())),
                &std::env::current_exe().unwrap(),
                root.path(),
                &root.path().join("Vadgr.AppImage")
            )
            .is_none()
        );
        assert!(
            pid_alive(starting.child.id()),
            "read-only refusal must not stop another process"
        );
    }

    #[tokio::test]
    async fn packaged_readiness_requires_runtime_admission_not_owner_enablement() {
        let (root, mut starting) = fixture().await;
        std::fs::write(root.path().join("release"), []).unwrap();
        assert!(
            !wait_for_api(
                &mut starting.child,
                starting.port,
                Duration::from_secs(5),
                true
            )
            .await
            .unwrap()
        );
        std::fs::write(root.path().join("runtime-ready"), []).unwrap();
        assert!(
            wait_for_api(
                &mut starting.child,
                starting.port,
                Duration::from_secs(5),
                true
            )
            .await
            .unwrap()
        );
    }
}

#[cfg(test)]
mod port_selection_tests {
    use super::*;

    #[cfg(unix)]
    #[test]
    fn an_existing_service_log_is_hardened_for_the_owner() {
        use std::os::unix::fs::PermissionsExt;

        let directory = tempfile::tempdir().unwrap();
        let path = directory.path().join("api.log");
        std::fs::write(&path, []).unwrap();
        std::fs::set_permissions(&path, std::fs::Permissions::from_mode(0o666)).unwrap();

        let _log = open_service_log(&path).unwrap();

        assert_eq!(
            std::fs::metadata(&path).unwrap().permissions().mode() & 0o777,
            0o600
        );
    }

    #[cfg(unix)]
    #[test]
    fn an_existing_service_home_is_hardened_for_the_owner() {
        use std::os::unix::fs::PermissionsExt;

        let directory = tempfile::tempdir().unwrap();
        let path = directory.path().join("home");
        std::fs::create_dir(&path).unwrap();
        std::fs::set_permissions(&path, std::fs::Permissions::from_mode(0o777)).unwrap();

        create_service_home(&path).unwrap();

        assert_eq!(
            std::fs::metadata(&path).unwrap().permissions().mode() & 0o777,
            0o700
        );
    }

    /// A socket bound and listening with a backlog of one, never accepting.
    ///
    /// This is the state a real busy port reaches under probing: the first
    /// connect fills the queue and every later one is refused, so a probe that
    /// asks by connecting reports the held port as free.
    #[cfg(unix)]
    fn hold_port_without_accepting() -> (i32, u16) {
        let seed = TcpListener::bind(("127.0.0.1", 0)).unwrap();
        let port = seed.local_addr().unwrap().port();
        drop(seed);
        unsafe {
            let fd = libc::socket(libc::AF_INET, libc::SOCK_STREAM, 0);
            assert!(fd >= 0, "socket");
            let one: libc::c_int = 1;
            libc::setsockopt(
                fd,
                libc::SOL_SOCKET,
                libc::SO_REUSEADDR,
                &one as *const _ as *const libc::c_void,
                std::mem::size_of::<libc::c_int>() as libc::socklen_t,
            );
            // `sockaddr_in` is not the same struct on every Unix. The BSDs,
            // macOS included, carry a leading `sin_len`; Linux does not have the
            // field at all, so naming it there is a compile error rather than a
            // portability wart. Zeroing the struct and filling the fields every
            // platform shares keeps one helper for all of them.
            let mut addr: libc::sockaddr_in = std::mem::zeroed();
            addr.sin_family = libc::AF_INET as libc::sa_family_t;
            addr.sin_port = port.to_be();
            addr.sin_addr = libc::in_addr {
                s_addr: u32::from_ne_bytes([127, 0, 0, 1]),
            };
            #[cfg(any(target_os = "macos", target_os = "ios", target_vendor = "apple"))]
            {
                addr.sin_len = std::mem::size_of::<libc::sockaddr_in>() as u8;
            }
            let rc = libc::bind(
                fd,
                &addr as *const _ as *const libc::sockaddr,
                std::mem::size_of::<libc::sockaddr_in>() as libc::socklen_t,
            );
            assert_eq!(rc, 0, "bind the held port");
            assert_eq!(libc::listen(fd, 1), 0, "listen with a backlog of one");
            (fd, port)
        }
    }

    /// The port search must never hand back a port it cannot bind.
    ///
    /// It used to decide with `port_in_use`, which answers by connecting. A
    /// listener that is not accepting refuses the second probe, so the port read
    /// busy once and free immediately after, and the search returned the very
    /// port it had just been told was taken. The daemon then died on bind with
    /// "Port 8815 busy, using 8815" printed above it.
    #[cfg(unix)]
    #[test]
    fn the_search_never_returns_a_port_it_cannot_bind() {
        let (fd, taken) = hold_port_without_accepting();

        // The state that broke it: probing by connecting answers "busy" once and
        // "free" once the accept queue is full, so the old search handed back the
        // port it had just been told was taken.
        //
        // **How many probes that takes is the kernel's business, not this test's.**
        // macOS refuses the second connect; Linux's effective backlog is larger
        // than the number asked for, so it queues another first. Asserting the
        // flip on the second probe made this test pass on one Unix and fail on
        // another for a reason that is not the product.
        assert!(
            port_in_use(taken),
            "the first probe should see the listener"
        );
        let flipped = (0..8).any(|_| !port_in_use(taken));

        // The invariant holds either way, and it is the thing the fix promises:
        // the search starts at the held port, so a search that still asked by
        // connecting would return it and the bind below would fail.
        let loopback = vec!["127.0.0.1".to_owned()];
        let chosen = find_free_port(taken, &loopback).expect("some port above it is free");
        assert!(
            flipped,
            "the probe never reported the held port free, so this run did not \
             reach the state the defect needed. The assertions below still hold, \
             but this host proved the invariant rather than the history."
        );

        assert_ne!(chosen, taken, "the search returned the held port");
        let proof = TcpListener::bind(("127.0.0.1", chosen));
        assert!(
            proof.is_ok(),
            "port {chosen} was reported free but will not bind"
        );
        unsafe { libc::close(fd) };
    }

    /// The two questions are different and must stay different: one asks whether
    /// anything answers, the other whether this process can take the port.
    #[test]
    fn bindability_is_not_the_same_question_as_liveness() {
        let loopback = vec!["127.0.0.1".to_owned()];
        let held = TcpListener::bind(("127.0.0.1", 0)).expect("a port to hold");
        let taken = held.local_addr().unwrap().port();
        assert!(
            !port_bindable(taken, &loopback),
            "a held port must not be bindable"
        );

        drop(held);
        assert!(
            port_bindable(taken, &loopback),
            "a released port must be bindable again"
        );
    }

    /// A daemon that refused to start says why, and the CLI repeats it.
    ///
    /// The CLI used to guess: it printed that the port might be in use, which
    /// is the usual cause and was the wrong one. The daemon had refused to
    /// merge two histories sharing a run id and had named the id and both
    /// files. The operator was sent to hunt a port conflict that did not exist.
    #[test]
    fn the_daemon_s_own_reason_is_read_from_its_log() {
        let directory = std::env::temp_dir().join(format!("vadgr-reason-{}", std::process::id()));
        std::fs::create_dir_all(&directory).unwrap();
        let log = directory.join("api.log");
        std::fs::write(
            &log,
            "INFO run recovery scan complete
             WARN no callback port could be bound
             Error: run r1 exists in both a.db and b.db. Nothing has been moved.
",
        )
        .unwrap();

        let reason = daemon_failure_reason(&log).expect("the log names a reason");
        assert!(reason.starts_with("run r1 exists in both"), "got: {reason}");
        assert!(
            !reason.contains("callback port"),
            "an earlier warning is not the cause of death"
        );
        let _ = std::fs::remove_file(&log);
    }

    /// A log with no failure line yields nothing, so the caller keeps its
    /// fallback rather than reporting an unrelated line as the cause.
    #[test]
    fn a_log_without_a_failure_line_reports_nothing() {
        let directory = std::env::temp_dir().join(format!("vadgr-noreason-{}", std::process::id()));
        std::fs::create_dir_all(&directory).unwrap();
        let log = directory.join("api.log");
        std::fs::write(
            &log,
            "INFO listening
WARN something odd
",
        )
        .unwrap();
        assert_eq!(daemon_failure_reason(&log), None);
        let _ = std::fs::remove_file(&log);
    }

    /// A port nothing listens on and nothing can bind must still be walked past.
    ///
    /// **This is the Windows defect, and it runs on every operating system.** The
    /// socket-level test above needs a held port it can simulate, so it is Unix
    /// only, and the platform that actually shipped this bug never executed it.
    /// Windows reserves port ranges with no listener behind them, so a probe that
    /// connects reports them free forever; `VADGR_PORT=8861` on a host with
    /// Hyper-V reservations printed no warning and killed the daemon on bind.
    #[test]
    fn a_reserved_port_with_no_listener_is_walked_past() {
        // Bindable answers false, and nothing is listening, so liveness would
        // answer false too. Only bindability can see this port.
        let reserved = [8861u16, 8862];
        let chosen = choose_port(8861, |port| !reserved.contains(&port))
            .expect("a port above the reserved range");

        assert_eq!(
            chosen, 8863,
            "the search must skip every port it cannot bind, not stop at the first"
        );
    }

    /// The requested port is used unchanged when it is available, so the "busy"
    /// line is never printed for a port that was fine.
    #[test]
    fn an_available_port_is_taken_as_asked() {
        assert_eq!(choose_port(8861, |_| true), Some(8861));
    }

    /// The search gives up rather than returning a port it cannot bind.
    #[test]
    fn a_search_that_finds_nothing_returns_nothing() {
        assert_eq!(choose_port(8861, |_| false), None);
    }

    /// Every host the daemon binds has to be free, not just loopback.
    ///
    /// A port open on `127.0.0.1` and taken on the transport's address would
    /// have passed a loopback-only check and died on the second bind.
    #[test]
    fn a_port_free_on_one_host_but_not_another_is_not_chosen() {
        let held = TcpListener::bind(("127.0.0.1", 0)).expect("a port to hold");
        let taken = held.local_addr().unwrap().port();

        // Loopback is genuinely taken here, so any host list including it must
        // reject this port however free the other addresses are.
        let hosts = vec!["127.0.0.1".to_owned()];
        assert!(!port_bindable(taken, &hosts));

        let empty: Vec<String> = Vec::new();
        assert!(
            port_bindable(taken, &empty),
            "no hosts means nothing to refuse it, which is why the caller must \
             pass the hosts the daemon will actually bind"
        );
    }
}
