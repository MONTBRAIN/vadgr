//! The installer and the CLI must name the same directories.
//!
//! `vadgr update` rebuilds the checkout the installer created. When the two
//! disagree the update reports a checkout that is not there, and the message
//! names a directory nothing ever wrote. That shipped: the installer moved to
//! `~/.vadgr` while the CLI still resolved the repository's former name, and
//! only a sweep of the whole surface caught it, inside an error string.

use std::path::Path;

fn repo_file(name: &str) -> String {
    // Normalised, because a checkout on Windows can carry CRLF and a pattern
    // written with `\n` would match nothing there. A source-reading test that
    // ignores this fails on exactly one platform.
    std::fs::read_to_string(Path::new(env!("CARGO_MANIFEST_DIR")).join(name))
        .unwrap_or_else(|_| panic!("{name} is in the repository"))
        .replace("\r\n", "\n")
}

fn assignment(script: &str, name: &str) -> String {
    let text = repo_file(script);
    let line = text
        .lines()
        .find(|line| line.trim_start().starts_with(&format!("{name}=")))
        .unwrap_or_else(|| panic!("{script} sets {name}"));
    line.split_once('=')
        .expect("an assignment")
        .1
        .trim()
        .trim_matches('"')
        .to_owned()
}

#[test]
fn the_installer_and_the_cli_agree_on_the_product_directory() {
    assert_eq!(assignment("install.sh", "VADGR_HOME"), "$HOME/.vadgr");
    let service = repo_file("src/cli/commands/service.rs");
    assert!(
        service.contains(r#"user_home().join(".vadgr")"#),
        "the CLI must default to the directory the installer creates"
    );
}

#[test]
fn the_installer_puts_the_checkout_where_the_cli_looks_for_it() {
    assert_eq!(assignment("install.sh", "VADGR_REPO"), "$VADGR_HOME/src");
    let service = repo_file("src/cli/commands/service.rs");
    assert!(
        service.contains(r#"vadgr_home().join("src")"#),
        "the CLI must rebuild the checkout the installer created"
    );
}

#[test]
fn nothing_shipped_still_carries_the_repositorys_former_name() {
    let mut checked = 0;
    for name in [
        "install.sh",
        "install.ps1",
        "README.md",
        "src/cli/commands/service.rs",
    ] {
        let text = repo_file(name);
        for stale in ["Agent-Forge", ".forge", "agent_forge"] {
            assert!(
                !text.contains(stale),
                "{name} still names {stale}, which this release removes"
            );
        }
        checked += 1;
    }
    assert_eq!(checked, 4);
    // The consolidation is the one place the old database name is allowed: it
    // is the file being moved off a machine that upgrades.
    assert!(
        repo_file("src/migrate.rs").contains("agent_forge.db"),
        "the consolidation still has to find the departing database"
    );
}

#[test]
fn every_relative_link_in_the_readme_resolves() {
    // The README outlived three of its own links: two pointed at the Python
    // tree's own READMEs and one at a guide for a provider format the product
    // stopped reading. Nothing failed, so nobody noticed until the files were
    // counted.
    let readme = repo_file("README.md");
    let root = Path::new(env!("CARGO_MANIFEST_DIR"));
    let mut seen = 0;
    let mut rest = readme.as_str();
    while let Some(open) = rest.find("](") {
        let after = &rest[open + 2..];
        let Some(close) = after.find(')') else { break };
        let target = &after[..close];
        rest = &after[close..];
        seen += 1;
        if target.starts_with("http") || target.starts_with('#') || target.is_empty() {
            continue;
        }
        let file = target.split('#').next().unwrap_or(target);
        if file.is_empty() {
            continue;
        }
        assert!(
            root.join(file).exists(),
            "README.md links to {file}, which is not in the repository"
        );
    }
    // The README carries no relative link today, and that is allowed. What is
    // not allowed is this test reading nothing and reporting success, so it
    // proves it parsed the links it did find.
    assert!(seen > 0, "no links were parsed out of README.md at all");
}

#[test]
fn no_interpreter_artefact_is_tracked_in_this_repository() {
    // The cutover checked for `.py` files and found none outside the two named
    // exceptions, while 1441 files of committed Windows bytecode sat in a
    // virtual environment beside them. A check that names one extension proves
    // one extension.
    let root = Path::new(env!("CARGO_MANIFEST_DIR"));
    let listing = std::process::Command::new("git")
        .args(["ls-files"])
        .current_dir(root)
        .output()
        .expect("git lists the tracked files");
    assert!(listing.status.success(), "git ls-files failed");
    let files = String::from_utf8(listing.stdout).expect("the listing is text");
    let mut tracked = 0;
    for file in files.lines() {
        tracked += 1;
        for artefact in [".pyc", ".pyo", ".pyd", ".egg-info", "__pycache__/"] {
            assert!(
                !file.contains(artefact),
                "{file} is an interpreter artefact and must not be tracked"
            );
        }
        for venv in [".venv", "venv/", "site-packages/"] {
            assert!(
                !file.contains(venv),
                "{file} belongs to a virtual environment and must not be tracked"
            );
        }
    }
    assert!(tracked > 50, "the listing looks empty: {tracked} files");

    // Every surviving `.py` is a gate, an E2E harness or the declared bundled
    // payload launcher. Product implementation remains Rust.
    for file in files.lines().filter(|f| f.ends_with(".py")) {
        assert!(
            file.starts_with("scripts/")
                || file.starts_with("E2E/")
                || file == "packaging/cua/bootstrap.py",
            "{file} is Python outside the declared gates, harnesses and payload"
        );
    }
}

#[test]
fn the_product_is_one_executable() {
    // A user received two files, `vadgr` and `vadgr-daemon`, and the CLI found
    // the daemon beside itself on disk. That asked a user to hold a detail that
    // belongs to the program, doubled what distribution must sign and publish,
    // and allowed the two halves to be different versions. It is one file: it
    // serves when invoked with `serve` and acts as the client otherwise.
    let manifest = repo_file("Cargo.toml");
    let targets = manifest.matches("[[bin]]").count();
    assert_eq!(targets, 1, "the crate must build exactly one binary");
    assert!(
        manifest.contains("name = \"vadgr\""),
        "the one binary is named vadgr"
    );

    // The installers copy one file, and nothing looks for a sibling daemon.
    for script in ["install.sh", "install.ps1"] {
        let text = repo_file(script);
        assert!(
            !text.contains("vadgr-daemon"),
            "{script} still installs a second binary"
        );
    }
    let service = repo_file("src/cli/commands/service.rs");
    assert!(
        service.contains("std::env::current_exe()"),
        "the daemon a start spawns is this executable"
    );
    assert!(
        service.contains("command.arg(\"serve\")"),
        "the spawned child is told to serve"
    );
}

#[test]
fn clean_install_checks_follow_the_payload_manifest() {
    // The clean-install jobs once named a prior payload generation and prior
    // CUA version directly. A pin update then broke every clean-install leg,
    // although the installer had assembled the new payload correctly.
    let workflow = repo_file(".github/workflows/ci.yml");
    assert!(
        !workflow.contains("/lib/cua/environments/0.")
            && !workflow.contains(r"\lib\cua\environments\0."),
        "clean-install must discover the private generation instead of typing one"
    );
    assert!(
        workflow.matches("lib/cua/payload.json").count()
            + workflow.matches(r"lib\cua\payload.json").count()
            >= 3,
        "every clean-install path must validate versions against payload.json"
    );
}
