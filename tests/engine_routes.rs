use async_trait::async_trait;
use axum::body::Body;
use axum::http::{Request, StatusCode};
use http_body_util::BodyExt;
use serde_json::{Map, Value, json};
use std::collections::VecDeque;
use std::sync::atomic::{AtomicBool, AtomicUsize, Ordering};
use std::sync::{Arc, Mutex, RwLock};
use std::time::Duration;
use tower::ServiceExt;
use vadgr_daemon::auth::pairing::PairingStore;
use vadgr_daemon::computer_use_setup::SetupService;
use vadgr_daemon::config::Config;
use vadgr_daemon::db::{self, Db};
use vadgr_daemon::engine::control::RunContext;
use vadgr_daemon::engine::journal::Journal;
use vadgr_daemon::engine::mcp::{HostFactory, McpHost, ToolServer};
use vadgr_daemon::engine::provider::credentials::CredentialStore;
use vadgr_daemon::engine::provider::service::{ProviderEndpoints, ProviderService};
use vadgr_daemon::engine::provider::{ModelClient, ModelFactory};
use vadgr_daemon::engine::supervisor::RunSupervisor;
use vadgr_daemon::engine::{
    ContentBlock, Engine, McpError, Message, ModelResponse, ProviderError, StopReason, ToolResult,
    ToolSpec, Usage,
};
use vadgr_daemon::state::AppState;
use vadgr_daemon::transport::LoopbackTransport;
use vadgr_daemon::ws::manager::ConnectionManager;
use vadgr_daemon::ws::run_ws::to_run_event;

struct ScriptedModel {
    responses: Mutex<VecDeque<ModelResponse>>,
}

#[async_trait]
impl ModelClient for ScriptedModel {
    async fn complete(
        &self,
        _messages: &[Message],
        _tools: &[ToolSpec],
        _max_tokens: u32,
    ) -> Result<ModelResponse, ProviderError> {
        self.responses
            .lock()
            .unwrap()
            .pop_front()
            .ok_or_else(|| ProviderError::Request("script exhausted".to_owned()))
    }
}

struct ScriptedFactory {
    scripts: Mutex<VecDeque<Vec<ModelResponse>>>,
}

impl ScriptedFactory {
    fn new(scripts: Vec<Vec<ModelResponse>>) -> Self {
        Self {
            scripts: Mutex::new(scripts.into()),
        }
    }
}

#[async_trait]
impl ModelFactory for ScriptedFactory {
    async fn build(
        &self,
        provider: &str,
        model: &str,
    ) -> Result<Box<dyn ModelClient>, ProviderError> {
        assert_eq!((provider, model), ("fake", "fake-model"));
        let responses = self
            .scripts
            .lock()
            .unwrap()
            .pop_front()
            .ok_or_else(|| ProviderError::Request("no model script".to_owned()))?;
        Ok(Box::new(ScriptedModel {
            responses: Mutex::new(responses.into()),
        }))
    }
}

struct BlockingFactory(Arc<AtomicBool>);

struct BlockingModel(Arc<AtomicBool>);

struct DropMark(Arc<AtomicBool>);

impl Drop for DropMark {
    fn drop(&mut self) {
        self.0.store(true, Ordering::SeqCst);
    }
}

#[async_trait]
impl ModelClient for BlockingModel {
    async fn complete(
        &self,
        _messages: &[Message],
        _tools: &[ToolSpec],
        _max_tokens: u32,
    ) -> Result<ModelResponse, ProviderError> {
        let _drop_mark = DropMark(self.0.clone());
        std::future::pending().await
    }
}

#[async_trait]
impl ModelFactory for BlockingFactory {
    async fn build(
        &self,
        _provider: &str,
        _model: &str,
    ) -> Result<Box<dyn ModelClient>, ProviderError> {
        Ok(Box::new(BlockingModel(self.0.clone())))
    }
}

struct CountingServer(Arc<AtomicUsize>);

