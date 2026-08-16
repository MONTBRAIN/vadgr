use super::{RunContext, schema, string_arg};
use crate::engine::types::{McpError, ToolResult, ToolSpec};
use serde_json::{Map, Value, json};

pub fn report_spec() -> ToolSpec {
    ToolSpec {
        name: "report_progress".to_owned(),
        description: "Surface a progress message to the watching client.".to_owned(),
        input_schema: schema(json!({
            "type":"object", "properties":{"message":{"type":"string"}}, "required":["message"]
        })),
    }
}

pub fn status_spec() -> ToolSpec {
    ToolSpec {
        name: "get_run_status".to_owned(),
        description: "Read the current run state, todos and token counts.".to_owned(),
        input_schema: schema(json!({"type":"object","properties":{"run_id":{"type":"string"}}})),
    }
}

pub async fn report(
    args: Map<String, Value>,
    context: &RunContext,
) -> Result<ToolResult, McpError> {
    let message = string_arg(&args, "message")?;
    context.events.emit(
        "agent_log",
        json!({"run_id":context.run_id,"message":message}),
    );
    Ok(ToolResult::text(r#"{"ok":true}"#))
}

pub async fn status(
    args: Map<String, Value>,
    context: &RunContext,
) -> Result<ToolResult, McpError> {
    let usage = context.usage();
    let todos = context.todos.lock().await.clone();
    Ok(ToolResult::text(
        json!({
            "run_id": args.get("run_id").and_then(Value::as_str).unwrap_or(&context.run_id),
            "state":"running",
            "iteration":context.iteration(),
            "todos":todos,
            "tokens":{"input":usage.input_tokens,"output":usage.output_tokens}
        })
        .to_string(),
    ))
}
