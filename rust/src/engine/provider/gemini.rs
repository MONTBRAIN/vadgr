use super::{CatalogModel, MACHINE_INSTRUCTIONS, ModelClient};
use crate::engine::types::{
    ContentBlock, Message, ModelResponse, ProviderError, StopReason, ToolSpec, Usage,
};
use async_trait::async_trait;
use reqwest::{Client, StatusCode};
use serde_json::{Map, Value, json};
use std::collections::HashMap;
use std::time::Duration;

pub const API_ROOT: &str = "https://generativelanguage.googleapis.com/v1beta";
pub const MODELS_URL: &str =
    "https://generativelanguage.googleapis.com/v1beta/models?pageSize=1000";

pub struct GeminiClient {
    http: Client,
    api_key: String,
    model: String,
    api_root: String,
}

impl GeminiClient {
    pub fn with_root(
        model: impl Into<String>,
        api_key: impl Into<String>,
        api_root: impl Into<String>,
    ) -> Result<Self, ProviderError> {
        let api_key = api_key.into();
        if api_key.trim().is_empty() {
            return Err(ProviderError::MissingCredentials);
        }
        Ok(Self {
            http: super::http_client(Duration::from_secs(90))?,
            api_key,
            model: model.into(),
            api_root: api_root.into().trim_end_matches('/').to_owned(),
        })
    }

    fn body(&self, messages: &[Message], tools: &[ToolSpec], max_tokens: u32) -> Value {
        let contents = convert_messages(messages);
        let declarations = tools
            .iter()
            .map(|tool| {
                json!({
                    "name": tool.name,
                    "description": tool.description,
                    "parameters": tool.input_schema,
                })
            })
            .collect::<Vec<_>>();
        let mut body = json!({
            "systemInstruction": {"parts":[{"text":MACHINE_INSTRUCTIONS}]},
            "contents": contents,
            "generationConfig": {"maxOutputTokens": max_tokens},
        });
        if !declarations.is_empty() {
            body["tools"] = json!([{"functionDeclarations": declarations}]);
        }
        body
    }

    async fn request(&self, body: &Value) -> Result<Value, ProviderError> {
        let url = format!(
            "{}/models/{}:generateContent",
            self.api_root,
            self.model.trim_start_matches("models/")
        );
        let mut attempt = 0u32;
        loop {
            let response = self
                .http
                .post(&url)
                .header("x-goog-api-key", &self.api_key)
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
                return Err(classify_status(response.status()));
            }
            return super::read_json(response).await;
        }
    }

    fn decode(value: Value) -> Result<ModelResponse, ProviderError> {
        let candidate = value
            .get("candidates")
            .and_then(Value::as_array)
            .and_then(|values| values.first())
            .ok_or_else(|| {
                ProviderError::InvalidResponse("response has no candidate".to_owned())
            })?;
        let parts = candidate
            .pointer("/content/parts")
            .and_then(Value::as_array)
            .ok_or_else(|| ProviderError::InvalidResponse("candidate has no parts".to_owned()))?;
        let mut content = Vec::new();
        for part in parts {
            if let Some(text) = part.get("text").and_then(Value::as_str) {
                content.push(ContentBlock::Text {
                    text: text.to_owned(),
                });
            }
            if let Some(call) = part.get("functionCall") {
                content.push(ContentBlock::ToolUse {
                    id: call
                        .get("id")
                        .and_then(Value::as_str)
                        .map(str::to_owned)
                        .unwrap_or_else(|| format!("gemini_{}", uuid::Uuid::new_v4())),
                    name: required_string(call, "name")?,
                    input: call
                        .get("args")
                        .cloned()
                        .unwrap_or_else(|| Value::Object(Map::new())),
                });
            }
        }
        let finish_reason = candidate
            .get("finishReason")
            .and_then(Value::as_str)
            .unwrap_or("STOP");
        let stop_reason = if content
            .iter()
            .any(|block| matches!(block, ContentBlock::ToolUse { .. }))
        {
            StopReason::ToolUse
        } else if finish_reason == "MAX_TOKENS" {
            StopReason::MaxTokens
        } else {
            StopReason::EndTurn
        };
        let usage = value.get("usageMetadata").ok_or_else(|| {
            ProviderError::InvalidResponse("response has no usage metadata".to_owned())
        })?;
        Ok(ModelResponse {
            content,
            stop_reason: Some(stop_reason),
            usage: Usage {
                input_tokens: required_u64(usage, "promptTokenCount")?,
                output_tokens: required_u64(usage, "candidatesTokenCount")?,
            },
        })
    }
}