#[async_trait]
impl ToolServer for CountingServer {
    fn namespace(&self) -> &str {
        "test"
    }

    async fn list_tools(&mut self) -> Result<Vec<ToolSpec>, McpError> {
        Ok(vec![ToolSpec {
            name: "act".to_owned(),
            description: "perform the test action".to_owned(),
            input_schema: Map::new(),
        }])
    }

    async fn call_tool(
        &mut self,
        name: &str,
        _args: Map<String, Value>,
    ) -> Result<ToolResult, McpError> {
        assert_eq!(name, "act");
        self.0.fetch_add(1, Ordering::SeqCst);
        Ok(ToolResult::text("acted"))
    }

    async fn close(&mut self) {}
}

struct CountingHostFactory(Arc<AtomicUsize>);

#[async_trait]
impl HostFactory for CountingHostFactory {
    async fn build(&self, _context: RunContext) -> Result<McpHost, McpError> {
        Ok(McpHost::new(vec![Box::new(CountingServer(self.0.clone()))]))
    }
}

fn response(content: Vec<ContentBlock>, stop_reason: StopReason) -> ModelResponse {
    ModelResponse {
        content,
        stop_reason: Some(stop_reason),
        usage: Usage {
            input_tokens: 3,
            output_tokens: 2,
        },
    }
}

fn tool_then_finish() -> Vec<ModelResponse> {
    vec![
        response(
            vec![ContentBlock::ToolUse {
                id: "call-1".to_owned(),
                name: "test__act".to_owned(),
                input: json!({"value": 1}),
                provider_signature: None,
            }],
            StopReason::ToolUse,
        ),
        response(
            vec![ContentBlock::Text {
                text: "finished".to_owned(),
            }],
            StopReason::EndTurn,
        ),
    ]
}

struct Harness {
    state: AppState,
    runs_dir: std::path::PathBuf,
    _directory: tempfile::TempDir,
}

fn harness(model: Arc<dyn ModelFactory>, calls: Arc<AtomicUsize>) -> Harness {
    let directory = tempfile::tempdir().unwrap();
    let runs_dir = directory.path().join("runs");
    let db = Db::open(directory.path().join("vadgr.db")).unwrap();
    db::providers::commit_connection(
        &db,
        &db::providers::ConnectionCommit {
            connection: db::providers::Connection {
                provider_id: "fake".to_owned(),
                auth_method: "api_key".to_owned(),
                secret_ref: "fake-reference".to_owned(),
                account_id: None,
                credential_expires_at: None,
            },
            models: vec![db::providers::ProviderModel {
                id: "fake-model".to_owned(),
                name: "Fake model".to_owned(),
                capabilities: json!({"text":true,"tools":true}),
            }],
            default_model: Some("fake-model".to_owned()),
        },
    )
    .unwrap();
    let ws = Arc::new(ConnectionManager::new());
    let engine = Arc::new(Engine::new(
        model,
        Arc::new(CountingHostFactory(calls)),
        db.clone(),
        runs_dir.clone(),
    ));
    let supervisor = RunSupervisor::new(engine, db.clone(), ws.clone());
    let config = Arc::new(Config {
        port: 0,
        db_path: directory.path().join("vadgr.db"),
        local_only: true,
        relays: vadgr_daemon::config::RelayChoice::Default,
        runs_dir: runs_dir.clone(),
        state_home: Some(directory.path().to_owned()),
    });
    let setup = Arc::new(SetupService::new(
        directory.path().join("settings.json"),
        None,
        false,
    ));
    let providers = ProviderService::new(
        db.clone(),
        CredentialStore::new(directory.path().join("credentials")).unwrap(),
        ProviderEndpoints::default(),
    )
    .unwrap();
    Harness {
        state: AppState {
            db,
            config,
            transports: Arc::new(vadgr_daemon::transport::Transports::new(vec![Arc::new(
                LoopbackTransport,
            )])),
            pairing: Arc::new(PairingStore::new(300)),
            ws,
            providers,
            computer_use_setup: setup,
            computer_use_status: Arc::new(RwLock::new(json!({"venv_ready": false}))),
            supervisor,
        },
        runs_dir,
        _directory: directory,
    }
}

