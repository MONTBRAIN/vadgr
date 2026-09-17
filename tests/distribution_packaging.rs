use std::path::PathBuf;

fn root() -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR"))
}

fn read(relative: &str) -> String {
    // Source assertions compare logical text, not checkout line endings.
    std::fs::read_to_string(root().join(relative))
        .unwrap()
        .replace("\r\n", "\n")
}

#[test]
fn package_source_reader_accepts_lf_and_crlf_without_changing_content() {
    let source = read("packaging/macos/vadgr-lifecycle").replace("\r\n", "\n");
    let fixture = tempfile::tempdir().unwrap();
    let path = fixture.path().join("lifecycle");
    for text in [source.clone(), source.replace('\n', "\r\n")] {
        std::fs::write(&path, text).unwrap();
        assert!(
            read(path.to_str().unwrap()) == source,
            "the source reader must normalize CRLF only"
        );
    }
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
    assert!(read("src/install/manifest.rs").contains("verify_attestation(&bytes, &bundle)?"));
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
    let installer = read("install.sh");
    assert!(installer.contains("VERIFIER_SHA_X86_64=UNCONFIGURED"));
    assert!(installer.contains("VERIFIER_SHA_AARCH64=UNCONFIGURED"));
    assert!(installer.contains("[ \"$VERIFIER_SHA\" != UNCONFIGURED ]"));
    for source in [read("packaging/linux/build.sh"), read("packaging/macos/build.sh"), installer] {
        assert!(!source.contains("self-sign"));
        assert!(!source.contains("ad-hoc"));
    }
}

