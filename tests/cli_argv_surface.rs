//! The command tree, asserted through the binary a user runs.
//!
//! The `0.4.3` recorded sweep is the release's own bar and it asserts **argv,
//! exit code and whether output was produced** for 25 rows. It cannot run in
//! `cargo test`, so this file holds the half that can: every verb parses, every
//! flag is accepted, and the codes a script branches on are the shipped ones.
//!
//! **These tests need no daemon.** Each runs against a dead port, so a command
//! that parses reaches the client and reports the daemon as unreachable, exit
//! `3`. That is the signal that parsing succeeded: a `2` means `clap` refused
//! the arguments before any request was made.

use std::process::Command;

/// Nothing listens here, so a parsed command exits `3` rather than doing work.
const DEAD_PORT: &str = "59998";

/// Exit codes, named rather than repeated as digits.
const UNREACHABLE: i32 = 3;
const USAGE: i32 = 2;

fn run(args: &[&str]) -> std::process::Output {
    // The CLI reads a running daemon's port file before the environment, so the
    // home is isolated or these tests would find a real daemon.
    let home = std::env::temp_dir().join(format!("vadgr-argv-test-{}", std::process::id()));
    let mut command = Command::new(env!("CARGO_BIN_EXE_vadgr"));
    command
        .args(args)
        .env("VADGR_HOME", &home)
        .env("VADGR_PORT", DEAD_PORT);
    // A key in the developer's own environment would be used instead of a
    // prompt, and the command would then reach the daemon rather than refuse.
    // The result must not depend on whose machine runs the test.
    for key in [
        "OPENAI_API_KEY",
        "GEMINI_API_KEY",
        "GOOGLE_API_KEY",
        "ANTHROPIC_API_KEY",
    ] {
        command.env_remove(key);
    }
    command.output().expect("the CLI binary runs")
}

fn code(args: &[&str]) -> i32 {
    run(args).status.code().unwrap_or(-1)
}

#[cfg(target_os = "linux")]
#[test]
fn installed_status_bounds_special_and_oversized_records_without_changing_them() {
    use std::os::unix::fs::MetadataExt;
    use std::process::Stdio;
    use std::time::{Duration, Instant};
    if vadgr_daemon::platform::machine_platform() != "linux" {
        return;
    }
    for name in ["api.pid", "api.port"] {
        for kind in ["fifo", "oversized", "symlink"] {
            let root = tempfile::tempdir().unwrap();
            let records = root.path().join("service/pids");
            std::fs::create_dir_all(&records).unwrap();
            std::fs::write(records.join("api.pid"), "invalid").unwrap();
            std::fs::write(records.join("api.port"), "0").unwrap();
            let path = records.join(name);
            std::fs::remove_file(&path).unwrap();
            let target = root.path().join("unrelated");
            std::fs::write(&target, "do not change").unwrap();
            match kind {
                "fifo" => rustix::fs::mkfifoat(
                    rustix::fs::CWD,
                    &path,
                    rustix::fs::Mode::RUSR | rustix::fs::Mode::WUSR,
                )
                .unwrap(),
                "oversized" => std::fs::write(&path, vec![b'9'; 4097]).unwrap(),
                "symlink" => std::os::unix::fs::symlink(&target, &path).unwrap(),
                _ => unreachable!(),
            }
            let before = std::fs::symlink_metadata(&path).unwrap();
            let mut child = Command::new(env!("CARGO_BIN_EXE_vadgr"))
                .arg("status")
                .env("HOME", root.path())
                .env("VADGR_HOME", root.path().join("service"))
                .env("VADGR_INSTALL_ROOT", root.path().join("installed-intent"))
                .env_remove("VADGR_API_URL")
                .env_remove("APPDIR")
                .env_remove("APPIMAGE")
                .stdout(Stdio::piped())
                .stderr(Stdio::piped())
                .spawn()
                .unwrap();
            let deadline = Instant::now() + Duration::from_secs(3);
            while child.try_wait().unwrap().is_none() && Instant::now() < deadline {
                std::thread::sleep(Duration::from_millis(5));
            }
            let timed_out = child.try_wait().unwrap().is_none();
            if timed_out {
                child.kill().unwrap();
            }
            let output = child.wait_with_output().unwrap();
            assert!(
                !timed_out,
                "{name} {kind}: installed status blocked on an untrusted record"
            );
            assert!(output.status.success());
            assert!(String::from_utf8_lossy(&output.stdout).contains("cleanup required"));
            let after = std::fs::symlink_metadata(&path).unwrap();
            assert_eq!(
                (
                    before.dev(),
                    before.ino(),
                    before.len(),
                    before.ctime(),
                    before.ctime_nsec()
                ),
                (
                    after.dev(),
                    after.ino(),
                    after.len(),
                    after.ctime(),
                    after.ctime_nsec()
                )
            );
            assert_eq!(std::fs::read(&target).unwrap(), b"do not change");
        }
    }
}

