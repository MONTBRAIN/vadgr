use crate::db::{self, Db};
use crate::engine::events::EventSink;
use crate::engine::journal::{RecoveryState, read_recovery};
use crate::engine::{Engine, EngineError, RunRecord};
use crate::ws::manager::ConnectionManager;
use serde_json::{Value, json};
use std::collections::HashMap;
use std::sync::{Arc, Weak};
use tokio::sync::{Mutex, oneshot};
use tokio::task::JoinHandle;
use tokio_util::sync::CancellationToken;

#[derive(Clone, Debug)]
pub struct StartRun {
    pub task: String,
    pub provider: Option<String>,
    pub model: Option<String>,
}

#[derive(Debug, thiserror::Error)]
pub enum RunError {
    #[error("run not found")]
    NotFound,
    #[error("run is not active")]
    NotActive,
    #[error("run is not resumable from status `{0}`")]
    NotResumable(String),
    #[error("run storage failed: {0}")]
    Storage(String),
    #[error("run recovery failed: {0}")]
    Recovery(String),
}

#[derive(Clone, Debug, Default, Eq, PartialEq)]
pub struct RecoveryReport {
    pub resumed: Vec<String>,
    pub parked: Vec<String>,
    pub failed: Vec<String>,
}

struct ActiveRun {
    generation: uuid::Uuid,
    cancelled: CancellationToken,
    _handle: JoinHandle<()>,
}

#[derive(Clone, Copy)]
enum Launch {
    New,
    Manual,
    Boot,
}

pub struct RunSupervisor {
    engine: Arc<Engine>,
    db: Db,
    events: Arc<ConnectionManager>,
    active: Mutex<HashMap<String, ActiveRun>>,
}

impl RunSupervisor {
    pub fn new(engine: Arc<Engine>, db: Db, events: Arc<ConnectionManager>) -> Arc<Self> {
        Arc::new(Self {
            engine,
            db,
            events,
            active: Mutex::new(HashMap::new()),
        })
    }

    pub async fn create(self: &Arc<Self>, request: StartRun) -> Result<Value, RunError> {
        let row = db::runs::create(
            &self.db,
            &request.task,
            request.provider.as_deref(),
            request.model.as_deref(),
        )
        .map_err(storage)?;
        let id = row_id(&row)?;
        self.spawn(id, None, Launch::New).await;
        Ok(row)
    }

    pub async fn resume(self: &Arc<Self>, id: &str) -> Result<Value, RunError> {
        let row = db::runs::get(&self.db, id)
            .map_err(storage)?
            .ok_or(RunError::NotFound)?;
        let status = row_status(&row)?;
        if status != "failed" {
            return Err(RunError::NotResumable(status.to_owned()));
        }
        let recovery = read_recovery(self.journal_path(id), id.to_owned())
            .await
            .map_err(RunError::Recovery)?;
        let row = db::runs::update_status(&self.db, id, "running")
            .map_err(storage)?
            .ok_or(RunError::NotFound)?;
        self.spawn(id.to_owned(), Some(recovery), Launch::Manual)
            .await;
        Ok(row)
    }

    pub async fn cancel(self: &Arc<Self>, id: &str) -> Result<Value, RunError> {
        let row = db::runs::get(&self.db, id)
            .map_err(storage)?
            .ok_or(RunError::NotFound)?;
        if matches!(row_status(&row)?, "completed" | "failed" | "cancelled") {
            return Err(RunError::NotActive);
        }
        let updated = db::runs::finish_if_active(
            &self.db,
            id,
            "cancelled",
            &json!({"error":"Run was cancelled"}),
        )
        .map_err(storage)?
        .ok_or(RunError::NotActive)?;
        if let Some(active) = self.active.lock().await.get(id) {
            active.cancelled.cancel();
        }
        Ok(updated)
    }

