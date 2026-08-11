use crate::state::AppState;
use axum::extract::State;
use axum::Json;
use serde_json::{json, Value};

pub async fn status(State(state): State<AppState>) -> Json<Value> {
    Json(json!({
        "available": state.config.computer_use_enabled,
        "platform": "wsl2",
    }))
}
