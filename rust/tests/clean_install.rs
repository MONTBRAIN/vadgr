use serde_json::{Value, json};
use std::fs;
use std::io::{Read, Write};
use std::net::{SocketAddr, TcpListener, TcpStream};
use std::path::Path;
use std::process::{Command, Output, Stdio};
use std::thread;
use std::time::{Duration, Instant, SystemTime, UNIX_EPOCH};

const STARTUP_TIMEOUT: Duration = Duration::from_secs(20);

fn validate_health(payload: &Value) -> Result<(), String> {
    let expected = [
        ("status", json!("healthy")),
        ("version", json!("0.4.5")),
        ("platform", json!("linux")),
        ("modules", json!({"computer_use": false})),
        (
            "transport",
            json!({
                "name": "loopback",
                "available": true,
                "advertise_host": null,
                "bind_host": "127.0.0.1",
            }),
        ),
    ];

    for (field, value) in expected {
        if payload.get(field) != Some(&value) {
            return Err(format!(
                "health field {field:?} was {:?}, expected {value}",
                payload.get(field)
            ));
        }
    }
    Ok(())
}

fn unused_loopback_port() -> Result<u16, String> {
    let listener = TcpListener::bind(("127.0.0.1", 0))
        .map_err(|error| format!("reserve a loopback port: {error}"))?;
    listener
        .local_addr()
        .map(|address| address.port())
        .map_err(|error| format!("read reserved loopback port: {error}"))
}

fn command_output(command: &mut Command, context: &str) -> Result<Output, String> {
    let output = command
        .output()
        .map_err(|error| format!("{context}: {error}"))?;
    if output.status.success() {
        return Ok(output);
    }
    Err(format!(
        "{context} failed with {}\nstdout:\n{}\nstderr:\n{}",
        output.status,
        String::from_utf8_lossy(&output.stdout),
        String::from_utf8_lossy(&output.stderr)
    ))
}

fn raw_health(port: u16) -> Result<Value, String> {
    let address = SocketAddr::from(([127, 0, 0, 1], port));
    let mut stream = TcpStream::connect_timeout(&address, Duration::from_secs(1))
        .map_err(|error| format!("connect to {address}: {error}"))?;
    stream
        .set_read_timeout(Some(Duration::from_secs(1)))
        .map_err(|error| format!("set read timeout: {error}"))?;
    stream
        .set_write_timeout(Some(Duration::from_secs(1)))
        .map_err(|error| format!("set write timeout: {error}"))?;
    stream
        .write_all(b"GET /api/health HTTP/1.1\r\nHost: 127.0.0.1\r\nConnection: close\r\n\r\n")
        .map_err(|error| format!("write health request: {error}"))?;

    let mut response = Vec::new();
    stream
        .read_to_end(&mut response)
        .map_err(|error| format!("read health response: {error}"))?;
    let separator = response
        .windows(4)
        .position(|window| window == b"\r\n\r\n")
        .ok_or_else(|| "health response had no header separator".to_string())?;
    let (headers, body) = response.split_at(separator + 4);
    let status = headers
        .split(|byte| *byte == b'\n')
        .next()
        .ok_or_else(|| "health response had no status line".to_string())?;
    if !status.windows(5).any(|window| window == b" 200 ") {
        return Err(format!(
            "health returned a non-200 status: {}",
            String::from_utf8_lossy(status).trim()
        ));
    }
    serde_json::from_slice(body).map_err(|error| format!("decode health body: {error}"))
}

fn container_state(docker: &str, container: &str) -> Result<String, String> {
    let output = command_output(
        Command::new(docker).args([
            "inspect",
            "--format",
            "status={{.State.Status}} exit={{.State.ExitCode}} error={{.State.Error}}",
            container,
        ]),
        "inspect clean-install container",
    )?;
    Ok(String::from_utf8_lossy(&output.stdout).trim().to_string())
}

fn container_logs(docker: &str, container: &str) -> String {
    Command::new(docker)
        .args(["logs", container])
        .output()
        .map(|output| {
            format!(
                "stdout:\n{}\nstderr:\n{}",
                String::from_utf8_lossy(&output.stdout),
                String::from_utf8_lossy(&output.stderr)
            )
        })
        .unwrap_or_else(|error| format!("could not read container logs: {error}"))
}

struct DockerCleanup {
    docker: String,
    container: String,
    image: String,
}

impl Drop for DockerCleanup {
    fn drop(&mut self) {
        let _ = Command::new(&self.docker)
            .args(["rm", "--force", &self.container])
            .stdout(Stdio::null())
            .stderr(Stdio::null())
            .status();
        let _ = Command::new(&self.docker)
            .args(["image", "rm", "--force", &self.image])
            .stdout(Stdio::null())
            .stderr(Stdio::null())
            .status();
    }
}