/// Every verb and sub-verb that talks to the daemon parses and reaches it.
#[test]
fn every_daemon_facing_command_parses() {
    let commands: &[&[&str]] = &[
        &["health"],
        &["providers"],
        &["computer-use", "status"],
        &["computer-use", "enable"],
        &["computer-use", "disable"],
        &["pair"],
        &["provider", "status"],
        &["provider", "status", "--refresh"],
        &["provider", "status", "openai"],
        &["provider", "logout", "gemini"],
        &["model", "list"],
        &["model", "default"],
        &["model", "default", "openai/gpt-5.6-sol"],
        &["runs"],
        &["runs", "list"],
        &["runs", "list", "--status", "failed"],
        &["runs", "get", "abcd1234"],
        &["runs", "cancel", "abcd1234"],
        &["runs", "resume", "abcd1234"],
        &["run", "tidy the desktop"],
        &["run", "tidy the desktop", "--background"],
        &["run", "tidy the desktop", "--json"],
    ];
    for args in commands {
        assert_eq!(
            code(args),
            UNREACHABLE,
            "{args:?} did not reach the daemon; a 2 means clap refused it"
        );
    }
}

/// `vadgr status` answers with the daemon down, because "what is running" is
/// exactly the question someone asks then. It exits `0` and prints the table.
#[test]
fn status_answers_with_the_daemon_down() {
    let out = run(&["status"]);
    assert_eq!(
        out.status.code(),
        Some(0),
        "a stopped daemon is not an error"
    );
    let stdout = String::from_utf8_lossy(&out.stdout);
    assert!(
        stdout.contains("api"),
        "the table names the service: {stdout}"
    );
    assert!(stdout.contains("stopped"), "and its state: {stdout}");
}

#[cfg(target_os = "linux")]
#[test]
fn installed_dispatch_status_preserves_failed_start_pid_and_port_fences() {
    if vadgr_daemon::platform::machine_platform() != "linux" {
        return;
    }
    // No stop/start/network command is invoked. This is the actual CLI main
    // dispatch, including implicit base_url resolution before status runs.
    for locator in ["APPDIR", "APPIMAGE", "VADGR_INSTALL_ROOT"] {
        let live_unrelated_pid = std::process::id().to_string();
        for pid in [
            "",
            "0",
            "2147483647",
            "4294967295",
            "invalid",
            live_unrelated_pid.as_str(),
        ] {
            let temp = tempfile::tempdir().unwrap();
            let records = temp.path().join("service/pids");
            std::fs::create_dir_all(&records).unwrap();
            let pid_path = records.join("api.pid");
            let port_path = records.join("api.port");
            std::fs::write(&pid_path, pid).unwrap();
            // An owned ephemeral listener prevents any dependency on a real
            // default port. Status neither connects nor signals anything.
            let listener = std::net::TcpListener::bind(("127.0.0.1", 0)).unwrap();
            let port = listener.local_addr().unwrap().port().to_string();
            std::fs::write(&port_path, &port).unwrap();
            let mut command = Command::new(env!("CARGO_BIN_EXE_vadgr"));
            command
                .arg("status")
                .env("HOME", temp.path())
                .env("VADGR_HOME", temp.path().join("service"))
                .env("VADGR_PORT", &port)
                .env_remove("VADGR_API_URL")
                .env_remove("APPDIR")
                .env_remove("APPIMAGE")
                .env_remove("VADGR_INSTALL_ROOT");
            command.env(locator, temp.path().join("installed-intent"));
            let result = command.output().unwrap();
            assert!(
                result.status.success(),
                "{locator}, PID {pid:?}: {}",
                String::from_utf8_lossy(&result.stderr)
            );
            let output = String::from_utf8(result.stdout).unwrap();
            assert!(output.contains("cleanup required"));
            assert!(output.contains("descendant cleanup is unproved"));
            assert!(output.contains("Verified cleanup is required"));
            assert!(
                !output.contains("stopped"),
                "a missing parent is not proof of stopped descendants"
            );
            assert_eq!(
                std::fs::read(&pid_path).unwrap(),
                pid.as_bytes(),
                "{locator}: PID fence changed during dispatch"
            );
            assert_eq!(
                std::fs::read(&port_path).unwrap(),
                port.as_bytes(),
                "{locator}: port fence changed during dispatch"
            );
            assert_eq!(listener.local_addr().unwrap().port().to_string(), port);
        }
    }
}

