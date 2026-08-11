use crate::config::VERSION;
use crate::state::AppState;
use axum::extract::State;
use axum::Json;
use serde_json::{json, Value};

/// Unauthenticated: it is the phone's post-pair connectivity probe, so it has
/// to answer before a token exists.
pub async fn health(State(state): State<AppState>) -> Json<Value> {
    Json(json!({
        "status": "healthy",
        "modules": { "computer_use": state.config.computer_use_enabled },
        "platform": "wsl2",
        "version": VERSION,
        "transport": state.transport.status(),
    }))
}
