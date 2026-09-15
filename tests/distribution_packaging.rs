use std::path::PathBuf;

fn root() -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR"))
}

fn read(relative: &str) -> String {
    std::fs::read_to_string(root().join(relative)).unwrap()
}

#[test]
fn every_runtime_surface_derives_the_cargo_package_version() {
    assert!(read("Cargo.toml").contains("version = \"0.5.0\""));
    let config = read("src/config.rs");
    assert!(config.contains("env!(\"CARGO_PKG_VERSION\")"));
    assert!(!config.contains("pub const VERSION: &str = \"0."));
}

#[test]
fn release_manifest_schema_and_runtime_have_the_same_closed_shape() {
    let schema: serde_json::Value =
        serde_json::from_str(&read("packaging/manifest-schema.json")).unwrap();
    assert_eq!(schema["properties"]["schema"]["const"], 1);
    assert_eq!(schema["properties"]["product"]["const"], "vadgr");
    assert_eq!(schema["additionalProperties"], false);
    assert!(read("src/install/manifest.rs").contains("#[serde(deny_unknown_fields)]"));
    assert!(read("src/install/manifest.rs").contains("verify_signature(&bytes"));
}

#[test]
fn native_linux_is_graphical_and_wsl_is_cli_only() {
    let app_run = read("packaging/linux/AppRun");
    let linux_build = read("packaging/linux/build.sh");
    let wsl = read("install.sh");
    assert!(app_run.contains("--installer --vehicle"));
    assert!(linux_build.contains("--features native-gui"));
    assert!(linux_build.contains("docs/pet.svg\" \"$appdir/com.montbrain.vadgr.svg"));
    assert!(wsl.contains("Native Linux uses the graphical AppImage installer"));
    assert!(!wsl.contains(".desktop"));
    assert!(!wsl.contains("autostart"));
    assert!(!wsl.contains("systemctl"));
}

#[test]
fn linux_lifecycle_accepts_an_already_healthy_daemon() {
    let linux = read("src/install/linux.rs");
    assert!(linux.contains(".arg(\"health\")"));
    assert!(linux.contains("the installed Vadgr daemon is not healthy"));
}

#[test]
fn every_unsigned_or_unconfigured_trust_path_fails_closed() {
    assert_eq!(
        read("packaging/release-public-key.txt").trim(),
        "UNCONFIGURED"
    );
    for source in [
        read("packaging/linux/build.sh"),
        read("packaging/macos/build.sh"),
        read("install.sh"),
    ] {
        assert!(source.contains("UNCONFIGURED"));
        assert!(!source.contains("self-sign"));
        assert!(!source.contains("ad-hoc"));
    }
}

#[test]
fn macos_packages_the_stable_responsible_process() {
    let app = read("packaging/macos/Vadgr-Info.plist");
    let host = read("packaging/macos/CuaHost-Info.plist");
    let build = read("packaging/macos/build.sh");
    let runtime = read("src/cua_payload.rs");
    assert!(app.contains("com.montbrain.vadgr"));
    assert!(host.contains("com.montbrain.vadgr.cua"));
    assert!(build.contains("Vadgr Computer Use.app"));
    assert!(runtime.contains("Vadgr Computer Use.app/Contents/MacOS/vadgr-cua-host"));
    assert!(runtime.contains("the signed Vadgr Computer Use host is missing"));
}

