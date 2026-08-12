use crate::state::AppState;
use axum::Json;
use axum::extract::State;
use serde_json::{Value, json};

pub async fn status(State(state): State<AppState>) -> Json<Value> {
    Json(json!({
        "available": state.config.computer_use_enabled,
        "platform": "wsl2",
    }))
}
