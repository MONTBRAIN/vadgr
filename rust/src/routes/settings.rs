//! The computer-use setting.
//!
//! `PUT` records the owner's intent and reports it back. **It does not install
//! anything**: the Python route calls a setup service that pip-installs cua,
//! and that service is not this release's - `0.4.6` is where the loop gains
//! hands, and wiring an installer into the release that cannot run a loop would
//! be a capability with no consumer.

use crate::state::AppState;
use axum::extract::State;
use axum::Json;
use serde::Deserialize;
use serde_json::{json, Value};

pub async fn get_computer_use(State(state): State<AppState>) -> Json<Value> {
    Json(json!({
        "enabled": state.config.computer_use_enabled,
        "available": state.config.computer_use_enabled,
    }))
}

/// Strict, like the Python body it mirrors: an undeclared field is a 422, not
/// silently dropped.
#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Update {
    pub enabled: bool,
}

pub async fn put_computer_use(
    State(state): State<AppState>,
    Json(body): Json<Update>,
) -> Json<Value> {
    Json(json!({
        "enabled": body.enabled,
        "available": state.config.computer_use_enabled,
    }))
}