#[test]
fn macos_package_declares_its_exact_host_architecture() {
    let build = read("packaging/macos/build.sh");
    assert!(build.contains(r#"hostArchitectures=\"$arch\""#));
    let distribution = read("packaging/macos/Distribution.xml");
    assert!(
        distribution.contains("<options hostArchitectures=\"arm64,x86_64\" customize=\"never\"")
    );
}

#[test]
fn macos_package_stages_executable_installer_scripts() {
    let build = read("packaging/macos/build.sh");
    for name in ["preinstall", "postinstall"] {
        assert!(
            build.contains(&format!(
                "install -m 0755 \"$repo/packaging/macos/scripts/{name}\" \"$scripts/{name}\""
            )),
            "package must stage {name} with executable permissions"
        );
    }
    assert!(build.contains("--scripts \"$scripts\""));
    assert!(!build.contains("--scripts \"$repo/packaging/macos/scripts\""));

    #[cfg(unix)]
    {
        use std::os::unix::fs::PermissionsExt;
        let staged = tempfile::tempdir().unwrap();
        let commands = build
            .lines()
            .filter(|line| line.starts_with("install -m 0755 \"$repo/packaging/macos/scripts/"))
            .collect::<Vec<_>>()
            .join("\n");
        let status = std::process::Command::new("sh")
            .args(["-ec", &format!("repo=$1; scripts=$2; {commands}"), "stage"])
            .arg(root())
            .arg(staged.path())
            .status()
            .unwrap();
        assert!(status.success());
        for name in ["preinstall", "postinstall"] {
            let path = staged.path().join(name);
            assert_eq!(
                std::fs::read(&path).unwrap(),
                std::fs::read(root().join("packaging/macos/scripts").join(name)).unwrap()
            );
            assert_eq!(
                std::fs::metadata(path).unwrap().permissions().mode() & 0o777,
                0o755
            );
        }
    }
}

#[test]
fn e2e_runbook_names_every_required_lifecycle_negative() {
    let runbook = read("E2E/0.5.0/e2e.md").to_ascii_lowercase();
    for required in [
        "terms declined",
        "tampered",
        "health-check failure",
        "repair",
        "roll back",
        "uninstall-preserve",
        "delete owner data",
        "authenticode",
        "designated requirement",
        "screen reader",
        "cleanup",
    ] {
        assert!(runbook.contains(required), "runbook lacks {required}");
    }
}

#[test]
fn macos_installer_creates_owner_cache_without_root_owned_parents() {
    let postinstall = read("packaging/macos/scripts/postinstall");
    assert!(postinstall.contains("/usr/bin/sudo -H -u \"$owner\" /bin/mkdir -p \"$cache\""));
    assert!(
        postinstall.contains("/usr/bin/sudo -H -u \"$owner\" /bin/cp \"$package\" \"$pending\"")
    );
    assert!(!postinstall.contains("/usr/sbin/chown -R"));
}

#[test]
fn macos_rollback_tracks_start_failure_and_stops_before_removing_the_app() {
    let script = read("packaging/macos/scripts/postinstall");
    let start = script
        .find("start_status=0")
        .expect("track the start result");
    let capture = script[start..]
        .find("remember_started_daemon\n")
        .expect("capture the child even when startup fails");
    let failure = script[start..]
        .find("if [ \"$start_status\" -ne 0 ]")
        .unwrap();
    assert!(capture < failure);
    let rollback = script.split("restore_previous() {").nth(1).unwrap();
    assert!(
        rollback.find("stop_started_daemon").unwrap()
            < rollback.find("/bin/rm -rf -- \"$app\"").unwrap()
    );
    assert!(!rollback.contains("\"$backend\" stop"));
}

#[cfg(unix)]
#[test]
fn macos_rollback_never_signals_an_old_or_changed_process() {
    let script = read("packaging/macos/scripts/postinstall");
    let functions = script
        .split_once("remember_started_daemon() {")
        .expect("rollback must identify the transaction's daemon")
        .1
        .split_once("restore_previous() {")
        .unwrap()
        .0;
    let functions = format!("remember_started_daemon() {{{functions}")
        .replace("/bin/cat", "fixture_cat")
        .replace("/bin/ps", "fixture_ps")
        .replace("/usr/bin/sudo -H -u \"$owner\" /bin/kill", "fixture_kill")
        .replace("/bin/sleep", "fixture_sleep");
    for (scenario, expected) in [
        ("new", "signal:-TERM 202\n"),
        ("old", ""),
        ("malformed", ""),
        ("foreign-owner", ""),
        ("foreign-command", ""),
        ("changed", "refused\n"),
        ("exited", ""),
        ("stuck", "signal:-TERM 202\nrefused\n"),
    ] {
        let fixture = tempfile::tempdir().unwrap();
        let body = format!(
            r#"
set -eu
cd "$1"
scenario=$2
owner=fixture
owner_uid=501
backend=/Applications/Vadgr.app/Contents/MacOS/vadgr
pid_file=unused
previous_pid=101
started_pid=
started_identity=
phase=capture
fixture_cat() {{
  case "$scenario" in old) echo 101;; malformed) echo invalid;; *) echo 202;; esac
}}
fixture_ps() {{
  if [ -f stopped ] || [ "$scenario:$phase" = exited:cleanup ]; then return 1; fi
  if [ "$4" = uid= ]; then
    if [ "$scenario" = foreign-owner ]; then echo 999; else echo 501; fi
  elif [ "$4" = command= ]; then
    if [ "$scenario" = foreign-command ]; then echo /usr/bin/unrelated; else echo "$backend serve --port 8765"; fi
  else
    if [ "$scenario:$phase" = changed:cleanup ]; then echo replacement; else echo "Tue Sep 15 09:00:00 2026 $backend serve --port 8765"; fi
  fi
}}
fixture_kill() {{ printf 'signal:%s %s\n' "$1" "$2"; if [ "$scenario" != stuck ]; then touch stopped; fi; }}
fixture_sleep() {{ :; }}
{functions}
remember_started_daemon
phase=cleanup
stop_started_daemon || echo refused
"#
        );
        let output = std::process::Command::new("sh")
            .args(["-ec", &body, "rollback-fixture"])
            .arg(fixture.path())
            .arg(scenario)
            .output()
            .unwrap();
        assert!(
            output.status.success(),
            "{scenario}: {}",
            String::from_utf8_lossy(&output.stderr)
        );
        assert_eq!(
            String::from_utf8_lossy(&output.stdout),
            expected,
            "{scenario}"
        );
    }
}

