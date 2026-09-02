//! `vadgr`, the on-box owner surface.
//!
//! The command tree is a contract: the recorded surface sweep asserts every
//! verb, its nesting and its exit code, so a change here is a change to what a
//! script can rely on.
//!
//! **Until the `0.4.9` cutover, `vadgr start` launches the still-shipped daemon
//! rather than the one in this crate.** The default flips once, in a release
//! that contains nothing else, so a defect found afterwards has one candidate
//! cause.

mod client;
mod commands;
mod error;
mod output;
mod prompt;
mod stream;

use std::path::PathBuf;
use std::time::Duration;

use clap::{Parser, Subcommand};

use client::Client;
use error::CliError;

/// The longest a watched run is followed before the watcher detaches.
const RUN_WATCH_TIMEOUT: Duration = Duration::from_secs(7200);

#[derive(Parser)]
#[command(
    name = "vadgr",
    about = "vadgr CLI.",
    version,
    disable_help_subcommand = true,
    arg_required_else_help = true
)]
struct Cli {
    /// The daemon's base URL.
    #[arg(long, global = true, env = "VADGR_API_URL", hide = true)]
    api_url: Option<String>,

    /// Open the installed local machine console.
    #[arg(long, conflicts_with_all = ["daemon", "installer"])]
    console: bool,

    /// Run the installed daemon in the foreground.
    #[arg(long, hide = true, conflicts_with_all = ["console", "installer"])]
    daemon: bool,

    /// Open the native release-vehicle installer.
    #[arg(long, hide = true, conflicts_with_all = ["console", "daemon"])]
    installer: bool,

    /// Exact release vehicle being installed.
    #[arg(long, hide = true, requires = "installer")]
    vehicle: Option<PathBuf>,

    #[command(subcommand)]
    command: Option<Command>,
}

#[derive(Subcommand)]
enum Command {
    /// Assemble vadgr's pinned private computer-use payload.
    #[command(name = "__payload-setup", hide = true)]
    PayloadSetup {
        #[arg(long)]
        install_root: PathBuf,
        #[arg(long)]
        apply_system_deps: bool,
        #[arg(long)]
        payload_only: bool,
    },
    /// Commit the package terms record after a successful installer transaction.
    #[command(name = "__record-terms-acceptance", hide = true)]
    RecordTermsAcceptance {
        #[arg(long)]
        terms_version: String,
        #[arg(long)]
        installer_version: String,
        #[arg(long)]
        terms_file: PathBuf,
        #[arg(long)]
        installer_file: PathBuf,
    },
    /// Retain the natively verified Windows setup after a committed MSI transaction.
    #[command(name = "__cache-install-vehicle", hide = true)]
    CacheInstallVehicle {
        #[arg(long)]
        installer_file: PathBuf,
    },
    /// Verify a retained native package against this installation's publisher.
    #[command(name = "__verify-install-vehicle", hide = true)]
    VerifyInstallVehicle {
        #[arg(long)]
        installer_file: PathBuf,
    },
    /// Delete owner state after the package UI received explicit confirmation.
    #[command(name = "__purge-owner-state", hide = true)]
    PurgeOwnerState,
    /// Commit anti-downgrade state after a fully successful package commit.
    #[command(name = "__accept-release-sequence", hide = true)]
    AcceptReleaseSequence {
        #[arg(long)]
        manifest: PathBuf,
        #[arg(long)]
        signature: PathBuf,
    },
    /// Verify one release artifact without executing it.
    #[command(name = "__verify-release-artifact", hide = true)]
    VerifyReleaseArtifact {
        #[arg(long)]
        manifest: PathBuf,
        #[arg(long)]
        signature: PathBuf,
        #[arg(long)]
        target: String,
        #[arg(long)]
        artifact: PathBuf,
    },
    /// Serve. The daemon itself, in the foreground.
    ///
    /// Hidden because nobody types it: `vadgr start` spawns this binary again
    /// with this verb and returns. It exists because the product is one
    /// executable, so the server and the client are the same file.
    #[command(hide = true)]
    Serve {
        /// An address to bind, repeated once per address.
        #[arg(long = "host")]
        host: Vec<String>,
        /// The port to serve on.
        #[arg(long = "port")]
        port: Option<u16>,
    },

