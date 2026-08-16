mod anthropic;
pub mod oauth;

pub use anthropic::{AnthropicOAuthClient, NativeModelFactory};

use crate::engine::types::{Message, ModelResponse, ProviderError, ToolSpec};
use async_trait::async_trait;

#[async_trait]
pub trait ModelClient: Send + Sync {
    async fn complete(
        &self,
        messages: &[Message],
        tools: &[ToolSpec],
        max_tokens: u32,
    ) -> Result<ModelResponse, ProviderError>;
}

#[async_trait]
pub trait ModelFactory: Send + Sync {
    async fn build(
        &self,
        provider: &str,
        model: &str,
    ) -> Result<Box<dyn ModelClient>, ProviderError>;
}
