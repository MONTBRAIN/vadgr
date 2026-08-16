use crate::engine::control::RunContext;
use crate::engine::journal::{Journal, RecoveryState};
use crate::engine::mcp::McpHost;
use crate::engine::provider::ModelClient;
use crate::engine::types::{
    ContentBlock, EngineError, LoopLimits, Message, RunResult, StopReason, ToolContent, ToolResult,
};
use serde_json::{Value, json};
use tokio_util::sync::CancellationToken;

pub const PRUNED_PLACEHOLDER_TEXT: &str = "[screenshot pruned]";

#[allow(clippy::too_many_arguments)]
pub async fn run_loop(
    model: &dyn ModelClient,
    host: &mut McpHost,
    journal: &Journal,
    context: &RunContext,
    task: &str,
    recovery: Option<RecoveryState>,
    cancelled: CancellationToken,
    limits: LoopLimits,
) -> Result<RunResult, EngineError> {
    let mut messages = opening_messages(task, recovery.as_ref());
    let mut usage = recovery
        .as_ref()
        .map(|state| state.prior_usage.clone())
        .unwrap_or_default();
    let mut completed_tool_count = recovery
        .as_ref()
        .map(|state| state.completed_tool_count)
        .unwrap_or(0);

    for iteration in 0..limits.max_iterations {
        if cancelled.is_cancelled() {
            return Err(EngineError::Cancelled);
        }
        prune_old_images(&mut messages, limits.keep_last_images);
        let response = tokio::select! {
            _ = cancelled.cancelled() => return Err(EngineError::Cancelled),
            result = model.complete(&messages, host.tools(), limits.max_tokens) => result?,
        };
        usage += &response.usage;
        journal
            .append_response(iteration, &response)
            .await
            .map_err(EngineError::Journal)?;
        context.set_turn(iteration + 1, &response.usage);

        let final_text = response
            .content
            .iter()
            .filter_map(|block| match block {
                ContentBlock::Text { text } => Some(text.as_str()),
                _ => None,
            })
            .collect::<String>();
        if !final_text.is_empty() {
            context.events.emit(
                "agent_log",
                json!({"run_id":context.run_id,"message":final_text}),
            );
        }
        let calls = response
            .content
            .iter()
            .filter_map(|block| match block {
                ContentBlock::ToolUse { id, name, input } => {
                    Some((id.clone(), name.clone(), input.clone()))
                }
                _ => None,
            })
            .collect::<Vec<_>>();

        match response.stop_reason.as_ref() {
            Some(StopReason::ToolUse) if calls.is_empty() => {
                return Err(EngineError::MalformedToolUse);
            }
            Some(StopReason::ToolUse) => {}
            Some(StopReason::MaxTokens) => return Err(EngineError::MaxTokens),
            Some(StopReason::EndTurn) if completed_tool_count == 0 => {
                return Err(EngineError::NoActionTaken);
            }
            Some(StopReason::EndTurn) => {
                return Ok(RunResult {
                    final_text,
                    iterations: iteration + 1,
                    usage,
                });
            }
            Some(StopReason::Unknown(_)) | None => return Err(EngineError::InvalidTerminal),
        }

        let assistant_content = serde_json::to_value(&response.content)
            .map_err(|error| EngineError::Journal(error.to_string()))?;
        let mut tool_results = Vec::with_capacity(calls.len());
        for (id, name, input) in calls {
            let args = input
                .as_object()
                .cloned()
                .ok_or(EngineError::MalformedToolUse)?;
            let seq = journal
                .append_in_flight(iteration, &name, &input)
                .await
                .map_err(EngineError::Journal)?;
            context.set_current_seq(seq);
            let result = tokio::select! {
                _ = cancelled.cancelled() => return Err(EngineError::Cancelled),
                result = host.dispatch(&name, args) => result,
            };
            let result = match result {
                Ok(result) if result.is_error => {
                    let error = result_text(&result);
                    journal
                        .append_error(seq, &error)
                        .await
                        .map_err(EngineError::Journal)?;
                    result
                }
                Ok(result) => {
                    journal
                        .append_done(seq, &result)
                        .await
                        .map_err(EngineError::Journal)?;
                    result
                }
                Err(error) => {
                    journal
                        .append_error(seq, &error.to_string())
                        .await
                        .map_err(EngineError::Journal)?;
                    ToolResult::error(format!("Error: {error}"))
                }
            };
            completed_tool_count += 1;
            tool_results.push(json!({
                "type":"tool_result",
                "tool_use_id":id,
                "content":result.content,
                "is_error":result.is_error,
            }));
        }
        messages.push(Message {
            role: "assistant".to_owned(),
            content: assistant_content,
        });
        messages.push(Message {
            role: "user".to_owned(),
            content: Value::Array(tool_results),
        });
    }
    Err(EngineError::MaxIterations(limits.max_iterations))
}