#[test]
fn unsigned_native_builds_never_require_or_embed_the_old_private_key() {
    for platform in ["linux", "macos"] {
        let script = read(&format!("packaging/{platform}/build.sh"));
        assert!(!script.contains("release-public-key.txt"), "{platform}");
        assert!(!script.contains("minisign"), "{platform}");
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
    assert_macos_rollback_order(&script);
}

fn assert_macos_rollback_order(script: &str) {
    let start = script
        .find("start_status=0")
        .expect("track the start result");
    let capture = script[start..]
        .lines()
        .position(|line| line == "remember_started_daemon")
        .expect("capture the child even when startup fails");
    let failure = script[start..]
        .lines()
        .position(|line| line.starts_with("if [ \"$start_status\" -ne 0 ]"))
        .unwrap();
    assert!(capture < failure);
    let rollback = script.split("restore_previous() {").nth(1).unwrap();
    assert!(
        rollback.find("stop_started_daemon").unwrap()
            < rollback.find("/bin/rm -rf -- \"$app\"").unwrap()
    );
    assert!(!rollback.contains("\"$backend\" stop"));
}

#[test]
fn macos_rollback_source_oracle_accepts_lf_and_crlf() {
    let lf = read("packaging/macos/scripts/postinstall").replace("\r\n", "\n");
    for script in [lf.clone(), lf.replace('\n', "\r\n")] {
        assert_macos_rollback_order(&script);
    }
}

#[test]
fn macos_rollback_source_oracle_rejects_missing_or_late_capture() {
    let lf = read("packaging/macos/scripts/postinstall").replace("\r\n", "\n");
    let missing = lf.replace("\nremember_started_daemon\n", "\n");
    assert_ne!(missing, lf);
    let late = format!("{missing}\nremember_started_daemon\n");
    for source in [missing, late] {
        for script in [source.clone(), source.replace('\n', "\r\n")] {
            assert!(std::panic::catch_unwind(|| assert_macos_rollback_order(&script)).is_err());
        }
    }
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

#[cfg(unix)]
#[test]
fn macos_uninstall_denied_authorization_preserves_the_entire_installation() {
    use std::os::unix::fs::PermissionsExt;
    // An isolated package tree, owner home and denied authorization command.
    // The fixture never calls the host's administrator prompt or login service.
    let fixture = tempfile::tempdir().unwrap();
    let app = fixture.path().join("Vadgr.app");
    let home = fixture.path().join("owner");
    let cache = home.join("Library/Application Support/vadgr/package-cache");
    std::fs::create_dir_all(app.join("Contents/MacOS")).unwrap();
    std::fs::create_dir_all(app.join("Contents/Helpers")).unwrap();
    std::fs::create_dir_all(&cache).unwrap();
    let retained = cache.join("current.pkg");
    std::fs::write(&retained, "retained package").unwrap();
    for (path, body) in [
        (app.join("Contents/MacOS/vadgr"), "echo purge >> \"$TRACE\""),
        (
            app.join("Contents/Helpers/vadgr-login-item"),
            "echo login-change >> \"$TRACE\"",
        ),
        (
            fixture.path().join("deny-authorization"),
            "echo denied >> \"$TRACE\"; exit 1",
        ),
        (
            fixture.path().join("owner-directory"),
            "printf 'NFSHomeDirectory: %s\\n' \"$HOME\"",
        ),
    ] {
        std::fs::write(&path, format!("#!/bin/sh\n{body}\n")).unwrap();
        std::fs::set_permissions(&path, std::fs::Permissions::from_mode(0o755)).unwrap();
    }
    let script = read("packaging/macos/vadgr-lifecycle")
        .replace("/Applications/Vadgr.app", app.to_str().unwrap())
        .replace(
            "/usr/local/bin/vadgr",
            fixture.path().join("vadgr-link").to_str().unwrap(),
        )
        .replace(
            "/usr/bin/dscl",
            fixture.path().join("owner-directory").to_str().unwrap(),
        )
        .replace(
            "/usr/bin/osascript",
            fixture.path().join("deny-authorization").to_str().unwrap(),
        );
    let script_path = fixture.path().join("lifecycle");
    std::fs::write(&script_path, script).unwrap();
    let trace = fixture.path().join("trace");
    let output = std::process::Command::new("sh")
        .arg(script_path)
        .args(["uninstall", "--purge-owner-state"])
        .env("HOME", &home)
        .env_remove("VADGR_HOME")
        .env_remove("VADGR_STATE_HOME")
        .env("TRACE", &trace)
        .output()
        .unwrap();
    assert!(!output.status.success());
    assert!(
        retained.exists(),
        "authorization denial removed the retained package"
    );
    assert_eq!(std::fs::read_to_string(trace).unwrap(), "denied\n");
    assert!(app.join("Contents/MacOS/vadgr").is_file());
}

#[cfg(unix)]
#[test]
fn macos_authorized_uninstall_validates_processes_before_any_owner_mutation() {
    let functions = read("packaging/macos/vadgr-lifecycle")
        .split_once("process_identity() (")
        .expect("uninstall must identify its daemon before deleting its package")
        .1
        .split_once("\ncase \"$action\" in")
        .unwrap()
        .0
        .to_owned();
    let functions = format!("process_identity() ({functions}")
        .replace("/bin/ps", "fixture_ps")
        .replace("/usr/bin/pgrep", "fixture_children")
        .replace("/usr/sbin/lsof", "fixture_lsof")
        .replace("/usr/bin/id", "fixture_id")
        .replace("/usr/bin/stat", "fixture_stat")
        .replace("/usr/bin/dscl", "fixture_directory")
        .replace("/usr/libexec/PlistBuddy", "fixture_bundle")
        .replace("/bin/launchctl", "fixture_launchctl")
        .replace("/usr/bin/sudo", "fixture_sudo")
        .replace("/bin/kill", "fixture_kill")
        .replace("/bin/sleep", "fixture_sleep")
        .replace("/usr/bin/mktemp", "fixture_mktemp")
        .replace("/usr/sbin/pkgutil", "fixture_receipt")
        .replace("/usr/local/bin/vadgr", "\"$fixture_link\"");
    for (scenario, success, expected) in [
        ("preserve", true, "disable\nstop:303\nstop:202\nforget\n"),
        (
            "purge",
            true,
            "disable\nstop:303\nstop:202\npurge\nforget\n",
        ),
        (
            "agent",
            true,
            "disable\nstop:303\nstop:202\nstop:204\nforget\n",
        ),
        ("stale", true, "disable\nforget\n"),
        ("foreign-owner", false, ""),
        ("foreign-command", false, ""),
        ("foreign-executable", false, ""),
        ("foreign-child", false, ""),
        ("changed", false, ""),
        ("new-child", false, ""),
        ("foreign-link", false, ""),
        ("cache-link", false, ""),
        ("login-failure", false, "disable\n"),
        ("stuck", false, "disable\nstop:303\n"),
    ] {
        let fixture = tempfile::tempdir().unwrap();
        let body = format!(
            r#"
set -eu
cd "$1"
scenario=$2
app="$PWD/Vadgr.app"
backend="$app/Contents/MacOS/vadgr"
login_helper="$app/Contents/Helpers/vadgr-login-item"
owner_home="$PWD/owner"
fixture_link="$PWD/vadgr-link"
cache="$owner_home/Library/Application Support/vadgr/package-cache"
mkdir -p "$app/Contents/MacOS" "$app/Contents/Helpers" "$owner_home/.vadgr/pids" "$cache"
touch "$backend" "$login_helper" "$cache/current.pkg" "$owner_home/data"
chmod +x "$login_helper"
printf '202\n' > "$owner_home/.vadgr/pids/api.pid"
: > trace
if [ "$scenario" = foreign-link ]; then touch "$fixture_link"; fi
if [ "$scenario" = cache-link ]; then mv "$cache" cache-retained; ln -s "$PWD/cache-retained" "$cache"; fi
fixture_id() {{ if [ "$1" = -u ]; then echo 0; else echo fixture; fi; }}
fixture_stat() {{ echo 501; }}
fixture_directory() {{ printf 'NFSHomeDirectory: %s\n' "$owner_home"; }}
fixture_bundle() {{ echo com.montbrain.vadgr; }}
fixture_mktemp() {{ mktemp -d "$PWD/snapshot.XXXXXX"; }}
fixture_receipt() {{ echo forget >> trace; }}
fixture_sleep() {{ :; }}
fixture_launchctl() {{
  if [ "$1" = print ]; then
    if [ "$scenario" = agent ]; then echo 'pid = 204'; fi
  else shift 2; "$@"; fi
}}
fixture_sudo() {{
  shift 3
  if [ "$1" = "$login_helper" ]; then
    if [ "$2" = status ]; then echo enabled; else
      echo disable >> trace
      [ "$scenario" != login-failure ]
    fi
  elif [ "$1" = "$backend" ]; then
    [ "$2" = __purge-owner-state ]
    echo purge >> trace
    rm "$owner_home/data"
  else "$@"; fi
}}
fixture_ps() {{
  pid=$2
  if [ -e "stopped-$pid" ] || [ "$scenario" = stale ]; then return 1; fi
  case "$4" in
    uid=) if [ "$scenario" = foreign-owner ]; then echo 999; else echo 501; fi;;
    ppid=) echo 202;;
    command=)
      if [ "$scenario" = foreign-command ] || {{ [ "$scenario" = foreign-child ] && [ "$pid" = 303 ]; }}; then echo /usr/bin/unrelated;
      elif [ "$pid" = 303 ]; then echo "$app/Contents/Resources/lib/cua/python/bin/python3.12 -m computer_use.browser.broker";
      elif [ "$pid" = 204 ]; then echo "$backend --daemon";
      else echo "$backend serve --port 8765"; fi;;
    *)
      if [ "$scenario" = changed ] && [ -e "seen-$pid" ]; then echo replacement;
      else echo "Tue Sep 15 09:00:00 2026 process-$pid"; touch "seen-$pid"; fi;;
  esac
}}
fixture_children() {{
  if [ "$2" = 202 ] && [ ! -e stopped-303 ]; then
    echo 303
    if [ "$scenario" = new-child ] && [ -e children-seen ]; then echo 304; fi
    touch children-seen
  fi
}}
fixture_lsof() {{
  if [ "$scenario" = foreign-executable ]; then echo n/usr/bin/unrelated;
  elif [ "$3" = 303 ]; then printf 'p303\nn%s/Contents/Resources/lib/cua/python/bin/python3.12\n' "$app";
  else printf 'p%s\nn%s\n' "$3" "$backend"; fi
}}
fixture_kill() {{ echo "stop:$2" >> trace; if [ "$scenario" != stuck ]; then touch "stopped-$2"; fi; }}
{functions}
purge=false
if [ "$scenario" = purge ]; then purge=true; fi
uninstall_authorized 501 "$purge"
"#
        );
        let output = std::process::Command::new("sh")
            .args(["-ec", &body, "uninstall-fixture"])
            .arg(fixture.path())
            .arg(scenario)
            .output()
            .unwrap();
        assert_eq!(
            output.status.success(),
            success,
            "{scenario}: {}",
            String::from_utf8_lossy(&output.stderr)
        );
        assert_eq!(
            std::fs::read_to_string(fixture.path().join("trace")).unwrap(),
            expected,
            "{scenario}"
        );
        assert_eq!(
            fixture.path().join("Vadgr.app").exists(),
            !success,
            "{scenario}"
        );
        assert_eq!(
            fixture.path().join("owner/data").exists(),
            scenario != "purge",
            "{scenario}"
        );
        assert_eq!(
            fixture
                .path()
                .join("owner/Library/Application Support/vadgr/package-cache/current.pkg")
                .exists(),
            !success,
            "{scenario}"
        );
    }
}

