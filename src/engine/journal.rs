use crate::engine::types::{ModelResponse, RunId, ToolContent, ToolResult, Usage};
use serde_json::{Map, Value, json};
use sha2::{Digest, Sha256};
use std::io::Write;
use std::path::{Path, PathBuf};
use std::sync::Arc;
use std::sync::LazyLock;
use std::sync::atomic::{AtomicI64, Ordering};
use tokio::sync::{mpsc, oneshot};

const RECENT_RESULTS: usize = 3;
const RECOVERY_RESULT_LIMIT: usize = 2000;
static CAMEL_CASE_BOUNDARY: LazyLock<regex::Regex> =
    LazyLock::new(|| regex::Regex::new(r"([a-z0-9])([A-Z])").expect("static camel-case regex"));
static SECRET_TEXT: LazyLock<regex::Regex> = LazyLock::new(|| {
    regex::Regex::new(r"(?i)(Bearer\s+|sk-)[A-Za-z0-9._-]{8,}").expect("static secret regex")
});

#[derive(Clone, Debug, PartialEq)]
pub struct InFlightRecord {
    pub seq: i64,
    pub tool: String,
    pub params: Value,
    pub idem: String,
}

#[derive(Clone, Debug, PartialEq)]
pub struct AwaitUserRecord {
    pub seq: i64,
    pub request: Value,
}

/// A completed call and the result it produced, kept together.
///
/// Recovery used to keep only the result and describe the work in prose. A model
/// resuming that way is told what happened instead of being shown it, so whether
/// it repeats a completed action depends on it obeying an instruction. Keeping
/// the pair lets the resumed conversation carry the same tool-use shape an
/// uninterrupted one has.
#[derive(Clone, Debug, PartialEq)]
pub struct RecoveredCall {
    pub seq: i64,
    pub tool: String,
    pub params: Value,
    pub result: ToolResult,
}

#[derive(Clone, Debug, PartialEq)]
pub struct RecoveryState {
    pub run_id: RunId,
    pub last_seq: i64,
    pub completed_seqs: Vec<i64>,
    pub recent_results: Vec<ToolResult>,
    pub recent_calls: Vec<RecoveredCall>,
    pub dangling: Option<InFlightRecord>,
    pub pending_ask: Option<AwaitUserRecord>,
    /// Tool calls that ran and returned a result, not calls that were tried.
    /// A call that failed did not do the step, so a resumed run must be free to
    /// try it again, and a run whose every call failed did nothing at all.
    pub succeeded_tool_count: u64,
    pub prior_usage: Usage,
    pub todos: Vec<Value>,
}

struct WriteCommand {
    record: Value,
    ack: oneshot::Sender<Result<(), String>>,
}

#[derive(Clone)]
pub struct Journal {
    run_id: RunId,
    path: PathBuf,
    seq: Arc<AtomicI64>,
    tx: mpsc::UnboundedSender<WriteCommand>,
}

impl Journal {
    pub async fn open(runs_dir: &Path, run_id: &str, start_seq: i64) -> Result<Self, String> {
        let path = runs_dir.join(run_id).join("trajectory.jsonl");
        let writer_path = path.clone();
        let (tx, mut rx) = mpsc::unbounded_channel::<WriteCommand>();
        tokio::task::spawn_blocking(move || {
            let result = (|| -> Result<std::fs::File, String> {
                let parent = writer_path.parent().ok_or("journal has no parent")?;
                crate::private_fs::create_dir_all(parent).map_err(|error| error.to_string())?;
                crate::private_fs::append(&writer_path).map_err(|error| error.to_string())
            })();
            let mut file = match result {
                Ok(file) => file,
                Err(error) => {
                    while let Some(command) = rx.blocking_recv() {
                        let _ = command.ack.send(Err(error.clone()));
                    }
                    return;
                }
            };
            while let Some(command) = rx.blocking_recv() {
                let result = serde_json::to_vec(&command.record)
                    .map_err(|error| error.to_string())
                    .and_then(|mut bytes| {
                        bytes.push(b'\n');
                        file.write_all(&bytes)
                            .and_then(|_| file.flush())
                            .and_then(|_| file.sync_data())
                            .map_err(|error| error.to_string())
                    });
                let _ = command.ack.send(result);
            }
        });
        Ok(Self {
            run_id: run_id.to_owned(),
            path,
            seq: Arc::new(AtomicI64::new(start_seq)),
            tx,
        })
    }