    pub async fn recover_on_boot(self: &Arc<Self>) -> RecoveryReport {
        let mut report = RecoveryReport::default();
        let rows = match db::runs::active(&self.db) {
            Ok(rows) => rows,
            Err(error) => {
                tracing::error!(%error, "active run recovery scan failed");
                return report;
            }
        };
        for row in rows {
            let Ok(id) = row_id(&row) else { continue };
            let status = row_status(&row).unwrap_or("").to_owned();
            let task = row
                .get("inputs")
                .and_then(|value| value.get("task"))
                .and_then(Value::as_str)
                .filter(|task| !task.trim().is_empty());
            if task.is_none() {
                let _ = db::runs::finish_if_active(
                    &self.db,
                    &id,
                    "failed",
                    &json!({"error":"recovery failed: run has no task"}),
                );
                report.failed.push(id);
                continue;
            }
            let recovery = match read_recovery(self.journal_path(&id), id.clone()).await {
                Ok(recovery) => recovery,
                Err(error) => {
                    let _ = db::runs::finish_if_active(
                        &self.db,
                        &id,
                        "failed",
                        &json!({"error":format!("recovery failed: {error}")}),
                    );
                    report.failed.push(id);
                    continue;
                }
            };
            if status == "awaiting_approval" {
                if recovery.pending_ask.is_some() {
                    self.spawn_parked(id.clone()).await;
                    report.parked.push(id);
                } else {
                    let _ = db::runs::finish_if_active(
                        &self.db,
                        &id,
                        "failed",
                        &json!({"error":"recovery failed: parked run has no pending ask"}),
                    );
                    report.failed.push(id);
                }
                continue;
            }
            self.spawn(id.clone(), Some(recovery), Launch::Boot).await;
            report.resumed.push(id);
        }
        report
    }

    async fn spawn(self: &Arc<Self>, id: String, recovery: Option<RecoveryState>, launch: Launch) {
        let generation = uuid::Uuid::new_v4();
        let cancelled = CancellationToken::new();
        let (start_tx, start_rx) = oneshot::channel();
        let supervisor = Arc::downgrade(self);
        let task_id = id.clone();
        let task_cancelled = cancelled.clone();
        let handle = tokio::spawn(async move {
            if start_rx.await.is_err() {
                return;
            }
            if let Some(supervisor) = supervisor.upgrade() {
                supervisor
                    .drive(task_id.clone(), recovery, launch, task_cancelled)
                    .await;
                supervisor.remove_if_current(&task_id, generation).await;
            }
        });
        self.active.lock().await.insert(
            id,
            ActiveRun {
                generation,
                cancelled,
                _handle: handle,
            },
        );
        let _ = start_tx.send(());
    }

    async fn spawn_parked(self: &Arc<Self>, id: String) {
        let generation = uuid::Uuid::new_v4();
        let cancelled = CancellationToken::new();
        let task_cancelled = cancelled.clone();
        let supervisor: Weak<Self> = Arc::downgrade(self);
        let task_id = id.clone();
        let handle = tokio::spawn(async move {
            task_cancelled.cancelled().await;
            if let Some(supervisor) = supervisor.upgrade() {
                supervisor.remove_if_current(&task_id, generation).await;
            }
        });
        self.active.lock().await.insert(
            id,
            ActiveRun {
                generation,
                cancelled,
                _handle: handle,
            },
        );
    }

