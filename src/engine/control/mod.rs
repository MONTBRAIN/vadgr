mod hitl;
mod notify;
mod progress;
mod todo;

use crate::db::Db;
use crate::engine::channel::PendingChannel;
use crate::engine::events::EventSink;
use crate::engine::journal::Journal;
use crate::engine::mcp::ToolServer;
use crate::engine::policy::PolicyHook;
use crate::engine::types::{McpError, ToolResult, ToolSpec, Usage};
use async_trait::async_trait;
use serde_json::{Map, Value, json};
use std::sync::Arc;
use std::sync::atomic::{AtomicI64, AtomicU64, Ordering};
use tokio::sync::Mutex;
use tokio_util::sync::CancellationToken;

pub const TOOL_NAMES: [&str; 8] = [
    "todo_write",
    "todo_update",
    "report_progress",
    "get_run_status",
    "request_approval",
    "ask_user",
    "propose_plan",
    "notify_user",
];

#[derive(Clone)]
pub struct RunContext {
    pub run_id: String,
    pub journal: Journal,
    pub events: EventSink,
    pub db: Db,
    pub cancelled: CancellationToken,
    pub todos: Arc<Mutex<Vec<Value>>>,
    iteration: Arc<AtomicU64>,
    input_tokens: Arc<AtomicU64>,
    output_tokens: Arc<AtomicU64>,
    current_seq: Arc<AtomicI64>,
}

impl RunContext {
    pub fn new(
        run_id: String,
        journal: Journal,
        events: EventSink,
        db: Db,
        cancelled: CancellationToken,
    ) -> Self {
        Self {
            run_id,
            journal,
            events,
            db,
            cancelled,
            todos: Arc::new(Mutex::new(Vec::new())),
            iteration: Arc::new(AtomicU64::new(0)),
            input_tokens: Arc::new(AtomicU64::new(0)),
            output_tokens: Arc::new(AtomicU64::new(0)),
            current_seq: Arc::new(AtomicI64::new(-1)),
        }
    }

    pub fn set_turn(&self, iteration: u32, usage: &Usage) {
        self.iteration.store(iteration as u64, Ordering::SeqCst);
        self.input_tokens
            .fetch_add(usage.input_tokens, Ordering::SeqCst);
        self.output_tokens
            .fetch_add(usage.output_tokens, Ordering::SeqCst);
    }

    pub fn set_current_seq(&self, seq: i64) {
        self.current_seq.store(seq, Ordering::SeqCst);
    }

    pub fn current_seq(&self) -> i64 {
        self.current_seq.load(Ordering::SeqCst)
    }

    pub fn iteration(&self) -> u64 {
        self.iteration.load(Ordering::SeqCst)
    }

    pub fn usage(&self) -> Usage {
        Usage {
            input_tokens: self.input_tokens.load(Ordering::SeqCst),
            output_tokens: self.output_tokens.load(Ordering::SeqCst),
        }
    }

    pub async fn restore_todos(&self, todos: &[Value]) {
        *self.todos.lock().await = todos.to_vec();
        if !todos.is_empty() {
            self.events.emit("todos", json!({"items":todos}));
        }
    }

    pub async fn park(&self, request: Value) -> Result<(), McpError> {
        let seq = self.current_seq();
        if seq < 0 {
            return Err(McpError::Server(
                "human gate has no open tool call".to_owned(),
            ));
        }
        self.journal
            .append_await_user(seq, &request)
            .await
            .map_err(McpError::Server)?;
        crate::db::runs::update_status(&self.db, &self.run_id, "awaiting_approval")
            .map_err(|error| McpError::Server(error.to_string()))?;
        self.events.emit("awaiting", request);
        PendingChannel::new(self.cancelled.clone())
            .park()
            .await
            .map_err(McpError::Server)
    }
}

pub struct ControlPlaneServer {
    context: RunContext,
    policy: Arc<dyn PolicyHook>,
}

/// The control plane's namespace. Named here because the engine loop has to
/// tell the run's own bookkeeping apart from work done on the machine.
pub const CONTROL_NAMESPACE: &str = "control";

impl ControlPlaneServer {
    pub fn new(context: RunContext, policy: Arc<dyn PolicyHook>) -> Self {
        Self { context, policy }
    }
}