    pub fn path(&self) -> &Path {
        &self.path
    }

    pub async fn append_response(
        &self,
        iteration: u32,
        response: &ModelResponse,
    ) -> Result<(), String> {
        let content = serde_json::to_value(&response.content).map_err(|error| error.to_string())?;
        self.append(json!({
            "phase": "response",
            "iteration": iteration,
            "response": {
                "content": content,
                "stop_reason": response.stop_reason.as_ref().map(ToString::to_string),
            },
            "usage": response.usage,
        }))
        .await
    }

    pub async fn append_in_flight(
        &self,
        iteration: u32,
        tool: &str,
        params: &Value,
    ) -> Result<i64, String> {
        let seq = self.seq.fetch_add(1, Ordering::SeqCst) + 1;
        let params = redact(params);
        let idem = idempotency_key(tool, &params);
        self.append(json!({
            "seq": seq,
            "phase": "in_flight",
            "iteration": iteration,
            "tool": tool,
            "params": params,
            "idem": idem,
        }))
        .await?;
        Ok(seq)
    }

    pub async fn append_done(&self, seq: i64, result: &ToolResult) -> Result<(), String> {
        self.append(json!({
            "seq": seq,
            "phase": "done",
            "status": "ok",
            "result": result,
        }))
        .await
    }

    pub async fn append_error(&self, seq: i64, error: &str) -> Result<(), String> {
        self.append(json!({
            "seq": seq,
            "phase": "error",
            "status": "error",
            "error": error,
        }))
        .await
    }

    pub async fn append_await_user(&self, seq: i64, request: &Value) -> Result<(), String> {
        self.append(json!({
            "seq": seq,
            "phase": "await_user",
            "request": request,
        }))
        .await
    }

    pub async fn append_server_failure(&self, server: &str, reason: &str) -> Result<(), String> {
        self.append(json!({
            "phase": "server_failed",
            "server": server,
            "error": reason,
        }))
        .await
    }

    async fn append(&self, body: Value) -> Result<(), String> {
        let body = redact(&body);
        let body = match body {
            Value::Object(mut object) => {
                let mut record = Map::new();
                record.insert("ts".to_owned(), Value::String(crate::db::now_iso()));
                record.insert("run_id".to_owned(), Value::String(self.run_id.clone()));
                record.append(&mut object);
                Value::Object(record)
            }
            _ => return Err("journal record must be an object".to_owned()),
        };
        let (ack, receive) = oneshot::channel();
        self.tx
            .send(WriteCommand { record: body, ack })
            .map_err(|_| "journal writer stopped".to_owned())?;
        receive
            .await
            .map_err(|_| "journal writer stopped".to_owned())?
    }
}

pub async fn read_recovery(path: PathBuf, run_id: RunId) -> Result<RecoveryState, String> {
    tokio::task::spawn_blocking(move || read_recovery_sync(&path, &run_id))
        .await
        .map_err(|error| error.to_string())?
}