    async fn drive(
        self: &Arc<Self>,
        id: String,
        recovery: Option<RecoveryState>,
        launch: Launch,
        cancelled: CancellationToken,
    ) {
        let events = EventSink::new(id.clone(), self.events.clone());
        let record = match self.prepare_record(&id) {
            Ok(record) => record,
            Err(error) => {
                self.fail(&id, error.to_string(), &events);
                return;
            }
        };
        match launch {
            Launch::New => events.emit("run_started", json!({})),
            Launch::Manual | Launch::Boot => events.emit(
                "run_resumed",
                json!({"from_seq":recovery.as_ref().map(|state| state.last_seq + 1).unwrap_or(0)}),
            ),
        }
        events.emit("agent_started", json!({"run_id":id,"name":record.title}));
        match self
            .engine
            .execute(record, recovery, events.clone(), cancelled)
            .await
        {
            Ok(result) => {
                let outputs = json!({
                    "result":result.final_text,
                    "iterations":result.iterations,
                    "usage":result.usage,
                });
                if db::runs::finish_if_active(&self.db, &id, "completed", &outputs)
                    .ok()
                    .flatten()
                    .is_some()
                {
                    events.emit("agent_completed", json!({"run_id":id,"outputs":outputs}));
                    events.emit("run_completed", json!({"outputs":outputs}));
                }
            }
            Err(EngineError::Cancelled) => {}
            Err(error) => self.fail(&id, error.to_string(), &events),
        }
    }

    fn prepare_record(&self, id: &str) -> Result<RunRecord, RunError> {
        let row = db::runs::get(&self.db, id)
            .map_err(storage)?
            .ok_or(RunError::NotFound)?;
        let task = row
            .get("inputs")
            .and_then(|value| value.get("task"))
            .and_then(Value::as_str)
            .filter(|value| !value.trim().is_empty())
            .ok_or_else(|| RunError::Recovery("run has no task".to_owned()))?
            .to_owned();
        let provider = row.get("provider").and_then(Value::as_str);
        let model = row.get("model").and_then(Value::as_str);
        let (provider, model) = match (provider, model) {
            (Some(provider), Some(model)) => {
                if !db::providers::model_exists(&self.db, provider, model)
                    .map_err(|error| RunError::Storage(error.to_string()))?
                {
                    return Err(RunError::Recovery(format!(
                        "model `{provider}/{model}` is not connected"
                    )));
                }
                (provider.to_owned(), model.to_owned())
            }
            (None, None) => db::providers::default_model(&self.db)
                .map_err(|error| RunError::Storage(error.to_string()))?
                .ok_or_else(|| RunError::Recovery("no default model is connected".to_owned()))?,
            _ => {
                return Err(RunError::Recovery(
                    "provider and model must be supplied together".to_owned(),
                ));
            }
        };
        db::runs::set_config(&self.db, id, &provider, &model).map_err(storage)?;
        db::runs::update_status(&self.db, id, "running").map_err(storage)?;
        Ok(RunRecord {
            id: id.to_owned(),
            title: row
                .get("agent_name")
                .and_then(Value::as_str)
                .unwrap_or("")
                .to_owned(),
            task,
            provider,
            model,
        })
    }

    fn fail(&self, id: &str, error: String, events: &EventSink) {
        if db::runs::finish_if_active(&self.db, id, "failed", &json!({"error":error}))
            .ok()
            .flatten()
            .is_some()
        {
            events.emit("agent_failed", json!({"run_id":id,"error":error}));
            events.emit("run_failed", json!({"error":error}));
        }
    }

    async fn remove_if_current(&self, id: &str, generation: uuid::Uuid) {
        let mut active = self.active.lock().await;
        if active
            .get(id)
            .is_some_and(|run| run.generation == generation)
        {
            active.remove(id);
        }
    }

    fn journal_path(&self, id: &str) -> std::path::PathBuf {
        self.engine.runs_dir().join(id).join("trajectory.jsonl")
    }
}

fn storage(error: rusqlite::Error) -> RunError {
    RunError::Storage(error.to_string())
}

fn row_id(row: &Value) -> Result<String, RunError> {
    row.get("id")
        .and_then(Value::as_str)
        .map(str::to_owned)
        .ok_or_else(|| RunError::Storage("run row has no id".to_owned()))
}

fn row_status(row: &Value) -> Result<&str, RunError> {
    row.get("status")
        .and_then(Value::as_str)
        .ok_or_else(|| RunError::Storage("run row has no status".to_owned()))
}