fn opening_messages(task: &str, recovery: Option<&RecoveryState>) -> Vec<Message> {
    let mut messages = vec![Message::text("user", task)];
    let Some(recovery) = recovery else {
        return messages;
    };
    let mut lines = vec![
        "This run was interrupted and has been resumed.".to_owned(),
        format!(
            "{} step(s) already completed before the interruption; do not repeat them.",
            recovery.completed_tool_count
        ),
    ];
    if !recovery.recent_results.is_empty() {
        lines.push("The most recent results were:".to_owned());
        lines.extend(
            recovery
                .recent_results
                .iter()
                .map(|result| format!("- {}", result_text(result))),
        );
    }
    if let Some(dangling) = &recovery.dangling {
        lines.push(format!(
            "The `{}` call with arguments {} and idempotency hash {} has an unknown outcome. Do not replay it. Inspect the live state first, then decide whether any new action is needed.",
            dangling.tool, dangling.params, dangling.idem
        ));
    }
    lines.push("Continue from the live state.".to_owned());
    messages.push(Message::text("user", lines.join("\n")));
    messages
}

pub fn prune_old_images(messages: &mut [Message], keep_last: usize) {
    let total = messages
        .iter()
        .map(|message| count_images(&message.content))
        .sum::<usize>();
    let mut replace = total.saturating_sub(keep_last);
    for message in messages {
        replace_images(&mut message.content, &mut replace);
    }
}

fn count_images(value: &Value) -> usize {
    match value {
        Value::Object(object) => {
            usize::from(object.get("type").and_then(Value::as_str) == Some("image"))
                + object.values().map(count_images).sum::<usize>()
        }
        Value::Array(values) => values.iter().map(count_images).sum(),
        _ => 0,
    }
}

fn replace_images(value: &mut Value, replace: &mut usize) {
    match value {
        Value::Object(object)
            if *replace > 0 && object.get("type").and_then(Value::as_str) == Some("image") =>
        {
            *value = json!({"type":"text","text":PRUNED_PLACEHOLDER_TEXT});
            *replace -= 1;
        }
        Value::Object(object) => {
            for value in object.values_mut() {
                replace_images(value, replace);
            }
        }
        Value::Array(values) => {
            for value in values {
                replace_images(value, replace);
            }
        }
        _ => {}
    }
}

fn result_text(result: &ToolResult) -> String {
    result
        .content
        .iter()
        .map(|content| match content {
            ToolContent::Text { text } => text.clone(),
            ToolContent::Image { source } => format!("[image: {} bytes]", source.data.len()),
        })
        .collect::<Vec<_>>()
        .join("\n")
}

#[cfg(test)]
mod tests {
    use super::{prune_old_images, run_loop};
    use crate::db::Db;
    use crate::engine::control::RunContext;
    use crate::engine::events::EventSink;
    use crate::engine::journal::Journal;
    use crate::engine::mcp::{McpHost, ToolServer};
    use crate::engine::provider::ModelClient;
    use crate::engine::types::{
        ContentBlock, EngineError, LoopLimits, McpError, Message, ModelResponse, ProviderError,
        StopReason, ToolResult, ToolSpec, Usage,
    };
    use crate::ws::manager::ConnectionManager;
    use async_trait::async_trait;
    use serde_json::{Map, Value, json};
    use std::collections::VecDeque;
    use std::sync::{Arc, Mutex};
    use tokio_util::sync::CancellationToken;

    struct FakeModel(Mutex<VecDeque<ModelResponse>>);

    #[async_trait]
    impl ModelClient for FakeModel {
        async fn complete(
            &self,
            _messages: &[Message],
            _tools: &[ToolSpec],
            _max_tokens: u32,
        ) -> Result<ModelResponse, ProviderError> {
            self.0
                .lock()
                .unwrap()
                .pop_front()
                .ok_or_else(|| ProviderError::Request("empty fake".to_owned()))
        }
    }

