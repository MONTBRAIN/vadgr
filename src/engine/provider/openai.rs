use super::oauth::OAuthDescriptor;
use super::{CatalogModel, MACHINE_INSTRUCTIONS, ModelClient};
use crate::engine::types::{
    ContentBlock, Message, ModelResponse, ProviderError, StopReason, ToolSpec, Usage,
};
use async_trait::async_trait;
use base64::Engine;
use base64::engine::general_purpose::URL_SAFE_NO_PAD;
use reqwest::{Client, StatusCode};
use serde_json::{Value, json};
use std::time::Duration;

const RESPONSE_BODY_LIMIT: usize = 16 * 1024 * 1024;

pub const PLATFORM_RESPONSES_URL: &str = "https://api.openai.com/v1/responses";
pub const PLATFORM_MODELS_URL: &str = "https://api.openai.com/v1/models";
pub const CHATGPT_RESPONSES_URL: &str = "https://chatgpt.com/backend-api/codex/responses";
pub const CHATGPT_MODELS_URL: &str = "https://chatgpt.com/backend-api/codex/models";
const CHATGPT_CATALOG_CLIENT_VERSION: &str = "0.147.0";
pub const OPENAI_OAUTH: OAuthDescriptor = OAuthDescriptor {
    authorize_url: "https://auth.openai.com/oauth/authorize",
    token_url: "https://auth.openai.com/oauth/token",
    client_id: "app_EMoamEEZ73f0CkXaXp7hrann",
    redirect_uri: "http://localhost:1455/auth/callback",
    scopes: &["openid", "profile", "email", "offline_access"],
    authorize_parameters: &[
        ("id_token_add_organizations", "true"),
        ("codex_cli_simplified_flow", "true"),
        ("originator", "vadgr"),
    ],
};

#[derive(Clone)]
pub enum OpenAiAuth {
    ApiKey(String),
    ChatGpt {
        access_token: String,
        account_id: String,
    },
}

pub struct OpenAiResponsesClient {
    http: Client,
    auth: OpenAiAuth,
    model: String,
    platform_url: String,
    chatgpt_url: String,
}

impl OpenAiResponsesClient {
    pub fn api_key(
        model: impl Into<String>,
        api_key: impl Into<String>,
    ) -> Result<Self, ProviderError> {
        Self::new(
            model,
            OpenAiAuth::ApiKey(api_key.into()),
            PLATFORM_RESPONSES_URL,
            CHATGPT_RESPONSES_URL,
        )
    }

    pub fn chatgpt(
        model: impl Into<String>,
        access_token: impl Into<String>,
        account_id: impl Into<String>,
    ) -> Result<Self, ProviderError> {
        Self::new(
            model,
            OpenAiAuth::ChatGpt {
                access_token: access_token.into(),
                account_id: account_id.into(),
            },
            PLATFORM_RESPONSES_URL,
            CHATGPT_RESPONSES_URL,
        )
    }

    pub fn new(
        model: impl Into<String>,
        auth: OpenAiAuth,
        platform_url: impl Into<String>,
        chatgpt_url: impl Into<String>,
    ) -> Result<Self, ProviderError> {
        let secret = match &auth {
            OpenAiAuth::ApiKey(value) => value,
            OpenAiAuth::ChatGpt { access_token, .. } => access_token,
        };
        if secret.trim().is_empty() {
            return Err(ProviderError::MissingCredentials);
        }
        if matches!(&auth, OpenAiAuth::ChatGpt { account_id, .. } if account_id.trim().is_empty()) {
            return Err(ProviderError::InvalidCredentials(
                "ChatGPT credential has no account id".to_owned(),
            ));
        }
        Ok(Self {
            http: super::http_client(Duration::from_secs(120))?,
            auth,
            model: model.into(),
            platform_url: platform_url.into(),
            chatgpt_url: chatgpt_url.into(),
        })
    }

