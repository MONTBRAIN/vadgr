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

/// The complete transitional HTTP and socket surface, now with the Rust engine
/// behind run creation and continuation.
pub fn router(state: AppState) -> Router {
    Router::new()
        .route("/api/health", get(health::health))
        .route("/api/auth/pair", post(auth::pair))
        .route("/api/auth/claim", post(auth::claim))
        .route("/api/devices", get(devices::list_devices))
        .route(
            "/api/devices/self/transports",
            post(devices::adopt_transport),
        )
        .route("/api/devices/{device_id}", delete(devices::revoke_device))
        .route("/api/providers", get(providers::list_providers))
        .route(
            "/api/providers/{provider_id}/auth-attempts",
            post(providers::start_attempt),
        )
        .route(
            "/api/provider-auth/{attempt_id}",
            get(providers::get_attempt),
        )
        .route(
            "/api/providers/{provider_id}/connection",
            put(providers::commit_connection).delete(providers::delete_connection),
        )
        .route(
            "/api/providers/{provider_id}/catalog-refresh",
            post(providers::refresh_catalog),
        )
        .route("/api/default-model", put(providers::put_default_model))
        .route(
            "/api/settings/computer-use",
            get(settings::get_computer_use),
        )
        .route(
            "/api/settings/computer-use",
            put(settings::put_computer_use),
        )
        .route("/api/computer-use/status", get(computer_use::status))
        .route("/api/runs", get(runs::list_runs).post(runs::start_run))
        .route("/api/runs/{run_id}", get(runs::get_run))
        .route("/api/runs/{run_id}/cancel", post(runs::cancel_run))
        .route("/api/runs/{run_id}/resume", post(runs::resume_run))
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
