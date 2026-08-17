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
                    "parameters": gemini_schema(&Value::Object(tool.input_schema.clone())),
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
            if !response.status().is_success() {
                // Read the body before deciding anything. A Gemini 429 carries
                // the difference between a per-minute pace limit and a spent
                // daily quota in the body, and a bad API key arrives as a 400,
                // not a 401; the status alone misreports both.
                let status = response.status();
                let retry_after = super::retry_after_seconds(response.headers());
                let body = response.json::<Value>().await.ok();
                let error = classify_error(status, body.as_ref());
                if retryable(&error) && attempt < super::MAX_RETRIES {
                    let wait = retry_after
                        .or_else(|| retry_delay_seconds(body.as_ref()))
                        .unwrap_or_else(|| super::backoff_seconds(attempt));
                    tokio::time::sleep(Duration::from_secs(wait)).await;
                    attempt += 1;
                    continue;
                }
                return Err(error);
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
                    provider_signature: part
                        .get("thoughtSignature")
                        .and_then(Value::as_str)
                        .map(str::to_owned),
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
        // Same rule as the model call: read the body, then classify.
        let status = response.status();
        let body = response.json::<Value>().await.ok();
        return Err(classify_error(status, body.as_ref()));
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
                                let mut part = json!({"functionCall":{
                                    "id":id,
                                    "name":name,
                                    "args":block.get("input").cloned().unwrap_or_else(|| json!({}))
                                }});
                                if let Some(signature) =
                                    block.get("provider_signature").and_then(Value::as_str)
                                {
                                    part["thoughtSignature"] = Value::String(signature.to_owned());
                                }
                                parts.push(part);
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
                            // An image in a tool result is a typed
                            // `inlineData` part on the function response, per
                            // the service's multimodal function-response
                            // shape. Embedding the raw block would send the
                            // screenshot as base64 text the model cannot see.
                            let mut texts = Vec::new();
                            let mut media = Vec::new();
                            match block.get("content") {
                                Some(Value::Array(items)) => {
                                    for item in items {
                                        match item.get("type").and_then(Value::as_str) {
                                            Some("text") => {
                                                if let Some(text) =
                                                    item.get("text").and_then(Value::as_str)
                                                {
                                                    texts.push(text.to_owned());
                                                }
                                            }
                                            Some("image") => {
                                                if let Some(source) = item.get("source") {
                                                    media.push(json!({"inlineData":{
                                                        "mimeType":source.get("media_type").and_then(Value::as_str).unwrap_or("image/png"),
                                                        "data":source.get("data").and_then(Value::as_str).unwrap_or("")
                                                    }}));
                                                }
                                            }
                                            _ => {}
                                        }
                                    }
                                }
                                Some(Value::String(text)) => texts.push(text.clone()),
                                _ => {}
                            }
                            let mut part = json!({"functionResponse":{
                                "id":id,
                                "name":name,
                                "response":{"result":texts.join("\n")}
                            }});
                            if !media.is_empty() {
                                part["functionResponse"]["parts"] = Value::Array(media);
                            }
                            parts.push(part);
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

fn gemini_schema(value: &Value) -> Value {
    match value {
        Value::Object(fields) => {
            let mut normalized = fields
                .iter()
                .filter(|(name, _)| name.as_str() != "additionalProperties")
                .map(|(name, value)| (name.clone(), gemini_schema(value)))
                .collect::<Map<String, Value>>();
            if normalized.get("type").and_then(Value::as_str) == Some("array")
                && !normalized.contains_key("items")
            {
                normalized.insert("items".to_owned(), Value::Object(Map::new()));
            }
            Value::Object(normalized)
        }
        Value::Array(values) => Value::Array(values.iter().map(gemini_schema).collect()),
        _ => value.clone(),
    }
}

fn retryable(error: &ProviderError) -> bool {
    // Waiting helps a pace limit and a server fault. It cannot help a spent
    // daily quota, a rejected key or a request the service will refuse again,
    // so those return at once rather than spending two more calls.
    matches!(
        error,
        ProviderError::RateLimited | ProviderError::Unavailable
    )
}

fn error_details(body: Option<&Value>) -> &[Value] {
    body.and_then(|value| value.pointer("/error/details"))
        .and_then(Value::as_array)
        .map(Vec::as_slice)
        .unwrap_or_default()
}

fn error_reason(body: Option<&Value>) -> Option<&str> {
    error_details(body)
        .iter()
        .find_map(|detail| detail.get("reason").and_then(Value::as_str))
}

/// Whether the 429 names a per-day quota. A day does not clear inside a retry
/// window, so it is exhaustion; every other 429 on this service is pace.
fn daily_quota_exhausted(body: Option<&Value>) -> bool {
    error_details(body).iter().any(|detail| {
        detail
            .get("violations")
            .and_then(Value::as_array)
            .is_some_and(|violations| {
                violations.iter().any(|violation| {
                    violation
                        .get("quotaId")
                        .and_then(Value::as_str)
                        .is_some_and(|id| id.contains("PerDay"))
                })
            })
    })
}

/// The wait the service itself asks for, from the `RetryInfo` detail
/// (`"retryDelay": "58s"`), bounded the same way as a `retry-after` header.
fn retry_delay_seconds(body: Option<&Value>) -> Option<u64> {
    error_details(body)
        .iter()
        .find_map(|detail| detail.get("retryDelay").and_then(Value::as_str))
        .and_then(|value| value.trim().trim_end_matches('s').parse::<f64>().ok())
        .filter(|value| *value >= 0.0)
        .map(|value| (value.ceil() as u64).min(60))
}

fn classify_error(status: StatusCode, body: Option<&Value>) -> ProviderError {
    // A rejected key is a 400 INVALID_ARGUMENT with reason API_KEY_INVALID on
    // this service, not a 401. Reporting it as a generic request failure sent
    // the owner to an outage page for a mistyped key.
    if status == StatusCode::BAD_REQUEST && error_reason(body) == Some("API_KEY_INVALID") {
        return ProviderError::Unauthorized;
    }
    match status {
        StatusCode::UNAUTHORIZED => ProviderError::Unauthorized,
        StatusCode::FORBIDDEN => ProviderError::Forbidden,
        StatusCode::TOO_MANY_REQUESTS => {
            if daily_quota_exhausted(body) {
                ProviderError::QuotaExhausted
            } else {
                ProviderError::RateLimited
            }
        }
        StatusCode::NOT_FOUND => ProviderError::ModelUnavailable,
        status if status.is_server_error() => ProviderError::Unavailable,
        status => {
            let detail = error_reason(body).or_else(|| {
                body.and_then(|value| value.pointer("/error/status"))
                    .and_then(Value::as_str)
            });
            ProviderError::Request(match detail {
                // Keep the provider's own code. It is the difference between a
                // report an owner can act on and one that sends them hunting.
                Some(code) => format!("Gemini request failed with HTTP {status} ({code})"),
                None => format!("Gemini request failed with HTTP {status}"),
            })
        }
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
                content: json!([{"type":"tool_use","id":"call-1","name":"test__act","input":{"n":1},"provider_signature":"signed"}]),
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
        assert_eq!(
            body["contents"][1]["parts"][0]["thoughtSignature"],
            "signed"
        );
    }

    #[test]
    fn an_image_tool_result_is_typed_inline_data_never_base64_text() {
        let messages = vec![
            Message {
                role: "assistant".to_owned(),
                content: json!([{"type":"tool_use","id":"call-1","name":"test__screenshot","input":{}}]),
            },
            Message {
                role: "user".to_owned(),
                content: json!([{"type":"tool_result","tool_use_id":"call-1","content":[
                    {"type":"text","text":"captured"},
                    {"type":"image","source":{"type":"base64","media_type":"image/png","data":"aWizaW1hZ2U"}}
                ]}]),
            },
        ];
        let body = client().body(&messages, &[], 512);
        let response = &body["contents"][1]["parts"][0]["functionResponse"];
        assert_eq!(response["response"]["result"], "captured");
        assert_eq!(response["parts"][0]["inlineData"]["mimeType"], "image/png");
        assert_eq!(response["parts"][0]["inlineData"]["data"], "aWizaW1hZ2U");
        assert!(!response["response"].to_string().contains("aWizaW1hZ2U"));
    }

    #[test]
    fn a_rejected_key_is_unauthorized_even_as_a_400() {
        let body = json!({"error":{
            "code":400,
            "message":"API key not valid. Please pass a valid API key.",
            "status":"INVALID_ARGUMENT",
            "details":[{"@type":"type.googleapis.com/google.rpc.ErrorInfo","reason":"API_KEY_INVALID"}]
        }});
        assert!(matches!(
            classify_error(StatusCode::BAD_REQUEST, Some(&body)),
            ProviderError::Unauthorized
        ));
    }

    #[test]
    fn a_429_is_pace_unless_the_body_names_a_daily_quota() {
        let pace = json!({"error":{"code":429,"status":"RESOURCE_EXHAUSTED","details":[
            {"@type":"type.googleapis.com/google.rpc.QuotaFailure","violations":[
                {"quotaId":"GenerateRequestsPerMinutePerProjectPerModel"}]},
            {"@type":"type.googleapis.com/google.rpc.RetryInfo","retryDelay":"7s"}
        ]}});
        assert!(matches!(
            classify_error(StatusCode::TOO_MANY_REQUESTS, Some(&pace)),
            ProviderError::RateLimited
        ));
        assert_eq!(retry_delay_seconds(Some(&pace)), Some(7));

        let daily = json!({"error":{"code":429,"status":"RESOURCE_EXHAUSTED","details":[
            {"@type":"type.googleapis.com/google.rpc.QuotaFailure","violations":[
                {"quotaId":"GenerateRequestsPerDayPerProjectPerModel-FreeTier"}]}
        ]}});
        assert!(matches!(
            classify_error(StatusCode::TOO_MANY_REQUESTS, Some(&daily)),
            ProviderError::QuotaExhausted
        ));
        assert!(matches!(
            classify_error(StatusCode::TOO_MANY_REQUESTS, None),
            ProviderError::RateLimited
        ));
    }

    #[test]
    fn request_removes_json_schema_fields_gemini_does_not_accept() {
        let body = client().body(
            &[Message::text("user", "task")],
            &[ToolSpec {
                name: "test__act".to_owned(),
                description: "act".to_owned(),
                input_schema: serde_json::from_value(json!({
                    "type": "object",
                    "properties": {
                        "headers": {
                            "type": "object",
                            "additionalProperties": {"type": "string"}
                        },
                        "options": {"type": "array"}
                    },
                    "additionalProperties": false
                }))
                .unwrap(),
            }],
            512,
        );
        let parameters = &body["tools"][0]["functionDeclarations"][0]["parameters"];
        assert!(parameters.get("additionalProperties").is_none());
        assert!(
            parameters["properties"]["headers"]
                .get("additionalProperties")
                .is_none()
        );
        assert_eq!(parameters["properties"]["options"]["items"], json!({}));
    }

    #[test]
    fn response_maps_function_calls_and_usage() {
        let response = GeminiClient::decode(json!({
            "candidates":[{"content":{"parts":[{"functionCall":{"id":"c1","name":"test__act","args":{"n":1}},"thoughtSignature":"signed"}]},"finishReason":"STOP"}],
            "usageMetadata":{"promptTokenCount":2,"candidatesTokenCount":3}
        })).unwrap();
        assert_eq!(response.stop_reason, Some(StopReason::ToolUse));
        assert_eq!(response.usage.output_tokens, 3);
        assert!(matches!(
            &response.content[0],
            ContentBlock::ToolUse {
                provider_signature: Some(signature),
                ..
            } if signature == "signed"
        ));
    }
}