async fn send(state: AppState, request: Request<Body>) -> (StatusCode, Value) {
    // The stamp the loopback listener would have put on the request; the
    // gate reads no socket address any more.
    let response = vadgr_daemon::routes::router(state.clone())
        .layer(axum::middleware::from_fn_with_state(
            state,
            vadgr_daemon::auth::gate::gate,
        ))
        .into_service::<Body>()
        .oneshot({
            let mut request = request;
            request
                .extensions_mut()
                .insert(vadgr_daemon::transport::Peer {
                    transport: "loopback",
                    identity: "127.0.0.1".to_string(),
                });
            request
        })
        .await
        .unwrap();
    let status = response.status();
    let bytes = response.into_body().collect().await.unwrap().to_bytes();
    (
        status,
        serde_json::from_slice(&bytes).unwrap_or(Value::Null),
    )
}

fn post(path: &str, body: Option<Value>) -> Request<Body> {
    let mut builder = Request::builder().method("POST").uri(path);
    let body = match body {
        Some(body) => {
            builder = builder.header("content-type", "application/json");
            Body::from(body.to_string())
        }
        None => Body::empty(),
    };
    builder.body(body).unwrap()
}

/// Wait for a run to reach a state, bounded generously.
///
/// **The bound is a failure deadline, not a measurement.** A passing run returns
/// as soon as the row changes, so a wide ceiling costs a fast machine nothing and
/// only decides how long a genuinely stuck run hangs before it reports. At 100
/// polls of 20 ms this was two seconds, which is a Windows CI runner's ordinary
/// scheduling noise for a run that starts a task, writes a journal and commits to
/// SQLite: it went red there on the `0.4.8` pull request while both other tests in
/// this file passed, and while Linux and macOS passed the lot.
async fn wait_for_status(db: &Db, id: &str, expected: &str) -> Value {
    const POLL: Duration = Duration::from_millis(20);
    const DEADLINE: Duration = Duration::from_secs(20);
    let started = std::time::Instant::now();
    let mut last = String::new();
    while started.elapsed() < DEADLINE {
        let row = db::runs::get(db, id).unwrap().unwrap();
        if row["status"] == expected {
            return row;
        }
        last = row["status"].as_str().unwrap_or("?").to_owned();
        tokio::time::sleep(POLL).await;
    }
    // Say what it did reach. "did not reach completed" alone sends the next
    // reader to the wrong half of the system.
    panic!("run {id} did not reach {expected} within {DEADLINE:?}; last status was {last:?}");
}

#[tokio::test]
async fn create_runs_to_completion_and_records_http_events_and_journal() {
    let calls = Arc::new(AtomicUsize::new(0));
    let harness = harness(
        Arc::new(ScriptedFactory::new(vec![tool_then_finish()])),
        calls.clone(),
    );
    let (status, created) = send(
        harness.state.clone(),
        post("/api/runs", Some(json!({"task": "do one action"}))),
    )
    .await;
    assert_eq!(status, StatusCode::ACCEPTED, "{created}");
    assert_eq!(created["status"], "queued");
    let id = created["id"].as_str().unwrap();

    let completed = wait_for_status(&harness.state.db, id, "completed").await;
    assert_eq!(completed["provider"], "fake");
    assert_eq!(completed["model"], "fake-model");
    assert_eq!(completed["outputs"]["result"], "finished");
    assert_eq!(completed["outputs"]["usage"]["input_tokens"], 6);
    assert_eq!(calls.load(Ordering::SeqCst), 1);

    let (_, raw_frames) = harness.state.ws.connect(id);
    let raw_types = raw_frames
        .iter()
        .filter_map(|frame| frame["type"].as_str())
        .collect::<Vec<_>>();
    assert!(raw_types.contains(&"run_started"));
    assert!(raw_types.contains(&"agent_completed"));
    assert!(raw_types.contains(&"run_completed"));
    let mobile_types = raw_frames
        .iter()
        .filter_map(to_run_event)
        .filter_map(|frame| frame["type"].as_str().map(str::to_owned))
        .collect::<Vec<_>>();
    assert!(mobile_types.contains(&"started".to_owned()));
    assert!(mobile_types.contains(&"completed".to_owned()));

    let journal =
        std::fs::read_to_string(harness.runs_dir.join(id).join("trajectory.jsonl")).unwrap();
    let phases = journal
        .lines()
        .map(|line| serde_json::from_str::<Value>(line).unwrap()["phase"].clone())
        .collect::<Vec<_>>();
    assert_eq!(phases, ["response", "in_flight", "done", "response"]);
}