fn read_recovery_sync(path: &Path, run_id: &str) -> Result<RecoveryState, String> {
    let bytes = match std::fs::read(path) {
        Ok(bytes) => bytes,
        Err(error) if error.kind() == std::io::ErrorKind::NotFound => Vec::new(),
        Err(error) => return Err(error.to_string()),
    };
    let ends_with_newline = bytes.last().is_none_or(|byte| *byte == b'\n');
    let chunks: Vec<&[u8]> = bytes.split(|byte| *byte == b'\n').collect();
    let last_nonempty = chunks.iter().rposition(|line| !line.is_empty());
    let mut records = Vec::new();
    for (index, line) in chunks.iter().enumerate() {
        if line.is_empty() {
            continue;
        }
        match serde_json::from_slice::<Value>(line) {
            Ok(record) => records.push(record),
            Err(_) if !ends_with_newline && Some(index) == last_nonempty => break,
            Err(error) => return Err(format!("journal corruption at line {}: {error}", index + 1)),
        }
    }

    let mut open = std::collections::BTreeMap::<i64, InFlightRecord>::new();
    let mut completed = Vec::new();
    let mut succeeded = 0u64;
    let mut recent = Vec::new();
    let mut recent_calls = Vec::new();
    let mut pending = None;
    let mut last_seq = -1;
    let mut prior_usage = Usage::default();
    let mut todos = Vec::new();
    for record in records {
        if let Some(seq) = record.get("seq").and_then(Value::as_i64) {
            last_seq = last_seq.max(seq);
            match record.get("phase").and_then(Value::as_str) {
                Some("in_flight") => {
                    open.insert(
                        seq,
                        InFlightRecord {
                            seq,
                            tool: record
                                .get("tool")
                                .and_then(Value::as_str)
                                .unwrap_or("")
                                .to_owned(),
                            params: record.get("params").cloned().unwrap_or_else(|| json!({})),
                            idem: record
                                .get("idem")
                                .and_then(Value::as_str)
                                .unwrap_or("")
                                .to_owned(),
                        },
                    );
                }
                Some("done") | Some("error") => {
                    let completed_call = open.remove(&seq);
                    completed.push(seq);
                    if record.get("phase").and_then(Value::as_str) == Some("done") {
                        succeeded += 1;
                    }
                    if record.get("phase").and_then(Value::as_str) == Some("done")
                        && let Some(value) = record.get("result")
                    {
                        if let (Some(call), Ok(result)) = (
                            completed_call.as_ref(),
                            serde_json::from_value::<ToolResult>(value.clone()),
                        ) {
                            apply_todo_result(&call.tool, &result, &mut todos);
                        }
                        let bounded = bounded_result(value);
                        if let Ok(result) = serde_json::from_value::<ToolResult>(bounded) {
                            if let Some(call) = completed_call.as_ref() {
                                recent_calls.push(RecoveredCall {
                                    seq,
                                    tool: call.tool.clone(),
                                    params: call.params.clone(),
                                    result: result.clone(),
                                });
                                if recent_calls.len() > RECENT_RESULTS {
                                    recent_calls.remove(0);
                                }
                            }
                            recent.push(result);
                            if recent.len() > RECENT_RESULTS {
                                recent.remove(0);
                            }
                        }
                    }
                    if pending
                        .as_ref()
                        .is_some_and(|ask: &AwaitUserRecord| ask.seq == seq)
                    {
                        pending = None;
                    }
                }
                Some("await_user") => {
                    pending = Some(AwaitUserRecord {
                        seq,
                        request: record.get("request").cloned().unwrap_or(Value::Null),
                    });
                }
                _ => {}
            }
        }
        if record.get("phase").and_then(Value::as_str) == Some("response")
            && let Some(usage) = record.get("usage")
        {
            prior_usage.input_tokens += usage
                .get("input_tokens")
                .and_then(Value::as_u64)
                .unwrap_or(0);
            prior_usage.output_tokens += usage
                .get("output_tokens")
                .and_then(Value::as_u64)
                .unwrap_or(0);
        }
    }
    completed.sort_unstable();
    completed.dedup();
    let dangling = open.into_values().next_back();
    Ok(RecoveryState {
        run_id: run_id.to_owned(),
        last_seq,
        succeeded_tool_count: succeeded,
        completed_seqs: completed,
        recent_results: recent,
        recent_calls,
        dangling,
        pending_ask: pending,
        prior_usage,
        todos,
    })
}

