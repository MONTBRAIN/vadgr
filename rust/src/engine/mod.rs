pub mod channel;
pub mod control;
pub mod events;
pub mod journal;
pub mod r#loop;
pub mod mcp;
pub mod policy;
pub mod provider;
pub mod supervisor;
pub mod types;

pub use mcp::HostFactory;
pub use provider::{ModelClient, ModelFactory};
pub use types::*;

use crate::db::Db;
use crate::engine::control::RunContext;
use crate::engine::events::EventSink;
use crate::engine::journal::{Journal, RecoveryState};
use crate::engine::r#loop::run_loop;
use std::path::{Path, PathBuf};
use std::sync::Arc;
use tokio_util::sync::CancellationToken;

pub struct Engine {
    model_factory: Arc<dyn ModelFactory>,
    host_factory: Arc<dyn HostFactory>,
    limits: LoopLimits,
    db: Db,
    runs_dir: PathBuf,
}

impl Engine {
    pub fn new(
        model_factory: Arc<dyn ModelFactory>,
        host_factory: Arc<dyn HostFactory>,
        db: Db,
        runs_dir: PathBuf,
    ) -> Self {
        Self {
            model_factory,
            host_factory,
            limits: LoopLimits::default(),
            db,
            runs_dir,
        }
    }

    pub fn with_limits(mut self, limits: LoopLimits) -> Self {
        self.limits = limits;
        self
    }

    pub fn runs_dir(&self) -> &Path {
        &self.runs_dir
    }

    pub async fn execute(
        &self,
        run: RunRecord,
        recovery: Option<RecoveryState>,
        events: EventSink,
        cancelled: CancellationToken,
    ) -> Result<RunResult, EngineError> {
        let start_seq = recovery.as_ref().map(|state| state.last_seq).unwrap_or(-1);
        let journal = Journal::open(&self.runs_dir, &run.id, start_seq)
            .await
            .map_err(EngineError::Journal)?;
        let context = RunContext::new(
            run.id.clone(),
            journal.clone(),
            events,
            self.db.clone(),
            cancelled.clone(),
        );
        let model = self.model_factory.build(&run.provider, &run.model).await?;
        let mut host = self.host_factory.build(context.clone()).await?;
        let result = async {
            host.connect().await?;
            for (server, reason) in host.failed() {
                journal
                    .append_server_failure(server, reason)
                    .await
                    .map_err(EngineError::Journal)?;
            }
            run_loop(
                model.as_ref(),
                &mut host,
                &journal,
                &context,
                &run.task,
                recovery,
                cancelled,
                self.limits,
            )
            .await
        }
        .await;
        host.close().await;
        result
    }
}

#[cfg(test)]
mod tests {
    use super::{Engine, HostFactory, McpError, ModelClient, ModelFactory, RunRecord};
    use crate::db::Db;
    use crate::engine::control::RunContext;
    use crate::engine::events::EventSink;
    use crate::engine::mcp::{McpHost, ToolServer};
    use crate::engine::types::{Message, ModelResponse, ProviderError, ToolResult, ToolSpec};
    use crate::ws::manager::ConnectionManager;
    use async_trait::async_trait;
    use serde_json::{Map, Value};
    use std::sync::Arc;
    use std::sync::atomic::{AtomicUsize, Ordering};
    use tokio_util::sync::CancellationToken;

    struct UnusedModel;

    #[async_trait]
    impl ModelClient for UnusedModel {
        async fn complete(
            &self,
            _messages: &[Message],
            _tools: &[ToolSpec],
            _max_tokens: u32,
        ) -> Result<ModelResponse, ProviderError> {
            unreachable!("duplicate namespaces fail before the first model request")
        }
    }

    struct Model;

    #[async_trait]
    impl ModelFactory for Model {
        async fn build(
            &self,
            _provider: &str,
            _model: &str,
        ) -> Result<Box<dyn ModelClient>, ProviderError> {
            Ok(Box::new(UnusedModel))
        }
    }

    struct ClosingServer(Arc<AtomicUsize>);

    #[async_trait]
    impl ToolServer for ClosingServer {
        fn namespace(&self) -> &str {
            "duplicate"
        }

        async fn list_tools(&mut self) -> Result<Vec<ToolSpec>, McpError> {
            Ok(Vec::new())
        }

        async fn call_tool(
            &mut self,
            _name: &str,
            _args: Map<String, Value>,
        ) -> Result<ToolResult, McpError> {
            unreachable!()
        }

        async fn close(&mut self) {
            self.0.fetch_add(1, Ordering::SeqCst);
        }
    }

    struct DuplicateHost(Arc<AtomicUsize>);

    #[async_trait]
    impl HostFactory for DuplicateHost {
        async fn build(&self, _context: RunContext) -> Result<McpHost, McpError> {
            Ok(McpHost::new(vec![
                Box::new(ClosingServer(self.0.clone())),
                Box::new(ClosingServer(self.0.clone())),
            ]))
        }
    }

    #[tokio::test]
    async fn host_is_closed_when_connect_fails() {
        let closed = Arc::new(AtomicUsize::new(0));
        let directory = tempfile::tempdir().unwrap();
        let db = Db::open(":memory:").unwrap();
        let engine = Engine::new(
            Arc::new(Model),
            Arc::new(DuplicateHost(closed.clone())),
            db,
            directory.path().to_owned(),
        );
        let result = engine
            .execute(
                RunRecord {
                    id: "run".to_owned(),
                    task: "task".to_owned(),
                    title: "task".to_owned(),
                    provider: "provider".to_owned(),
                    model: "model".to_owned(),
                },
                None,
                EventSink::new("run", Arc::new(ConnectionManager::new())),
                CancellationToken::new(),
            )
            .await;

        assert!(matches!(
            result,
            Err(super::EngineError::Mcp(McpError::DuplicateNamespace(name))) if name == "duplicate"
        ));
        assert_eq!(closed.load(Ordering::SeqCst), 2);
    }
}
