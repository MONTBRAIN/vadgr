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
use std::process::{Command, Stdio};
use std::time::Duration;

use crate::client::Client;
use crate::error::CliError;
use crate::output;

/// How long the CLI waits for the daemon to answer health after spawning it.
const API_STARTUP_TIMEOUT: Duration = Duration::from_secs(30);
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
/// **The directory is still `~/.forge`, and that is deliberate.** `0.4.8`
/// renames the variables a person types; `0.4.9` moves what the product owns,
/// with the rest of the paths. Moving a database in the release before the
/// cutover would give a later defect two candidate causes.
pub fn vadgr_home() -> PathBuf {
    std::env::var_os("VADGR_HOME")
        .map(PathBuf::from)
        .unwrap_or_else(|| user_home().join(".forge"))
}

/// The checkout the daemon runs from.
///
/// The installer puts it at `~/.forge/Agent-Forge`, which is what the shipped
/// launcher hard-codes. A checkout anywhere else sets `VADGR_REPO`, which is how
/// a development tree runs.
pub fn vadgr_repo() -> PathBuf {
    std::env::var_os("VADGR_REPO")
        .map(PathBuf::from)
        .unwrap_or_else(|| vadgr_home().join("Agent-Forge"))
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
fn port_bindable(port: u16) -> bool {
    match TcpListener::bind(("127.0.0.1", port)) {
        Ok(listener) => {
            drop(listener);
            true
        }
        Err(_) => false,
    }
}

/// The first port at or above `default` that this process can bind.
fn find_free_port(default: u16) -> Option<u16> {
    (0..PORT_SEARCH_ATTEMPTS)
        .filter_map(|offset| default.checked_add(offset))
        .find(|candidate| port_bindable(*candidate))
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

async fn wait_for_api(port: u16) -> bool {
    let client = Client::new(format!("http://127.0.0.1:{port}"));
    let deadline = std::time::Instant::now() + API_STARTUP_TIMEOUT;
    while std::time::Instant::now() < deadline {
        if client.is_running().await {
            return true;
        }
        tokio::time::sleep(Duration::from_secs(1)).await;
    }
    false
}

/// The interpreter inside the daemon's own virtual environment.
fn api_python() -> Result<PathBuf, CliError> {
    let repo = vadgr_repo();
    let path = if cfg!(windows) {
        repo.join("api")
            .join(".venv")
            .join("Scripts")
            .join("python.exe")
    } else {
        repo.join("api").join(".venv").join("bin").join("python")
    };
    if !path.exists() {
        return Err(CliError::Failed(format!(
            "API venv not found at {}. Run setup first.",
            path.display()
        )));
    }
    Ok(path)
}

/// The addresses the daemon binds.
///
/// **The address `vadgr start` binds and the address `vadgr pair` advertises can
/// never be two different answers**, because both come from this crate's own
/// transport module rather than from two separate computations.
///
/// Computed here rather than left to the child, because `start` writes a pid
/// file and prints success, and it must know the address resolves before it does
/// either. A transport that is down falls back to loopback loudly: the CLI, runs
/// and the journal are all loopback clients, and a tailnet outage should not
/// stop someone using their own machine.
fn resolve_bind_hosts() -> Vec<String> {
    let name = std::env::var("VADGR_TRANSPORT").unwrap_or_else(|_| "loopback".to_owned());
    let transport = match vadgr_daemon::transport::create(&name) {
        Ok(t) => t,
        Err(error) => {
            anstream::println!(
                "{}",
                output::warning(&format!(
                    "{error} Binding 127.0.0.1 only; pairing will refuse."
                ))
            );
            return vec!["127.0.0.1".to_owned()];
        }
    };
    match transport.bind_host() {
        Ok(primary) if primary == "127.0.0.1" => vec![primary],
        Ok(primary) => vec![primary, "127.0.0.1".to_owned()],
        Err(error) => {
            anstream::println!(
                "{}",
                output::warning(&format!(
                    "{error} Binding 127.0.0.1 only; pairing will refuse."
                ))
            );
            vec!["127.0.0.1".to_owned()]
        }
    }
}

pub async fn start(api_port: Option<u16>) -> Result<(), CliError> {
    let mut port = api_port.unwrap_or_else(default_port);
    std::fs::create_dir_all(pid_dir())
        .map_err(|e| CliError::Failed(format!("Could not create {}: {e}", pid_dir().display())))?;

    if read_pid("api").is_some() {
        anstream::println!(
            "{}",
            output::warning("vadgr is already running. Use 'vadgr stop' first.")
        );
        return Err(CliError::Failed(String::new()));
    }

    if port_in_use(port) {
        let original = port;
        let Some(free) = find_free_port(port) else {
            anstream::println!(
                "{}",
                output::warning(&format!("No free port found starting from {original}."))
            );
            return Err(CliError::Failed(String::new()));
        };
        port = free;
        anstream::println!(
            "{}",
            output::info(&format!("Port {original} busy, using {port}"))
        );
    }

    let bind_hosts = resolve_bind_hosts();
    anstream::println!(
        "{}",
        output::info(&format!(
            "Starting API server ({} on port {port})...",
            bind_hosts.join(", ")
        ))
    );

    let log_path = vadgr_home().join("api.log");
    std::fs::create_dir_all(vadgr_home()).map_err(|e| {
        CliError::Failed(format!("Could not create {}: {e}", vadgr_home().display()))
    })?;
    let log = std::fs::File::create(&log_path)
        .map_err(|e| CliError::Failed(format!("Could not open {}: {e}", log_path.display())))?;
    let errors = log
        .try_clone()
        .map_err(|e| CliError::Failed(format!("Could not open {}: {e}", log_path.display())))?;

    let mut command = Command::new(api_python()?);
    command.args(["-m", "api.serve"]);
    for host in &bind_hosts {
        command.args(["--host", host]);
    }
    command
        .args(["--port", &port.to_string()])
        .current_dir(vadgr_repo())
        .env("PYTHONPATH", vadgr_repo())
        .env("VADGR_PORT", port.to_string())
        .stdin(Stdio::null())
        .stdout(Stdio::from(log))
        .stderr(Stdio::from(errors));
    detach(&mut command);

    let mut child = command
        .spawn()
        .map_err(|e| CliError::Failed(format!("Could not start the API: {e}")))?;
    write_pid("api", child.id()).map_err(|e| CliError::Failed(e.to_string()))?;
    write_port("api", port).map_err(|e| CliError::Failed(e.to_string()))?;

    tokio::time::sleep(Duration::from_secs(1)).await;
    if matches!(child.try_wait(), Ok(Some(_))) {
        anstream::println!(
            "{}",
            output::warning(&format!(
                "API process died. Port {port} may be in use. Check {}",
                log_path.display()
            ))
        );
        let _ = std::fs::remove_file(pid_dir().join("api.pid"));
        let _ = std::fs::remove_file(pid_dir().join("api.port"));
        return Err(CliError::Failed(String::new()));
    }

    if !wait_for_api(port).await {
        anstream::println!(
            "{}",
            output::warning(&format!(
                "API failed to start. Check {}",
                log_path.display()
            ))
        );
        return Err(CliError::Failed(String::new()));
    }

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

pub async fn restart(api_port: Option<u16>) -> Result<(), CliError> {
    stop()?;
    tokio::time::sleep(Duration::from_secs(1)).await;
    start(api_port).await
}

pub async fn status(client: &Client) -> Result<(), CliError> {
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
    if client.is_running().await {
        let daemon = client
            .get("/api/settings/computer-use")
            .await
            .ok()
            .and_then(|body| {
                body.get("daemon")
                    .and_then(|v| v.as_str())
                    .map(str::to_owned)
            });
        if let Some(daemon) = daemon {
            rows.push(vec![
                "daemon".to_owned(),
                "-".to_owned(),
                output::format_status(&daemon),
            ]);
        }
    }

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

fn file_hash(path: &Path) -> Option<String> {
    use sha2::{Digest, Sha256};
    let bytes = std::fs::read(path).ok()?;
    Some(
        Sha256::digest(&bytes)
            .iter()
            .map(|byte| format!("{byte:02x}"))
            .collect(),
    )
}

fn git(repo: &Path, args: &[&str]) -> Result<std::process::Output, CliError> {
    Command::new("git")
        .args(args)
        .current_dir(repo)
        .output()
        .map_err(|e| CliError::Failed(format!("Could not run git: {e}")))
}

/// `vadgr update`, with the check path the runbook has been blocked on.
///
/// `S12f` and `F21` are blocked on every platform in `0.4.7`'s runbook for one
/// reason: the only way to test `update` was to run it, and running it changes
/// the installation the rest of the pass is measuring. `--check` answers the
/// same question and changes nothing, so the cell becomes runnable.
pub async fn update(check: bool) -> Result<(), CliError> {
    let repo = vadgr_repo();
    if !repo.join(".git").exists() {
        return Err(CliError::Failed(format!(
            "{} is not a git checkout, so it cannot be updated.",
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
        let names = git(
            &repo,
            &[
                "diff",
                "--name-only",
                "HEAD..origin/master",
                "--",
                "api/requirements.txt",
                "cli/requirements.txt",
            ],
        )?;
        let changed = String::from_utf8_lossy(&names.stdout);
        for line in changed.lines().filter(|l| !l.trim().is_empty()) {
            anstream::println!("  dependencies change: {line}");
        }
        return Ok(());
    }

    anstream::println!("{}", output::info("Updating vadgr..."));
    let api_req = repo.join("api").join("requirements.txt");
    let cli_req = repo.join("cli").join("requirements.txt");
    let old_api = file_hash(&api_req);
    let old_cli = file_hash(&cli_req);

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

    if file_hash(&api_req) != old_api {
        anstream::println!("{}", output::info("API deps changed, reinstalling..."));
        install_requirements(&repo.join("api"), &api_req)?;
    }
    if file_hash(&cli_req) != old_cli {
        anstream::println!("{}", output::info("CLI deps changed, reinstalling..."));
        install_requirements(&repo.join("cli"), &cli_req)?;
    }

    if read_pid("api").is_some() {
        anstream::println!("{}", output::info("Restarting services..."));
        anstream::println!("Run 'vadgr restart' to apply changes.");
    } else {
        anstream::println!(
            "{}",
            output::success("Update complete. Run 'vadgr start' to start.")
        );
    }
    Ok(())
}

fn install_requirements(package: &Path, requirements: &Path) -> Result<(), CliError> {
    let pip = if cfg!(windows) {
        package.join(".venv").join("Scripts").join("pip.exe")
    } else {
        package.join(".venv").join("bin").join("pip")
    };
    if !pip.exists() {
        return Err(CliError::Failed(format!(
            "pip not found at {}. Run setup first.",
            pip.display()
        )));
    }
    let status = Command::new(pip)
        .args(["install", "-q", "-r"])
        .arg(requirements)
        .status()
        .map_err(|e| CliError::Failed(format!("Could not run pip: {e}")))?;
    if !status.success() {
        return Err(CliError::Failed(
            "Reinstalling dependencies failed.".to_owned(),
        ));
    }
    Ok(())
}

#[cfg(test)]
mod port_selection_tests {
    use super::*;

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
        let chosen = find_free_port(taken).expect("some port above it is free");
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
        let held = TcpListener::bind(("127.0.0.1", 0)).expect("a port to hold");
        let taken = held.local_addr().unwrap().port();
        assert!(!port_bindable(taken), "a held port must not be bindable");

        drop(held);
        assert!(
            port_bindable(taken),
            "a released port must be bindable again"
        );
    }
}
