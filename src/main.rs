//! `vadgr 0.4.7` - the Rust daemon with provider onboarding.
//!
//! **The daemon, and now the only one.** It was built beside the daemon it
//! replaced, on its own port and its own database, for five releases; that is
//! what kept every step reversible. `0.4.9` retired the other one.
//!
// The modules live in the library (`lib.rs`) and the binary uses them from
// there rather than declaring them a second time. Declaring both compiles every
// module twice and makes anything the binary happens not to call look dead.
use vadgr_daemon::engine::Engine;
use vadgr_daemon::engine::mcp::DefaultHostFactory;
use vadgr_daemon::engine::provider::NativeModelFactory;
use vadgr_daemon::engine::supervisor::RunSupervisor;
use vadgr_daemon::{auth, computer_use_setup, config, db, migrate, routes, transport, ws};

use anyhow::Result;
use std::sync::Arc;
use std::sync::RwLock;
use tower_http::trace::{DefaultMakeSpan, DefaultOnResponse, TraceLayer};
use tracing::Level;
use vadgr_daemon::state::AppState;

#[tokio::main]
async fn main() -> Result<()> {
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
    let transport = transport::create(&config.transport_name)?;
    let providers = vadgr_daemon::engine::provider::ProviderService::native(
        db.clone(),
        config.state_home.clone(),
    )?;
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

    let bind_hosts = transport::bind_hosts(transport.as_ref());
    let port = config.port;

    let state = AppState {
        db,
        config: Arc::new(config),
        transport: Arc::from(transport),
        pairing: Arc::new(auth::pairing::PairingStore::new(
            auth::pairing::PAIRING_TTL_SECONDS,
        )),
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
        loop {
            match tokio::net::TcpListener::bind(("127.0.0.1", 1455)).await {
                Ok(listener) => {
                    callback_state.providers.set_oauth_callback_available(true);
                    tracing::info!(addr = "127.0.0.1:1455", "OpenAI callback listening");
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
                Err(error) => {
                    tracing::debug!(%error, "OpenAI callback port is unavailable");
                }
            }
            callback_state.providers.set_oauth_callback_available(false);
            tokio::time::sleep(std::time::Duration::from_secs(1)).await;
        }
    });

    let mut listeners = Vec::new();
    for host in bind_hosts {
        let addr = transport::listener_address(&host, port)?;
        listeners.push((addr, tokio::net::TcpListener::bind(addr).await?));
        tracing::info!(%addr, "vadgr daemon (rust) listening");
    }
    futures_util::future::try_join_all(listeners.into_iter().map(|(_, listener)| {
        let app = app.clone();
        async move {
            axum::serve(
                listener,
                app.into_make_service_with_connect_info::<std::net::SocketAddr>(),
            )
            .await
        }
    }))
    .await?;
    callback.abort();
    Ok(())
}
