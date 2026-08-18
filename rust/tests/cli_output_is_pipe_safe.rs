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

#[test]
fn piped_output_carries_no_escape_sequences() {
    let out = Command::new(env!("CARGO_BIN_EXE_vadgr-cli"))
        .args(["health"])
        .env("VADGR_PORT", DEAD_PORT)
        .output()
        .expect("the CLI binary runs");

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
    let out = Command::new(env!("CARGO_BIN_EXE_vadgr-cli"))
        .args(["health"])
        .env("VADGR_PORT", DEAD_PORT)
        .output()
        .expect("the CLI binary runs");
    assert_eq!(out.status.code(), Some(3), "down is exit 3, not 1");
}

/// A usage error is `clap`'s `2`, the same code `click` produced, because the
/// recorded surface sweep asserts exit codes.
#[test]
fn a_usage_error_exits_two() {
    let out = Command::new(env!("CARGO_BIN_EXE_vadgr-cli"))
        .args(["runs", "get"])
        .output()
        .expect("the CLI binary runs");
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
