use crate::engine::control::{CONTROL_NAMESPACE, RunContext};
use crate::engine::journal::{Journal, RecoveryState};
use crate::engine::mcp::{McpHost, NAMESPACE_SEPARATOR};
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
    let mut succeeded_tool_count = recovery
        .as_ref()
        .map(|state| state.succeeded_tool_count)
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
                ContentBlock::ToolUse {
                    id, name, input, ..
                } => Some((id.clone(), name.clone(), input.clone())),
                _ => None,
            })
            .collect::<Vec<_>>();

        match response.stop_reason.as_ref() {
            Some(StopReason::ToolUse) if calls.is_empty() => {
                return Err(EngineError::MalformedToolUse);
            }
            Some(StopReason::ToolUse) => {}
            Some(StopReason::MaxTokens) => return Err(EngineError::MaxTokens),
            // A call that was tried and failed is not an action. The count
            // used to rise on every call whatever it returned, so a run whose
            // only tool call came back `unknown tool` ended as a success with
            // the task untouched: the model apologised in text and the CLI
            // exited 0. Nothing was done, so the run did nothing.
            Some(StopReason::EndTurn) if succeeded_tool_count == 0 => {
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
            if !result.is_error && acts_on_the_machine(&name) {
                succeeded_tool_count += 1;
            }
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
    // Replay the completed calls as the tool-use pairs they were, so a resumed
    // conversation has the same shape an uninterrupted one has. Describing them
    // in prose instead made "do not repeat them" an instruction to obey rather
    // than a fact to read, and a model that did not obey it repeated a completed
    // side effect.
    for call in &recovery.recent_calls {
        let id = format!("recovered_{}", call.seq);
        messages.push(Message {
            role: "assistant".to_owned(),
            content: json!([{
                "type": "tool_use",
                "id": id,
                "name": call.tool,
                "input": call.params,
            }]),
        });
        messages.push(Message {
            role: "user".to_owned(),
            content: json!([{
                "type": "tool_result",
                "tool_use_id": id,
                "content": call.result.content,
                "is_error": call.result.is_error,
            }]),
        });
    }

    let mut lines = vec![
        "This run was interrupted and has been resumed.".to_owned(),
        format!(
            "{} step(s) already completed before the interruption; do not repeat them.",
            recovery.succeeded_tool_count
        ),
    ];
    if !recovery.recent_calls.is_empty() {
        lines.push(
            "The calls above already ran and their results are shown; treat them as done."
                .to_owned(),
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

/// The run's own bookkeeping is not work done on the machine. `todo_write`,
/// `report_progress` and `notify_user` all succeed with no tool host at all,
/// so counting them let a run whose acting tools never loaded finish green
/// while the model narrated a file it had not written. Seen for real: the
/// computer-use server failed to start, the model called five control tools,
/// and `vadgr run` printed "Run completed" and exited 0 with nothing done.
fn acts_on_the_machine(tool: &str) -> bool {
    !matches!(
        tool.split_once(NAMESPACE_SEPARATOR),
        Some((CONTROL_NAMESPACE, _))
    )
}

#[cfg(test)]
mod tests {
    use super::{opening_messages, prune_old_images, run_loop};
    use crate::db::Db;
    use crate::engine::control::{CONTROL_NAMESPACE, RunContext};
    use crate::engine::events::EventSink;
    use crate::engine::journal::Journal;
    use crate::engine::journal::{RecoveredCall, RecoveryState};
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

    /// A resumed run must show the model its completed calls, not describe them.
    ///
    /// Recovery used to emit prose only, so not repeating a completed action
    /// depended on the model obeying an instruction. On a native Windows pass a
    /// live model did not obey it and rewrote a file it had already written,
    /// which is what D04 to D06 exist to catch.
    #[test]
    fn a_resumed_run_replays_its_completed_calls_as_tool_use() {
        let recovery = RecoveryState {
            run_id: "run-1".to_owned(),
            last_seq: 1,
            completed_seqs: vec![0],
            recent_results: vec![ToolResult::text("wrote the marker")],
            recent_calls: vec![RecoveredCall {
                seq: 0,
                tool: "computer-use__fs".to_owned(),
                params: json!({"op":"write","path":"marker.txt"}),
                result: ToolResult::text("wrote the marker"),
            }],
            dangling: None,
            pending_ask: None,
            succeeded_tool_count: 1,
            prior_usage: Usage::default(),
            todos: Vec::new(),
        };
        let messages = opening_messages("do the thing", Some(&recovery));

        let assistant = messages
            .iter()
            .find(|message| message.role == "assistant")
            .expect("a resumed conversation must carry the assistant tool call");
        let block = &assistant.content[0];
        assert_eq!(block["type"], "tool_use");
        assert_eq!(block["name"], "computer-use__fs");
        assert_eq!(block["input"]["path"], "marker.txt");

        let result = messages
            .iter()
            .find(|message| {
                message
                    .content
                    .get(0)
                    .map(|item| item["type"] == "tool_result")
                    == Some(true)
            })
            .expect("a resumed conversation must carry the matching tool result");
        assert_eq!(result.content[0]["tool_use_id"], block["id"]);
        assert_eq!(result.content[0]["is_error"], false);
    }

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

    /// Stands in for the real control plane: it always succeeds, because the
    /// run's own bookkeeping does not need a tool host to work.
    struct FakeControl(Arc<Mutex<Vec<String>>>);

    #[async_trait]
    impl ToolServer for FakeControl {
        fn namespace(&self) -> &str {
            CONTROL_NAMESPACE
        }
        async fn list_tools(&mut self) -> Result<Vec<ToolSpec>, McpError> {
            Ok(vec![ToolSpec {
                name: "todo_write".to_owned(),
                description: String::new(),
                input_schema: Map::new(),
            }])
        }
        async fn call_tool(
            &mut self,
            name: &str,
            _args: Map<String, Value>,
        ) -> Result<ToolResult, McpError> {
            self.0.lock().unwrap().push(format!("control:{name}"));
            Ok(ToolResult::text("{\"ok\":true}"))
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
        let mut host = McpHost::new(vec![
            Box::new(FakeServer(calls.clone())),
            Box::new(FakeControl(calls.clone())),
        ]);
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
                        provider_signature: None,
                    },
                    ContentBlock::ToolUse {
                        id: "2".to_owned(),
                        name: "test__act".to_owned(),
                        input: json!({"n":2}),
                        provider_signature: None,
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

    /// The live shape this came from: the computer-use server failed to start,
    /// so the only tools the model had were the run's own bookkeeping. It
    /// ticked a todo off and said the file was written. Nothing was.
    #[tokio::test]
    async fn bookkeeping_alone_is_not_action() {
        let (model, mut host, journal, context, _) = harness(vec![
            response(
                vec![ContentBlock::ToolUse {
                    id: "1".to_owned(),
                    name: "control__todo_write".to_owned(),
                    input: json!({"todos":[]}),
                    provider_signature: None,
                }],
                StopReason::ToolUse,
            ),
            response(
                vec![ContentBlock::Text {
                    text: "The word ready has been written to the file.".to_owned(),
                }],
                StopReason::EndTurn,
            ),
        ])
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

    /// The live shape this came from: the model called a tool the host does not
    /// have, the call came back an error, and the model then explained itself
    /// in text. The run used to end as a success with the task untouched.
    #[tokio::test]
    async fn a_run_whose_only_call_failed_took_no_action() {
        let (model, mut host, journal, context, _) = harness(vec![
            response(
                vec![ContentBlock::ToolUse {
                    id: "1".to_owned(),
                    // The live one was `computer_usefs`: the model dropped the
                    // separator out of `computer-use__fs`, so nothing resolved.
                    name: "testact".to_owned(),
                    input: json!({}),
                    provider_signature: None,
                }],
                StopReason::ToolUse,
            ),
            response(
                vec![ContentBlock::Text {
                    text: "I could not do that.".to_owned(),
                }],
                StopReason::EndTurn,
            ),
        ])
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