#[async_trait]
impl ModelClient for GeminiClient {
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
            .header("x-goog-api-key", api_key)
            .header("user-agent", user_agent()),
    )
    .await?;
    if !response.status().is_success() {
        return Err(classify_status(response.status()));
    }
    let body = super::read_json(response).await?;
    let rows = body
        .get("models")
        .and_then(Value::as_array)
        .ok_or_else(|| ProviderError::InvalidResponse("models must be an array".to_owned()))?;
    let mut models = rows
        .iter()
        .filter_map(|row| {
            let methods = row.get("supportedGenerationMethods")?.as_array()?;
            if !methods
                .iter()
                .any(|method| method.as_str() == Some("generateContent"))
            {
                return None;
            }
            let id = row.get("name")?.as_str()?.trim_start_matches("models/");
            let lowered = id.to_ascii_lowercase();
            if ["embedding", "image", "tts", "aqa"]
                .iter()
                .any(|part| lowered.contains(part))
            {
                return None;
            }
            Some(CatalogModel {
                id: id.to_owned(),
                name: row
                    .get("displayName")
                    .and_then(Value::as_str)
                    .unwrap_or(id)
                    .to_owned(),
            })
        })
        .collect::<Vec<_>>();
    models.sort_by(|left, right| left.id.cmp(&right.id));
    if models.is_empty() {
        return Err(ProviderError::InvalidResponse(
            "Gemini returned no usable models".to_owned(),
        ));
    }
    Ok(models)
}

fn convert_messages(messages: &[Message]) -> Vec<Value> {
    let mut call_names = HashMap::<String, String>::new();
    let mut converted = Vec::with_capacity(messages.len());
    for message in messages {
        let mut parts = Vec::new();
        match &message.content {
            Value::String(text) => parts.push(json!({"text":text})),
            Value::Array(blocks) => {
                for block in blocks {
                    match block.get("type").and_then(Value::as_str) {
                        Some("text") => {
                            if let Some(text) = block.get("text").and_then(Value::as_str) {
                                parts.push(json!({"text":text}));
                            }
                        }
                        Some("image") => {
                            if let Some(source) = block.get("source") {
                                parts.push(json!({"inlineData":{
                                    "mimeType":source.get("media_type").and_then(Value::as_str).unwrap_or("image/png"),
                                    "data":source.get("data").and_then(Value::as_str).unwrap_or("")
                                }}));
                            }
                        }
                        Some("tool_use") => {
                            let id = block.get("id").and_then(Value::as_str).unwrap_or("");
                            let name = block.get("name").and_then(Value::as_str).unwrap_or("");
                            if !id.is_empty() && !name.is_empty() {
                                call_names.insert(id.to_owned(), name.to_owned());
                                parts.push(json!({"functionCall":{
                                    "id":id,
                                    "name":name,
                                    "args":block.get("input").cloned().unwrap_or_else(|| json!({}))
                                }}));
                            }
                        }
                        Some("tool_result") => {
                            let id = block
                                .get("tool_use_id")
                                .and_then(Value::as_str)
                                .unwrap_or("");
                            let name = call_names
                                .get(id)
                                .cloned()
                                .unwrap_or_else(|| "tool".to_owned());
                            parts.push(json!({"functionResponse":{
                                "id":id,
                                "name":name,
                                "response":{"result":block.get("content").cloned().unwrap_or(Value::Null)}
                            }}));
                        }
                        _ => {}
                    }
                }
            }
            _ => {}
        }
        if !parts.is_empty() {
            converted.push(json!({
                "role": if message.role == "assistant" { "model" } else { "user" },
                "parts": parts,
            }));
        }
    }
    converted
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
        status => ProviderError::Request(format!("Gemini request failed with HTTP {status}")),
    }
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
    use serde_json::Map;

    fn client() -> GeminiClient {
        GeminiClient::with_root("gemini-test", "key", "http://localhost/v1beta").unwrap()
    }

    #[test]
    fn request_converts_tools_and_tool_results() {
        let messages = vec![
            Message::text("user", "task"),
            Message {
                role: "assistant".to_owned(),
                content: json!([{"type":"tool_use","id":"call-1","name":"test__act","input":{"n":1}}]),
            },
            Message {
                role: "user".to_owned(),
                content: json!([{"type":"tool_result","tool_use_id":"call-1","content":[{"type":"text","text":"done"}]}]),
            },
        ];
        let body = client().body(
            &messages,
            &[ToolSpec {
                name: "test__act".to_owned(),
                description: "act".to_owned(),
                input_schema: Map::new(),
            }],
            512,
        );
        assert_eq!(
            body["tools"][0]["functionDeclarations"][0]["name"],
            "test__act"
        );
        assert_eq!(
            body["contents"][2]["parts"][0]["functionResponse"]["name"],
            "test__act"
        );
    }

    #[test]
    fn response_maps_function_calls_and_usage() {
        let response = GeminiClient::decode(json!({
            "candidates":[{"content":{"parts":[{"functionCall":{"id":"c1","name":"test__act","args":{"n":1}}}]},"finishReason":"STOP"}],
            "usageMetadata":{"promptTokenCount":2,"candidatesTokenCount":3}
        })).unwrap();
        assert_eq!(response.stop_reason, Some(StopReason::ToolUse));
        assert_eq!(response.usage.output_tokens, 3);
    }
}
