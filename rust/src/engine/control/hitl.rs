use super::{RunContext, schema, string_arg};
use crate::engine::policy::{ApprovalRequest, Decision, PolicyHook};
use crate::engine::types::{McpError, ToolResult, ToolSpec};
use serde_json::{Map, Value, json};

pub fn approval_spec() -> ToolSpec {
    ToolSpec {
        name: "request_approval".to_owned(),
        description: "Ask the owner to approve a gated action.".to_owned(),
        input_schema: schema(json!({
            "type":"object",
            "properties":{
                "action":{"type":"string","description":"The action you want approved."},
                // Named severities, not prose. A free string invited a sentence
                // describing the risk, which no policy can rank.
                "risk":{"type":"string","enum":["low","medium","high"],
                        "description":"Severity of the action. Use high for anything that deletes, overwrites, sends or spends. Anything not recognised is treated as needing the owner."},
                "preview":{"type":"string","description":"Exactly what will run or change."},
                "timeout":{"type":"number"}},
            "required":["action","risk","preview"]
        })),
    }
}

pub fn ask_spec() -> ToolSpec {
    ToolSpec {
        name: "ask_user".to_owned(),
        description: "Ask the owner a question and wait for an answer.".to_owned(),
        input_schema: schema(json!({
            "type":"object", "properties":{"question":{"type":"string"},"options":{"type":"array"},"timeout":{"type":"number"}}, "required":["question"]
        })),
    }
}

pub fn plan_spec() -> ToolSpec {
    ToolSpec {
        name: "propose_plan".to_owned(),
        description: "Propose a plan for owner review.".to_owned(),
        input_schema: schema(json!({
            "type":"object", "properties":{"plan":{"type":"string"}}, "required":["plan"]
        })),
    }
}

pub async fn approval(
    args: Map<String, Value>,
    context: &RunContext,
    policy: &dyn PolicyHook,
) -> Result<ToolResult, McpError> {
    let action = string_arg(&args, "action")?;
    let risk = args.get("risk").and_then(Value::as_str).unwrap_or("medium");
    match policy
        .check(ApprovalRequest {
            action: &action,
            risk,
        })
        .await
    {
        Decision::AutoAllow { reason: _ } => {
            Ok(ToolResult::text(r#"{"decision":"approve","note":null}"#))
        }
        Decision::AutoDeny { reason } => Ok(ToolResult::text(
            json!({"decision":"reject","note":reason}).to_string(),
        )),
        Decision::NeedsHuman { reason } => {
            let timeout = seconds(args.get("timeout"));
            context
                .park(json!({"kind":"approval","action":action,"risk":risk,"prompt":action,"reason":reason,"timeout":timeout}))
                .await?;
            unreachable!("pending channel has no reply surface in this release")
        }
    }
}

pub async fn ask(args: Map<String, Value>, context: &RunContext) -> Result<ToolResult, McpError> {
    let question = string_arg(&args, "question")?;
    context
        .park(json!({
            "kind":"question", "question":question, "prompt":question,
            "options":args.get("options"), "timeout":seconds(args.get("timeout"))
        }))
        .await?;
    unreachable!("pending channel has no reply surface in this release")
}

pub async fn plan(args: Map<String, Value>, context: &RunContext) -> Result<ToolResult, McpError> {
    let plan = string_arg(&args, "plan")?;
    context.park(json!({"kind":"plan","prompt":plan})).await?;
    unreachable!("pending channel has no reply surface in this release")
}

fn seconds(value: Option<&Value>) -> Option<f64> {
    let value = value?;
    let number = value
        .as_f64()
        .or_else(|| value.as_str().and_then(|text| text.parse::<f64>().ok()))?;
    (number > 0.0).then_some(number)
}

#[cfg(test)]
mod tests {
    use super::seconds;
    use serde_json::json;

    #[test]
    fn timeout_accepts_number_or_numeric_string() {
        assert_eq!(seconds(Some(&json!(300))), Some(300.0));
        assert_eq!(seconds(Some(&json!("300"))), Some(300.0));
        assert_eq!(seconds(Some(&json!("bad"))), None);
    }
}