#[cfg(unix)]
#[test]
fn ordinary_unix_status_discards_invalid_pid_records_without_process_probe() {
    for pid in ["0", "2147483648", "4294967295"] {
        let root = tempfile::tempdir().unwrap();
        let records = root.path().join("service/pids");
        std::fs::create_dir_all(&records).unwrap();
        std::fs::write(records.join("api.pid"), pid).unwrap();
        std::fs::write(records.join("api.port"), "0").unwrap();
        let output = Command::new(env!("CARGO_BIN_EXE_vadgr"))
            .arg("status")
            .env("HOME", root.path())
            .env("VADGR_HOME", root.path().join("service"))
            .env_remove("VADGR_API_URL")
            .env_remove("APPDIR")
            .env_remove("APPIMAGE")
            .env_remove("VADGR_INSTALL_ROOT")
            .output()
            .unwrap();
        assert!(
            output.status.success(),
            "PID {pid}: {}",
            String::from_utf8_lossy(&output.stderr)
        );
        assert!(String::from_utf8_lossy(&output.stdout).contains("stopped"));
        assert!(!records.join("api.pid").exists());
        assert!(!records.join("api.port").exists());
    }
}

/// The commands that ask a person a question before they touch the daemon.
///
/// **A prompt fails closed when there is no terminal.** Reading EOF in a loop
/// would hang a script for ever instead of telling it what is wrong. The exit is
/// `1` with a named reason, never a wait.
#[test]
fn a_prompt_without_a_terminal_fails_closed() {
    for args in [
        vec!["provider", "login"],
        vec!["provider", "login", "openai"],
        vec!["provider", "login", "openai", "--auth", "api-key"],
    ] {
        let out = run(&args);
        assert_eq!(out.status.code(), Some(1), "{args:?} must not hang or pass");
        let stderr = String::from_utf8_lossy(&out.stderr);
        assert!(
            stderr.contains("terminal"),
            "{args:?} must say why: {stderr}"
        );
    }
}

/// The short flags a person actually types.
#[test]
fn the_short_flags_are_accepted() {
    assert_eq!(code(&["runs", "list", "-s", "failed"]), UNREACHABLE);
    assert_eq!(code(&["run", "do it", "-b"]), UNREACHABLE);
    assert_eq!(
        code(&["run", "do it", "-p", "openai", "-m", "gpt-5.6-sol"]),
        UNREACHABLE
    );
}

/// `vadgr api` and `vadgr start` are the same command under two names, and
/// `--port` is the spelling the old `api` used. Neither is blessed by this
/// release; both are kept because the sweep asserts argv.
#[test]
fn the_service_verbs_and_both_port_spellings_parse() {
    for args in [
        vec!["start", "--help"],
        vec!["api", "--help"],
        vec!["restart", "--help"],
        vec!["stop", "--help"],
        vec!["logs", "--help"],
        vec!["update", "--help"],
    ] {
        let out = run(&args);
        assert_eq!(out.status.code(), Some(0), "{args:?} has no help");
        assert!(!out.stdout.is_empty(), "{args:?} printed no help");
    }
    let help = String::from_utf8_lossy(&run(&["start", "--help"]).stdout).to_string();
    assert!(help.contains("--api-port"), "{help}");
    assert!(help.contains("--port"), "the old spelling still reaches it");
}

