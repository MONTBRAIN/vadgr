pub mod cua;

use crate::computer_use_setup::SetupService;
use crate::engine::control::{ControlPlaneServer, RunContext};
use crate::engine::policy::{DefaultPolicy, PolicyHook};
use crate::engine::types::{McpError, ToolResult, ToolSpec};
use async_trait::async_trait;
use serde_json::{Map, Value};
use std::collections::{BTreeMap, HashMap};
use std::sync::Arc;

pub const NAMESPACE_SEPARATOR: &str = "__";

#[async_trait]
pub trait ToolServer: Send {
    fn namespace(&self) -> &str;
    async fn list_tools(&mut self) -> Result<Vec<ToolSpec>, McpError>;
    async fn call_tool(
        &mut self,
        name: &str,
        args: Map<String, Value>,
    ) -> Result<ToolResult, McpError>;
    async fn close(&mut self);
}

#[async_trait]
pub trait HostFactory: Send + Sync {
    async fn build(&self, context: RunContext) -> Result<McpHost, McpError>;
}

pub struct DefaultHostFactory {
    setup: Arc<SetupService>,
    policy: Arc<dyn PolicyHook>,
}

impl DefaultHostFactory {
    pub fn new(setup: Arc<SetupService>) -> Self {
        Self {
            setup,
            policy: Arc::new(DefaultPolicy::default()),
        }
    }
}

#[async_trait]
impl HostFactory for DefaultHostFactory {
    async fn build(&self, context: RunContext) -> Result<McpHost, McpError> {
        let entry = self
            .setup
            .entry()
            .map_err(|error| McpError::Server(error.to_string()))?;
        let mut servers: Vec<Box<dyn ToolServer>> = vec![Box::new(ControlPlaneServer::new(
            context,
            self.policy.clone(),
        ))];
        if entry.enabled {
            match entry.command {
                Some(command) => servers.push(Box::new(cua::CuaServer::new(command))),
                None => servers.push(Box::new(UnavailableServer::new(
                    "computer-use",
                    "vadgr-cua was not found",
                ))),
            }
        }
        Ok(McpHost::new(servers))
    }
}

struct UnavailableServer {
    namespace: String,
    reason: String,
}

impl UnavailableServer {
    fn new(namespace: &str, reason: &str) -> Self {
        Self {
            namespace: namespace.to_owned(),
            reason: reason.to_owned(),
        }
    }
}

#[async_trait]
impl ToolServer for UnavailableServer {
    fn namespace(&self) -> &str {
        &self.namespace
    }

    async fn list_tools(&mut self) -> Result<Vec<ToolSpec>, McpError> {
        Err(McpError::Server(self.reason.clone()))
    }

    async fn call_tool(
        &mut self,
        _name: &str,
        _args: Map<String, Value>,
    ) -> Result<ToolResult, McpError> {
        Err(McpError::Server(self.reason.clone()))
    }

    async fn close(&mut self) {}
}

pub struct McpHost {
    servers: Vec<Box<dyn ToolServer>>,
    by_namespace: HashMap<String, usize>,
    tools: Vec<ToolSpec>,
    failed: BTreeMap<String, String>,
}

impl McpHost {
    pub fn new(servers: Vec<Box<dyn ToolServer>>) -> Self {
        Self {
            servers,
            by_namespace: HashMap::new(),
            tools: Vec::new(),
            failed: BTreeMap::new(),
        }
    }

    pub async fn connect(&mut self) -> Result<(), McpError> {
        let mut declared = HashMap::new();
        for (index, server) in self.servers.iter().enumerate() {
            let namespace = server.namespace().to_owned();
            if declared.insert(namespace.clone(), index).is_some() {
                return Err(McpError::DuplicateNamespace(namespace));
            }
        }

        self.by_namespace.clear();
        self.tools.clear();
        self.failed.clear();
        for index in 0..self.servers.len() {
            let namespace = self.servers[index].namespace().to_owned();
            match self.servers[index].list_tools().await {
                Ok(specs) => {
                    self.by_namespace.insert(namespace.clone(), index);
                    self.tools.extend(specs.into_iter().map(|mut tool| {
                        tool.name = format!("{namespace}{NAMESPACE_SEPARATOR}{}", tool.name);
                        tool
                    }));
                }
                Err(error) => {
                    let reason = error.to_string();
                    tracing::warn!(server = namespace, reason, "MCP server was dropped");
                    self.failed.insert(namespace, reason);
                }
            }
        }
        Ok(())
    }

