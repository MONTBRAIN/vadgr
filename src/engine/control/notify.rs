use super::{RunContext, schema, string_arg};
use crate::engine::types::{McpError, ToolResult, ToolSpec};
use serde_json::{Map, Value, json};

pub fn spec() -> ToolSpec {
    ToolSpec {
        name: "notify_user".to_owned(),
        description: "Notify the owner through the active run stream.".to_owned(),
        input_schema: schema(json!({
            "type":"object", "properties":{"message":{"type":"string"},"channel":{"type":"string"},"importance":{"type":"string"}}, "required":["message"]
        })),
    }
}

pub async fn notify(
    args: Map<String, Value>,
    context: &RunContext,
) -> Result<ToolResult, McpError> {
    let message = string_arg(&args, "message")?;
    context.events.emit(
        "agent_log",
        json!({"run_id":context.run_id,"message":message}),
    );
    Ok(ToolResult::text(r#"{"ok":true,"delivered":["stream"]}"#))
}
