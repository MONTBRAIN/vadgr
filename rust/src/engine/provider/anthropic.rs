use super::{CatalogModel, MACHINE_INSTRUCTIONS, ModelClient};
use crate::engine::types::{
    ContentBlock, Message, ModelResponse, ProviderError, StopReason, ToolSpec, Usage,
};
use async_trait::async_trait;
use reqwest::{Client, StatusCode};
use serde_json::{Value, json};
use std::time::Duration;

pub const MESSAGES_URL: &str = "https://api.anthropic.com/v1/messages";
pub const MODELS_URL: &str = "https://api.anthropic.com/v1/models?limit=1000";
const VERSION: &str = "2023-06-01";

pub struct AnthropicMessagesClient {
    http: Client,
    api_key: String,
    model: String,
    messages_url: String,
}

impl AnthropicMessagesClient {
    pub fn new(
        model: impl Into<String>,
        api_key: impl Into<String>,
    ) -> Result<Self, ProviderError> {
        Self::with_url(model, api_key, MESSAGES_URL)
    }

    pub fn with_url(
        model: impl Into<String>,
        api_key: impl Into<String>,
        messages_url: impl Into<String>,
    ) -> Result<Self, ProviderError> {
        let api_key = api_key.into();
        if api_key.trim().is_empty() {
            return Err(ProviderError::MissingCredentials);
        }
        Ok(Self {
            http: super::http_client(Duration::from_secs(90))?,
            api_key,
            model: model.into(),
            messages_url: messages_url.into(),
        })
    }

    fn body(&self, messages: &[Message], tools: &[ToolSpec], max_tokens: u32) -> Value {
        let tools = tools
            .iter()
            .map(|tool| {
                json!({
                    "name": tool.name,
                    "description": tool.description,
                    "input_schema": tool.input_schema,
                })
            })
            .collect::<Vec<_>>();
        let mut body = json!({
            "model": self.model,
            "max_tokens": max_tokens,
            "system": MACHINE_INSTRUCTIONS,
            "messages": messages,
        });
        if !tools.is_empty() {
            body["tools"] = Value::Array(tools);
        }
        body
    }

    async fn request(&self, body: &Value) -> Result<Value, ProviderError> {
        let mut attempt = 0u32;
        loop {
            let response = self
                .http
                .post(&self.messages_url)
                .header("x-api-key", &self.api_key)
                .header("anthropic-version", VERSION)
                .header("user-agent", user_agent())
                .json(body)
                .send()
                .await
                .map_err(|error| ProviderError::Request(error.to_string()))?;
            if retryable(response.status()) && attempt < 2 {
                tokio::time::sleep(Duration::from_millis(500u64 << attempt)).await;
                attempt += 1;
                continue;
            }
            if !response.status().is_success() {
                let status = response.status();
                let body = response.json::<Value>().await.ok();
                return Err(classify_error(status, body.as_ref()));
            }
            return super::read_json(response).await;
        }
    }

    fn decode(value: Value) -> Result<ModelResponse, ProviderError> {
        let raw_content = value
            .get("content")
            .and_then(Value::as_array)
            .ok_or_else(|| ProviderError::InvalidResponse("content must be an array".to_owned()))?;
        let mut content = Vec::with_capacity(raw_content.len());
        for block in raw_content {
            content.push(match required_string(block, "type")?.as_str() {
                "text" => ContentBlock::Text {
                    text: required_string(block, "text")?,
                },
                "thinking" => ContentBlock::Thinking {
                    thinking: required_string(block, "thinking")?,
                    signature: required_string(block, "signature")?,
                },
                "redacted_thinking" => ContentBlock::RedactedThinking {
                    data: required_string(block, "data")?,
                },
                "tool_use" => ContentBlock::ToolUse {
                    id: required_string(block, "id")?,
                    name: required_string(block, "name")?,
                    input: block.get("input").cloned().ok_or_else(|| {
                        ProviderError::InvalidResponse("tool_use block has no input".to_owned())
                    })?,
                },
                other => {
                    return Err(ProviderError::InvalidResponse(format!(
                        "unsupported Anthropic content block: {other}"
                    )));
                }
            });
        }
        let usage = value
            .get("usage")
            .ok_or_else(|| ProviderError::InvalidResponse("response has no usage".to_owned()))?;
        Ok(ModelResponse {
            content,
            stop_reason: value
                .get("stop_reason")
                .and_then(Value::as_str)
                .map(StopReason::from_wire),
            usage: Usage {
                input_tokens: required_u64(usage, "input_tokens")?,
                output_tokens: required_u64(usage, "output_tokens")?,
            },
        })
    }
}

#[async_trait]
impl ModelClient for AnthropicMessagesClient {
    async fn complete(
        &self,
        messages: &[Message],
        tools: &[ToolSpec],
        max_tokens: u32,
    ) -> Result<ModelResponse, ProviderError> {
        Self::decode(
            self.request(&self.body(messages, tools, max_tokens))
                .await?,
        )
    }
}