    pub fn tools(&self) -> &[ToolSpec] {
        &self.tools
    }

    pub fn failed(&self) -> &BTreeMap<String, String> {
        &self.failed
    }

    pub async fn dispatch(
        &mut self,
        namespaced_name: &str,
        args: Map<String, Value>,
    ) -> Result<ToolResult, McpError> {
        let (namespace, name) = namespaced_name
            .split_once(NAMESPACE_SEPARATOR)
            .ok_or_else(|| McpError::UnknownTool(namespaced_name.to_owned()))?;
        let index = self
            .by_namespace
            .get(namespace)
            .copied()
            .ok_or_else(|| McpError::UnknownTool(namespaced_name.to_owned()))?;
        self.servers[index].call_tool(name, args).await
    }

    pub async fn close(&mut self) {
        for server in &mut self.servers {
            server.close().await;
        }
    }
}

impl Drop for McpHost {
    fn drop(&mut self) {
        if !self.servers.is_empty() {
            tracing::debug!("MCP host dropped; server transports use kill-on-drop cleanup");
        }
    }
}

#[cfg(test)]
mod tests {
    use super::{McpHost, ToolServer};
    use crate::engine::types::{McpError, ToolResult, ToolSpec};
    use async_trait::async_trait;
    use serde_json::{Map, Value, json};

    struct FakeServer {
        namespace: String,
        tools: Vec<&'static str>,
        fail: bool,
    }

    #[async_trait]
    impl ToolServer for FakeServer {
        fn namespace(&self) -> &str {
            &self.namespace
        }

        async fn list_tools(&mut self) -> Result<Vec<ToolSpec>, McpError> {
            if self.fail {
                return Err(McpError::Server("offline".to_owned()));
            }
            Ok(self
                .tools
                .iter()
                .map(|name| ToolSpec {
                    name: (*name).to_owned(),
                    description: String::new(),
                    input_schema: Map::new(),
                })
                .collect())
        }

        async fn call_tool(
            &mut self,
            name: &str,
            args: Map<String, Value>,
        ) -> Result<ToolResult, McpError> {
            Ok(ToolResult::text(
                json!({"tool": name, "args": args}).to_string(),
            ))
        }

        async fn close(&mut self) {}
    }

    fn server(namespace: &str, tools: Vec<&'static str>) -> Box<dyn ToolServer> {
        Box::new(FakeServer {
            namespace: namespace.to_owned(),
            tools,
            fail: false,
        })
    }

    #[tokio::test]
    async fn order_is_declaration_then_server_order_and_routing_is_exact() {
        for _ in 0..3 {
            let mut host = McpHost::new(vec![
                server("control", vec!["first", "second"]),
                server("computer-use", vec!["third"]),
            ]);
            host.connect().await.unwrap();
            assert_eq!(
                host.tools()
                    .iter()
                    .map(|tool| tool.name.as_str())
                    .collect::<Vec<_>>(),
                ["control__first", "control__second", "computer-use__third"]
            );
            let result = host
                .dispatch("computer-use__third", Map::new())
                .await
                .unwrap();
            assert!(!result.is_error);
        }
    }

    #[tokio::test]
    async fn failed_server_does_not_remove_healthy_server() {
        let mut host = McpHost::new(vec![
            Box::new(FakeServer {
                namespace: "bad".to_owned(),
                tools: vec![],
                fail: true,
            }),
            server("good", vec!["tool"]),
        ]);
        host.connect().await.unwrap();
        assert!(host.failed().contains_key("bad"));
        assert_eq!(host.tools()[0].name, "good__tool");
    }

    #[tokio::test]
    async fn duplicate_namespace_is_rejected_before_start() {
        let mut host = McpHost::new(vec![server("same", vec![]), server("same", vec![])]);
        assert!(matches!(
            host.connect().await,
            Err(McpError::DuplicateNamespace(name)) if name == "same"
        ));
    }
}
