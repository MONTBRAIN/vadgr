//! Process configuration, and the one place a path is decided.
//!
//! **Nothing resolves relative to the working directory.** An installed daemon
//! that keeps its database below wherever it was launched from puts a machine's
//! history somewhere different depending on which terminal started it, which is
//! the defect D-97 rules out. Every default here comes from the platform's own
//! local-state root.

use std::ffi::OsString;
use std::path::{Path, PathBuf};

/// The version this daemon reports at `GET /api/health`.
pub const VERSION: &str = "0.4.9";

/// The environment a path is resolved from, as values rather than as globals.
///
/// Taking it as a struct is what makes the four-target matrix a unit test
/// instead of four machines: every case below is one `Environment` and one
/// assertion.
#[derive(Default, Clone)]
pub struct Environment {
    pub state_home: Option<OsString>,
    pub db: Option<OsString>,
    pub runs_dir: Option<OsString>,
    pub xdg_state_home: Option<OsString>,
    pub home: Option<OsString>,
    pub local_app_data: Option<OsString>,
    pub user_profile: Option<OsString>,
}

impl Environment {
    pub fn from_env() -> Self {
        Self {
            state_home: std::env::var_os("VADGR_STATE_HOME"),
            db: std::env::var_os("VADGR_DB"),
            runs_dir: std::env::var_os("VADGR_RUNS_DIR"),
            xdg_state_home: std::env::var_os("XDG_STATE_HOME"),
            home: std::env::var_os("HOME"),
            local_app_data: std::env::var_os("LOCALAPPDATA"),
            user_profile: std::env::var_os("USERPROFILE"),
        }
    }
}

/// Which platform's layout to resolve.
///
/// Named rather than read from `cfg!` at the point of use, so a test can ask
/// for macOS's answer on Linux. WSL is Linux here on purpose: it uses the Linux
/// layout, and the distinction that matters elsewhere, which interop it can
/// reach, has nothing to do with where state lives.
#[derive(Clone, Copy, PartialEq, Eq, Debug)]
pub enum Layout {
    Unix,
    MacOs,
    Windows,
}

impl Layout {
    pub fn host() -> Self {
        if cfg!(target_os = "windows") {
            Self::Windows
        } else if cfg!(target_os = "macos") {
            Self::MacOs
        } else {
            Self::Unix
        }
    }
}

/// The local-state root, from `ARCHITECTURE.md` section 3.1.
///
/// `VADGR_STATE_HOME` overrides it exactly, which is the seam tests and managed
/// deployments use. Everything else derives from the result, because three
/// resolvers is how two of them drift.
pub fn state_root(env: &Environment, layout: Layout) -> Option<PathBuf> {
    if let Some(explicit) = env.state_home.as_ref() {
        return Some(PathBuf::from(explicit));
    }
    let absolute = |value: &Option<OsString>| {
        value
            .as_ref()
            .map(PathBuf::from)
            .filter(|path| is_absolute_for(path, layout))
    };
    match layout {
        Layout::Unix => absolute(&env.xdg_state_home)
            .map(|base| base.join("vadgr"))
            .or_else(|| {
                absolute(&env.home).map(|home| home.join(".local").join("state").join("vadgr"))
            }),
        Layout::MacOs => absolute(&env.home).map(|home| {
            home.join("Library")
                .join("Application Support")
                .join("vadgr")
                .join("state")
        }),
        Layout::Windows => absolute(&env.local_app_data)
            .map(|base| base.join("vadgr"))
            .or_else(|| {
                absolute(&env.user_profile)
                    .map(|home| home.join("AppData").join("Local").join("vadgr"))
            }),
    }
}

/// Whether a path is absolute **for the layout being resolved**, not for the
/// host doing the resolving.
///
/// `Path::is_absolute` answers for the host, so `C:\\Users\\o` reads as relative on
/// Linux and the Windows case could only be tested on Windows. Deciding by
/// layout is what makes the whole matrix checkable from one machine, which is
/// the difference between a test that runs and a test that waits for a runner.
fn is_absolute_for(path: &Path, layout: Layout) -> bool {
    match layout {
        Layout::Unix | Layout::MacOs => path.to_string_lossy().starts_with('/'),
        Layout::Windows => {
            let text = path.to_string_lossy();
            let mut chars = text.chars();
            let drive = matches!(
                (chars.next(), chars.next(), chars.next()),
                (Some(letter), Some(':'), Some('\\' | '/')) if letter.is_ascii_alphabetic()
            );
            drive || text.starts_with("\\\\")
        }
    }
}

/// Where the database, the run journals and the credentials live.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct Paths {
    pub root: PathBuf,
    pub db: PathBuf,
    pub runs: PathBuf,
    pub credentials: PathBuf,
}

