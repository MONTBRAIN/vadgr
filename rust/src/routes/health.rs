use crate::config::VERSION;
use crate::state::AppState;
use axum::Json;
use axum::extract::State;
use serde_json::{Value, json};

/// Unauthenticated: it is the phone's post-pair connectivity probe, so it has
/// to answer before a token exists.
pub async fn health(State(state): State<AppState>) -> Json<Value> {
    let computer_use_installed = state.computer_use_status.read().unwrap()["venv_ready"]
        .as_bool()
        .unwrap_or(false);
    Json(json!({
        "status": "healthy",
        "modules": { "computer_use": computer_use_installed },
        "platform": crate::platform::machine_platform(),
        "version": VERSION,
        "transport": state.transport.status(),
    }))
}