#[async_trait]
impl ToolServer for ControlPlaneServer {
    fn namespace(&self) -> &str {
        CONTROL_NAMESPACE
    }

    async fn list_tools(&mut self) -> Result<Vec<ToolSpec>, McpError> {
        Ok(vec![
            todo::write_spec(),
            todo::update_spec(),
            progress::report_spec(),
            progress::status_spec(),
            hitl::approval_spec(),
            hitl::ask_spec(),
            hitl::plan_spec(),
            notify::spec(),
        ])
    }

    async fn call_tool(
        &mut self,
        name: &str,
        args: Map<String, Value>,
    ) -> Result<ToolResult, McpError> {
        match name {
            "todo_write" => todo::write(args, &self.context).await,
            "todo_update" => todo::update(args, &self.context).await,
            "report_progress" => progress::report(args, &self.context).await,
            "get_run_status" => progress::status(args, &self.context).await,
            "request_approval" => hitl::approval(args, &self.context, self.policy.as_ref()).await,
            "ask_user" => hitl::ask(args, &self.context).await,
            "propose_plan" => hitl::plan(args, &self.context).await,
            "notify_user" => notify::notify(args, &self.context).await,
            _ => Err(McpError::UnknownTool(format!("control__{name}"))),
        }
    }

    async fn close(&mut self) {}
}

pub(super) fn schema(value: Value) -> Map<String, Value> {
    value
        .as_object()
        .cloned()
        .expect("tool schema is an object")
}

pub(super) fn string_arg(args: &Map<String, Value>, key: &str) -> Result<String, McpError> {
    args.get(key)
        .and_then(Value::as_str)
        .map(str::to_owned)
        .ok_or_else(|| McpError::Server(format!("`{key}` must be a string")))
}

#[cfg(test)]
mod tests {
    use super::{ControlPlaneServer, RunContext, TOOL_NAMES};
    use crate::db::Db;
    use crate::engine::events::EventSink;
    use crate::engine::journal::Journal;
    use crate::engine::mcp::ToolServer;
    use crate::engine::policy::DefaultPolicy;
    use crate::ws::manager::ConnectionManager;
    use serde_json::{Map, json};
    use std::sync::Arc;
    use tokio_util::sync::CancellationToken;

    async fn server() -> ControlPlaneServer {
        let directory = tempfile::tempdir().unwrap().keep();
        let journal = Journal::open(&directory, "run", -1).await.unwrap();
        ControlPlaneServer::new(
            RunContext::new(
                "run".to_owned(),
                journal,
                EventSink::new("run", Arc::new(ConnectionManager::new())),
                Db::open(":memory:").unwrap(),
                CancellationToken::new(),
            ),
            Arc::new(DefaultPolicy::default()),
        )
    }

    #[tokio::test]
    async fn publishes_exactly_eight_tools_in_stable_order() {
        let mut server = server().await;
        let names = server
            .list_tools()
            .await
            .unwrap()
            .into_iter()
            .map(|tool| tool.name)
            .collect::<Vec<_>>();
        assert_eq!(names, TOOL_NAMES);
    }

    #[tokio::test]
    async fn accepts_json_string_todos_and_status_aliases() {
        let mut server = server().await;
        let mut args = Map::new();
        args.insert(
            "items".to_owned(),
            json!(r#"[{"id":"1","content":"work","status":"completed"}]"#),
        );
        let result = server.call_tool("todo_write", args).await.unwrap();
        let value = serde_json::to_value(result).unwrap();
        assert!(value.to_string().contains("done"));
    }

    #[tokio::test]
    async fn restored_todos_can_be_updated_after_restart() {
        let mut server = server().await;
        server
            .context
            .restore_todos(&[json!({
                "id":"inspect",
                "content":"Inspect live state",
                "status":"in_progress"
            })])
            .await;
        let mut args = Map::new();
        args.insert("id".to_owned(), json!("inspect"));
        args.insert("status".to_owned(), json!("done"));

        let result = server.call_tool("todo_update", args).await.unwrap();

        assert!(
            serde_json::to_value(result)
                .unwrap()
                .to_string()
                .contains("done")
        );
    }
}