#[cfg(target_os = "macos")]
#[test]
fn macos_uninstall_stops_only_its_captured_native_fixture_tree() {
    use std::io::{BufRead, BufReader};
    use std::process::{Child, Command, Stdio};
    struct FixtureProcess(Child);
    impl Drop for FixtureProcess {
        fn drop(&mut self) {
            if self.0.try_wait().unwrap().is_none() {
                let _ = Command::new("/bin/kill")
                    .args(["-TERM", &self.0.id().to_string()])
                    .status();
                let _ = self.0.wait();
            }
        }
    }
    // Native processes in an isolated package-shaped tree. The parent owns and
    // reaps its fixture child, including when an assertion aborts the test.
    let fixture = tempfile::tempdir().unwrap();
    let app = fixture.path().canonicalize().unwrap().join("Vadgr.app");
    let backend = app.join("Contents/MacOS/vadgr");
    let child_path = app
        .join("Contents/Library/LoginItems/Vadgr Computer Use.app/Contents/MacOS/vadgr-cua-host");
    for path in [&backend, &child_path] {
        std::fs::create_dir_all(path.parent().unwrap()).unwrap();
    }
    let source = fixture.path().join("process.c");
    std::fs::write(
        &source,
        r#"
#include <signal.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/wait.h>
#include <unistd.h>
static volatile sig_atomic_t stopping;
static void stop(int signal) { (void)signal; stopping = 1; }
int main(int argc, char **argv) {
    pid_t child = 0;
    if (argc == 3 && strcmp(argv[1], "serve") == 0) {
        int ready[2];
        if (pipe(ready) != 0) return 1;
        child = fork();
        if (child < 0) return 1;
        if (child == 0) {
            char descriptor[24];
            close(ready[0]);
            snprintf(descriptor, sizeof(descriptor), "%d", ready[1]);
            execl(argv[2], argv[2], "--python", "fixture", descriptor, (char *)0);
            _exit(2);
        }
        close(ready[1]);
        char marker;
        if (read(ready[0], &marker, 1) != 1) { waitpid(child, 0, 0); return 2; }
        close(ready[0]);
        printf("%d\n", child);
        fflush(stdout);
    }
    signal(SIGTERM, stop);
    if (argc == 4) { int descriptor = atoi(argv[3]); write(descriptor, "1", 1); close(descriptor); }
    while (!stopping) pause();
    if (child > 0) { kill(child, SIGTERM); waitpid(child, 0, 0); }
    return 0;
}
"#,
    )
    .unwrap();
    let built = Command::new("cc")
        .arg(&source)
        .arg("-o")
        .arg(&backend)
        .output()
        .unwrap();
    assert!(
        built.status.success(),
        "{}",
        String::from_utf8_lossy(&built.stderr)
    );
    std::fs::copy(&backend, &child_path).unwrap();
    let mut parent = FixtureProcess(
        Command::new(&backend)
            .arg("serve")
            .arg(&child_path)
            .stdin(Stdio::null())
            .stdout(Stdio::piped())
            .stderr(Stdio::null())
            .spawn()
            .unwrap(),
    );
    let mut child_pid = String::new();
    BufReader::new(parent.0.stdout.take().unwrap())
        .read_line(&mut child_pid)
        .unwrap();
    let child_pid = child_pid.trim().to_owned();
    let mut foreign = FixtureProcess(
        Command::new("/bin/sleep")
            .arg("60")
            .stdin(Stdio::null())
            .stdout(Stdio::null())
            .stderr(Stdio::null())
            .spawn()
            .unwrap(),
    );
    let functions = read("packaging/macos/vadgr-lifecycle")
        .split_once("process_identity() (")
        .unwrap()
        .1
        .split_once("\nuninstall_authorized() {")
        .unwrap()
        .0
        .to_owned();
    let functions = format!("process_identity() ({functions}")
        .replace("/usr/bin/sudo -H -u \"$owner\" /bin/kill", "/bin/kill");
    let body = format!(
        r#"
set -eu
app=$1
backend="$app/Contents/MacOS/vadgr"
snapshot=$2
owner_uid=$(/usr/bin/id -u)
mkdir "$snapshot"
: > "$snapshot/order"
{functions}
capture_process_tree "$3" daemon
while IFS= read -r pid; do check_captured_process "$pid"; done < "$snapshot/order"
while IFS= read -r pid; do stop_captured_process "$pid"; done < "$snapshot/order"
"#
    );
    let output = Command::new("sh")
        .args(["-ec", &body, "native-uninstall-fixture"])
        .arg(&app)
        .arg(fixture.path().join("snapshot"))
        .arg(parent.0.id().to_string())
        .output()
        .unwrap();
    assert!(
        output.status.success(),
        "{}",
        String::from_utf8_lossy(&output.stderr)
    );
    assert_eq!(
        std::fs::read_to_string(fixture.path().join("snapshot/order")).unwrap(),
        format!("{child_pid}\n{}\n", parent.0.id())
    );
    assert!(parent.0.wait().unwrap().success());
    assert!(
        foreign.0.try_wait().unwrap().is_none(),
        "an unrelated process was stopped"
    );
}
