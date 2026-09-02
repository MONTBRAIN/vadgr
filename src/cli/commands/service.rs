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

    let mut child = command
        .spawn()
        .map_err(|e| CliError::Failed(format!("Could not start the API: {e}")))?;
    write_pid("api", child.id()).map_err(|e| CliError::Failed(e.to_string()))?;
    write_port("api", port).map_err(|e| CliError::Failed(e.to_string()))?;

    tokio::time::sleep(Duration::from_secs(1)).await;
    if matches!(child.try_wait(), Ok(Some(_))) {
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
    let package =
        vadgr_daemon::install::status().map_err(|error| CliError::Failed(error.to_string()))?;
    if package.installed {
        if check {
            let update = vadgr_daemon::install::check_for_updates()
                .map_err(|error| CliError::Failed(error.to_string()))?;
            if update.update_available {
                anstream::println!(
                    "{}",
                    output::info(&format!("Vadgr {} is available.", update.available_version))
                );
            } else {
                anstream::println!("{}", output::success("vadgr is up to date."));
            }
            return Ok(());
        }
        let update = vadgr_daemon::install::apply_update()
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