    fn body(&self, messages: &[Message], tools: &[ToolSpec], max_tokens: u32) -> Value {
        let tools = tools
            .iter()
            .map(|tool| {
                json!({
                    "type":"function",
                    "name":tool.name,
                    "description":tool.description,
                    "parameters":tool.input_schema,
                    "strict":false,
                })
            })
            .collect::<Vec<_>>();
        let mut body = json!({
            "model":self.model,
            "store":false,
            "stream":matches!(self.auth, OpenAiAuth::ChatGpt { .. }),
            "instructions":MACHINE_INSTRUCTIONS,
            "input":convert_messages(messages),
            "include":["reasoning.encrypted_content"],
        });
        if matches!(self.auth, OpenAiAuth::ApiKey(_)) {
            body["max_output_tokens"] = Value::from(max_tokens);
        }
        if !tools.is_empty() {
            body["tools"] = Value::Array(tools);
            body["tool_choice"] = Value::String("auto".to_owned());
            body["parallel_tool_calls"] = Value::Bool(false);
        }
        body
    }

    async fn request(&self, body: &Value) -> Result<Value, ProviderError> {
        let (url, token, account_id, streaming) = match &self.auth {
            OpenAiAuth::ApiKey(api_key) => {
                (self.platform_url.as_str(), api_key.as_str(), None, false)
            }
            OpenAiAuth::ChatGpt {
                access_token,
                account_id,
            } => (
                self.chatgpt_url.as_str(),
                access_token.as_str(),
                Some(account_id.as_str()),
                true,
            ),
        };
        let mut attempt = 0u32;
        loop {
            let mut request = self
                .http
                .post(url)
                .bearer_auth(token)
                .header("user-agent", user_agent())
                .json(body);
            if let Some(account_id) = account_id {
                request = request
                    .header("chatgpt-account-id", account_id)
                    .header("originator", "vadgr")
                    .header("OpenAI-Beta", "responses=experimental")
                    .header("accept", "text/event-stream");
            }
            let response = request
                .send()
                .await
                .map_err(|error| ProviderError::Request(error.to_string()))?;
            let status = response.status();
            if !status.is_success() {
                // **Read the body before deciding anything.** The status alone
                // cannot tell exhausted credit from a pace limit, and the
                // earlier version returned on the status and dropped the
                // response, which destroyed the one field that says which.
                // Diagnosing a single failure then took an account
                // investigation that the provider had already answered.
                let retry_after = retry_after_seconds(response.headers());
                let body = response.text().await.unwrap_or_default();
                let error = classify_failure(status, &body);
                if retryable(&error) && attempt < MAX_RETRIES {
                    // A pace limit is measured in seconds, so honour the
                    // provider's own number when it sends one. The earlier
                    // 500 ms and 1 s could not clear a per-minute window and
                    // only spent two more requests failing the same way.
                    let wait = retry_after.unwrap_or_else(|| backoff_seconds(attempt));
                    tokio::time::sleep(Duration::from_secs(wait)).await;
                    attempt += 1;
                    continue;
                }
                return Err(error);
            }
            let bytes =
                super::read_bounded(response, RESPONSE_BODY_LIMIT, "OpenAI response").await?;
            if streaming {
                let text = std::str::from_utf8(&bytes)
                    .map_err(|error| ProviderError::InvalidResponse(error.to_string()))?;
                return decode_sse(text);
            }
            return serde_json::from_slice(&bytes)
                .map_err(|error| ProviderError::InvalidResponse(error.to_string()));
        }
    }

    fn decode(value: Value) -> Result<ModelResponse, ProviderError> {
        let output = value
            .get("output")
            .and_then(Value::as_array)
            .ok_or_else(|| {
                ProviderError::InvalidResponse("response output must be an array".to_owned())
            })?;
        let mut content = Vec::new();
        for item in output {
            match item.get("type").and_then(Value::as_str) {
                Some("message") => {
                    for block in item
                        .get("content")
                        .and_then(Value::as_array)
                        .into_iter()
                        .flatten()
                    {
                        if matches!(
                            block.get("type").and_then(Value::as_str),
                            Some("output_text") | Some("text")
                        ) && let Some(text) = block.get("text").and_then(Value::as_str)
                        {
                            content.push(ContentBlock::Text {
                                text: text.to_owned(),
                            });
                        }
                    }
                }
                Some("function_call") => {
                    let arguments = item
                        .get("arguments")
                        .and_then(Value::as_str)
                        .unwrap_or("{}");
                    content.push(ContentBlock::ToolUse {
                        id: item
                            .get("call_id")
                            .or_else(|| item.get("id"))
                            .and_then(Value::as_str)
                            .map(str::to_owned)
                            .unwrap_or_else(|| format!("openai_{}", uuid::Uuid::new_v4())),
                        name: required_string(item, "name")?,
                        input: serde_json::from_str(arguments).map_err(|error| {
                            ProviderError::InvalidResponse(format!(
                                "function arguments are invalid JSON: {error}"
                            ))
                        })?,
                        provider_signature: None,
                    });
                }
                Some("reasoning") => {
                    if let Some(data) = item.get("encrypted_content").and_then(Value::as_str) {
                        content.push(ContentBlock::RedactedThinking {
                            data: data.to_owned(),
                        });
                    }
                }
                _ => {}
            }
        }
        let usage = value
            .get("usage")
            .ok_or_else(|| ProviderError::InvalidResponse("response has no usage".to_owned()))?;
        let has_tool = content
            .iter()
            .any(|block| matches!(block, ContentBlock::ToolUse { .. }));
        let incomplete = value.get("status").and_then(Value::as_str) == Some("incomplete");
        Ok(ModelResponse {
            content,
            stop_reason: Some(if has_tool {
                StopReason::ToolUse
            } else if incomplete {
                StopReason::MaxTokens
            } else {
                StopReason::EndTurn
            }),
            usage: Usage {
                input_tokens: required_u64(usage, "input_tokens")?,
                output_tokens: required_u64(usage, "output_tokens")?,
            },
        })
    }
}