    /// Start the vadgr daemon (the API).
    Api {
        /// API server port.
        #[arg(long = "api-port", visible_alias = "port")]
        api_port: Option<u16>,
    },
    /// Manage computer use (desktop automation).
    ComputerUse {
        #[command(subcommand)]
        action: ComputerUseAction,
    },
    /// Read or change machine configuration.
    Config {
        #[command(subcommand)]
        action: ConfigAction,
    },
    /// Check API health.
    Health,
    /// Tail service logs.
    Logs {
        #[arg(long, short, default_value = "api")]
        service: String,
        /// Follow the log. `--no-follow` prints the tail and returns.
        #[arg(long, short, default_value_t = true, overrides_with = "no_follow")]
        follow: bool,
        #[arg(long = "no-follow")]
        no_follow: bool,
        #[arg(long, short = 'n', default_value_t = 50)]
        lines: usize,
    },
    /// List models and select the machine default.
    Model {
        #[command(subcommand)]
        action: ModelAction,
    },
    /// Show this machine and its complete configuration.
    Machine {
        /// Print the machine as JSON.
        #[arg(long = "json")]
        as_json: bool,
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
    Restart {
        #[arg(long = "api-port", visible_alias = "port")]
        api_port: Option<u16>,
    },
    /// Start a run from a task sentence and watch it.
    Run {
        /// What the machine should do.
        task: String,
        /// Provider to run on (needs --model).
        #[arg(long, short)]
        provider: Option<String>,
        /// Model to run (needs --provider).
        #[arg(long, short)]
        model: Option<String>,
        /// Start it and return.
        #[arg(long, short)]
        background: bool,
        /// Print the run row as JSON.
        #[arg(long = "json")]
        as_json: bool,
    },
    /// Manage runs.
    Runs {
        #[command(subcommand)]
        action: Option<RunsAction>,
    },
    /// Start the vadgr daemon (the API).
    Start {
        /// API server port.
        #[arg(long = "api-port", visible_alias = "port")]
        api_port: Option<u16>,
    },
    /// Show service status.
    Status,
    /// Stop the vadgr daemon.
    Stop,
    /// Pull latest code and reinstall deps if changed.
    Update {
        /// Report what an update would do, and change nothing.
        #[arg(long)]
        check: bool,
    },
}

#[derive(Subcommand)]
enum ComputerUseAction {
    /// Enable computer use.
    Enable,
    /// Disable computer use.
    Disable,
    /// Check computer use status.
    Status,
}

#[derive(Subcommand)]
enum ConfigAction {
    /// Read one machine setting.
    Get { key: String },
    /// Change one machine setting.
    Set { key: String, value: String },
}

#[derive(Subcommand)]
enum ModelAction {
    /// Set the machine default after a live check.
    Default {
        /// The `provider/model` pair.
        model: Option<String>,
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
        #[arg(long = "replacement-default-model", hide = true)]
        replacement_default_model: Option<String>,
    },
    /// Disconnect one non-default provider.
    Logout { provider: String },
    /// Show connected providers and their model catalogs.
    Status {
        #[arg(long = "refresh")]
        refresh: bool,
        provider: Option<String>,
    },
}

#[derive(Subcommand)]
enum RunsAction {
    /// Cancel a running run.
    Cancel { run_id: String },
    /// Show run details.
    Get { run_id: String },
    /// List all runs.
    List {
        /// Filter by status.
        #[arg(long, short)]
        status: Option<String>,
    },
    /// Resume a failed run.
    Resume { run_id: String },
}

/// Where the daemon is, resolved once.
///
/// `--api-url`, then `VADGR_API_URL` (which `clap` folds into the same option),
/// then the port a running daemon actually took, then `VADGR_PORT`, then the
/// default. **The port file comes before the environment** because `start` walks
/// up from a busy port, and a CLI that ignored that would call a port nothing is
/// listening on while the daemon runs one along.
///
/// The names this product used before `0.4.8` are gone rather than deprecated:
/// §6a allows an adapter only for a named released consumer, and there is one
/// installation, the owner's, on the same machine as the new state root.
fn base_url(explicit: Option<&str>) -> String {
    if let Some(url) = explicit {
        return url.to_owned();
    }
    let port = commands::service::read_active_port("api", commands::service::default_port());
    format!("http://127.0.0.1:{port}")
}

async fn run_task(
    client: &Client,
    task: String,
    provider: Option<String>,
    model: Option<String>,
    background: bool,
    as_json: bool,
) -> Result<(), CliError> {
    if task.trim().is_empty() {
        return Err(CliError::Usage("TASK must not be empty.".to_owned()));
    }
    if provider.is_some() != model.is_some() {
        return Err(CliError::Usage(
            "--provider and --model must be given together.".to_owned(),
        ));
    }

    let mut body = serde_json::json!({"task": task});
    if let (Some(provider), Some(model)) = (provider, model) {
        body["provider"] = serde_json::Value::String(provider);
        body["model"] = serde_json::Value::String(model);
    }

    let result = client.post("/api/runs", Some(body)).await?;
    let run_id = result
        .get("id")
        .and_then(|v| v.as_str())
        .unwrap_or("?")
        .to_owned();

    // Under `--json` a watched run prints nothing yet: the document a script
    // wants is the finished run, and printing the queued row first would put two
    // documents on one stdout. A background run prints now, because the queued
    // row is all that will ever be known here.
    if as_json {
        if background {
            anstream::println!(
                "{}",
                serde_json::to_string_pretty(&result).unwrap_or_else(|_| result.to_string())
            );
        }
    } else {
        anstream::println!("{}", output::success(&format!("Run started: {run_id}")));
    }

    // `--background` exits `0` once the run is accepted, because the outcome is
    // not known yet and inventing one would be a lie a script acts on.
    if background {
        // Not under `--json`. That flag's whole purpose is a stdout a script can
        // parse, and a friendly line after the object makes the stream invalid
        // JSON, so `jq` fails on output the CLI just called machine readable.
        if !as_json {
            anstream::println!("  Watch it with: vadgr runs get {run_id}");
        }
        return Ok(());
    }

    let outcome = stream::follow(client.base_url(), &run_id, RUN_WATCH_TIMEOUT, as_json).await;
    if as_json {
        // One document, written once the run has an outcome to describe.
        let row = client.get(&format!("/api/runs/{run_id}")).await?;
        anstream::println!(
            "{}",
            serde_json::to_string_pretty(&row).unwrap_or_else(|_| row.to_string())
        );
    }
    match outcome.exit_code() {
        0 => Ok(()),
        // The outcome was already reported. A second `Error:` line would read as
        // the CLI having failed rather than the run.
        130 => Err(CliError::Detached),
        _ => Err(CliError::Failed(String::new())),
    }
}

#[tokio::main]
async fn main() {
    let cli = Cli::parse();
    let client = match Client::new(base_url(cli.api_url.as_deref())) {
        Ok(client) => client,
        // The same rendering and exit code as `CliError::Failed`, without a
        // command ever having run.
        Err(message) => {
            anstream::eprintln!("{}", output::error(&message));
            std::process::exit(1);
        }
    };

    let result: Result<(), CliError> = if cli.console {
        open_console(base_url(cli.api_url.as_deref()))
    } else if cli.installer {
        open_installer(cli.vehicle)
    } else if cli.daemon {
        vadgr_daemon::daemon::serve(Vec::new(), None)
            .await
            .map_err(|error| CliError::Failed(error.to_string()))
    } else {
        match cli.command {
            None => Err(CliError::Usage("a command is required".to_owned())),
            Some(Command::PayloadSetup {
                install_root,
                apply_system_deps,
                payload_only,
            }) => payload_setup(install_root, apply_system_deps, payload_only).await,
            Some(Command::RecordTermsAcceptance {
                terms_version,
                installer_version,
                terms_file,
                installer_file,
            }) => vadgr_daemon::install::record_terms_acceptance(
                &terms_version,
                &installer_version,
                &terms_file,
                &installer_file,
            )
            .map(|_| ())
            .map_err(|error| CliError::Failed(error.to_string())),
            Some(Command::CacheInstallVehicle { installer_file }) => {
                vadgr_daemon::install::cache_install_vehicle(&installer_file)
                    .map_err(|error| CliError::Failed(error.to_string()))
            }
            Some(Command::VerifyInstallVehicle { installer_file }) => {
                vadgr_daemon::install::verify_install_vehicle(&installer_file)
                    .map_err(|error| CliError::Failed(error.to_string()))
            }
            Some(Command::PurgeOwnerState) => vadgr_daemon::install::purge_owner_state()
                .map_err(|error| CliError::Failed(error.to_string())),
            Some(Command::AcceptReleaseSequence {
                manifest,
                signature,
            }) => {
                let result = (|| -> anyhow::Result<()> {
                    let verified = vadgr_daemon::install::VerifiedManifest::open(
                        &manifest,
                        &signature,
                        vadgr_daemon::install::RELEASE_PUBLIC_KEY,
                    )?;
                    let state = vadgr_daemon::config::Config::from_env()
                        .map_err(|error| anyhow::anyhow!(error.to_string()))?
                        .state_home
                        .ok_or_else(|| anyhow::anyhow!("the Vadgr state root is unavailable"))?;
                    verified.accept_sequence(&state)
                })();
                result.map_err(|error| CliError::Failed(error.to_string()))
            }
            Some(Command::VerifyReleaseArtifact {
                manifest,
                signature,
                target,
                artifact,
            }) => {
                let result = (|| -> anyhow::Result<()> {
                    let verified = vadgr_daemon::install::VerifiedManifest::open(
                        &manifest,
                        &signature,
                        vadgr_daemon::install::RELEASE_PUBLIC_KEY,
                    )?;
                    let row = verified.verify_artifact(&artifact, &target)?;
                    if row.artifact.kind == "tar.gz" {
                        vadgr_daemon::install::validate_tar_gz(&artifact)?;
                    }
                    Ok(())
                })();
                result.map_err(|error| CliError::Failed(error.to_string()))
            }
            Some(Command::Health) => commands::info::health(&client).await,
            Some(Command::Providers) => commands::info::providers(&client).await,
            Some(Command::ComputerUse { action }) => match action {
                ComputerUseAction::Enable => commands::info::computer_use_enable(&client).await,
                ComputerUseAction::Disable => commands::info::computer_use_disable(&client).await,
                ComputerUseAction::Status => commands::info::computer_use_status(&client).await,
            },
            Some(Command::Config { action }) => match action {
                ConfigAction::Get { key } => commands::machine::get(&client, &key).await,
                ConfigAction::Set { key, value } => {
                    commands::machine::set(&client, &key, &value).await
                }
            },
            Some(Command::Pair) => commands::pair::pair(&client).await,
            Some(Command::Provider { action }) => match action {
                ProviderAction::Login {
                    provider,
                    auth,
                    replacement_default_model,
                } => {
                    commands::provider::login(&client, provider, auth, replacement_default_model)
                        .await
                }
                ProviderAction::Logout { provider } => {
                    commands::provider::logout(&client, &provider).await
                }
                ProviderAction::Status { refresh, provider } => {
                    commands::provider::status(&client, refresh, provider).await
                }
            },
            Some(Command::Model { action }) => match action {
                ModelAction::List => commands::provider::model_list(&client).await,
                ModelAction::Default { model } => {
                    commands::provider::model_default(&client, model).await
                }
            },
            Some(Command::Machine { as_json }) => commands::machine::show(&client, as_json).await,
            Some(Command::Runs { action }) => match action {
                // `vadgr runs` with no subcommand lists them, which is the shipped
                // behaviour and what the listing's own output invites.
                None => commands::runs::list(&client, None).await,
                Some(RunsAction::List { status }) => {
                    commands::runs::list(&client, status.as_deref()).await
                }
                Some(RunsAction::Get { run_id }) => commands::runs::get(&client, &run_id).await,
                Some(RunsAction::Cancel { run_id }) => {
                    commands::runs::cancel(&client, &run_id).await
                }
                Some(RunsAction::Resume { run_id }) => {
                    commands::runs::resume(&client, &run_id).await
                }
            },
            Some(Command::Run {
                task,
                provider,
                model,
                background,
                as_json,
            }) => run_task(&client, task, provider, model, background, as_json).await,
            Some(Command::Serve { host, port }) => vadgr_daemon::daemon::serve(host, port)
                .await
                .map_err(|e| CliError::Failed(e.to_string())),
            Some(Command::Start { api_port }) | Some(Command::Api { api_port }) => {
                commands::service::start(api_port).await
            }
            Some(Command::Stop) => commands::service::stop(),
            Some(Command::Restart { api_port }) => commands::service::restart(api_port).await,
            Some(Command::Status) => commands::service::status(),
            Some(Command::Logs {
                service,
                follow,
                no_follow,
                lines,
            }) => commands::service::logs(&service, follow && !no_follow, lines).await,
            Some(Command::Update { check }) => commands::service::update(check).await,
        }
    };

    if let Err(e) = result {
        // Some failures have already said everything there is to say, and a
        // command that printed its own warning gets an empty message rather than
        // a second line contradicting it.
        let message = e.to_string();
        if !e.is_silent() && !message.is_empty() {
            anstream::eprintln!("{}", output::error(&message));
            // A `5xx` is the daemon blaming itself, and its message rarely says
            // why. The log does, and nothing else on the machine will point
            // someone at it.
            if matches!(&e, CliError::Client(client::ClientError::Api(api)) if api.is_server_fault())
            {
                anstream::eprintln!("  The daemon logged it: vadgr logs --no-follow");
            }
        }
        std::process::exit(e.exit_code());
    }
}

#[cfg(feature = "native-gui")]
fn open_installer(vehicle: Option<PathBuf>) -> Result<(), CliError> {
    let vehicle =
        vehicle.ok_or_else(|| CliError::Usage("--installer requires --vehicle".to_owned()))?;
    vadgr_daemon::installer::run(vehicle).map_err(|error| CliError::Failed(error.to_string()))
}

#[cfg(not(feature = "native-gui"))]
fn open_installer(_vehicle: Option<PathBuf>) -> Result<(), CliError> {
    Err(CliError::Failed(
        "This build does not include the native installer.".to_owned(),
    ))
}

#[cfg(feature = "native-gui")]
fn open_console(base_url: String) -> Result<(), CliError> {
    vadgr_daemon::console::run(base_url).map_err(|error| CliError::Failed(error.to_string()))
}

#[cfg(not(feature = "native-gui"))]
fn open_console(_base_url: String) -> Result<(), CliError> {
    Err(CliError::Failed(
        "This build does not include the native console.".to_owned(),
    ))
}

async fn payload_setup(
    install_root: PathBuf,
    apply_system_deps: bool,
    payload_only: bool,
) -> Result<(), CliError> {
    let installer = vadgr_daemon::cua_payload::CuaPayloadInstaller::new(install_root)
        .map_err(|error| CliError::Failed(error.to_string()))?;
    let runtime = installer
        .assemble()
        .await
        .map_err(|error| CliError::Failed(format!("Could not assemble computer use: {error:#}")))?;
    if payload_only {
        return Ok(());
    }
    let setup = runtime.setup_command(apply_system_deps);
    let status = std::process::Command::new(setup.program)
        .args(setup.args)
        .status()
        .map_err(|error| {
            CliError::Failed(format!("Could not check computer-use setup: {error}"))
        })?;
    if !status.success() {
        return Err(CliError::Failed(
            "Computer-use setup did not complete. Nothing was installed.".to_owned(),
        ));
    }
    Ok(())
}
