use super::{RunContext, schema, string_arg};
use crate::engine::types::{McpError, ToolResult, ToolSpec};
use serde_json::{Map, Value, json};

pub fn write_spec() -> ToolSpec {
    ToolSpec {
        name: "todo_write".to_owned(),
        description: "Replace the agent's todo list.".to_owned(),
        input_schema: schema(json!({
            "type":"object",
            "properties":{"items":{"type":"array"}},
            "required":["items"]
        })),
    }
}

pub fn update_spec() -> ToolSpec {
    ToolSpec {
        name: "todo_update".to_owned(),
        description: "Update one todo's status.".to_owned(),
        input_schema: schema(json!({
            "type":"object",
            "properties":{"id":{"type":"string"},"status":{"type":"string"}},
            "required":["id","status"]
        })),
    }
}

pub async fn write(args: Map<String, Value>, context: &RunContext) -> Result<ToolResult, McpError> {
    let raw = args.get("items").cloned().unwrap_or_else(|| json!([]));
    let raw = match raw {
        Value::String(text) => serde_json::from_str::<Value>(&text)
            .map_err(|_| McpError::Server("items string must contain JSON".to_owned()))?,
        other => other,
    };
    let raw_items = match raw {
        Value::Array(items) => items,
        Value::Object(object) => vec![Value::Object(object)],
        _ => return Err(McpError::Server("items must be an array".to_owned())),
    };
    let mut items = Vec::with_capacity(raw_items.len());
    for (index, item) in raw_items.into_iter().enumerate() {
        let object = match item {
            Value::String(content) => json!({"content":content}),
            Value::Object(object) => Value::Object(object),
            _ => {
                return Err(McpError::Server(format!(
                    "todo item {} must be an object",
                    index + 1
                )));
            }
        };
        let content = object
            .get("content")
            .or_else(|| object.get("title"))
            .or_else(|| object.get("text"))
            .and_then(Value::as_str)
            .unwrap_or("");
        let status = canonical_status(
            object
                .get("status")
                .and_then(Value::as_str)
                .unwrap_or("pending"),
        )?;
        items.push(json!({
            "id": object.get("id").and_then(Value::as_str).map(str::to_owned).unwrap_or_else(|| (index + 1).to_string()),
            "content": content,
            "status": status,
        }));
    }
    *context.todos.lock().await = items.clone();
    context.events.emit("todos", json!({"items": items}));
    Ok(ToolResult::text(
        json!({"ok":true,"todos":items}).to_string(),
    ))
}

pub async fn update(
    args: Map<String, Value>,
    context: &RunContext,
) -> Result<ToolResult, McpError> {
    let id = string_arg(&args, "id")?;
    let status = canonical_status(&string_arg(&args, "status")?)?;
    let mut todos = context.todos.lock().await;
    let Some(todo) = todos
        .iter_mut()
        .find(|todo| todo.get("id").and_then(Value::as_str) == Some(&id))
    else {
        return Err(McpError::Server(format!("unknown todo id: {id}")));
    };
    todo["status"] = Value::String(status.to_owned());
    let updated = todo.clone();
    context.events.emit("todos", json!({"items":*todos}));
    Ok(ToolResult::text(
        json!({"ok":true,"todo":updated}).to_string(),
    ))
}

fn canonical_status(status: &str) -> Result<&'static str, McpError> {
    match status.trim().to_lowercase().replace(' ', "_").as_str() {
        "pending" | "todo" | "not_started" => Ok("pending"),
        "in_progress" | "in-progress" | "inprogress" | "active" | "running" => Ok("in_progress"),
        "done" | "complete" | "completed" | "finished" | "success" => Ok("done"),
        "cancelled" | "canceled" | "cancel" | "skipped" => Ok("cancelled"),
        other => Err(McpError::Server(format!("invalid todo status: {other}"))),
    }
}
