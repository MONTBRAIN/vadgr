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

async fn wait_for_api(port: u16) -> Result<bool, CliError> {
    let client = Client::new(format!("http://127.0.0.1:{port}")).map_err(CliError::Failed)?;
    let deadline = std::time::Instant::now() + API_STARTUP_TIMEOUT;
    while std::time::Instant::now() < deadline {
        if client.is_running().await {
            return Ok(true);
        }
        tokio::time::sleep(Duration::from_secs(1)).await;
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

    if !wait_for_api(port).await? {
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
fn git(repo: &Path, args: &[&str]) -> Result<std::process::Output, CliError> {
    Command::new("git")
        .args(args)
        .current_dir(repo)
        .output()
        .map_err(|e| CliError::Failed(format!("Could not run git: {e}")))
}

/// `vadgr update`: bring the checkout forward and rebuild the binary.
///
/// `--check` reports what an update would do and changes nothing, which is what
/// makes the runbook cells for this command runnable at all: before it existed,
/// the only way to test `update` was to run it, and running it changes the
/// installation the rest of the pass is measuring.
///
/// The product is one binary now, so an update is a pull and a build rather than
/// a pull and two dependency installs.
pub async fn update(check: bool) -> Result<(), CliError> {
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
