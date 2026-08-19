use crate::ws::manager::ConnectionManager;
use serde_json::{Value, json};
use std::sync::Arc;

#[derive(Clone)]
pub struct EventSink {
    run_id: String,
    manager: Arc<ConnectionManager>,
}

impl EventSink {
    pub fn new(run_id: impl Into<String>, manager: Arc<ConnectionManager>) -> Self {
        Self {
            run_id: run_id.into(),
            manager,
        }
    }

    pub fn emit(&self, kind: &str, data: Value) {
        self.manager.broadcast(
            &self.run_id,
            json!({
                "type": kind,
                "data": data,
                "timestamp": crate::db::now_iso(),
            }),
        );
    }
}