fn run_clean_install(binary: &Path, docker: &str) -> Result<Value, String> {
    if !binary.is_file() {
        return Err(format!(
            "release binary does not exist: {}",
            binary.display()
        ));
    }

    let nonce = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map_err(|error| format!("read clock: {error}"))?
        .as_nanos();
    let image = format!("vadgr-clean-install-{}-{nonce}", std::process::id());
    let container = format!("{image}-run");
    let _cleanup = DockerCleanup {
        docker: docker.to_string(),
        container: container.clone(),
        image: image.clone(),
    };

    let context = tempfile::tempdir().map_err(|error| format!("create build context: {error}"))?;
    let installed_binary = context.path().join("vadgr-daemon");
    fs::copy(binary, &installed_binary).map_err(|error| {
        format!(
            "copy {} into clean build context: {error}",
            binary.display()
        )
    })?;
    #[cfg(unix)]
    {
        use std::os::unix::fs::PermissionsExt;
        fs::set_permissions(&installed_binary, fs::Permissions::from_mode(0o755))
            .map_err(|error| format!("mark release binary executable: {error}"))?;
    }
    fs::write(
        context.path().join("Dockerfile"),
        "FROM scratch\nCOPY vadgr-daemon /usr/local/bin/vadgr-daemon\nENTRYPOINT [\"/usr/local/bin/vadgr-daemon\"]\n",
    )
    .map_err(|error| format!("write scratch Dockerfile: {error}"))?;

    command_output(
        Command::new(docker).args([
            "build",
            "--network=none",
            "--tag",
            &image,
            context
                .path()
                .to_str()
                .ok_or("build context is not UTF-8")?,
        ]),
        "build scratch image",
    )?;
    let port = unused_loopback_port()?;
    let port_environment = format!("VADGR_PORT={port}");
    command_output(
        Command::new(docker).args([
            "run",
            "--detach",
            "--name",
            &container,
            "--network",
            "host",
            "--env",
            "VADGR_CONFIG_HOME=/var/lib/vadgr",
            "--env",
            "VADGR_DB=/var/lib/vadgr/vadgr.db",
            "--env",
            "VADGR_PROVIDERS=/var/lib/vadgr/providers.yaml",
            "--env",
            &port_environment,
            "--env",
            "VADGR_TRANSPORT=loopback",
            &image,
        ]),
        "start installed daemon",
    )?;

    let deadline = Instant::now() + STARTUP_TIMEOUT;
    let mut last_error = "the first health request has not run".to_string();
    while Instant::now() < deadline {
        let state = container_state(docker, &container)?;
        if !state.contains("status=running") {
            return Err(format!(
                "installed daemon exited before readiness: {state}\n{}",
                container_logs(docker, &container)
            ));
        }
        match raw_health(port).and_then(|payload| {
            validate_health(&payload)?;
            Ok(payload)
        }) {
            Ok(payload) => return Ok(payload),
            Err(error) => last_error = error,
        }
        thread::sleep(Duration::from_millis(250));
    }

    Err(format!(
        "installed daemon did not become ready within {}s: {last_error}\n{}\n{}",
        STARTUP_TIMEOUT.as_secs(),
        container_state(docker, &container)?,
        container_logs(docker, &container)
    ))
}

#[test]
fn the_clean_install_health_shape_is_accepted() {
    let payload = json!({
        "status": "healthy",
        "version": "0.4.5",
        "platform": "linux",
        "modules": {"computer_use": false},
        "transport": {
            "name": "loopback",
            "available": true,
            "advertise_host": null,
            "bind_host": "127.0.0.1",
        },
    });

    validate_health(&payload).unwrap();
}

#[test]
fn each_required_health_fact_is_checked() {
    let expected = json!({
        "status": "healthy",
        "version": "0.4.5",
        "platform": "linux",
        "modules": {"computer_use": false},
        "transport": {
            "name": "loopback",
            "available": true,
            "advertise_host": null,
            "bind_host": "127.0.0.1",
        },
    });
    let mutations = [
        ("status", json!("degraded")),
        ("version", json!("0.4.4")),
        ("platform", json!("wsl")),
        ("modules", json!({"computer_use": true})),
        ("transport", json!({"name": "loopback"})),
    ];

    for (field, value) in mutations {
        let mut payload = expected.clone();
        payload[field] = value;
        let error = validate_health(&payload).unwrap_err();
        assert!(error.contains(field), "{error}");
    }
}

#[test]
fn a_loopback_port_can_be_reserved_for_the_installed_daemon() {
    assert_ne!(unused_loopback_port().unwrap(), 0);
}

#[test]
#[ignore = "requires a static release binary and Docker"]
fn installed_release_starts_and_serves() {
    let binary = std::env::var_os("VADGR_RELEASE_BINARY")
        .expect("VADGR_RELEASE_BINARY must name the static release binary");
    let docker = std::env::var("DOCKER").unwrap_or_else(|_| "docker".to_string());
    let payload = run_clean_install(Path::new(&binary), &docker).unwrap();
    println!("clean install served: {payload}");
}
