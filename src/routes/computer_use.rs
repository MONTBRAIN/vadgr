use crate::state::AppState;
use axum::Json;
use axum::extract::State;
use serde_json::{Value, json};
use std::time::Duration;

use crate::engine::mcp::ToolServer;

const HANDSHAKE_TIMEOUT: Duration = Duration::from_secs(10);

pub async fn status(State(state): State<AppState>) -> Json<Value> {
    let entry = state.computer_use_setup.entry();
    let available = match entry {
        Ok(entry) if entry.enabled => match entry.command {
            Some(command) => {
                let mut server = crate::engine::mcp::cua::CuaServer::new(command);
                let available = host_available(&mut server, HANDSHAKE_TIMEOUT).await;
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

/// The launch check before the handshake reads the whole installed package and
/// can outlast the bound on a working host, so only the handshake is bounded.
async fn host_available<S: ToolServer + ?Sized>(server: &mut S, handshake: Duration) -> bool {
    if server.prepare().await.is_err() {
        return false;
    }
    let result = tokio::time::timeout(handshake, server.list_tools()).await;
    matches!(result, Ok(Ok(tools)) if !tools.is_empty())
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::engine::types::{McpError, ToolResult, ToolSpec};
    use async_trait::async_trait;
    use serde_json::Map;

    /// An installed host whose launch check outlasts the handshake deadline
    /// while its handshake answers at once.
    struct SlowLaunchCheck {
        check: Duration,
    }

    #[async_trait]
    impl ToolServer for SlowLaunchCheck {
        fn namespace(&self) -> &str {
            "computer-use"
        }

        async fn prepare(&mut self) -> Result<(), McpError> {
            let check = self.check;
            tokio::task::spawn_blocking(move || std::thread::sleep(check))
                .await
                .map_err(|error| McpError::Server(error.to_string()))
        }

        async fn list_tools(&mut self) -> Result<Vec<ToolSpec>, McpError> {
            Ok(vec![ToolSpec {
                name: "get_platform_info".to_owned(),
                description: String::new(),
                input_schema: Map::new(),
            }])
        }

        async fn call_tool(
            &mut self,
            name: &str,
            _args: Map<String, Value>,
        ) -> Result<ToolResult, McpError> {
            Err(McpError::UnknownTool(name.to_owned()))
        }

        async fn close(&mut self) {}
    }

    #[tokio::test]
    async fn a_launch_check_longer_than_the_handshake_bound_is_still_available() {
        let mut server = SlowLaunchCheck {
            check: Duration::from_millis(300),
        };
        assert!(host_available(&mut server, Duration::from_millis(100)).await);
    }
}