/// The two argument rules the parser cannot express, so the command checks them.
#[test]
fn the_hand_checked_argument_rules_exit_two() {
    assert_eq!(
        code(&["run", "   "]),
        USAGE,
        "an empty task is a usage error, not a run"
    );
    assert_eq!(
        code(&["run", "do it", "--provider", "openai"]),
        USAGE,
        "--provider without --model is a usage error"
    );
    assert_eq!(
        code(&["run", "do it", "--model", "gpt-5.6-sol"]),
        USAGE,
        "--model without --provider is a usage error"
    );
}

/// A missing required argument exits `2`, the shipped code for a usage error.
#[test]
fn a_missing_argument_exits_two() {
    for args in [
        vec!["runs", "get"],
        vec!["runs", "cancel"],
        vec!["runs", "resume"],
        vec!["run"],
        vec!["provider", "logout"],
    ] {
        assert_eq!(code(&args), USAGE, "{args:?} should be a usage error");
    }
}

/// An unknown verb is refused rather than silently ignored.
#[test]
fn an_unknown_command_exits_two() {
    assert_eq!(code(&["registry", "list"]), USAGE);
    assert_eq!(code(&["agents"]), USAGE);
    assert_eq!(code(&["workflow", "run"]), USAGE);
}

/// The surfaces deleted at `0.4.4` must not come back through the CLI, and a
/// guardrail is cheaper than remembering.
#[test]
fn the_deleted_surfaces_have_no_verb() {
    let help = String::from_utf8_lossy(&run(&["--help"]).stdout).to_string();
    for gone in ["registry", "agent", "workflow", "project", "forge"] {
        assert!(
            !help.contains(gone),
            "the help still names the deleted `{gone}` surface:\n{help}"
        );
    }
}

/// The tree a user sees, in full. A verb that disappears in a port is exactly
/// what the sweep exists to catch, and this catches it before the sweep runs.
#[test]
fn the_help_lists_every_shipped_verb() {
    let help = String::from_utf8_lossy(&run(&["--help"]).stdout).to_string();
    for verb in [
        "api",
        "computer-use",
        "health",
        "logs",
        "model",
        "pair",
        "provider",
        "providers",
        "restart",
        "run",
        "runs",
        "start",
        "status",
        "stop",
        "update",
    ] {
        assert!(
            help.contains(verb),
            "the help does not list `{verb}`:\n{help}"
        );
    }
}

/// `--api-url` overrides everything, and it is hidden because it is a debugging
/// aid rather than part of the surface.
#[test]
fn the_api_url_override_is_accepted_and_hidden() {
    assert_eq!(
        code(&["--api-url", "http://127.0.0.1:59997", "health"]),
        UNREACHABLE
    );
    let help = String::from_utf8_lossy(&run(&["--help"]).stdout).to_string();
    assert!(!help.contains("--api-url"), "a hidden flag stays hidden");
}

/// `vadgr update --check` reports and changes nothing, which is what makes the
/// blocked runbook cells runnable. It needs no daemon at all.
#[test]
fn the_update_check_needs_no_daemon_and_refuses_a_non_checkout() {
    let out = run(&["update", "--check"]);
    // The isolated home has no clone in it, so the command says so and exits 1
    // rather than reaching for the network.
    assert_eq!(out.status.code(), Some(1));
    let stderr = String::from_utf8_lossy(&out.stderr);
    assert!(
        stderr.contains("not a git checkout"),
        "it must name why: {stderr}"
    );
}

#[test]
fn update_help_exposes_the_explicit_signed_source() {
    let output = run(&["update", "--help"]);
    assert!(output.status.success());
    let help = String::from_utf8_lossy(&output.stdout);
    assert!(help.contains("--source <URL_OR_DIRECTORY>"), "{help}");
    assert!(
        help.contains("HTTPS or an absolute local directory"),
        "{help}"
    );
}
