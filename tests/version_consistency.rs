//! The manifest, the daemon and the changelog agree on the version.
//!
//! **Nothing checked this, and it drifted**: the crate moved to `0.4.7` while
//! the other half of the product still answered `0.4.5`, and the gap shipped as
//! far as a pull request caveat before anyone noticed. There is one daemon now,
//! which makes the check smaller and not less necessary: `GET /api/health` is
//! what a phone reads to decide whether it is talking to the machine it thinks
//! it is.
//!
//! The changelog is included because a version that moves without an entry is
//! the same defect one step earlier.

use std::path::{Path, PathBuf};

fn repo() -> PathBuf {
    Path::new(env!("CARGO_MANIFEST_DIR")).to_path_buf()
}

fn manifest_version() -> String {
    let text = std::fs::read_to_string(repo().join("Cargo.toml")).expect("the manifest reads");
    for line in text.lines() {
        if let Some(rest) = line.strip_prefix("version = ") {
            return rest.trim().trim_matches('"').to_owned();
        }
    }
    panic!("the manifest has no top-level version");
}

#[test]
fn the_daemon_reports_the_version_the_manifest_declares() {
    assert_eq!(
        vadgr_daemon::config::VERSION,
        manifest_version(),
        "the daemon and the manifest disagree, so a client cannot tell which \
         half answered it"
    );
}

#[test]
fn the_changelog_names_this_version_first() {
    let text = std::fs::read_to_string(repo().join("CHANGELOG.md")).expect("the changelog reads");
    let first = text
        .lines()
        .find(|line| line.starts_with("## ["))
        .expect("the changelog has a version heading");
    let version = manifest_version();
    assert!(
        first.contains(&version),
        "the newest changelog entry is {first:?} and the manifest says {version}. \
         A version that moves without an entry is a release nobody can read."
    );
}