#[test]
fn macos_upgrade_stops_both_installed_daemon_entries_before_moving_the_app() {
    let script = read("packaging/macos/scripts/preinstall");
    let identify = script
        .find("cli_identity=$(previous_daemon_identity")
        .expect("validate the CLI daemon");
    let agent = script
        .find("agent_identity=$(previous_daemon_identity")
        .expect("validate the login daemon");
    let stop = script
        .find("stop_previous_daemon \"$cli_pid\"")
        .expect("stop the previous daemon");
    let stop_agent = script.find("stop_previous_daemon \"$agent_pid\"").unwrap();
    let move_app = script.find("/bin/mv \"$app\" \"$backup\"").unwrap();
    assert!(identify < stop && agent < stop && stop < stop_agent && stop_agent < move_app);
    assert!(script.contains("gui/$owner_uid/com.montbrain.vadgr.agent"));
    assert!(!script.contains("\"$backend\" stop"));
    assert!(!script.contains("pkill"));
}

#[cfg(unix)]
#[test]
fn macos_upgrade_checks_owner_executable_and_process_generation_before_signaling() {
    let script = read("packaging/macos/scripts/preinstall");
    let functions = script
        .split_once("previous_daemon_identity() {")
        .expect("identify the previous installed daemon")
        .1
        .split_once("[ ! -L \"$app\" ]")
        .unwrap()
        .0;
    let functions = format!("previous_daemon_identity() {{{functions}")
        .replace("/bin/ps", "fixture_ps")
        .replace("/usr/sbin/lsof", "fixture_lsof")
        .replace("/usr/bin/sudo -H -u \"$owner\" /bin/kill", "fixture_kill")
        .replace("/bin/sleep", "fixture_sleep");
    for (scenario, expected) in [
        ("cli", "signal:-TERM 202\n"),
        ("agent", "signal:-TERM 202\n"),
        ("absent", ""),
        ("stale", ""),
        ("malformed", "refused\n"),
        ("reserved-pid", "refused\n"),
        ("foreign-owner", "refused\n"),
        ("foreign-command", "refused\n"),
        ("foreign-executable", "refused\n"),
        ("changed", "refused\n"),
        ("stuck", "signal:-TERM 202\nrefused\n"),
    ] {
        let fixture = tempfile::tempdir().unwrap();
        let body = format!(
            r#"
set -eu
cd "$1"
scenario=$2
owner=fixture
owner_uid=501
backend=/Applications/Vadgr.app/Contents/MacOS/vadgr
phase=identify
fixture_ps() {{
  if [ -f stopped ] || [ "$scenario" = stale ]; then return 1; fi
  if [ "$4" = uid= ]; then
    if [ "$scenario" = foreign-owner ]; then echo 999; else echo 501; fi
  elif [ "$4" = command= ]; then
    case "$scenario" in
      foreign-command) echo /usr/bin/unrelated;;
      agent) echo "$backend --daemon";;
      *) echo "$backend serve --port 8765";;
    esac
  else
    if [ "$scenario:$phase" = changed:stop ]; then echo replacement; else echo "Tue Sep 15 09:00:00 2026 $backend"; fi
  fi
}}
fixture_lsof() {{
  if [ "$scenario" = foreign-executable ]; then echo n/usr/bin/unrelated; else printf 'p202\nn%s\n' "$backend"; fi
}}
fixture_kill() {{ printf 'signal:%s %s\n' "$1" "$2"; if [ "$scenario" != stuck ]; then touch stopped; fi; }}
fixture_sleep() {{ :; }}
{functions}
pid=202
case "$scenario" in absent) pid=;; malformed) pid=invalid;; reserved-pid) pid=1;; esac
if identity=$(previous_daemon_identity "$pid"); then
  phase=stop
  stop_previous_daemon "$pid" "$identity" || echo refused
else
  echo refused
fi
"#
        );
        let output = std::process::Command::new("sh")
            .args(["-ec", &body, "upgrade-fixture"])
            .arg(fixture.path())
            .arg(scenario)
            .output()
            .unwrap();
        assert!(
            output.status.success(),
            "{scenario}: {}",
            String::from_utf8_lossy(&output.stderr)
        );
        assert_eq!(
            String::from_utf8_lossy(&output.stdout),
            expected,
            "{scenario}"
        );
    }
}