impl Paths {
    /// Derive every path from one root, then apply the two exact overrides.
    pub fn resolve(env: &Environment, layout: Layout) -> Result<Self, PathError> {
        let root = state_root(env, layout).ok_or(PathError::NoPlatformRoot)?;
        Ok(Self {
            db: env
                .db
                .as_ref()
                .map(PathBuf::from)
                .unwrap_or_else(|| root.join("vadgr.db")),
            runs: env
                .runs_dir
                .as_ref()
                .map(PathBuf::from)
                .unwrap_or_else(|| root.join("runs")),
            credentials: root.join("credentials"),
            root,
        })
    }
}

/// The one way resolving a path can fail.
///
/// A machine with no home directory at all is not a case to guess at: the
/// daemon says so and does not start, rather than writing a user's credentials
/// somewhere it invented.
#[derive(Debug, PartialEq, Eq)]
pub enum PathError {
    NoPlatformRoot,
}

impl std::fmt::Display for PathError {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            Self::NoPlatformRoot => f.write_str(
                "no platform state directory is available. Set VADGR_STATE_HOME to \
                 an absolute path.",
            ),
        }
    }
}

pub struct Config {
    pub port: u16,
    pub db_path: PathBuf,
    pub transport_name: String,
    pub runs_dir: PathBuf,
    pub state_home: Option<PathBuf>,
}

impl Config {
    pub fn from_env() -> Result<Self, PathError> {
        let environment = Environment::from_env();
        let paths = Paths::resolve(&environment, Layout::host())?;
        Ok(Self::from_values(
            std::env::var("VADGR_PORT").ok(),
            std::env::var("VADGR_TRANSPORT").ok(),
            &paths,
        ))
    }

    /// A config for an explicit set of paths.
    ///
    /// **A test must never resolve the real platform root.** One that did would
    /// write into the machine running it and pass or fail on whatever was
    /// already there, so an isolated root is an argument rather than an
    /// environment variable the test has to remember to set.
    pub fn for_paths(paths: &Paths) -> Self {
        Self::from_values(None, None, paths)
    }

    fn from_values(port: Option<String>, transport_name: Option<String>, paths: &Paths) -> Self {
        Self {
            // 8000 is the port the product has always answered on. The second
            // port existed while two daemons ran side by side; one does now.
            port: port.and_then(|v| v.parse().ok()).unwrap_or(8000),
            db_path: paths.db.clone(),
            transport_name: transport_name.unwrap_or_else(|| "loopback".to_string()),
            runs_dir: paths.runs.clone(),
            state_home: Some(paths.root.clone()),
        }
    }
}

/// A path this crate wrote, for the consolidation to recognise its own work.
pub fn is_our_root(path: &Path) -> bool {
    path.join("vadgr.db").exists()
        || path.join("runs").is_dir()
        || path.join("credentials").is_dir()
}

#[cfg(test)]
mod tests {
    use super::*;

    fn env(pairs: &[(&str, &str)]) -> Environment {
        let mut e = Environment::default();
        for (key, value) in pairs {
            let v = Some(OsString::from(value));
            match *key {
                "VADGR_STATE_HOME" => e.state_home = v,
                "VADGR_DB" => e.db = v,
                "VADGR_RUNS_DIR" => e.runs_dir = v,
                "XDG_STATE_HOME" => e.xdg_state_home = v,
                "HOME" => e.home = v,
                "LOCALAPPDATA" => e.local_app_data = v,
                "USERPROFILE" => e.user_profile = v,
                other => panic!("unknown variable {other}"),
            }
        }
        e
    }

    /// The six cases of `ARCHITECTURE.md` section 3.1, as one test rather than
    /// four machines. The environment is an input, so every platform's answer is
    /// checkable from any platform.
    #[test]
    fn the_platform_root_is_the_one_the_architecture_names() {
        let linux = env(&[("HOME", "/home/o")]);
        assert_eq!(
            state_root(&linux, Layout::Unix).unwrap(),
            Path::new("/home/o/.local/state/vadgr")
        );

        let xdg = env(&[("XDG_STATE_HOME", "/xdg"), ("HOME", "/home/o")]);
        assert_eq!(
            state_root(&xdg, Layout::Unix).unwrap(),
            Path::new("/xdg/vadgr")
        );

        // A relative XDG_STATE_HOME is not a root. Honouring it would put state
        // below the launch directory, which is the defect this release removes.
        let relative = env(&[("XDG_STATE_HOME", "xdg"), ("HOME", "/home/o")]);
        assert_eq!(
            state_root(&relative, Layout::Unix).unwrap(),
            Path::new("/home/o/.local/state/vadgr")
        );

        let mac = env(&[("HOME", "/Users/o")]);
        assert_eq!(
            state_root(&mac, Layout::MacOs).unwrap(),
            Path::new("/Users/o/Library/Application Support/vadgr/state")
        );

        // The Windows cases are built with `join`, which uses the **host's**
        // separator, so the expectation is built the same way rather than
        // written with backslashes a Linux runner cannot produce. What is being
        // asserted is the base and the component, which is the decision; the
        // separator is the platform's and is right by construction there.
        let windows = env(&[("LOCALAPPDATA", r"C:\Users\o\AppData\Local")]);
        assert_eq!(
            state_root(&windows, Layout::Windows).unwrap(),
            PathBuf::from(r"C:\Users\o\AppData\Local").join("vadgr")
        );

        let fallback = env(&[("USERPROFILE", r"C:\Users\o")]);
        assert_eq!(
            state_root(&fallback, Layout::Windows).unwrap(),
            PathBuf::from(r"C:\Users\o")
                .join("AppData")
                .join("Local")
                .join("vadgr")
        );

        // A Windows path is not absolute to a Linux `Path`, so a host-based
        // check would silently skip this case on every runner we have.
        let relative_windows = env(&[("LOCALAPPDATA", r"AppData\Local")]);
        assert!(state_root(&relative_windows, Layout::Windows).is_none());
    }

