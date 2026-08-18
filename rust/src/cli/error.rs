//! What a command can fail with, and the code each failure leaves behind.
//!
//! `client.rs` owns the two failures that come from the daemon, and their exit
//! codes are a contract (§2.0). A command has two more of its own, and `click`
//! already separated them: a usage error exits `2`, and a command that ran and
//! could not finish exits `1`. Collapsing those is the same mistake as
//! collapsing "the daemon is down" into "the daemon said no".

use crate::client::ClientError;

#[derive(Debug)]
pub enum CliError {
    /// The daemon was unreachable, or answered with an error envelope.
    Client(ClientError),
    /// The arguments were wrong. `clap` exits `2` for the ones it parses, and
    /// this is the same code for the ones only the command can check.
    Usage(String),
    /// The command ran and could not finish. `click.ClickException`'s `1`.
    Failed(String),
    /// The owner detached from a watched run with Ctrl-C.
    ///
    /// `130` is the shell's convention for SIGINT, and the run keeps going, so
    /// this is not a failure of either the run or the CLI.
    Detached,
}

impl CliError {
    pub fn exit_code(&self) -> i32 {
        match self {
            Self::Client(e) => e.exit_code(),
            Self::Usage(_) => 2,
            Self::Failed(_) => 1,
            Self::Detached => 130,
        }
    }

    /// Whether the failure still owes the owner a message.
    ///
    /// A detached run has already printed its own line, and a second one reading
    /// `Error:` would say the CLI failed when nothing did.
    pub fn is_silent(&self) -> bool {
        matches!(self, Self::Detached)
    }
}

impl std::fmt::Display for CliError {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            Self::Client(e) => e.fmt(f),
            Self::Usage(m) | Self::Failed(m) => f.write_str(m),
            Self::Detached => f.write_str("detached"),
        }
    }
}

impl From<ClientError> for CliError {
    fn from(e: ClientError) -> Self {
        Self::Client(e)
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::client::{ApiClientError, DaemonUnreachable};

    #[test]
    fn each_failure_keeps_its_own_code() {
        assert_eq!(
            CliError::Client(ClientError::Unreachable(DaemonUnreachable {
                base_url: "http://127.0.0.1:8000".into()
            }))
            .exit_code(),
            3
        );
        assert_eq!(
            CliError::Client(ClientError::Api(ApiClientError {
                message: "no".into(),
                status: 400,
                code: None,
                details: serde_json::Value::Null,
            }))
            .exit_code(),
            1
        );
        assert_eq!(CliError::Usage("wrong".into()).exit_code(), 2);
        assert_eq!(CliError::Failed("stopped".into()).exit_code(), 1);
        assert_eq!(CliError::Detached.exit_code(), 130);
    }

    /// The detached case is the only one that must not print a second line.
    #[test]
    fn only_a_detached_run_prints_nothing_more() {
        assert!(CliError::Detached.is_silent());
        assert!(!CliError::Failed("stopped".into()).is_silent());
        assert!(!CliError::Usage("wrong".into()).is_silent());
    }
}
