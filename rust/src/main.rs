//! `vadgr 0.4.5` - the daemon minus the engine.
//!
//! The first Rust release, and the one that carries no new behaviour. It runs
//! **beside** the Python daemon on its own port and its own database for four
//! releases; that is what "strangler" means, and it is what keeps every step
//! reversible.
//!
//! **This daemon cannot start a run.** `POST /api/runs` and
//! `POST /api/runs/{id}/resume` need a loop behind them and the loop is
//! `0.4.6`'s, so they are absent rather than stubbed and the runbook cells that
//! trigger a run are held.

// The modules live in the library (`lib.rs`) and the binary uses them from
// there rather than declaring them a second time. Declaring both compiles every
// module twice and makes anything the binary happens not to call look dead.
use vadgr_daemon::{auth, config, db, routes, transport, ws};

use anyhow::Result;
use vadgr_daemon::state::AppState;
use std::net::SocketAddr;
use std::sync::Arc;

#[tokio::main]
async fn main() -> Result<()> {
    tracing_subscriber::fmt()
        .with_env_filter(
            tracing_subscriber::EnvFilter::try_from_default_env()
                .unwrap_or_else(|_| "info".into()),
        )
        .init();

    let config = config::Config::from_env();
    let db = db::Db::open(&config.db_path)?;
    let transport = transport::create(&config.transport_name)?;

    // **The F2 fix, reproduced.** The daemon binds what the transport
    // advertises, so the address a QR carries is one the daemon answers on.
    // A transport that cannot name one stops the boot here, out loud: a
    // daemon that silently bound loopback instead would advertise nothing
    // and answer nowhere the QR points.
    let bind_host = transport.bind_host()?;
    let port = config.port;

    let state = AppState {
        db,
        config: Arc::new(config),
        transport: Arc::from(transport),
        pairing: Arc::new(auth::pairing::PairingStore::new(
            auth::pairing::PAIRING_TTL_SECONDS,
        )),
        ws: Arc::new(ws::manager::ConnectionManager::new()),
    };

    let app = routes::router(state.clone()).layer(axum::middleware::from_fn_with_state(
        state,
        auth::gate::gate,
    ));

    let addr: SocketAddr = format!("{bind_host}:{port}").parse()?;
    tracing::info!(%addr, "vadgr daemon (rust) listening");
    let listener = tokio::net::TcpListener::bind(addr).await?;
    axum::serve(
        listener,
        app.into_make_service_with_connect_info::<SocketAddr>(),
    )
    .await?;
    Ok(())
}