pub async fn discover_models(
    http: &Client,
    api_key: &str,
    url: &str,
) -> Result<Vec<CatalogModel>, ProviderError> {
    let response = super::send_with_retry(
        http.get(url)
            .header("x-api-key", api_key)
            .header("anthropic-version", VERSION)
            .header("user-agent", user_agent()),
    )
    .await?;
    if !response.status().is_success() {
        return Err(classify_status(response.status()));
    }
    let body = super::read_json(response).await?;
    let rows = body
        .get("data")
        .and_then(Value::as_array)
        .ok_or_else(|| ProviderError::InvalidResponse("models data must be an array".to_owned()))?;
    let mut models = rows
        .iter()
        .filter_map(|row| {
            let id = row.get("id")?.as_str()?;
            if !id.starts_with("claude-") {
                return None;
            }
            Some(CatalogModel {
                id: id.to_owned(),
                name: row
                    .get("display_name")
                    .and_then(Value::as_str)
                    .unwrap_or(id)
                    .to_owned(),
            })
        })
        .collect::<Vec<_>>();
    models.sort_by(|left, right| left.id.cmp(&right.id));
    if models.is_empty() {
        return Err(ProviderError::InvalidResponse(
            "Anthropic returned no usable models".to_owned(),
        ));
    }
    Ok(models)
}

fn retryable(status: StatusCode) -> bool {
    status == StatusCode::TOO_MANY_REQUESTS || status.is_server_error()
}

fn classify_status(status: StatusCode) -> ProviderError {
    match status {
        StatusCode::UNAUTHORIZED => ProviderError::Unauthorized,
        StatusCode::FORBIDDEN => ProviderError::Forbidden,
        StatusCode::TOO_MANY_REQUESTS => ProviderError::QuotaExhausted,
        StatusCode::NOT_FOUND => ProviderError::ModelUnavailable,
        status if status.is_server_error() => ProviderError::Unavailable,
        status => ProviderError::Request(format!("Anthropic request failed with HTTP {status}")),
    }
}

fn classify_error(status: StatusCode, body: Option<&Value>) -> ProviderError {
    let provider_type = body
        .and_then(|value| value.pointer("/error/type"))
        .and_then(Value::as_str);
    let message = body
        .and_then(|value| value.pointer("/error/message"))
        .and_then(Value::as_str)
        .unwrap_or_default()
        .to_ascii_lowercase();
    if status == StatusCode::BAD_REQUEST
        && (provider_type == Some("billing_error")
            || (message.contains("credit balance")
                && (message.contains("too low") || message.contains("purchase credits"))))
    {
        return ProviderError::QuotaExhausted;
    }
    classify_status(status)
}

fn user_agent() -> String {
    format!("vadgr/{}", env!("CARGO_PKG_VERSION"))
}

fn required_string(value: &Value, key: &str) -> Result<String, ProviderError> {
    value
        .get(key)
        .and_then(Value::as_str)
        .map(str::to_owned)
        .ok_or_else(|| ProviderError::InvalidResponse(format!("missing string `{key}`")))
}

fn required_u64(value: &Value, key: &str) -> Result<u64, ProviderError> {
    value
        .get(key)
        .and_then(Value::as_u64)
        .ok_or_else(|| ProviderError::InvalidResponse(format!("missing integer `{key}`")))
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::{Map, json};

    fn client() -> AnthropicMessagesClient {
        AnthropicMessagesClient::with_url("claude-test", "key", "http://localhost/messages")
            .unwrap()
    }

    #[test]
    fn request_uses_api_key_identity_and_unmodified_tool_names() {
        let body = client().body(
            &[Message::text("user", "task")],
            &[ToolSpec {
                name: "computer-use__get_platform".to_owned(),
                description: "platform".to_owned(),
                input_schema: Map::new(),
            }],
            512,
        );
        assert_eq!(body["tools"][0]["name"], "computer-use__get_platform");
        assert_eq!(body["max_tokens"], 512);
        assert_eq!(body["system"], MACHINE_INSTRUCTIONS);
        assert!(!body.to_string().contains("Claude Code"));
    }

    #[test]
    fn low_credit_response_is_quota_exhausted() {
        let body = json!({
            "type": "error",
            "error": {
                "type": "invalid_request_error",
                "message": "Your credit balance is too low to access the Anthropic API."
            }
        });
        assert!(matches!(
            classify_error(StatusCode::BAD_REQUEST, Some(&body)),
            ProviderError::QuotaExhausted
        ));
    }

    #[test]
    fn response_maps_text_tools_stop_reason_and_usage() {
        let response = AnthropicMessagesClient::decode(json!({
            "content": [
                {"type":"text", "text":"working"},
                {"type":"tool_use", "id":"call-1", "name":"control__todo_write", "input":{"x":1}}
            ],
            "stop_reason":"tool_use",
            "usage":{"input_tokens":2,"output_tokens":3}
        }))
        .unwrap();
        assert_eq!(response.stop_reason, Some(StopReason::ToolUse));
        assert_eq!(response.usage.input_tokens, 2);
        assert!(matches!(response.content[1], ContentBlock::ToolUse { .. }));
    }
}