    struct FakeServer(Arc<Mutex<Vec<String>>>);

    #[async_trait]
    impl ToolServer for FakeServer {
        fn namespace(&self) -> &str {
            "test"
        }
        async fn list_tools(&mut self) -> Result<Vec<ToolSpec>, McpError> {
            Ok(vec![ToolSpec {
                name: "act".to_owned(),
                description: String::new(),
                input_schema: Map::new(),
            }])
        }
        async fn call_tool(
            &mut self,
            name: &str,
            _args: Map<String, Value>,
        ) -> Result<ToolResult, McpError> {
            self.0.lock().unwrap().push(name.to_owned());
            Ok(ToolResult::text("done"))
        }
        async fn close(&mut self) {}
    }

    async fn harness(
        responses: Vec<ModelResponse>,
    ) -> (
        FakeModel,
        McpHost,
        Journal,
        RunContext,
        Arc<Mutex<Vec<String>>>,
    ) {
        let calls = Arc::new(Mutex::new(Vec::new()));
        let mut host = McpHost::new(vec![Box::new(FakeServer(calls.clone()))]);
        host.connect().await.unwrap();
        let directory = tempfile::tempdir().unwrap().keep();
        let journal = Journal::open(&directory, "run", -1).await.unwrap();
        let context = RunContext::new(
            "run".to_owned(),
            journal.clone(),
            EventSink::new("run", Arc::new(ConnectionManager::new())),
            Db::open(":memory:").unwrap(),
            CancellationToken::new(),
        );
        (
            FakeModel(Mutex::new(responses.into())),
            host,
            journal,
            context,
            calls,
        )
    }

    fn response(content: Vec<ContentBlock>, stop_reason: StopReason) -> ModelResponse {
        ModelResponse {
            content,
            stop_reason: Some(stop_reason),
            usage: Usage {
                input_tokens: 1,
                output_tokens: 2,
            },
        }
    }

    #[tokio::test]
    async fn tool_calls_are_sequential_and_end_turn_requires_prior_action() {
        let (model, mut host, journal, context, calls) = harness(vec![
            response(
                vec![
                    ContentBlock::ToolUse {
                        id: "1".to_owned(),
                        name: "test__act".to_owned(),
                        input: json!({"n":1}),
                    },
                    ContentBlock::ToolUse {
                        id: "2".to_owned(),
                        name: "test__act".to_owned(),
                        input: json!({"n":2}),
                    },
                ],
                StopReason::ToolUse,
            ),
            response(
                vec![ContentBlock::Text {
                    text: "finished".to_owned(),
                }],
                StopReason::EndTurn,
            ),
        ])
        .await;
        let result = run_loop(
            &model,
            &mut host,
            &journal,
            &context,
            "task",
            None,
            CancellationToken::new(),
            LoopLimits::default(),
        )
        .await
        .unwrap();
        assert_eq!(result.final_text, "finished");
        assert_eq!(*calls.lock().unwrap(), ["act", "act"]);
        assert_eq!(result.usage.input_tokens, 2);
    }

    #[tokio::test]
    async fn first_end_turn_is_no_action() {
        let (model, mut host, journal, context, _) = harness(vec![response(
            vec![ContentBlock::Text {
                text: "narrative".to_owned(),
            }],
            StopReason::EndTurn,
        )])
        .await;
        assert!(matches!(
            run_loop(
                &model,
                &mut host,
                &journal,
                &context,
                "task",
                None,
                CancellationToken::new(),
                LoopLimits::default()
            )
            .await,
            Err(EngineError::NoActionTaken)
        ));
    }

    #[test]
    fn image_pruning_replaces_old_nested_images_in_place() {
        let mut messages = vec![Message {
            role: "user".to_owned(),
            content: json!([
                {"type":"tool_result","content":[{"type":"image","source":{"data":"old"}},{"type":"image","source":{"data":"new"}}]}
            ]),
        }];
        prune_old_images(&mut messages, 1);
        assert_eq!(
            messages[0].content[0]["content"][0]["text"],
            "[screenshot pruned]"
        );
        assert_eq!(messages[0].content[0]["content"][1]["type"], "image");
    }
}
