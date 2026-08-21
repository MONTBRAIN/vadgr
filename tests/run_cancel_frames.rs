//! A cancelled run says so on the socket.
//!
//! Completion and failure each broadcast a terminal frame. Cancellation used to
//! broadcast nothing at all, so the run row read `cancelled` while a client
//! watching the stream sat on `agent_started` for ever. That is invisible to
//! every test that only reads the row, which is why this one reads the wire.

use async_trait::async_trait;
use serde_json::{Map, Value, json};
use std::sync::Arc;
use std::time::Duration;
use vadgr_daemon::db::providers::{Connection, ConnectionCommit, ProviderModel};
use vadgr_daemon::db::{self, Db};
use vadgr_daemon::engine::control::RunContext;
use vadgr_daemon::engine::mcp::{HostFactory, McpHost, ToolServer};
use vadgr_daemon::engine::provider::{ModelClient, ModelFactory};
use vadgr_daemon::engine::supervisor::{RunSupervisor, StartRun};
use vadgr_daemon::engine::{
    Engine, McpError, Message, ModelResponse, ProviderError, ToolResult, ToolSpec,
};
use vadgr_daemon::ws::manager::ConnectionManager;

fn seed_fake_model(db: &Db) {
    db::providers::commit_connection(
        db,
        &ConnectionCommit {
            connection: Connection {
                provider_id: "fake".to_owned(),
                auth_method: "api_key".to_owned(),
                secret_ref: "fake-reference".to_owned(),
                account_id: None,
                credential_expires_at: None,
            },
            models: vec![ProviderModel {
                id: "fake-model".to_owned(),
                name: "Fake model".to_owned(),
                capabilities: json!({"text":true,"tools":true}),
            }],
            default_model: Some("fake-model".to_owned()),
        },
    )
    .unwrap();
}

/// Never answers within the test's lifetime, so the run stays cancellable.
struct BlockingModel;

#[async_trait]
impl ModelClient for BlockingModel {
    async fn complete(
        &self,
        _messages: &[Message],
        _tools: &[ToolSpec],
        _max_tokens: u32,
    ) -> Result<ModelResponse, ProviderError> {
        tokio::time::sleep(Duration::from_secs(600)).await;
        unreachable!("the run is cancelled long before this resolves")
    }
}

struct BlockingModelFactory;

#[async_trait]
impl ModelFactory for BlockingModelFactory {
    async fn build(
        &self,
        _provider: &str,
        _model: &str,
    ) -> Result<Box<dyn ModelClient>, ProviderError> {
        Ok(Box::new(BlockingModel))
    }
}

struct NoTools;

#[async_trait]
impl ToolServer for NoTools {
    fn namespace(&self) -> &str {
        "none"
    }

    async fn list_tools(&mut self) -> Result<Vec<ToolSpec>, McpError> {
        Ok(Vec::new())
    }

    async fn call_tool(
        &mut self,
        _name: &str,
        _args: Map<String, Value>,
    ) -> Result<ToolResult, McpError> {
        Err(McpError::Server("no tools in this test".to_owned()))
    }

    async fn close(&mut self) {}
}

struct NoToolsFactory;

#[async_trait]
impl HostFactory for NoToolsFactory {
    async fn build(&self, _context: RunContext) -> Result<McpHost, McpError> {
        Ok(McpHost::new(vec![Box::new(NoTools)]))
    }
}

#[tokio::test]
async fn a_cancelled_run_broadcasts_its_terminal_frame() {
    let directory = tempfile::tempdir().unwrap();
    let db = Db::open(directory.path().join("vadgr.db")).unwrap();
    seed_fake_model(&db);

    let manager = Arc::new(ConnectionManager::new());
    let engine = Arc::new(Engine::new(
        Arc::new(BlockingModelFactory),
        Arc::new(NoToolsFactory),
        db.clone(),
        directory.path().to_owned(),
    ));
    let supervisor = RunSupervisor::new(engine, db.clone(), manager.clone());

    let row = supervisor
        .create(StartRun {
            task: "block until cancelled".to_owned(),
            provider: None,
            model: None,
        })
        .await
        .expect("run accepted");
    let id = row["id"].as_str().unwrap().to_owned();

    // Wait until the run is really running, so the cancel lands on an active
    // run rather than racing its own acceptance.
    for _ in 0..200 {
        if db::runs::get(&db, &id).unwrap().unwrap()["status"] == "running" {
            break;
        }
        tokio::time::sleep(Duration::from_millis(25)).await;
    }

    supervisor.cancel(&id).await.expect("cancel accepted");

    // The row is the easy half and it was never the broken one.
    let mut settled = false;
    for _ in 0..200 {
        if db::runs::get(&db, &id).unwrap().unwrap()["status"] == "cancelled" {
            settled = true;
            break;
        }
        tokio::time::sleep(Duration::from_millis(25)).await;
    }
    assert!(settled, "the run row must reach cancelled");

    // The wire is the half that was silent. `connect` hands back the replay
    // buffer, which is every frame a client would have been sent.
    let mut frames = Vec::new();
    for _ in 0..200 {
        let (_rx, replay) = manager.connect(&id);
        frames = replay;
        if frames.iter().any(|frame| frame["type"] == "run_cancelled") {
            break;
        }
        tokio::time::sleep(Duration::from_millis(25)).await;
    }

    let types: Vec<&str> = frames
        .iter()
        .filter_map(|frame| frame["type"].as_str())
        .collect();
    assert!(
        types.contains(&"run_cancelled"),
        "a cancelled run must broadcast a terminal frame; the stream carried {types:?}"
    );
    assert!(
        types.contains(&"agent_cancelled"),
        "the agent-level terminal is broadcast too, like the completed and failed paths; got {types:?}"
    );
    assert!(
        !types.contains(&"run_failed"),
        "a cancel is a decision and must not be reported as a failure; got {types:?}"
    );
}
