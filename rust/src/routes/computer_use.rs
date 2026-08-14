use crate::state::AppState;
use axum::Json;
use axum::extract::State;
use serde_json::{Value, json};

pub async fn status(State(_state): State<AppState>) -> Json<Value> {
    Json(json!({
        // The engine does not arrive until 0.4.6. An enabled setting is not an
        // available tool host, so this release must report false honestly.
        "available": false,
        "platform": crate::platform::computer_use_platform(),
    }))
}
