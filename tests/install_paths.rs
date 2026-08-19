//! The installer and the CLI must name the same directories.
//!
//! `vadgr update` rebuilds the checkout the installer created. When the two
//! disagree the update reports a checkout that is not there, and the message
//! names a directory nothing ever wrote. That shipped: the installer moved to
//! `~/.vadgr` while the CLI still resolved the repository's former name, and
//! only a sweep of the whole surface caught it, inside an error string.

use std::path::Path;

fn repo_file(name: &str) -> String {
    std::fs::read_to_string(Path::new(env!("CARGO_MANIFEST_DIR")).join(name))
        .unwrap_or_else(|_| panic!("{name} is in the repository"))
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
    assert_eq!(assignment("setup.sh", "VADGR_HOME"), "$HOME/.vadgr");
    let service = repo_file("src/cli/commands/service.rs");
    assert!(
        service.contains(r#"user_home().join(".vadgr")"#),
        "the CLI must default to the directory the installer creates"
    );
}

#[test]
fn the_installer_puts_the_checkout_where_the_cli_looks_for_it() {
    assert_eq!(assignment("setup.sh", "VADGR_REPO"), "$VADGR_HOME/src");
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
        "setup.sh",
        "setup.ps1",
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
