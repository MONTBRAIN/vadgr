//! The routes this release serves, and the two it deliberately does not.

pub mod auth;
pub mod computer_use;
pub mod devices;
pub mod health;
pub mod providers;
pub mod runs;
pub mod settings;

use crate::state::AppState;
use axum::Json;
use axum::Router;
use axum::extract::rejection::JsonRejection;
use axum::http::StatusCode;
use axum::routing::{delete, get, post, put};
use serde_json::{Value, json};

fn validation_error(rejection: JsonRejection) -> (StatusCode, Json<Value>) {
    (
        StatusCode::UNPROCESSABLE_ENTITY,
        Json(json!({
            "detail": [{
                "type": "value_error",
                "msg": rejection.body_text(),
            }]
        })),
    )
}

/// **Twelve HTTP routes and two socket paths.**
///
/// Two of the Python daemon's fourteen HTTP routes are held for `0.4.6`, and
/// they are held rather than stubbed. Both socket paths exist, but their
/// existing-run behavior is also held because this daemon cannot create the
/// run that the comparison needs. A `501`, a plausible `202` with no run
/// behind it, or a row nothing will ever pick up would lie to the sweep.
///
/// - `POST /api/runs` starts a run and needs the loop.
/// - `POST /api/runs/{id}/resume` hands the run to the execution service and
///   answers `{"status": "running"}`. Its **validation** paths port cleanly and
///   its **success** path cannot: without an engine this daemon has no way to
///   make the response true. Porting half of it would give the
///   sweep matching error rows and a lying success row, which is worse than an
///   absent route.
pub fn router(state: AppState) -> Router {
    Router::new()
        .route("/api/health", get(health::health))
        .route("/api/auth/pair", post(auth::pair))
        .route("/api/auth/claim", post(auth::claim))
        .route("/api/devices", get(devices::list_devices))
        .route("/api/devices/{device_id}", delete(devices::revoke_device))
        .route("/api/providers", get(providers::list_providers))
        .route(
            "/api/settings/computer-use",
            get(settings::get_computer_use),
        )
        .route(
            "/api/settings/computer-use",
            put(settings::put_computer_use),
        )
        .route("/api/computer-use/status", get(computer_use::status))
        .route("/api/runs", get(runs::list_runs))
        .route("/api/runs/{run_id}", get(runs::get_run))
        .route("/api/runs/{run_id}/cancel", post(runs::cancel_run))
        .route(
            "/api/runs/{run_id}/stream",
            get(crate::ws::run_ws::run_stream),
        )
        .route(
            "/api/ws/runs/{run_id}",
            get(crate::ws::run_ws::run_websocket),
        )
        .with_state(state)
}
