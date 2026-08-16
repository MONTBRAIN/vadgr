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
            if retryable(response.status()) && attempt < 2 {
                tokio::time::sleep(Duration::from_millis(500u64 << attempt)).await;
                attempt += 1;
                continue;
            }
            if !response.status().is_success() {
                return Err(classify_status(response.status()));
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
        return Err(classify_status(response.status()));
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
        return Err(classify_status(response.status()));
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
                                "output":tool_result_text(block)
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

fn tool_result_text(block: &Value) -> String {
    block
        .get("content")
        .and_then(Value::as_array)
        .map(|items| {
            items
                .iter()
                .filter_map(|item| item.get("text").and_then(Value::as_str))
                .collect::<Vec<_>>()
                .join("\n")
        })
        .filter(|value| !value.is_empty())
        .unwrap_or_else(|| {
            block
                .get("content")
                .cloned()
                .unwrap_or(Value::Null)
                .to_string()
        })
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
        status => ProviderError::Request(format!("OpenAI request failed with HTTP {status}")),
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
        let pending = super::super::oauth::begin(&OPENAI_OAUTH).unwrap();
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
}
