use crate::state::AppState;
use axum::Json;
use axum::extract::State;
use serde_json::{Value, json};
use std::time::Duration;

use crate::engine::mcp::ToolServer;

pub async fn status(State(state): State<AppState>) -> Json<Value> {
    let entry = state.computer_use_setup.entry();
    let available = match entry {
        Ok(entry) if entry.enabled => match entry.command {
            Some(command) => {
                let mut server = crate::engine::mcp::cua::CuaServer::new(command);
                let result =
                    tokio::time::timeout(Duration::from_secs(10), server.list_tools()).await;
                let available = matches!(result, Ok(Ok(tools)) if !tools.is_empty());
                server.close().await;
                available
            }
            None => false,
        },
        _ => false,
    };
    Json(json!({
        "available": available,
        "platform": crate::platform::computer_use_platform(),
    }))
}
