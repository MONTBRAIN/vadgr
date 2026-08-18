//! `vadgr`, the on-box owner surface.
//!
//! Ported from `cli/` at `0.4.8`. The command tree is unchanged: same verbs,
//! same nesting, same exit codes, because the recorded surface sweep asserts
//! argv and exit code and a port is judged against it.
//!
//! **`vadgr start` still launches the Python daemon in this release.** The
//! cutover is `0.4.9`, alone in its release, so a defect found after it has one
//! candidate cause.

mod client;
mod commands;
mod output;
mod stream;

use clap::{Parser, Subcommand};

use client::{Client, ClientError};

/// The base URL, resolved once.
///
/// `--api-url`, then `VADGR_API_URL`, then `VADGR_PORT` on loopback, then the
/// default. The old `FORGE_*` names are gone rather than deprecated: §6a allows
/// an adapter only for a named released consumer, and there is one installation,
/// the owner's, on the same machine as the new state root.
const DEFAULT_PORT: u16 = 8000;

#[derive(Parser)]
#[command(
    name = "vadgr",
    about = "vadgr CLI.",
    version,
    disable_help_subcommand = true
)]
struct Cli {
    /// The daemon's base URL.
    #[arg(long, global = true, env = "VADGR_API_URL", hide = true)]
    api_url: Option<String>,

    #[command(subcommand)]
    command: Command,
}

#[derive(Subcommand)]
enum Command {
    /// Start the vadgr daemon (the API).
    Api,
    /// Manage computer use (desktop automation).
    ComputerUse {
        #[command(subcommand)]
        action: ComputerUseAction,
    },
    /// Check API health.
    Health,
    /// Tail service logs.
    Logs,
    /// List models and select the machine default.
    Model {
        #[command(subcommand)]
        action: ModelAction,
    },
    /// Pair a mobile device: mint a one-time code and show a QR.
    Pair,
    /// Connect and manage model providers.
    Provider {
        #[command(subcommand)]
        action: ProviderAction,
    },
    /// List available providers and models.
    Providers,
    /// Restart the vadgr daemon.
    Restart,
    /// Start a run from a task sentence and watch it.
    Run {
        /// What the machine should do.
        task: String,
    },
    /// Manage runs.
    Runs {
        #[command(subcommand)]
        action: RunsAction,
    },
    /// Start the vadgr daemon (the API).
    Start,
    /// Show service status.
    Status,
    /// Stop the vadgr daemon.
    Stop,
    /// Pull latest code and reinstall deps if changed.
    Update,
}

#[derive(Subcommand)]
enum ComputerUseAction {
    /// Enable computer use.
    Enable,
    /// Disable computer use.
    Disable,
    /// Show computer-use status.
    Status,
}

#[derive(Subcommand)]
enum ModelAction {
    /// Set the machine default after a live check.
    Default {
        /// The `provider/model` pair.
        model: String,
    },
    /// List models from every connected provider.
    List,
}

#[derive(Subcommand)]
enum ProviderAction {
    /// Connect or reauthenticate one provider.
    Login {
        provider: Option<String>,
        /// `chatgpt` or `api-key`, for OpenAI.
        #[arg(long)]
        auth: Option<String>,
    },
    /// Disconnect one non-default provider.
    Logout { provider: Option<String> },
    /// Show connected providers and their model catalogs.
    Status {
        #[arg(long = "refresh")]
        refresh: bool,
    },
}

#[derive(Subcommand)]
enum RunsAction {
    /// Cancel a running run.
    Cancel { run_id: String },
    /// Show run details.
    Get { run_id: String },
    /// List all runs.
    List,
    /// Resume a failed run.
    Resume { run_id: String },
}

fn base_url(explicit: Option<&str>) -> String {
    if let Some(url) = explicit {
        return url.to_owned();
    }
    let port = std::env::var("VADGR_PORT")
        .ok()
        .and_then(|p| p.parse::<u16>().ok())
        .unwrap_or(DEFAULT_PORT);
    format!("http://127.0.0.1:{port}")
}

#[tokio::main]
async fn main() {
    let cli = Cli::parse();
    let client = Client::new(base_url(cli.api_url.as_deref()));

    let result: Result<(), ClientError> = match cli.command {
        Command::Health => commands::info::health(&client).await,
        Command::Providers => commands::info::providers(&client).await,
        Command::ComputerUse { action } => match action {
            ComputerUseAction::Enable => commands::info::computer_use_set(&client, true).await,
            ComputerUseAction::Disable => commands::info::computer_use_set(&client, false).await,
            ComputerUseAction::Status => commands::info::computer_use_status(&client).await,
        },
        Command::Runs { action } => match action {
            RunsAction::List => commands::runs::list(&client).await,
            RunsAction::Get { run_id } => commands::runs::get(&client, &run_id).await,
            RunsAction::Cancel { run_id } => commands::runs::cancel(&client, &run_id).await,
            RunsAction::Resume { run_id } => commands::runs::resume(&client, &run_id).await,
        },
        _ => {
            anstream::eprintln!("{}", output::error("not yet ported at this commit"));
            std::process::exit(1);
        }
    };

    if let Err(e) = result {
        anstream::eprintln!("{}", output::error(&e.to_string()));
        std::process::exit(e.exit_code());
    }
}