fn apply_todo_result(tool: &str, result: &ToolResult, todos: &mut Vec<Value>) {
    let Some(text) = result.content.iter().find_map(|content| match content {
        ToolContent::Text { text } => Some(text),
        ToolContent::Image { .. } => None,
    }) else {
        return;
    };
    let Ok(value) = serde_json::from_str::<Value>(text) else {
        return;
    };
    match tool {
        "control__todo_write" => {
            if let Some(items) = value.get("todos").and_then(Value::as_array) {
                *todos = items.clone();
            }
        }
        "control__todo_update" => {
            let Some(updated) = value.get("todo") else {
                return;
            };
            let Some(id) = updated.get("id").and_then(Value::as_str) else {
                return;
            };
            if let Some(item) = todos
                .iter_mut()
                .find(|item| item.get("id").and_then(Value::as_str) == Some(id))
            {
                *item = updated.clone();
            }
        }
        _ => {}
    }
}

pub fn redact(value: &Value) -> Value {
    match value {
        Value::Object(object) => Value::Object(
            object
                .iter()
                .map(|(key, value)| {
                    let value = if is_secret_key(key) {
                        Value::String("[REDACTED]".to_owned())
                    } else {
                        redact(value)
                    };
                    (key.clone(), value)
                })
                .collect(),
        ),
        Value::Array(values) => Value::Array(values.iter().map(redact).collect()),
        Value::String(value) => Value::String(redact_string(value)),
        other => other.clone(),
    }
}

fn is_secret_key(key: &str) -> bool {
    let normalized = CAMEL_CASE_BOUNDARY
        .replace_all(key, "${1}_${2}")
        .replace('-', "_")
        .to_lowercase();
    let words: Vec<&str> = normalized.split('_').collect();
    let whole = [
        "token",
        "secret",
        "password",
        "passwd",
        "passphrase",
        "authorization",
        "bearer",
        "cookie",
        "credential",
        "credentials",
        "signature",
    ];
    whole.iter().any(|secret| words.contains(secret))
        || normalized.ends_with("api_key")
        || normalized.ends_with("access_key")
        || normalized.ends_with("private_key")
}

fn redact_string(value: &str) -> String {
    SECRET_TEXT.replace_all(value, "[REDACTED]").into_owned()
}

fn idempotency_key(tool: &str, params: &Value) -> String {
    let canonical =
        serde_json::to_vec(&json!({"tool": tool, "params": params})).unwrap_or_default();
    let digest = Sha256::digest(canonical);
    let hex = digest
        .iter()
        .map(|byte| format!("{byte:02x}"))
        .collect::<String>();
    format!("sha256:{hex}")
}

fn bounded_result(value: &Value) -> Value {
    let encoded = value.to_string();
    let character_count = encoded.chars().count();
    if character_count <= RECOVERY_RESULT_LIMIT {
        value.clone()
    } else {
        let prefix: String = encoded.chars().take(RECOVERY_RESULT_LIMIT).collect();
        serde_json::to_value(ToolResult::text(format!(
            "{}... ({} chars)",
            prefix, character_count
        )))
        .unwrap_or(Value::Null)
    }
}

#[cfg(test)]
mod tests {
    use super::{Journal, bounded_result, read_recovery, redact};
    use crate::engine::types::ToolResult;
    use serde_json::json;

    #[cfg(unix)]
    use std::os::unix::fs::PermissionsExt;

    #[cfg(unix)]
    #[tokio::test]
    async fn an_existing_journal_is_hardened_for_the_owner() {
        let directory = tempfile::tempdir().unwrap();
        let run = directory.path().join("run-1");
        let path = run.join("trajectory.jsonl");
        std::fs::create_dir(&run).unwrap();
        std::fs::write(&path, []).unwrap();
        std::fs::set_permissions(&run, std::fs::Permissions::from_mode(0o777)).unwrap();
        std::fs::set_permissions(&path, std::fs::Permissions::from_mode(0o666)).unwrap();

        let journal = Journal::open(directory.path(), "run-1", -1).await.unwrap();
        journal
            .append_in_flight(0, "probe", &json!({}))
            .await
            .unwrap();
        drop(journal);

        assert_eq!(
            std::fs::metadata(&run).unwrap().permissions().mode() & 0o777,
            0o700
        );
        assert_eq!(
            std::fs::metadata(&path).unwrap().permissions().mode() & 0o777,
            0o600
        );
    }

