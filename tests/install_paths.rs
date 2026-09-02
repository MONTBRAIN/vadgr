//! The legacy development installers and the 0.5.0 package entry points must
//! keep their platform boundaries explicit.

use std::path::Path;

#[cfg(unix)]
use std::os::unix::fs::PermissionsExt;

fn repo_file(name: &str) -> String {
    // Normalised, because a checkout on Windows can carry CRLF and a pattern
    // written with `\n` would match nothing there. A source-reading test that
    // ignores this fails on exactly one platform.
    std::fs::read_to_string(Path::new(env!("CARGO_MANIFEST_DIR")).join(name))
        .unwrap_or_else(|_| panic!("{name} is in the repository"))
        .replace("\r\n", "\n")
}

#[cfg(unix)]
#[test]
fn the_unix_installer_can_be_invoked_directly() {
    let path = Path::new(env!("CARGO_MANIFEST_DIR")).join("install.sh");
    let mode = std::fs::metadata(path)
        .expect("install.sh is in the repository")
        .permissions()
        .mode();
    assert_ne!(
        mode & 0o111,
        0,
        "install.sh must be executable because the public runbook invokes it directly"
    );
}

#[test]
fn the_wsl_installer_and_runtime_agree_on_the_package_directory() {
    let installer = repo_file("install.sh");
    assert!(
        installer.contains(r#"DATA_HOME=${XDG_DATA_HOME:-"$HOME/.local/share"}"#)
            && installer.contains(r#"ROOT="$DATA_HOME/vadgr""#)
            && installer.contains(r#"CURRENT="$ROOT/current""#),
        "WSL must use the versioned XDG package root"
    );
}

#[test]
fn the_wsl_installer_never_creates_or_updates_a_source_checkout() {
    let installer = repo_file("install.sh");
    assert!(
        !installer.contains("git clone")
            && !installer.contains("git pull")
            && !installer.contains("VADGR_REPO="),
        "the released WSL installer must consume only verified release artifacts"
    );
}

#[test]
fn the_current_e2e_uses_the_installers_real_override_names() {
    let runbook = repo_file("E2E/0.4.12/e2e.md");
    for expected in [
        "HOME=\"$E2E_HOME\"",
        "VADGR_REPO_URL=\"$E2E_ROOT/source\"",
        "VADGR_REF=\"$SUBJECT_COMMIT\"",
        "$env:USERPROFILE",
        "$env:VADGR_REPO_URL",
        "$env:VADGR_REF",
    ] {
        assert!(
            runbook.contains(expected),
            "the runbook must set {expected}"
        );
    }
    assert!(
        !runbook.contains("VADGR_REPO=\"$E2E_ROOT/source\""),
        "the runbook must not set an installer-local shell variable"
    );
}

#[test]
fn the_windows_installer_does_not_persist_path_for_an_alternate_profile() {
    let installer = repo_file("install.ps1");
    let add_to_path = installer
        .split("function AddToPath")
        .nth(1)
        .and_then(|text| text.split("# Main").next())
        .expect("install.ps1 contains the AddToPath function");

    assert!(
        add_to_path.contains("[Environment+SpecialFolder]::UserProfile"),
        "the installer must compare USERPROFILE with the real Windows profile"
    );
    assert!(
        add_to_path.contains("return"),
        "an alternate profile must return before changing the real user PATH"
    );
}

/// Every line of macOS grant guidance sits inside a macOS guard.
///
/// The prompt only exists on macOS, so telling a Linux or Windows owner about
/// Accessibility or Screen Recording is noise about a dialog they will never
/// see. Both guard shapes the installer uses are honoured: the `if` around the
/// payload step and the `case` arm the platform helpers use.
#[test]
fn macos_guidance_never_reaches_another_operating_system() {
    let text = repo_file("install.sh");
    let mut guarded = false;
    let mut depth = 0usize;
    let mut guard_at: Option<usize> = None;
    let mut unguarded = Vec::new();

    for line in text.lines() {
        let trimmed = line.trim();

        if trimmed.starts_with("if ") {
            depth += 1;
            if trimmed.contains("= \"macos\"") {
                guard_at.get_or_insert(depth);
            }
        } else if trimmed == "fi" {
            if guard_at == Some(depth) {
                guard_at = None;
            }
            depth = depth.saturating_sub(1);
        } else if trimmed.starts_with("macos)") {
            guarded = true;
        } else if trimmed == ";;" {
            guarded = false;
        }

        let inside = guarded || guard_at.is_some();
        let prints = trimmed.starts_with("info \"") || trimmed.starts_with("ok \"");
        let grant_text = trimmed.contains("Accessibility") || trimmed.contains("Screen Recording");
        if prints && grant_text && !inside {
            unguarded.push(trimmed.to_owned());
        }
    }

    assert!(
        unguarded.is_empty(),
        "these lines print macOS grant guidance outside a macOS guard: {unguarded:#?}"
    );
}

/// The Windows installer carries none of it either.
#[test]
fn the_windows_installer_says_nothing_about_macos_grants() {
    let text = repo_file("install.ps1").to_lowercase();
    for term in ["accessibility", "screen recording", "macos"] {
        assert!(
            !text.contains(term),
            "install.ps1 mentions {term}, which belongs to macOS alone"
        );
    }
}

/// The package installer must not mutate or tell the owner to source a shell
/// profile: it installs one stable link under the conventional user bin path.
#[test]
fn the_closing_step_does_not_name_a_profile_it_never_wrote() {
    let text = repo_file("install.sh");
    for profile in [".bashrc", ".zshrc", ".profile"] {
        assert!(
            !text.contains(profile),
            "install.sh must not mutate {profile}"
        );
    }
    assert!(text.contains(r#"BIN="$HOME/.local/bin/vadgr""#));
}

/// The non-mutation snapshot must not hash a countdown.
///
/// `netstat -rn` mixes the routing table with the ARP and NDP caches, and macOS
/// has no `ip`, so those caches were the whole network hash. They move on their
/// own: an Expire timer counts down every second, flags age, and a VPN peer
/// route comes and goes. On an idle machine with vadgr not running the table
/// changed twice in ninety seconds, so the cell could never pass.
#[test]
fn the_unix_snapshot_hashes_routes_rather_than_neighbour_state() {
    let text = repo_file("E2E/0.4.12/harness/snapshot-unix.sh");
    let at = text
        .find("netstat -rn")
        .expect("the snapshot reads the routing table");
    // The invocation carries a line continuation, so take the statement rather
    // than the line: a single-line search reads the call and misses its filter.
    let statement = &text[at..text[at..]
        .find("\n        fi")
        .map(|end| at + end)
        .unwrap_or(text.len())];
    assert!(
        statement.contains("awk"),
        "netstat output must be reduced before hashing, found: {statement}"
    );
    assert!(
        statement.contains("$2 !~ /:/") && statement.contains("$2 !~ /^link#/"),
        "rows reached through a link-layer address or an interface scope are the \
         ARP and NDP caches, which move on their own, found: {statement}"
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
fn the_product_has_one_backend_and_only_declared_native_helpers() {
    // A user received two files, `vadgr` and `vadgr-daemon`, and the CLI found
    // the daemon beside itself on disk. That asked a user to hold a detail that
    // belongs to the program, doubled what distribution must sign and publish,
    // and allowed the two halves to be different versions. The product logic is
    // one file: it serves under an explicit mode and acts as the client otherwise.
    // Native packages add one windowless launcher with no product logic so Start
    // menu and login launch do not create a terminal window. WSL does not build it.
    let manifest = repo_file("Cargo.toml");
    let targets = manifest.matches("[[bin]]").count();
    assert_eq!(
        targets, 4,
        "only the declared product and release binaries may ship"
    );
    assert!(
        manifest.contains("name = \"vadgr\""),
        "the backend binary is named vadgr"
    );
    assert!(
        manifest.contains("name = \"vadgr-app\"")
            && manifest.contains("required-features = [\"native-gui\"]"),
        "the launcher must remain native-GUI-only"
    );
    assert!(
        manifest.contains("name = \"vadgr-cua-host\"")
            && manifest.contains("required-features = [\"macos-cua-host\"]"),
        "the macOS responsible process must remain an explicit package-only helper"
    );
    assert!(
        manifest.contains("name = \"vadgr-release-verify\"")
            && manifest.contains("required-features = [\"release-verifier\"]"),
        "the WSL bootstrap verifier must remain an explicit release helper"
    );

    // The legacy script installers remain CLI-only and nothing looks for a
    // sibling daemon executable.
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
            >= 2,
        "both native clean-install assembly paths must validate versions against payload.json"
    );
    assert!(
        !workflow.contains(".available == true and .platform ==")
            && !workflow.contains("$computerUse.available"),
        "clean-install must assert the published computer-use settings fields"
    );
    assert!(
        workflow.matches("venv_ready").count() >= 3,
        "every clean-install OS must assert that the private payload is ready"
    );
    assert!(
        !workflow.contains(r#"docker cp -q "$CLEAN_INSTALL_ROOT/.""#),
        "the private environment is not relocatable after assembly"
    );
    assert!(
        workflow.contains(r#"src=$CLEAN_INSTALL_ROOT,dst=$CLEAN_INSTALL_ROOT,readonly"#),
        "the clean Linux machine must mount the assembled root at its original path"
    );
}

#[test]
fn shell_installers_keep_unix_line_endings_on_windows_checkouts() {
    let attributes = repo_file(".gitattributes");
    assert!(
        attributes.lines().any(|line| line == "*.sh text eol=lf"),
        "Windows checkouts must not convert shell installers to CRLF"
    );
    assert!(
        attributes
            .lines()
            .any(|line| line == "packaging/cua/requirements.lock text eol=lf"),
        "the hashed payload lock must have identical bytes on every checkout"
    );
}
