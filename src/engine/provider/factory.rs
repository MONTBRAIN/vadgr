use super::service::{ProviderService, ServiceError};
use super::{ModelClient, ModelFactory};
use crate::engine::types::{Message, ModelResponse, ProviderError, ToolSpec};
use async_trait::async_trait;
use std::sync::Arc;

pub struct NativeModelFactory {
    service: Arc<ProviderService>,
}

impl NativeModelFactory {
    pub fn new(service: Arc<ProviderService>) -> Self {
        Self { service }
    }
}

struct ManagedModelClient {
    service: Arc<ProviderService>,
    provider: String,
    model: String,
}

#[async_trait]
impl ModelClient for ManagedModelClient {
    async fn complete(
        &self,
        messages: &[Message],
        tools: &[ToolSpec],
        max_tokens: u32,
    ) -> Result<ModelResponse, ProviderError> {
        let client = self
            .service
            .build_client(&self.provider, &self.model)
            .map_err(provider_error)?;
        let result = client.complete(messages, tools, max_tokens).await;
        match result {
            Err(ProviderError::Unauthorized)
                if self.provider == "openai"
                    && self
                        .service
                        .auth_method(&self.provider)
                        .map_err(provider_error)?
                        == "oauth" =>
            {
                self.service
                    .refresh_oauth_credential(&self.provider)
                    .await
                    .map_err(provider_error)?;
                self.service
                    .build_client(&self.provider, &self.model)
                    .map_err(provider_error)?
                    .complete(messages, tools, max_tokens)
                    .await
            }
            Err(ProviderError::ModelUnavailable) => {
                if let Err(error) = self.service.refresh_catalog(&self.provider).await {
                    tracing::warn!(
                        provider = self.provider,
                        error = %error,
                        "provider catalog refresh after model rejection failed"
                    );
                }
                Err(ProviderError::ModelUnavailable)
            }
            result => result,
        }
    }
}

#[async_trait]
impl ModelFactory for NativeModelFactory {
    async fn build(
        &self,
        provider: &str,
        model: &str,
    ) -> Result<Box<dyn ModelClient>, ProviderError> {
        self.service
            .build_client(provider, model)
            .map_err(provider_error)?;
        Ok(Box::new(ManagedModelClient {
            service: self.service.clone(),
            provider: provider.to_owned(),
            model: model.to_owned(),
        }))
    }
}

fn provider_error(error: ServiceError) -> ProviderError {
    match error {
        ServiceError::Provider(error) => error,
        ServiceError::UnknownProvider(provider) => ProviderError::UnknownProvider(provider),
        error => ProviderError::Request(error.to_string()),
    }
}
