//! Signed macOS responsible-process host for the private CUA interpreter.

#[cfg(target_os = "macos")]
fn main() {
    use std::ffi::OsString;
    use std::process::Command;

    let mut arguments = std::env::args_os().skip(1);
    let mut python = None;
    let mut child = Vec::<OsString>::new();
    while let Some(argument) = arguments.next() {
        if argument == "--python" {
            python = arguments.next();
        } else if argument == "--" {
            child.extend(arguments);
            break;
        } else {
            fail("the CUA host received an unsupported argument");
        }
    }
    let Some(python) = python else {
        fail("the CUA host received no private interpreter")
    };
    if child.is_empty() {
        fail("the CUA host received no private command")
    }
    let status = Command::new(python)
        .args(child)
        .status()
        .unwrap_or_else(|error| {
            fail(&format!(
                "the private CUA interpreter did not start: {error}"
            ))
        });
    std::process::exit(status.code().unwrap_or(1));
}

#[cfg(target_os = "macos")]
fn fail(message: &str) -> ! {
    eprintln!("{message}");
    std::process::exit(1)
}

#[cfg(not(target_os = "macos"))]
fn main() {
    eprintln!("vadgr-cua-host is available only in the signed macOS package");
    std::process::exit(1);
}