#[async_trait]
impl ModelClient for OpenAiResponsesClient {
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

pub async fn discover_platform_models(
    http: &Client,
    api_key: &str,
    url: &str,
) -> Result<Vec<CatalogModel>, ProviderError> {
    let response = super::send_with_retry(
        http.get(url)
            .bearer_auth(api_key)
            .header("user-agent", user_agent()),
    )
    .await?;
    if !response.status().is_success() {
        // Same rule as the model call: read the body, then classify. A catalog
        // that fails for pace and one that fails for credit are different
        // problems for the owner.
        let status = response.status();
        let body = response.text().await.unwrap_or_default();
        return Err(classify_failure(status, &body));
    }
    let body = super::read_json(response).await?;
    catalog_rows(&body, "data", false)
}

pub async fn discover_chatgpt_models(
    http: &Client,
    access_token: &str,
    account_id: &str,
    url: &str,
) -> Result<Vec<CatalogModel>, ProviderError> {
    let url = chatgpt_catalog_url(url)?;
    let response = super::send_with_retry(
        http.get(url)
            .bearer_auth(access_token)
            .header("chatgpt-account-id", account_id)
            .header("originator", "vadgr")
            .header("user-agent", user_agent()),
    )
    .await?;
    if !response.status().is_success() {
        // Same rule as the model call: read the body, then classify. A catalog
        // that fails for pace and one that fails for credit are different
        // problems for the owner.
        let status = response.status();
        let body = response.text().await.unwrap_or_default();
        return Err(classify_failure(status, &body));
    }
    let body = super::read_json(response).await?;
    catalog_rows(&body, "models", true)
}

fn chatgpt_catalog_url(value: &str) -> Result<url::Url, ProviderError> {
    let mut url = UrlBuilder::new(value)?;
    url.append("client_version", CHATGPT_CATALOG_CLIENT_VERSION);
    Ok(url.finish())
}

pub fn account_id(access_token: &str) -> Result<String, ProviderError> {
    let payload = access_token
        .split('.')
        .nth(1)
        .ok_or_else(|| ProviderError::InvalidCredentials("access token is not a JWT".to_owned()))?;
    let bytes = URL_SAFE_NO_PAD
        .decode(payload)
        .map_err(|error| ProviderError::InvalidCredentials(error.to_string()))?;
    let claims: Value = serde_json::from_slice(&bytes)
        .map_err(|error| ProviderError::InvalidCredentials(error.to_string()))?;
    claims
        .pointer("/https:~1~1api.openai.com~1auth/chatgpt_account_id")
        .and_then(Value::as_str)
        .filter(|value| !value.is_empty())
        .map(str::to_owned)
        .ok_or_else(|| {
            ProviderError::InvalidCredentials("access token has no ChatGPT account id".to_owned())
        })
}

fn catalog_rows(
    body: &Value,
    key: &str,
    chatgpt: bool,
) -> Result<Vec<CatalogModel>, ProviderError> {
    let rows = body
        .get(key)
        .and_then(Value::as_array)
        .ok_or_else(|| ProviderError::InvalidResponse(format!("{key} must be an array")))?;
    let mut models = rows
        .iter()
        .filter_map(|row| {
            if chatgpt {
                let visibility = row.get("visibility").and_then(Value::as_str);
                if visibility.is_some_and(|value| value != "list")
                    || row.get("show_in_picker").and_then(Value::as_bool) == Some(false)
                {
                    return None;
                }
            }
            let id = row
                .get(if chatgpt { "slug" } else { "id" })
                .or_else(|| row.get("id"))?
                .as_str()?;
            if !chatgpt && !platform_tool_model(id) {
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
    models.dedup_by(|left, right| left.id == right.id);
    if models.is_empty() {
        return Err(ProviderError::InvalidResponse(
            "OpenAI returned no usable models".to_owned(),
        ));
    }
    Ok(models)
}

fn platform_tool_model(id: &str) -> bool {
    let id = id.to_ascii_lowercase();
    (id.starts_with("gpt-5")
        || id.starts_with("gpt-4.1")
        || id.starts_with("o3")
        || id.starts_with("o4"))
        && !["audio", "image", "realtime", "search", "transcribe", "tts"]
            .iter()
            .any(|part| id.contains(part))
}

fn convert_messages(messages: &[Message]) -> Vec<Value> {
    let mut input = Vec::new();
    for message in messages {
        match &message.content {
            Value::String(text) => input.push(json!({
                "type":"message",
                "role":message.role,
                "content":[{"type":if message.role == "assistant" {"output_text"} else {"input_text"},"text":text}]
            })),
            Value::Array(blocks) => {
                let mut message_content = Vec::new();
                for block in blocks {
                    match block.get("type").and_then(Value::as_str) {
                        Some("text") => {
                            if let Some(text) = block.get("text").and_then(Value::as_str) {
                                message_content.push(json!({
                                    "type":if message.role == "assistant" {"output_text"} else {"input_text"},
                                    "text":text
                                }));
                            }
                        }
                        Some("image") if message.role != "assistant" => {
                            if let Some(source) = block.get("source") {
                                let media = source
                                    .get("media_type")
                                    .and_then(Value::as_str)
                                    .unwrap_or("image/png");
                                let data = source.get("data").and_then(Value::as_str).unwrap_or("");
                                message_content.push(json!({
                                    "type":"input_image",
                                    "image_url":format!("data:{media};base64,{data}")
                                }));
                            }
                        }
                        Some("tool_use") => {
                            flush_message_content(&mut input, &message.role, &mut message_content);
                            input.push(json!({
                                "type":"function_call",
                                "call_id":block.get("id").and_then(Value::as_str).unwrap_or(""),
                                "name":block.get("name").and_then(Value::as_str).unwrap_or(""),
                                "arguments":block.get("input").cloned().unwrap_or_else(|| json!({})).to_string()
                            }));
                        }
                        Some("tool_result") => {
                            flush_message_content(&mut input, &message.role, &mut message_content);
                            input.push(json!({
                                "type":"function_call_output",
                                "call_id":block.get("tool_use_id").and_then(Value::as_str).unwrap_or(""),
                                "output":tool_result_output(block)
                            }));
                        }
                        Some("redacted_thinking") => {
                            flush_message_content(&mut input, &message.role, &mut message_content);
                            input.push(json!({
                                "type":"reasoning",
                                "encrypted_content":block.get("data").and_then(Value::as_str).unwrap_or(""),
                                "summary":[]
                            }));
                        }
                        _ => {}
                    }
                }
                flush_message_content(&mut input, &message.role, &mut message_content);
            }
            _ => {}
        }
    }
    input
}

fn flush_message_content(input: &mut Vec<Value>, role: &str, content: &mut Vec<Value>) {
    if !content.is_empty() {
        input.push(json!({
            "type":"message",
            "role":role,
            "content":std::mem::take(content),
        }));
    }
}

/// What a tool result becomes in `function_call_output.output`.
///
/// **An image must arrive as a typed image part, never as its own base64.**
/// A screen capture result is `content:[{type:"image",source:{data,media_type}}]`
/// and carries no `text` field. The earlier version collected `text` fields,
/// found none, and fell back to serialising the whole array, which put the
/// base64 into the request as prose: one screen capture became 739,560
/// characters, roughly 185,000 tokens, in a single request against an
/// organization ceiling of 200,000 tokens per minute. The model could not see
/// the image either, because base64 text is not an image to it.
///
/// The Responses API accepts a typed array here, verified live against the
/// service: `[{"type":"input_image","image_url":"data:image/png;base64,..."}]`
/// returns HTTP 200 and the model reads the picture.
///
/// A result with only text stays a plain string, which is the common case and
/// the cheapest shape on the wire.
fn tool_result_output(block: &Value) -> Value {
    let Some(items) = block.get("content").and_then(Value::as_array) else {
        // No content array at all: keep the old scalar behaviour rather than
        // inventing a shape the caller did not send.
        return Value::String(
            block
                .get("content")
                .cloned()
                .unwrap_or(Value::Null)
                .to_string(),
        );
    };

    let mut parts = Vec::new();
    let mut text_only = Vec::new();
    for item in items {
        match item.get("type").and_then(Value::as_str) {
            Some("image") => {
                if let Some(source) = item.get("source") {
                    let media = source
                        .get("media_type")
                        .and_then(Value::as_str)
                        .unwrap_or("image/png");
                    let data = source.get("data").and_then(Value::as_str).unwrap_or("");
                    parts.push(json!({
                        "type":"input_image",
                        "image_url":format!("data:{media};base64,{data}")
                    }));
                }
            }
            _ => {
                if let Some(text) = item.get("text").and_then(Value::as_str) {
                    text_only.push(text.to_owned());
                    parts.push(json!({"type":"input_text","text":text}));
                }
            }
        }
    }

    if parts.iter().any(|part| part["type"] == "input_image") {
        return Value::Array(parts);
    }
    if !text_only.is_empty() {
        return Value::String(text_only.join("\n"));
    }
    // Content the adapter does not recognise: serialise it rather than drop it,
    // because a tool result the model never sees is a silent hole in the loop.
    Value::String(
        block
            .get("content")
            .cloned()
            .unwrap_or(Value::Null)
            .to_string(),
    )
}

fn decode_sse(text: &str) -> Result<Value, ProviderError> {
    let mut completed = None;
    let mut completed_items = Vec::new();
    for line in text.lines() {
        let Some(data) = line.strip_prefix("data:") else {
            continue;
        };
        let data = data.trim();
        if data.is_empty() || data == "[DONE]" {
            continue;
        }
        let event: Value = serde_json::from_str(data)
            .map_err(|error| ProviderError::InvalidResponse(error.to_string()))?;
        match event.get("type").and_then(Value::as_str) {
            Some("response.output_item.done") => {
                if let Some(item) = event.get("item") {
                    completed_items.push(item.clone());
                }
            }
            Some("response.completed") | Some("response.done") | Some("response.incomplete") => {
                completed = event.get("response").cloned();
            }
            Some("error") => {
                return Err(ProviderError::InvalidResponse(
                    "OpenAI stream failed".to_owned(),
                ));
            }
            _ => {}
        }
    }
    let mut completed = completed.ok_or_else(|| {
        ProviderError::InvalidResponse("OpenAI stream has no completed response".to_owned())
    })?;
    if completed
        .get("output")
        .and_then(Value::as_array)
        .is_none_or(Vec::is_empty)
        && !completed_items.is_empty()
    {
        completed["output"] = Value::Array(completed_items);
    }
    Ok(completed)
}

/// Two attempts after the first, which is what a per-minute window can afford.
const MAX_RETRIES: u32 = 2;

fn retryable(error: &ProviderError) -> bool {
    // Waiting helps a pace limit and a server fault. It cannot help an empty
    // account, a rejected credential or a request the service will refuse
    // again, so those return at once rather than spending two more calls.
    matches!(
        error,
        ProviderError::RateLimited | ProviderError::Unavailable
    )
}

fn backoff_seconds(attempt: u32) -> u64 {
    // 5 s then 20 s. Seconds, because the limit that produces a 429 here is
    // measured per minute.
    5u64 << (attempt * 2)
}

fn retry_after_seconds(headers: &reqwest::header::HeaderMap) -> Option<u64> {
    headers
        .get(reqwest::header::RETRY_AFTER)
        .and_then(|value| value.to_str().ok())
        .and_then(|value| value.trim().parse::<f64>().ok())
        .filter(|value| *value >= 0.0)
        // A provider asking for longer than a minute is asking for more than a
        // retry is for. Cap it and surface the failure instead of stalling the
        // run behind a sleep the owner cannot see.
        .map(|value| (value.ceil() as u64).min(60))
}

/// The upstream `code`, when the service sent one.
///
/// The body is untrusted input and may be anything, so a missing or malformed
/// body simply yields `None` and the status decides alone.
fn upstream_code(body: &str) -> Option<String> {
    serde_json::from_str::<Value>(body)
        .ok()?
        .get("error")?
        .get("code")?
        .as_str()
        .map(str::to_owned)
}

/// Classify a failure from the status **and** the body.
///
/// HTTP 429 carries two opposite facts on this service. `insufficient_quota`
/// means the account has no credit and waiting cannot help. Anything else at
/// 429 is pace, which clears by itself. Reporting both as exhausted quota sent
/// an owner to the billing pages of an account that was working.
fn classify_failure(status: StatusCode, body: &str) -> ProviderError {
    let code = upstream_code(body);
    match status {
        StatusCode::UNAUTHORIZED => ProviderError::Unauthorized,
        StatusCode::FORBIDDEN => ProviderError::Forbidden,
        StatusCode::TOO_MANY_REQUESTS => match code.as_deref() {
            Some("insufficient_quota") => ProviderError::QuotaExhausted,
            _ => ProviderError::RateLimited,
        },
        StatusCode::NOT_FOUND => ProviderError::ModelUnavailable,
        status if status.is_server_error() => ProviderError::Unavailable,
        status => ProviderError::Request(match code {
            // Keep the provider's own code. It is the difference between a
            // report an owner can act on and one that sends them hunting.
            Some(code) => format!("OpenAI request failed with HTTP {status} ({code})"),
            None => format!("OpenAI request failed with HTTP {status}"),
        }),
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

struct UrlBuilder(url::Url);

impl UrlBuilder {
    fn new(value: &str) -> Result<Self, ProviderError> {
        Ok(Self(url::Url::parse(value).map_err(|error| {
            ProviderError::InvalidResponse(error.to_string())
        })?))
    }

    fn append(&mut self, key: &str, value: &str) {
        self.0.query_pairs_mut().append_pair(key, value);
    }

    fn finish(self) -> url::Url {
        self.0
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::Map;

    fn api_client() -> OpenAiResponsesClient {
        OpenAiResponsesClient::new(
            "gpt-test",
            OpenAiAuth::ApiKey("key".to_owned()),
            "http://localhost/platform",
            "http://localhost/chatgpt",
        )
        .unwrap()
    }

    fn chatgpt_client() -> OpenAiResponsesClient {
        OpenAiResponsesClient::new(
            "gpt-test",
            OpenAiAuth::ChatGpt {
                access_token: "token".to_owned(),
                account_id: "account".to_owned(),
            },
            "http://localhost/platform",
            "http://localhost/chatgpt",
        )
        .unwrap()
    }

    #[test]
    fn chatgpt_authorization_descriptor_matches_the_direct_flow() {
        let pending = super::super::oauth::begin(&OPENAI_OAUTH, OPENAI_OAUTH.redirect_uri).unwrap();
        let url = url::Url::parse(&pending.authorization_url).unwrap();
        let query = url
            .query_pairs()
            .collect::<std::collections::HashMap<_, _>>();
        assert_eq!(
            OPENAI_OAUTH.redirect_uri,
            "http://localhost:1455/auth/callback"
        );
        assert_eq!(
            query.get("originator").map(|value| value.as_ref()),
            Some("vadgr")
        );
    }

    #[test]
    fn chatgpt_catalog_uses_its_protocol_version() {
        let url = chatgpt_catalog_url(CHATGPT_MODELS_URL).unwrap();
        assert_eq!(
            url.query_pairs()
                .find(|(key, _)| key == "client_version")
                .map(|(_, value)| value.into_owned())
                .as_deref(),
            Some(CHATGPT_CATALOG_CLIENT_VERSION)
        );
        assert_ne!(CHATGPT_CATALOG_CLIENT_VERSION, env!("CARGO_PKG_VERSION"));
    }

    #[test]
    fn request_converts_tools_calls_results_and_keeps_vadgr_identity() {
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
        let body = api_client().body(
            &messages,
            &[ToolSpec {
                name: "test__act".to_owned(),
                description: "act".to_owned(),
                input_schema: Map::new(),
            }],
            1024,
        );
        assert_eq!(body["max_output_tokens"], 1024);
        assert_eq!(body["tools"][0]["name"], "test__act");
        assert!(
            body["input"]
                .as_array()
                .unwrap()
                .iter()
                .any(|item| item["type"] == "function_call_output")
        );
        assert!(!body.to_string().contains("OpenClaw"));
    }

    #[test]
    fn chatgpt_request_omits_unsupported_output_limit() {
        let body = chatgpt_client().body(&[Message::text("user", "task")], &[], 32);
        assert!(body.get("max_output_tokens").is_none());
    }

    #[test]
    fn message_conversion_preserves_text_and_tool_item_order() {
        let converted = convert_messages(&[Message {
            role: "assistant".to_owned(),
            content: json!([
                {"type":"text","text":"before"},
                {"type":"tool_use","id":"call-1","name":"test__act","input":{}},
                {"type":"text","text":"after"}
            ]),
        }]);
        assert_eq!(
            converted
                .iter()
                .map(|item| item["type"].as_str().unwrap())
                .collect::<Vec<_>>(),
            ["message", "function_call", "message"]
        );
    }

    #[test]
    fn response_maps_function_calls_and_usage() {
        let response = OpenAiResponsesClient::decode(json!({
            "status":"completed",
            "output":[
                {"type":"message","content":[{"type":"output_text","text":"working"}]},
                {"type":"function_call","call_id":"c1","name":"test__act","arguments":"{\"n\":1}"}
            ],
            "usage":{"input_tokens":2,"output_tokens":3}
        }))
        .unwrap();
        assert_eq!(response.stop_reason, Some(StopReason::ToolUse));
        assert_eq!(response.usage.output_tokens, 3);
    }

    #[test]
    fn account_id_comes_from_the_openai_auth_claim() {
        let header = URL_SAFE_NO_PAD.encode(br#"{"alg":"none"}"#);
        let payload = URL_SAFE_NO_PAD
            .encode(br#"{"https://api.openai.com/auth":{"chatgpt_account_id":"acct-test"}}"#);
        assert_eq!(
            account_id(&format!("{header}.{payload}.sig")).unwrap(),
            "acct-test"
        );
    }

    #[test]
    fn sse_requires_a_terminal_response_event() {
        assert!(decode_sse("data: {\"type\":\"response.created\"}\n\n").is_err());
        let value = decode_sse(
            "data: {\"type\":\"response.completed\",\"response\":{\"output\":[],\"usage\":{\"input_tokens\":1,\"output_tokens\":1}}}\n\n",
        )
        .unwrap();
        assert_eq!(value["usage"]["input_tokens"], 1);
    }

    #[test]
    fn sse_keeps_completed_output_items_when_terminal_output_is_empty() {
        let value = decode_sse(concat!(
            "data: {\"type\":\"response.output_item.done\",\"item\":{\"type\":\"message\",\"content\":[{\"type\":\"output_text\",\"text\":\"OK\"}]}}\n\n",
            "data: {\"type\":\"response.completed\",\"response\":{\"status\":\"completed\",\"output\":[],\"usage\":{\"input_tokens\":1,\"output_tokens\":1}}}\n\n",
        ))
        .unwrap();

        assert_eq!(value["output"][0]["content"][0]["text"], "OK");
    }

    /// The defect that blocked the 0.4.7 dogfood cell. A screen capture result
    /// carries an image block and no text, and the earlier extractor turned the
    /// whole array into a string, putting 739,560 characters of base64 into one
    /// request as prose.
    #[test]
    fn a_screen_capture_result_rides_as_an_image_not_as_its_own_base64() {
        let block = json!({
            "type":"tool_result",
            "tool_use_id":"call_1",
            "content":[{"type":"image","source":{
                "type":"base64","media_type":"image/png","data":"QUJD"}}]
        });

        let output = tool_result_output(&block);

        let parts = output.as_array().expect("an image result is a typed array");
        assert_eq!(parts.len(), 1);
        assert_eq!(parts[0]["type"], "input_image");
        assert_eq!(parts[0]["image_url"], "data:image/png;base64,QUJD");
        // The base64 must never appear as prose. Before the fix the whole
        // content array was stringified into `output`.
        assert!(
            !output.is_string(),
            "the image was serialised as text, which is the defect"
        );
    }

    #[test]
    fn a_text_only_result_stays_a_plain_string() {
        let block = json!({
            "type":"tool_result",
            "content":[{"type":"text","text":"first"},{"type":"text","text":"second"}]
        });
        assert_eq!(tool_result_output(&block), json!("first\nsecond"));
    }

    #[test]
    fn a_mixed_result_keeps_the_text_beside_the_image() {
        let block = json!({
            "type":"tool_result",
            "content":[
                {"type":"text","text":"1920x1080"},
                {"type":"image","source":{"media_type":"image/jpeg","data":"WFla"}}
            ]
        });
        let parts = tool_result_output(&block);
        let parts = parts.as_array().unwrap();
        assert_eq!(parts[0], json!({"type":"input_text","text":"1920x1080"}));
        assert_eq!(parts[1]["type"], "input_image");
        assert_eq!(parts[1]["image_url"], "data:image/jpeg;base64,WFla");
    }

    #[test]
    fn unrecognised_content_is_serialised_rather_than_dropped() {
        // A tool result the model never sees is a silent hole in the loop.
        let block = json!({"type":"tool_result","content":[{"type":"future","x":1}]});
        assert!(
            tool_result_output(&block)
                .as_str()
                .unwrap()
                .contains("future")
        );
    }

    /// The misreport that cost an account investigation. 429 carries two
    /// opposite facts and only the body says which.
    #[test]
    fn exhausted_credit_and_a_pace_limit_are_two_different_answers() {
        let quota = classify_failure(
            StatusCode::TOO_MANY_REQUESTS,
            r#"{"error":{"code":"insufficient_quota","message":"..."}}"#,
        );
        assert!(matches!(quota, ProviderError::QuotaExhausted));

        let pace = classify_failure(
            StatusCode::TOO_MANY_REQUESTS,
            r#"{"error":{"code":"rate_limit_exceeded","message":"..."}}"#,
        );
        assert!(
            matches!(pace, ProviderError::RateLimited),
            "a pace limit must not be reported as an empty account"
        );
    }

    #[test]
    fn a_429_with_no_readable_body_is_pace_rather_than_an_empty_account() {
        // Guessing "no credit" from silence sends the owner to a billing page.
        // Guessing "wait" costs one retry.
        for body in ["", "not json", "{}", r#"{"error":{}}"#] {
            assert!(matches!(
                classify_failure(StatusCode::TOO_MANY_REQUESTS, body),
                ProviderError::RateLimited
            ));
        }
    }

    #[test]
    fn the_upstream_code_survives_into_the_message() {
        let error = classify_failure(
            StatusCode::BAD_REQUEST,
            r#"{"error":{"code":"context_length_exceeded","message":"..."}}"#,
        );
        match error {
            ProviderError::Request(text) => {
                assert!(text.contains("context_length_exceeded"), "got: {text}")
            }
            other => panic!("expected a request error, got {other:?}"),
        }
    }

    #[test]
    fn only_the_conditions_that_waiting_can_clear_are_retried() {
        assert!(retryable(&ProviderError::RateLimited));
        assert!(retryable(&ProviderError::Unavailable));
        // Retrying these spends two more calls to fail the same way.
        assert!(!retryable(&ProviderError::QuotaExhausted));
        assert!(!retryable(&ProviderError::Unauthorized));
        assert!(!retryable(&ProviderError::ModelUnavailable));
    }

    #[test]
    fn the_backoff_is_measured_in_seconds_because_the_limit_is_per_minute() {
        // 500 ms and 1 s could not clear a per-minute window.
        assert_eq!(backoff_seconds(0), 5);
        assert_eq!(backoff_seconds(1), 20);
    }

    #[test]
    fn the_providers_own_retry_after_wins_and_is_capped() {
        let mut headers = reqwest::header::HeaderMap::new();
        headers.insert(reqwest::header::RETRY_AFTER, "12".parse().unwrap());
        assert_eq!(retry_after_seconds(&headers), Some(12));

        headers.insert(reqwest::header::RETRY_AFTER, "0.4".parse().unwrap());
        assert_eq!(
            retry_after_seconds(&headers),
            Some(1),
            "round up, never to zero"
        );

        // Longer than a minute is more than a retry is for.
        headers.insert(reqwest::header::RETRY_AFTER, "900".parse().unwrap());
        assert_eq!(retry_after_seconds(&headers), Some(60));

        // A date form, which this service does not send, must not panic.
        headers.insert(
            reqwest::header::RETRY_AFTER,
            "Wed, 21 Oct 2026 07:28:00 GMT".parse().unwrap(),
        );
        assert_eq!(retry_after_seconds(&headers), None);
    }
}