    #[tokio::test]
    async fn sequence_continues_and_closes_reuse_the_opening_number() {
        let directory = tempfile::tempdir().unwrap();
        let journal = Journal::open(directory.path(), "run-1", -1).await.unwrap();
        let first = journal
            .append_in_flight(0, "one", &json!({}))
            .await
            .unwrap();
        journal
            .append_done(first, &ToolResult::text("ok"))
            .await
            .unwrap();
        let second = journal
            .append_in_flight(1, "two", &json!({}))
            .await
            .unwrap();
        assert_eq!((first, second), (0, 1));
        drop(journal);
        let state = read_recovery(
            directory.path().join("run-1/trajectory.jsonl"),
            "run-1".to_owned(),
        )
        .await
        .unwrap();
        assert_eq!(state.completed_seqs, vec![0]);
        assert_eq!(state.dangling.unwrap().seq, 1);
    }

    #[tokio::test]
    async fn recovery_restores_the_latest_successful_todo_state() {
        let directory = tempfile::tempdir().unwrap();
        let journal = Journal::open(directory.path(), "run-1", -1).await.unwrap();
        let write = journal
            .append_in_flight(
                0,
                "control__todo_write",
                &json!({"items":[{"id":"inspect","content":"Inspect","status":"in_progress"}]}),
            )
            .await
            .unwrap();
        journal
            .append_done(
                write,
                &ToolResult::text(
                    json!({"ok":true,"todos":[{"id":"inspect","content":"Inspect","status":"in_progress"}]}).to_string(),
                ),
            )
            .await
            .unwrap();
        let update = journal
            .append_in_flight(
                1,
                "control__todo_update",
                &json!({"id":"inspect","status":"done"}),
            )
            .await
            .unwrap();
        journal
            .append_done(
                update,
                &ToolResult::text(
                    json!({"ok":true,"todo":{"id":"inspect","content":"Inspect","status":"done"}})
                        .to_string(),
                ),
            )
            .await
            .unwrap();
        drop(journal);

        let state = read_recovery(
            directory.path().join("run-1/trajectory.jsonl"),
            "run-1".to_owned(),
        )
        .await
        .unwrap();

        assert_eq!(
            state.todos,
            vec![json!({"id":"inspect","content":"Inspect","status":"done"})]
        );
    }

    #[test]
    fn deep_redaction_keeps_usage_counts() {
        let value = redact(&json!({
            "accessToken":"secret", "nested":[{"authorization":"Bearer abcdefghijk"}],
            "input_tokens": 12, "max_tokens": 20
        }));
        assert_eq!(value["accessToken"], "[REDACTED]");
        assert_eq!(value["nested"][0]["authorization"], "[REDACTED]");
        assert_eq!(value["input_tokens"], 12);
        assert_eq!(value["max_tokens"], 20);
    }

    #[test]
    fn bounded_result_truncates_unicode_on_character_boundaries() {
        let bounded = bounded_result(&json!({"text": "é".repeat(2100)}));
        let text = bounded["content"][0]["text"].as_str().unwrap();
        assert!(text.ends_with("(2111 chars)"));
        assert!(text.contains('é'));
    }

    #[tokio::test]
    async fn incomplete_final_line_is_ignored_but_earlier_corruption_fails() {
        let directory = tempfile::tempdir().unwrap();
        let path = directory.path().join("trajectory.jsonl");
        std::fs::write(&path, b"{\"phase\":\"response\"}\n{\"phase\":").unwrap();
        assert!(read_recovery(path.clone(), "run".to_owned()).await.is_ok());
        std::fs::write(&path, b"not-json\n{\"phase\":\"response\"}\n").unwrap();
        assert!(read_recovery(path, "run".to_owned()).await.is_err());
    }
}
