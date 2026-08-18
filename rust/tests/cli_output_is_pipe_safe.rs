//! Piped CLI output carries no terminal escape sequences.
//!
//! This is a regression test for a real defect, found by driving the CLI rather
//! than by a unit test. `anstyle` describes a style; it does not decide whether
//! to emit one. Printing a styled string through `std::println!` writes the
//! escapes unconditionally, so `vadgr runs list > file` wrote
//! `\x1b[34m[vadgr]\x1b[0m No runs yet.` into the file.
//!
//! The shipped Python CLI writes clean text when piped, so this was a
//! regression rather than a new rough edge, and the migration standard's ratchet
//! makes a regression block the release.
//!
//! The command here needs no daemon: with nothing listening, the CLI reports the
//! daemon as unreachable, and that message is styled.

use std::process::Command;

/// A port chosen to have nothing on it, so the CLI takes its unreachable path.
const DEAD_PORT: &str = "59999";

/// The CLI reads a running daemon's port file before it reads the environment,
/// which is what makes `vadgr health` reach a daemon that walked up from a busy
/// port. A test that did not isolate the home would therefore read the port of
/// whatever daemon the developer happens to be running.
fn isolated(args: &[&str]) -> std::process::Output {
    let home = std::env::temp_dir().join(format!("vadgr-cli-test-{}", std::process::id()));
    Command::new(env!("CARGO_BIN_EXE_vadgr-cli"))
        .args(args)
        .env("VADGR_HOME", &home)
        .env("VADGR_PORT", DEAD_PORT)
        .output()
        .expect("the CLI binary runs")
}

#[test]
fn piped_output_carries_no_escape_sequences() {
    let out = isolated(&["health"]);

    let stdout = String::from_utf8_lossy(&out.stdout);
    let stderr = String::from_utf8_lossy(&out.stderr);

    assert!(
        !stdout.contains('\u{1b}'),
        "stdout carried an escape sequence when piped: {stdout:?}"
    );
    assert!(
        !stderr.contains('\u{1b}'),
        "stderr carried an escape sequence when piped: {stderr:?}"
    );
    assert!(
        !stderr.is_empty(),
        "the unreachable daemon must still say so; a silent pass proves nothing"
    );
}

/// The two failures keep different exit codes, because a script branches on
/// them: "it is down" is retried after a start and "it ran and said no" is not.
#[test]
fn an_unreachable_daemon_exits_three() {
    let out = isolated(&["health"]);
    assert_eq!(out.status.code(), Some(3), "down is exit 3, not 1");
}

/// A usage error is `clap`'s `2`, the same code `click` produced, because the
/// recorded surface sweep asserts exit codes.
#[test]
fn a_usage_error_exits_two() {
    let out = isolated(&["runs", "get"]);
    assert_eq!(
        out.status.code(),
        Some(2),
        "a missing required argument is a usage error"
    );
    assert!(
        !out.stderr.is_empty(),
        "usage goes to stderr, so a shell can separate it from output"
    );
}
