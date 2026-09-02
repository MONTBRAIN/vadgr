#![cfg_attr(target_os = "windows", windows_subsystem = "windows")]

//! Windowless native entry point for Start menu and Startup Apps launch.

use std::process::{Command, Stdio};

fn main() {
    let daemon_only = std::env::args_os()
        .skip(1)
        .any(|argument| argument == "--daemon");
    let Some(directory) = std::env::current_exe()
        .ok()
        .and_then(|path| path.parent().map(std::path::Path::to_owned))
    else {
        return;
    };
    let backend = directory.join(if cfg!(windows) { "vadgr.exe" } else { "vadgr" });
    let mut start = hidden_command(&backend);
    start.arg("start");
    if daemon_only {
        let _ = start.spawn();
        return;
    }

    // An ordinary Start-menu launch owns the ordinary daemon lifecycle. `start`
    // waits for readiness. It also returns promptly when an existing daemon is
    // already running; either way the console then reads the truthful health.
    let _ = start.status();
    let mut command = hidden_command(&backend);
    command.arg("--console");
    let _ = command.spawn();
}

fn hidden_command(executable: &std::path::Path) -> Command {
    let mut command = Command::new(executable);
    command
        .stdin(Stdio::null())
        .stdout(Stdio::null())
        .stderr(Stdio::null());
    hide_window(&mut command);
    command
}

#[cfg(target_os = "windows")]
fn hide_window(command: &mut Command) {
    use std::os::windows::process::CommandExt;
    command.creation_flags(0x0800_0000);
}

#[cfg(not(target_os = "windows"))]
fn hide_window(_command: &mut Command) {}
