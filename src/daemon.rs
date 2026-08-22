//! Serving. The daemon half of the one binary this product ships.
//!
//! It was a second executable until `0.4.9`. Two files meant a user received
//! two artifacts, kept them in step and trusted both to run one product, and
//! every distribution step happened twice. The CLI now spawns itself with
//! `serve`, so there is one file to build, copy, sign and publish.

use crate::engine::Engine;
use crate::engine::mcp::DefaultHostFactory;
use crate::engine::provider::NativeModelFactory;
use crate::engine::supervisor::RunSupervisor;
use crate::state::AppState;
use crate::{auth, computer_use_setup, config, db, migrate, routes, transport, ws};
use anyhow::Result;
use std::sync::Arc;
use std::sync::RwLock;
use tower_http::trace::{DefaultMakeSpan, DefaultOnResponse, TraceLayer};
use tracing::Level;

/// Run the daemon in the foreground until it stops.
///
/// The caller has already decided this process serves. `vadgr start` spawns
/// this binary again with `serve` and returns; nothing else calls it.
pub async fn serve(hosts: Vec<String>, port: Option<u16>) -> Result<()> {
    tracing_subscriber::fmt()
        .with_env_filter(
            tracing_subscriber::EnvFilter::try_from_default_env().unwrap_or_else(|_| "info".into()),
        )
        .init();

    // A machine with no platform state directory is not a case to guess at: the
    // daemon says so and does not start, rather than inventing somewhere to put
    // a user's credentials.
    let environment = config::Environment::from_env();
    let paths = config::Paths::resolve(&environment, config::Layout::host())
        .map_err(|e| anyhow::anyhow!("{e}"))?;

    // **Before anything is served.** A run submitted into a half-migrated
    // machine is the defect this ordering removes, and a refusal here stops the
    // process with the sources untouched rather than starting a machine that has
    // quietly lost its history.
    let working_dir = std::env::current_dir().unwrap_or_default();
    let home = environment.home.clone().map(std::path::PathBuf::from);
    let inventory = migrate::take_inventory(&paths.root, &working_dir, home.as_deref());
    let plan = migrate::decide(&inventory, &paths.root).map_err(|e| anyhow::anyhow!("{e}"))?;
    if !matches!(plan, migrate::Plan::AlreadyHere | migrate::Plan::Fresh) {
        tracing::info!(?plan, root = %paths.root.display(), "consolidating machine state");
    }
    migrate::apply(&plan, &paths.root).map_err(|e| anyhow::anyhow!("{e}"))?;

    let config = config::Config::from_env().map_err(|e| anyhow::anyhow!("{e}"))?;
    let db = db::Db::open(&config.db_path)?;
    let providers =
        crate::engine::provider::ProviderService::native(db.clone(), config.state_home.clone())?;
    let computer_use_setup = Arc::new(computer_use_setup::SetupService::from_env()?);
    let computer_use_status = computer_use_setup.status()?;
    let ws = Arc::new(ws::manager::ConnectionManager::new());
    let model_factory = Arc::new(NativeModelFactory::new(providers.clone()));
    let host_factory = Arc::new(DefaultHostFactory::new(computer_use_setup.clone()));
    let engine = Arc::new(Engine::new(
        model_factory,
        host_factory,
        db.clone(),
        config.runs_dir.clone(),
    ));
    let supervisor = RunSupervisor::new(engine, db.clone(), ws.clone());
    let recovery = supervisor.recover_on_boot().await;
    tracing::info!(
        resumed = recovery.resumed.len(),
        parked = recovery.parked.len(),
        failed = recovery.failed.len(),
        "run recovery scan complete"
    );

    // What the caller asked for wins, and what it did not ask for is resolved
    // as before: `vadgr start` passes the hosts its port probe bound, and each
    // transport takes its own out of that override.
    let port = port.unwrap_or(config.port);
    let pairing = Arc::new(auth::pairing::PairingStore::new(
        auth::pairing::PAIRING_TTL_SECONDS,
    ));
    // The registry: every transport this build supports, or the loopback
    // transport alone under the local-only override. The daemon names no
    // member and counts none; it serves whatever the registry holds.
    let transports = Arc::new(transport::Transports::from_config(
        &config,
        port,
        Some(transport::TransportRuntime {
            db: db.clone(),
            pairing: pairing.clone(),
            ws: ws.clone(),
        }),
    ));
    tracing::info!(
        supported = ?transports.iter().map(|t| t.name()).collect::<Vec<_>>(),
        "transports"
    );

    let state = AppState {
        db,
        config: Arc::new(config),
        transports: transports.clone(),
        pairing,
        ws,
        providers,
        computer_use_setup,
        computer_use_status: Arc::new(RwLock::new(computer_use_status)),
        supervisor,
    };

    let app = routes::router(state.clone())
        .layer(axum::middleware::from_fn_with_state(
            state.clone(),
            auth::gate::gate,
        ))
        .layer(
            TraceLayer::new_for_http()
                .make_span_with(DefaultMakeSpan::new().level(Level::INFO))
                .on_response(DefaultOnResponse::new().level(Level::INFO)),
        );

    let callback_state = state.clone();
    let callback = tokio::spawn(async move {
        // Both ports, in order, because the authorization server matches the
        // redirect against a fixed allow-list: an arbitrary free port is
        // rejected, and these two are the ones it accepts. The listener takes
        // whichever it can get and the flow is told which, so the browser is
        // sent to the port that is actually listening.
        const CALLBACK_PORTS: [u16; 2] = [1455, 1457];
        // A port can be unavailable with nothing listening on it, which is how
        // Windows reserves ranges, so this state can last for the daemon's
        // whole life. It is reported once when it changes rather than on every
        // retry, which would write a line a second forever.
        let mut reported_unavailable = false;
        loop {
            let mut bound = None;
            for port in CALLBACK_PORTS {
                match tokio::net::TcpListener::bind(("127.0.0.1", port)).await {
                    Ok(listener) => {
                        bound = Some((listener, port));
                        break;
                    }
                    Err(error) => {
                        tracing::debug!(%error, port, "callback port is unavailable");
                    }
                }
            }
            match bound.ok_or(()) {
                Ok((listener, port)) => {
                    reported_unavailable = false;
                    callback_state.providers.set_oauth_callback_port(Some(port));
                    tracing::info!(addr = %format!("127.0.0.1:{port}"), "OpenAI callback listening");
                    // The callback listener is a served surface like any other,
                    // so it gets the same tracing. Without it a callback left no
                    // record at all: the redirect a browser followed could not be
                    // read back from the daemon log on any platform, which made
                    // the live-authorization row unverifiable rather than merely
                    // unrun. Query values never reach the log, because the span
                    // records the path only.
                    if let Err(error) = axum::serve(
                        listener,
                        routes::providers::callback_router(callback_state.clone()).layer(
                            TraceLayer::new_for_http()
                                .make_span_with(routes::providers::callback_span)
                                .on_response(DefaultOnResponse::new().level(Level::INFO)),
                        ),
                    )
                    .await
                    {
                        tracing::warn!(%error, "OpenAI callback listener stopped");
                    }
                }
                Err(()) => {
                    // At `warn`, because the CLI tells a person to read this
                    // log when a sign-in refuses, and at `debug` that
                    // instruction sent them to an empty file.
                    if !reported_unavailable {
                        reported_unavailable = true;
                        tracing::warn!(
                            ports = ?CALLBACK_PORTS,
                            "no callback port could be bound, so ChatGPT sign-in \
                             is refused until one frees"
                        );
                    }
                }
            }
            callback_state.providers.set_oauth_callback_port(None);
            tokio::time::sleep(std::time::Duration::from_secs(1)).await;
        }
    });

    // Serve every member of the registry. A transport that cannot come up
    // does not stop the others: its error is logged at warn, its reach turns
    // unavailable in its own words, and loopback keeps serving, so the CLI
    // and the journal never depend on a network being there. The daemon ends
    // only when nothing at all is serving.
    let mut serving = Vec::new();
    for member in transports.iter() {
        let name = member.name();
        let serve = member.serve(app.clone(), port, &hosts);
        serving.push(async move {
            if let Err(error) = serve.await {
                tracing::warn!(transport = name, %error, "transport is not serving");
            }
            name
        });
    }
    futures_util::future::join_all(serving).await;
    callback.abort();
    anyhow::bail!("no transport is serving; see the log for each one's refusal")
}
