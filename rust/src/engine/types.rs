use serde::{Deserialize, Serialize};
use serde_json::{Map, Value};
use std::fmt;

pub type RunId = String;

#[derive(Clone, Debug, Default, Eq, PartialEq, Serialize, Deserialize)]
pub struct Usage {
    pub input_tokens: u64,
    pub output_tokens: u64,
}

impl std::ops::AddAssign<&Usage> for Usage {
    fn add_assign(&mut self, other: &Usage) {
        self.input_tokens += other.input_tokens;
        self.output_tokens += other.output_tokens;
    }
}

#[derive(Clone, Debug, Eq, PartialEq)]
pub enum StopReason {
    ToolUse,
    EndTurn,
    MaxTokens,
    Unknown(String),
}

impl StopReason {
    pub fn from_wire(value: &str) -> Self {
        match value {
            "tool_use" => Self::ToolUse,
            "end_turn" => Self::EndTurn,
            "max_tokens" => Self::MaxTokens,
            other => Self::Unknown(other.to_owned()),
        }
    }
}

#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
#[serde(tag = "type", rename_all = "snake_case")]
pub enum ContentBlock {
    Text {
        text: String,
    },
    Thinking {
        thinking: String,
        signature: String,
    },
    RedactedThinking {
        data: String,
    },
    ToolUse {
        id: String,
        name: String,
        input: Value,
    },
}

#[derive(Clone, Debug, PartialEq)]
pub struct ModelResponse {
    pub content: Vec<ContentBlock>,
    pub stop_reason: Option<StopReason>,
    pub usage: Usage,
}

#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
pub struct Message {
    pub role: String,
    pub content: Value,
}

impl Message {
    pub fn text(role: &str, text: impl Into<String>) -> Self {
        Self {
            role: role.to_owned(),
            content: Value::String(text.into()),
        }
    }
}

#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
pub struct ToolSpec {
    pub name: String,
    pub description: String,
    pub input_schema: Map<String, Value>,
}

#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
#[serde(tag = "type", rename_all = "snake_case")]
pub enum ToolContent {
    Text { text: String },
    Image { source: ImageSource },
}

#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
pub struct ImageSource {
    #[serde(rename = "type")]
    pub kind: String,
    pub media_type: String,
    pub data: String,
}

#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
pub struct ToolResult {
    pub content: Vec<ToolContent>,
    #[serde(default)]
    pub is_error: bool,
}

impl ToolResult {
    pub fn text(text: impl Into<String>) -> Self {
        Self {
            content: vec![ToolContent::Text { text: text.into() }],
            is_error: false,
        }
    }

    pub fn error(text: impl Into<String>) -> Self {
        Self {
            content: vec![ToolContent::Text { text: text.into() }],
            is_error: true,
        }
    }
}

#[derive(Clone, Debug, PartialEq)]
pub struct RunRecord {
    pub id: RunId,
    pub task: String,
    pub title: String,
    pub provider: String,
    pub model: String,
}

#[derive(Clone, Debug, PartialEq)]
pub struct RunResult {
    pub final_text: String,
    pub iterations: u32,
    pub usage: Usage,
}

#[derive(Clone, Copy, Debug)]
pub struct LoopLimits {
    pub max_iterations: u32,
    pub max_tokens: u32,
    pub keep_last_images: usize,
}

impl Default for LoopLimits {
    fn default() -> Self {
        Self {
            max_iterations: 100,
            max_tokens: 8192,
            keep_last_images: 3,
        }
    }
}

#[derive(Debug, thiserror::Error)]
pub enum ProviderError {
    #[error("credentials are missing; run `claude setup-token`")]
    MissingCredentials,
    #[error("credentials are malformed: {0}")]
    InvalidCredentials(String),
    #[error("credential store failed: {0}")]
    CredentialStore(String),
    #[error("Anthropic rejected the credentials (401); run `claude setup-token`")]
    Unauthorized,
    #[error("Anthropic validator rejected the request (403)")]
    ValidatorRejected,
    #[error("provider request failed: {0}")]
    Request(String),
    #[error("provider response is invalid: {0}")]
    InvalidResponse(String),
    #[error("unknown native provider: {0}")]
    UnknownProvider(String),
}

#[derive(Debug, thiserror::Error)]
pub enum McpError {
    #[error("MCP server `{0}` is configured twice")]
    DuplicateNamespace(String),
    #[error("unknown tool: {0}")]
    UnknownTool(String),
    #[error("MCP server failed: {0}")]
    Server(String),
    #[error("unsupported MCP content: {0}")]
    UnsupportedContent(String),
}

#[derive(Debug, thiserror::Error)]
pub enum EngineError {
    #[error(transparent)]
    Provider(#[from] ProviderError),
    #[error(transparent)]
    Mcp(#[from] McpError),
    #[error("journal failed: {0}")]
    Journal(String),
    #[error("run was cancelled")]
    Cancelled,
    #[error("agent did not finish in {0} iterations")]
    MaxIterations(u32),
    #[error("provider response was truncated at max_tokens")]
    MaxTokens,
    #[error("provider returned tool_use without a valid tool call")]
    MalformedToolUse,
    #[error("provider returned no valid terminal stop reason")]
    InvalidTerminal,
    #[error("NO_ACTION_TAKEN")]
    NoActionTaken,
}

impl fmt::Display for StopReason {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            Self::ToolUse => f.write_str("tool_use"),
            Self::EndTurn => f.write_str("end_turn"),
            Self::MaxTokens => f.write_str("max_tokens"),
            Self::Unknown(value) => f.write_str(value),
        }
    }
}
