use async_trait::async_trait;
use serde_json::{Map, Value, json};
use std::collections::VecDeque;
use std::sync::atomic::{AtomicUsize, Ordering};
use std::sync::{Arc, Mutex};
use std::time::Duration;
use vadgr_daemon::db::providers::{Connection, ConnectionCommit, ProviderModel};
use vadgr_daemon::db::{self, Db};
use vadgr_daemon::engine::control::RunContext;
use vadgr_daemon::engine::journal::Journal;
use vadgr_daemon::engine::mcp::{HostFactory, McpHost, ToolServer};
use vadgr_daemon::engine::provider::{ModelClient, ModelFactory};
use vadgr_daemon::engine::supervisor::RunSupervisor;
use vadgr_daemon::engine::{
    ContentBlock, Engine, McpError, Message, ModelResponse, ProviderError, StopReason, ToolResult,
    ToolSpec, Usage,
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

struct RecoveryModel {
    responses: Mutex<VecDeque<ModelResponse>>,
    opening_messages: Arc<Mutex<Vec<Message>>>,
}

#[async_trait]
impl ModelClient for RecoveryModel {
    async fn complete(
        &self,
        messages: &[Message],
        _tools: &[ToolSpec],
        _max_tokens: u32,
    ) -> Result<ModelResponse, ProviderError> {
        if self.opening_messages.lock().unwrap().is_empty() {
            *self.opening_messages.lock().unwrap() = messages.to_vec();
        }
        self.responses
            .lock()
            .unwrap()
            .pop_front()
            .ok_or_else(|| ProviderError::Request("recovery script exhausted".to_owned()))
    }
}

struct RecoveryModelFactory {
    opening_messages: Arc<Mutex<Vec<Message>>>,
}

#[async_trait]
impl ModelFactory for RecoveryModelFactory {
    async fn build(
        &self,
        _provider: &str,
        _model: &str,
    ) -> Result<Box<dyn ModelClient>, ProviderError> {
        Ok(Box::new(RecoveryModel {
            responses: Mutex::new(
                vec![
                    ModelResponse {
                        content: vec![ContentBlock::ToolUse {
                            id: "inspect-1".to_owned(),
                            name: "side-effect__inspect".to_owned(),
                            input: json!({}),
                        }],
                        stop_reason: Some(StopReason::ToolUse),
                        usage: Usage {
                            input_tokens: 4,
                            output_tokens: 2,
                        },
                    },
                    ModelResponse {
                        content: vec![ContentBlock::Text {
                            text: "recovered".to_owned(),
                        }],
                        stop_reason: Some(StopReason::EndTurn),
                        usage: Usage {
                            input_tokens: 2,
                            output_tokens: 1,
                        },
                    },
                ]
                .into(),
            ),
            opening_messages: self.opening_messages.clone(),
        }))
    }
}

struct SideEffectServer {
    inspected: Arc<AtomicUsize>,
    replayed: Arc<AtomicUsize>,
}

#[async_trait]
impl ToolServer for SideEffectServer {
    fn namespace(&self) -> &str {
        "side-effect"
    }

    async fn list_tools(&mut self) -> Result<Vec<ToolSpec>, McpError> {
        Ok(["act", "inspect"]
            .into_iter()
            .map(|name| ToolSpec {
                name: name.to_owned(),
                description: name.to_owned(),
                input_schema: Map::new(),
            })
            .collect())
    }

    async fn call_tool(
        &mut self,
        name: &str,
        _args: Map<String, Value>,
    ) -> Result<ToolResult, McpError> {
        match name {
            "inspect" => {
                self.inspected.fetch_add(1, Ordering::SeqCst);
                Ok(ToolResult::text("the effect already exists"))
            }
            "act" => {
                self.replayed.fetch_add(1, Ordering::SeqCst);
                Ok(ToolResult::text("acted again"))
            }
            _ => Err(McpError::UnknownTool(name.to_owned())),
        }
    }

    async fn close(&mut self) {}
}

struct RecoveryHostFactory {
    inspected: Arc<AtomicUsize>,
    replayed: Arc<AtomicUsize>,
}

#[async_trait]
impl HostFactory for RecoveryHostFactory {
    async fn build(&self, _context: RunContext) -> Result<McpHost, McpError> {
        Ok(McpHost::new(vec![Box::new(SideEffectServer {
            inspected: self.inspected.clone(),
            replayed: self.replayed.clone(),
        })]))
    }
}

async fn wait_for_status(db: &Db, id: &str, expected: &str) -> Value {
    for _ in 0..100 {
        let row = db::runs::get(db, id).unwrap().unwrap();
        if row["status"] == expected {
            return row;
        }
        tokio::time::sleep(Duration::from_millis(20)).await;
    }
    panic!("run {id} did not reach {expected}");
}

#[tokio::test]
async fn boot_recovery_inspects_but_never_replays_a_dangling_call() {
    let directory = tempfile::tempdir().unwrap();
    let db = Db::open(directory.path().join("vadgr.db")).unwrap();
    seed_fake_model(&db);
    let row = db::runs::create(&db, "make one effect", Some("fake"), Some("fake-model")).unwrap();
    let id = row["id"].as_str().unwrap().to_owned();
    db::runs::update_status(&db, &id, "running").unwrap();

    let journal = Journal::open(directory.path(), &id, -1).await.unwrap();
    let old_seq = journal
        .append_in_flight(0, "side-effect__act", &json!({"target": "one"}))
        .await
        .unwrap();
    assert_eq!(old_seq, 0);
    drop(journal);

    let opening_messages = Arc::new(Mutex::new(Vec::new()));
    let inspected = Arc::new(AtomicUsize::new(0));
    let replayed = Arc::new(AtomicUsize::new(0));
    let engine = Arc::new(Engine::new(
        Arc::new(RecoveryModelFactory {
            opening_messages: opening_messages.clone(),
        }),
        Arc::new(RecoveryHostFactory {
            inspected: inspected.clone(),
            replayed: replayed.clone(),
        }),
        db.clone(),
        directory.path().to_owned(),
    ));
    let supervisor = RunSupervisor::new(engine, db.clone(), Arc::new(ConnectionManager::new()));

    let report = supervisor.recover_on_boot().await;
    assert_eq!(report.resumed.as_slice(), std::slice::from_ref(&id));
    let completed = wait_for_status(&db, &id, "completed").await;
    assert_eq!(completed["outputs"]["result"], "recovered");
    assert_eq!(inspected.load(Ordering::SeqCst), 1);
    assert_eq!(replayed.load(Ordering::SeqCst), 0);

    let messages = opening_messages.lock().unwrap();
    assert_eq!(messages[0].content, json!("make one effect"));
    let notice = messages[1].content.as_str().unwrap();
    assert!(notice.contains("side-effect__act"));
    assert!(notice.contains("unknown outcome"));
    assert!(notice.contains("Inspect the live state first"));

    let trajectory =
        std::fs::read_to_string(directory.path().join(&id).join("trajectory.jsonl")).unwrap();
    let records = trajectory
        .lines()
        .map(|line| serde_json::from_str::<Value>(line).unwrap())
        .collect::<Vec<_>>();
    assert_eq!(records[0]["seq"], 0);
    assert_eq!(records[0]["tool"], "side-effect__act");
    assert!(records.iter().any(|record| {
        record["phase"] == "in_flight"
            && record["seq"] == 1
            && record["tool"] == "side-effect__inspect"
    }));
    assert!(!records.iter().any(|record| {
        record["phase"] == "in_flight" && record["seq"] != 0 && record["tool"] == "side-effect__act"
    }));
}

#[tokio::test]
async fn corrupt_active_journal_fails_that_row_without_blocking_the_scan() {
    let directory = tempfile::tempdir().unwrap();
    let db = Db::open(directory.path().join("vadgr.db")).unwrap();
    seed_fake_model(&db);
    let row = db::runs::create(&db, "recover me", Some("fake"), Some("fake-model")).unwrap();
    let id = row["id"].as_str().unwrap().to_owned();
    let run_dir = directory.path().join(&id);
    std::fs::create_dir_all(&run_dir).unwrap();
    std::fs::write(run_dir.join("trajectory.jsonl"), "not-json\n{}\n").unwrap();

    let engine = Arc::new(Engine::new(
        Arc::new(RecoveryModelFactory {
            opening_messages: Arc::new(Mutex::new(Vec::new())),
        }),
        Arc::new(RecoveryHostFactory {
            inspected: Arc::new(AtomicUsize::new(0)),
            replayed: Arc::new(AtomicUsize::new(0)),
        }),
        db.clone(),
        directory.path().to_owned(),
    ));
    let supervisor = RunSupervisor::new(engine, db.clone(), Arc::new(ConnectionManager::new()));
    let report = supervisor.recover_on_boot().await;

    assert_eq!(report.failed.as_slice(), std::slice::from_ref(&id));
    let failed = db::runs::get(&db, &id).unwrap().unwrap();
    assert_eq!(failed["status"], "failed");
    assert!(
        failed["outputs"]["error"]
            .as_str()
            .unwrap()
            .contains("recovery failed")
    );
}
