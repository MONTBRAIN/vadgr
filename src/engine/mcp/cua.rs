use super::ToolServer;
use crate::engine::types::{ImageSource, McpError, ToolContent, ToolResult, ToolSpec};
use async_trait::async_trait;
use rmcp::model::{CallToolRequestParams, ContentBlock};
use rmcp::service::RunningService;
use rmcp::transport::{ConfigureCommandExt, TokioChildProcess};
use rmcp::{RoleClient, ServiceExt};
use serde_json::{Map, Value};
use std::path::PathBuf;
use std::process::Stdio;
use std::time::Duration;
use tokio::io::{AsyncBufReadExt, BufReader};
use tokio::task::JoinHandle;

const STDERR_LINE_LIMIT: usize = 4096;
const CLOSE_TIMEOUT: Duration = Duration::from_secs(3);

pub struct CuaServer {
    command: PathBuf,
    client: Option<RunningService<RoleClient, ()>>,
    stderr_task: Option<JoinHandle<()>>,
}

impl CuaServer {
    pub fn new(command: PathBuf) -> Self {
        Self {
            command,
            client: None,
            stderr_task: None,
        }
    }

    async fn connect(&mut self) -> Result<(), McpError> {
        if self.client.is_some() {
            return Ok(());
        }
        let command_path = self.command.clone();
        let command = tokio::process::Command::new(command_path).configure(|command| {
            command.arg("--transport").arg("stdio").kill_on_drop(true);
            configure_windows_process(command);
        });
        let (transport, stderr) = TokioChildProcess::builder(command)
            .stderr(Stdio::piped())
            .spawn()
            .map_err(|error| McpError::Server(error.to_string()))?;
        let stderr =
            stderr.ok_or_else(|| McpError::Server("cua stderr was not piped".to_owned()))?;
        self.stderr_task = Some(tokio::spawn(async move {
            let mut lines = BufReader::new(stderr).lines();
            while let Ok(Some(line)) = lines.next_line().await {
                let line: String = line.chars().take(STDERR_LINE_LIMIT).collect();
                tracing::debug!(server = "computer-use", stderr = line);
            }
        }));
        match ().serve(transport).await {
            Ok(client) => {
                self.client = Some(client);
                Ok(())
            }
            Err(error) => {
                self.finish_stderr().await;
                Err(McpError::Server(error.to_string()))
            }
        }
    }

    async fn finish_stderr(&mut self) {
        if let Some(mut task) = self.stderr_task.take()
            && tokio::time::timeout(CLOSE_TIMEOUT, &mut task)
                .await
                .is_err()
        {
            task.abort();
            let _ = task.await;
        }
    }
}

#[async_trait]
impl ToolServer for CuaServer {
    fn namespace(&self) -> &str {
        "computer-use"
    }

    async fn list_tools(&mut self) -> Result<Vec<ToolSpec>, McpError> {
        self.connect().await?;
        let tools = self
            .client
            .as_ref()
            .expect("connected client")
            .list_all_tools()
            .await
            .map_err(|error| McpError::Server(error.to_string()))?;
        Ok(tools
            .into_iter()
            .map(|tool| ToolSpec {
                name: tool.name.into_owned(),
                description: tool
                    .description
                    .map(|value| value.into_owned())
                    .unwrap_or_default(),
                input_schema: (*tool.input_schema).clone(),
            })
            .collect())
    }

    async fn call_tool(
        &mut self,
        name: &str,
        args: Map<String, Value>,
    ) -> Result<ToolResult, McpError> {
        let client = self
            .client
            .as_ref()
            .ok_or_else(|| McpError::Server("cua is not connected".to_owned()))?;
        let result = client
            .call_tool(CallToolRequestParams::new(name.to_owned()).with_arguments(args))
            .await
            .map_err(|error| McpError::Server(error.to_string()))?;
        let mut content = Vec::with_capacity(result.content.len());
        for block in result.content {
            content.push(match block {
                ContentBlock::Text(text) => ToolContent::Text { text: text.text },
                ContentBlock::Image(image) => ToolContent::Image {
                    source: ImageSource {
                        kind: "base64".to_owned(),
                        media_type: image.mime_type,
                        data: image.data,
                    },
                },
                other => {
                    return Err(McpError::UnsupportedContent(format!("{other:?}")));
                }
            });
        }
        Ok(ToolResult {
            content,
            is_error: result.is_error.unwrap_or(false),
        })
    }

    async fn close(&mut self) {
        if let Some(mut client) = self.client.take() {
            match client.close_with_timeout(CLOSE_TIMEOUT).await {
                Ok(Some(_)) => {}
                Ok(None) => tracing::warn!(server = "computer-use", "cua close timed out"),
                Err(error) => tracing::warn!(server = "computer-use", %error, "cua close failed"),
            }
        }
        self.finish_stderr().await;
    }
}

#[cfg(windows)]
fn configure_windows_process(command: &mut tokio::process::Command) {
    const CREATE_NO_WINDOW: u32 = 0x08000000;
    command.creation_flags(CREATE_NO_WINDOW);
}

#[cfg(not(windows))]
fn configure_windows_process(_command: &mut tokio::process::Command) {}