    /// **The defect D-97 names.** Resolving from two different working
    /// directories must produce the same paths, because an installed daemon's
    /// database cannot depend on which terminal started it.
    #[test]
    fn no_default_is_relative_to_the_working_directory() {
        let paths = Paths::resolve(&env(&[("HOME", "/home/o")]), Layout::Unix).unwrap();
        for path in [&paths.root, &paths.db, &paths.runs, &paths.credentials] {
            assert!(path.is_absolute(), "{} is not absolute", path.display());
        }
        assert_eq!(paths.db, Path::new("/home/o/.local/state/vadgr/vadgr.db"));
        assert_eq!(paths.runs, Path::new("/home/o/.local/state/vadgr/runs"));
        assert_eq!(
            paths.credentials,
            Path::new("/home/o/.local/state/vadgr/credentials")
        );
    }

    /// The three overrides stay exact, because a managed deployment and the
    /// three concurrent e2e passes depend on them.
    #[test]
    fn each_override_moves_exactly_what_it_names() {
        let whole = Paths::resolve(
            &env(&[("VADGR_STATE_HOME", "/srv/v"), ("HOME", "/home/o")]),
            Layout::Unix,
        )
        .unwrap();
        assert_eq!(whole.db, Path::new("/srv/v/vadgr.db"));
        assert_eq!(whole.runs, Path::new("/srv/v/runs"));
        assert_eq!(whole.credentials, Path::new("/srv/v/credentials"));

        let one = Paths::resolve(
            &env(&[("VADGR_DB", "/tmp/x.db"), ("HOME", "/home/o")]),
            Layout::Unix,
        )
        .unwrap();
        assert_eq!(one.db, Path::new("/tmp/x.db"));
        assert_eq!(one.runs, Path::new("/home/o/.local/state/vadgr/runs"));

        let runs = Paths::resolve(
            &env(&[("VADGR_RUNS_DIR", "/tmp/r"), ("HOME", "/home/o")]),
            Layout::Unix,
        )
        .unwrap();
        assert_eq!(runs.runs, Path::new("/tmp/r"));
        assert_eq!(runs.db, Path::new("/home/o/.local/state/vadgr/vadgr.db"));
    }

    /// No home at all is refused, not guessed at.
    #[test]
    fn a_machine_with_no_home_is_told_rather_than_guessed_at() {
        let err = Paths::resolve(&Environment::default(), Layout::Unix).unwrap_err();
        assert_eq!(err, PathError::NoPlatformRoot);
        assert!(err.to_string().contains("VADGR_STATE_HOME"));
    }

    #[cfg(unix)]
    #[test]
    fn configured_paths_preserve_non_utf8_os_strings() {
        use std::os::unix::ffi::OsStringExt;

        let db = OsString::from_vec(b"/tmp/vadgr-\xff.db".to_vec());
        let environment = Environment {
            home: Some(OsString::from("/home/o")),
            db: Some(db.clone()),
            ..Default::default()
        };
        let paths = Paths::resolve(&environment, Layout::Unix).unwrap();
        assert_eq!(paths.db.as_os_str(), db);
    }

    /// The port default moved with the cutover: one daemon, one port.
    #[test]
    fn the_default_port_is_the_one_the_product_has_always_answered_on() {
        let paths = Paths::resolve(&env(&[("HOME", "/home/o")]), Layout::Unix).unwrap();
        assert_eq!(Config::from_values(None, None, &paths).port, 8000);
        assert_eq!(
            Config::from_values(Some("9001".into()), None, &paths).port,
            9001
        );
    }
}
