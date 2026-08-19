//! Process configuration.

use std::ffi::OsString;
use std::path::PathBuf;

/// The version this daemon reports at `GET /api/health`.
pub const VERSION: &str = "0.4.8";

pub struct Config {
    pub port: u16,
    pub db_path: PathBuf,
    pub transport_name: String,
    pub runs_dir: PathBuf,
    pub state_home: Option<PathBuf>,
}

impl Config {
    pub fn from_env() -> Self {
        Self::from_values(
            std::env::var("VADGR_PORT").ok(),
            std::env::var_os("VADGR_DB"),
            std::env::var("VADGR_TRANSPORT").ok(),
            std::env::var_os("VADGR_RUNS_DIR"),
            std::env::var_os("VADGR_STATE_HOME"),
        )
    }

    fn from_values(
        port: Option<String>,
        db_path: Option<OsString>,
        transport_name: Option<String>,
        runs_dir: Option<OsString>,
        state_home: Option<OsString>,
    ) -> Self {
        let port = port
            .and_then(|v| v.parse().ok())
            // Not 8000. The strangler runs both daemons at once, so the Rust
            // one takes its own port by default and only shares when told to.
            .unwrap_or(8100);
        Self {
            port,
            db_path: db_path
                .map(PathBuf::from)
                .unwrap_or_else(|| PathBuf::from("data").join("vadgr-rust.db")),
            transport_name: transport_name.unwrap_or_else(|| "loopback".to_string()),
            runs_dir: runs_dir.map(PathBuf::from).unwrap_or_else(default_runs_dir),
            state_home: state_home.map(PathBuf::from),
        }
    }
}

fn default_runs_dir() -> PathBuf {
    let home = if cfg!(windows) {
        std::env::var_os("USERPROFILE")
    } else {
        std::env::var_os("HOME")
    };
    home.map(PathBuf::from)
        .filter(|path| path.is_absolute())
        .map(|path| path.join(".vadgr").join("runs"))
        .unwrap_or_else(|| PathBuf::from("data").join("runs"))
}

#[cfg(test)]
mod tests {
    use super::Config;
    use std::path::Path;

    #[test]
    fn default_paths_are_built_from_native_components() {
        let config = Config::from_values(None, None, None, None, None);

        assert_eq!(config.db_path, Path::new("data").join("vadgr-rust.db"));
        assert!(
            config.runs_dir.ends_with(Path::new(".vadgr").join("runs"))
                || config.runs_dir == Path::new("data").join("runs")
        );
    }

    #[cfg(unix)]
    #[test]
    fn configured_paths_preserve_non_utf8_os_strings() {
        use std::ffi::OsString;
        use std::os::unix::ffi::OsStringExt;

        let db_path = OsString::from_vec(b"/tmp/vadgr-\xff.db".to_vec());
        let state_home = OsString::from_vec(b"/tmp/state-\xfe".to_vec());
        let config = Config::from_values(
            None,
            Some(db_path.clone()),
            None,
            None,
            Some(state_home.clone()),
        );

        assert_eq!(config.db_path.as_os_str(), db_path);
        assert_eq!(config.state_home.unwrap().as_os_str(), state_home);
    }
}
