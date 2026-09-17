use std::path::PathBuf;

fn repo_file(relative: &str) -> String {
    // Source assertions compare logical text, not checkout line endings.
    std::fs::read_to_string(PathBuf::from(env!("CARGO_MANIFEST_DIR")).join(relative))
        .unwrap()
        .replace("\r\n", "\n")
}

#[test]
fn workflow_source_reader_accepts_lf_and_crlf_without_changing_the_tag_guard() {
    let source = repo_file(".github/workflows/release.yml").replace("\r\n", "\n");
    let fixture = tempfile::tempdir().unwrap();
    let path = fixture.path().join("release.yml");
    for text in [source.clone(), source.replace('\n', "\r\n")] {
        std::fs::write(&path, &text).unwrap();
        let workflow = repo_file(path.to_str().unwrap());
        assert!(workflow.contains("tags:\n      - 'v*'"));
        assert_eq!(workflow, source);
        std::fs::write(&path, text.replace("- 'v*'", "- 'untrusted*'")).unwrap();
        assert!(!repo_file(path.to_str().unwrap()).contains("tags:\n      - 'v*'"));
    }
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
fn candidate_is_manual_protected_and_builds_without_attesting_unreviewed_platforms() {
    let workflow = repo_file(".github/workflows/candidate.yml");
    assert!(workflow.contains("workflow_dispatch:"));
    assert!(!workflow.contains("pull_request_target"));
    assert!(!workflow.contains("workflow_run"));
    assert!(workflow.contains("cancel-in-progress: false"));
    for target in [
        "candidate-linux-${{ matrix.arch }}",
        "candidate-wsl-${{ matrix.arch }}",
        "sign-windows:",
        "attest:",
        "refs/heads/master",
        "-Authorization authorization.json",
        "release-manifest.json.bundle.jsonl",
        "windows-11-arm",
    ] {
        assert!(workflow.contains(target), "candidate omits {target}");
    }
    assert!(workflow.contains("secrets.ES_PASSWORD"));
    assert!(!workflow.contains("subject-path: held/**/*"));
    assert_actions_are_full_sha(&workflow);
}

#[test]
fn candidate_payloads_are_assembled_outside_the_source_checkout() {
    let workflow = repo_file(".github/workflows/candidate.yml");
    assert!(!workflow.contains("--install-root \"$PWD/dist/payload\""));
    assert_eq!(workflow.matches("$RUNNER_TEMP/vadgr-payload").count(), 2);
    assert!(workflow.contains("scripts/candidate/build-windows.ps1"));
    assert!(!workflow.contains("--install-root \"$PWD/source_checkout"));
}

#[test]
fn macos_candidate_assembles_payload_beside_the_responsible_host() {
    let workflow = repo_file(".github/workflows/signed-candidate-macos.yml");
    assert!(workflow.contains(
        "cargo build --locked --release --features macos-cua-host --bin vadgr --bin vadgr-cua-host"
    ));
    assert!(workflow.contains(
        "$payload_bundle/Contents/Library/LoginItems/Vadgr Computer Use.app/Contents/MacOS/vadgr-cua-host"
    ));
    assert!(workflow.contains("--install-root \"$payload_root\" --payload-only"));
}

#[test]
fn candidate_invokes_non_executable_packaging_sources_through_the_shell() {
    let workflow = repo_file(".github/workflows/candidate.yml");
    for source in ["linux", "wsl"] {
        assert!(
            workflow.contains(&format!("sh packaging/{source}/build.sh 0.5.0")),
            "candidate executes the non-executable {source} package source directly"
        );
    }
    assert!(
        repo_file(".github/workflows/signed-candidate-macos.yml")
            .contains("sh packaging/macos/build.sh 0.5.0")
    );
}

#[test]
fn windows_import_gate_accepts_native_gui_system_libraries_but_not_the_vc_runtime() {
    let gate = repo_file("scripts/check_windows_imports.ps1").to_ascii_lowercase();
    for library in [
        "dwmapi.dll",
        "gdi32.dll",
        "imm32.dll",
        "opengl32.dll",
        "uiautomationcore.dll",
        "uxtheme.dll",
    ] {
        assert!(gate.contains(&format!("'{library}'")));
    }
    assert!(!gate.contains("'vcruntime140.dll'"));
}

#[test]
fn tag_triggered_release_remains_disabled_without_rebuilding_or_resigning() {
    let workflow = repo_file(".github/workflows/release.yml");
    assert!(workflow.contains("tags:\n      - 'v*'"));
    assert!(!workflow.contains("workflow_dispatch:"));
    assert!(workflow.contains("Tag-triggered rebuild and signing are disabled"));
    assert!(!workflow.contains("uses: ./.github/workflows/candidate.yml"));
    assert!(!workflow.contains("secrets."));
    assert_actions_are_full_sha(&workflow);
}

#[test]
fn signing_inputs_are_environment_scoped_and_never_literal_values() {
    let workflow = repo_file(".github/workflows/candidate.yml");
    assert!(workflow.contains("environment: candidate-windows"));
    assert!(workflow.contains("environment: candidate-authorize"));
    assert!(
        repo_file(".github/workflows/signed-candidate-macos.yml")
            .contains("environment: release-macos")
    );
    assert!(!workflow.contains("BEGIN PRIVATE KEY"));
    assert!(!workflow.contains(".p12"));
    assert!(!workflow.contains(".pfx"));
    for name in ["ES_USERNAME", "ES_PASSWORD", "ES_TOTP_SECRET"] {
        assert!(workflow.contains(&format!("secrets.{name}")));
    }
    assert!(workflow.contains("scripts/signing/release.ps1 -Mode sign"));
}

#[test]
fn publication_reverifies_before_one_protected_state_change() {
    let workflow = repo_file(".github/workflows/publish-release.yml");
    assert!(workflow.contains("workflow_dispatch:"));
    assert!(workflow.contains("test \"$GITHUB_REF_TYPE\" = tag"));
    assert!(workflow.contains("release-manifest.json.bundle.jsonl"));
    assert!(workflow.contains("--custom-trusted-root packaging/release-trusted-root.jsonl"));
    assert!(!workflow.contains("release-manifest.json.minisig"));
    assert!(workflow.contains("gh attestation verify"));
    assert!(workflow.contains("environment: release-publish"));
    assert!(workflow.contains("gh release edit \"$GITHUB_REF_NAME\" --draft=false"));
    assert!(!workflow.contains("gh release upload"));
    assert!(!workflow.contains("gh release delete"));
    assert_actions_are_full_sha(&workflow);
}