#[tokio::test]
async fn cancel_drops_an_in_flight_model_request_and_wins_terminal_state() {
    let dropped = Arc::new(AtomicBool::new(false));
    let harness = harness(
        Arc::new(BlockingFactory(dropped.clone())),
        Arc::new(AtomicUsize::new(0)),
    );
    let (_, created) = send(
        harness.state.clone(),
        post(
            "/api/runs",
            Some(json!({"task": "wait", "provider": "fake", "model": "fake-model"})),
        ),
    )
    .await;
    let id = created["id"].as_str().unwrap();
    wait_for_status(&harness.state.db, id, "running").await;

    let (status, cancelled) = send(
        harness.state.clone(),
        post(&format!("/api/runs/{id}/cancel"), None),
    )
    .await;
    assert_eq!(status, StatusCode::OK);
    assert_eq!(cancelled["status"], "cancelled");
    for _ in 0..100 {
        if dropped.load(Ordering::SeqCst) {
            break;
        }
        tokio::time::sleep(Duration::from_millis(10)).await;
    }
    assert!(dropped.load(Ordering::SeqCst));
    tokio::time::sleep(Duration::from_millis(20)).await;
    assert_eq!(
        db::runs::get(&harness.state.db, id).unwrap().unwrap()["status"],
        "cancelled"
    );
}

#[tokio::test]
async fn failed_run_resumes_from_its_journal_and_keeps_prior_usage() {
    let final_response = response(
        vec![ContentBlock::Text {
            text: "continued".to_owned(),
        }],
        StopReason::EndTurn,
    );
    let harness = harness(
        Arc::new(ScriptedFactory::new(vec![vec![final_response]])),
        Arc::new(AtomicUsize::new(0)),
    );
    let row = db::runs::create(
        &harness.state.db,
        "continue me",
        Some("fake"),
        Some("fake-model"),
    )
    .unwrap();
    let id = row["id"].as_str().unwrap();
    let journal = Journal::open(&harness.runs_dir, id, -1).await.unwrap();
    journal
        .append_response(
            0,
            &response(
                vec![ContentBlock::ToolUse {
                    id: "old-call".to_owned(),
                    name: "test__act".to_owned(),
                    input: json!({}),
                    provider_signature: None,
                }],
                StopReason::ToolUse,
            ),
        )
        .await
        .unwrap();
    let seq = journal
        .append_in_flight(0, "test__act", &json!({}))
        .await
        .unwrap();
    journal
        .append_done(seq, &ToolResult::text("already done"))
        .await
        .unwrap();
    drop(journal);
    db::runs::update_status(&harness.state.db, id, "failed").unwrap();

    let (status, resumed) = send(
        harness.state.clone(),
        post(&format!("/api/runs/{id}/resume"), None),
    )
    .await;
    assert_eq!(status, StatusCode::OK);
    assert_eq!(resumed["status"], "running");
    let completed = wait_for_status(&harness.state.db, id, "completed").await;
    assert_eq!(completed["outputs"]["result"], "continued");
    assert_eq!(completed["outputs"]["usage"]["input_tokens"], 6);
    assert_eq!(completed["outputs"]["usage"]["output_tokens"], 4);
}
