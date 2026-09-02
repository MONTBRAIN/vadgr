use std::path::PathBuf;

fn repo_file(relative: &str) -> String {
    std::fs::read_to_string(PathBuf::from(env!("CARGO_MANIFEST_DIR")).join(relative)).unwrap()
}

fn assert_actions_are_full_sha(workflow: &str) {
    for line in workflow.lines().map(str::trim) {
        let Some(reference) = line.strip_prefix("- uses: ") else {
            continue;
        };
        if reference.starts_with("./") {
            continue;
        }
        let revision = reference
            .split('#')
            .next()
            .unwrap()
            .rsplit_once('@')
            .unwrap()
            .1
            .trim();
        assert_eq!(revision.len(), 40, "action is not pinned: {reference}");
        assert!(
            revision
                .chars()
                .all(|character| character.is_ascii_hexdigit()),
            "action is not pinned: {reference}"
        );
    }
}

#[test]
fn candidate_is_manual_secret_free_and_builds_the_complete_matrix() {
    let workflow = repo_file(".github/workflows/candidate.yml");
    assert!(workflow.contains("workflow_dispatch:"));
    assert!(!workflow.contains("pull_request_target"));
    assert!(!workflow.contains("workflow_run"));
    assert!(!workflow.contains("secrets."));
    assert!(workflow.contains("cancel-in-progress: false"));
    for target in [
        "candidate-linux-${{ matrix.arch }}",
        "candidate-wsl-${{ matrix.arch }}",
        "candidate-macos-${{ matrix.arch }}",
        "candidate-windows-${{ matrix.arch }}",
        "ubuntu-24.04-arm",
        "windows-11-arm",
        "macos-15-intel",
    ] {
        assert!(workflow.contains(target), "candidate omits {target}");
    }
    assert_actions_are_full_sha(&workflow);
}

#[test]
fn release_is_signed_tag_only_and_separates_protected_environments() {
    let workflow = repo_file(".github/workflows/release.yml");
    assert!(workflow.contains("tags:\n      - v*"));
    assert!(!workflow.contains("workflow_dispatch:"));
    assert!(workflow.contains("git verify-tag --raw"));
    assert!(workflow.contains("environment: release-windows"));
    assert!(workflow.contains("environment: release-macos"));
    assert!(workflow.contains("burn detach"));
    assert!(workflow.contains("xcrun notarytool submit"));
    assert!(workflow.contains("--draft --verify-tag"));
    assert!(workflow.contains("cancel-in-progress: false"));
    assert_actions_are_full_sha(&workflow);
}

#[test]
fn signing_inputs_are_environment_scoped_and_never_literal_values() {
    let workflow = repo_file(".github/workflows/release.yml");
    for name in [
        "WINDOWS_PUBLISHER_THUMBPRINT",
        "MACOS_APPLICATION_IDENTITY",
        "MACOS_INSTALLER_IDENTITY",
        "APPROVED_TAG_SIGNER_FINGERPRINT",
    ] {
        assert!(workflow.contains(&format!("vars.{name}")));
    }
    assert!(!workflow.contains("BEGIN PRIVATE KEY"));
    assert!(!workflow.contains(".p12"));
    assert!(!workflow.contains(".pfx"));
}

#[test]
fn publication_reverifies_before_one_protected_state_change() {
    let workflow = repo_file(".github/workflows/publish-release.yml");
    assert!(workflow.contains("workflow_dispatch:"));
    assert!(workflow.contains("test \"$GITHUB_REF_TYPE\" = tag"));
    assert!(workflow.contains("release-manifest.json.minisig"));
    assert!(workflow.contains("gh attestation verify"));
    assert!(workflow.contains("environment: release-publish"));
    assert!(workflow.contains("gh release edit \"$GITHUB_REF_NAME\" --draft=false"));
    assert!(!workflow.contains("gh release upload"));
    assert!(!workflow.contains("gh release delete"));
    assert_actions_are_full_sha(&workflow);
}
