use super::anthropic;
use super::credentials::{Credential, CredentialStore};
use super::gemini;
use super::oauth;
use super::openai;
use super::{CatalogModel, ModelClient};
use crate::db::Db;
use crate::db::providers::{self, Connection, ConnectionCommit, ProviderModel};
use crate::engine::types::{Message, ProviderError};
use reqwest::Client;
use serde::Serialize;
use serde_json::{Value, json};
use std::collections::HashMap;
use std::path::PathBuf;
use std::sync::Arc;
use std::sync::atomic::{AtomicU16, Ordering};
use time::{Duration, OffsetDateTime};
use tokio::sync::Mutex;

const ATTEMPT_TTL_MINUTES: i64 = 10;
const READINESS_PROMPT: &str = "Reply with OK.";

#[derive(Clone, Copy, Debug)]
pub struct ProviderDescriptor {
    pub id: &'static str,
    pub name: &'static str,
    pub auth_methods: &'static [&'static str],
    pub policy_url: &'static str,
    starter_preferences: &'static [&'static str],
}

pub const DESCRIPTORS: [ProviderDescriptor; 3] = [
    ProviderDescriptor {
        id: "openai",
        name: "OpenAI",
        auth_methods: &["oauth", "api_key"],
        policy_url: "https://openai.com/policies/usage-policies/",
        starter_preferences: &["gpt-5.6-sol", "gpt-5.6-terra", "gpt-5.4"],
    },
    ProviderDescriptor {
        id: "gemini",
        name: "Google Gemini",
        auth_methods: &["api_key"],
        policy_url: "https://ai.google.dev/gemini-api/terms",
        starter_preferences: &["gemini-3.7-flash", "gemini-3.6-flash", "gemini-2.5-flash"],
    },
    ProviderDescriptor {
        id: "anthropic",
        name: "Anthropic",
        auth_methods: &["api_key"],
        policy_url: "https://www.anthropic.com/legal/aup",
        starter_preferences: &["claude-opus-5", "claude-sonnet-5", "claude-sonnet-4-5"],
    },
];

#[derive(Clone, Debug)]
pub struct ProviderEndpoints {
    pub openai_oauth: oauth::OAuthDescriptor,
    pub openai_platform_responses: String,
    pub openai_platform_models: String,
    pub openai_chatgpt_responses: String,
    pub openai_chatgpt_models: String,
    pub gemini_api_root: String,
    pub gemini_models: String,
    pub anthropic_messages: String,
    pub anthropic_models: String,
}

impl ProviderEndpoints {
    /// The published endpoints, with each one overridable by environment.
    ///
    /// **This is configuration, not a test hook.** A machine can be required to
    /// reach a provider through a gateway, a corporate proxy or a compatible
    /// endpoint that is not the vendor's own host, and without this the daemon
    /// cannot be pointed anywhere. It also lets a runbook drive a deterministic
    /// provider or an unreachable one, which is how the failure cells are
    /// exercised without pretending a real account is broken.
    ///
    /// An override is used verbatim. The daemon does not rewrite it, so a
    /// mistyped host fails as a request error rather than silently falling back
    /// to the vendor, which would make an override look like it worked.
    pub fn from_env() -> Self {
        fn or_env(name: &str, fallback: String) -> String {
            std::env::var(name)
                .ok()
                .map(|value| value.trim().to_owned())
                .filter(|value| !value.is_empty())
                .unwrap_or(fallback)
        }
        let base = Self::default();
        Self {
            openai_oauth: base.openai_oauth,
            openai_platform_responses: or_env(
                "VADGR_OPENAI_RESPONSES_URL",
                base.openai_platform_responses,
            ),
            openai_platform_models: or_env("VADGR_OPENAI_MODELS_URL", base.openai_platform_models),
            openai_chatgpt_responses: base.openai_chatgpt_responses,
            openai_chatgpt_models: base.openai_chatgpt_models,
            gemini_api_root: or_env("VADGR_GEMINI_API_ROOT", base.gemini_api_root),
            gemini_models: or_env("VADGR_GEMINI_MODELS_URL", base.gemini_models),
            anthropic_messages: or_env("VADGR_ANTHROPIC_MESSAGES_URL", base.anthropic_messages),
            anthropic_models: or_env("VADGR_ANTHROPIC_MODELS_URL", base.anthropic_models),
        }
    }
}

impl Default for ProviderEndpoints {
    fn default() -> Self {
        Self {
            openai_oauth: openai::OPENAI_OAUTH.clone(),
            openai_platform_responses: openai::PLATFORM_RESPONSES_URL.to_owned(),
            openai_platform_models: openai::PLATFORM_MODELS_URL.to_owned(),
            openai_chatgpt_responses: openai::CHATGPT_RESPONSES_URL.to_owned(),
            openai_chatgpt_models: openai::CHATGPT_MODELS_URL.to_owned(),
            gemini_api_root: gemini::API_ROOT.to_owned(),
            gemini_models: gemini::MODELS_URL.to_owned(),
            anthropic_messages: anthropic::MESSAGES_URL.to_owned(),
            anthropic_models: anthropic::MODELS_URL.to_owned(),
        }
    }
}

#[derive(Clone, Debug, Eq, PartialEq)]
enum AttemptStatus {
    Pending,
    Authenticated,
    Failed,
    Cancelled,
}

impl AttemptStatus {
    fn as_str(&self) -> &'static str {
        match self {
            Self::Pending => "pending",
            Self::Authenticated => "authenticated",
            Self::Failed => "failed",
            Self::Cancelled => "cancelled",
        }
    }
}

#[derive(Clone, Debug)]
struct AuthAttempt {
    id: String,
    provider_id: String,
    method: String,
    status: AttemptStatus,
    authorization_url: Option<String>,
    verifier: Option<String>,
    state: Option<String>,
    /// The redirect this attempt was started with, kept so the exchange sends
    /// the same one even if the listener rebinds to a different port meanwhile.
    redirect_uri: Option<String>,
    exchange_in_progress: bool,
    credential: Option<Credential>,
    account_id: Option<String>,
    error_code: Option<&'static str>,
    expires_at: OffsetDateTime,
}

#[derive(Clone, Debug, Serialize)]
pub struct AttemptView {
    pub id: String,
    pub provider_id: String,
    pub method: String,
    pub status: String,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub authorization_url: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub error_code: Option<&'static str>,
    pub expires_at: String,
}

impl From<&AuthAttempt> for AttemptView {
    fn from(value: &AuthAttempt) -> Self {
        Self {
            id: value.id.clone(),
            provider_id: value.provider_id.clone(),
            method: value.method.clone(),
            status: value.status.as_str().to_owned(),
            authorization_url: value.authorization_url.clone(),
            error_code: value.error_code,
            expires_at: value
                .expires_at
                .format(&time::format_description::well_known::Rfc3339)
                .expect("a timestamp always formats"),
        }
    }
}

#[derive(Debug, thiserror::Error)]
pub enum ServiceError {
    #[error("unknown provider: {0}")]
    UnknownProvider(String),
    #[error("authentication method `{method}` is not supported for `{provider}`")]
    InvalidMethod { provider: String, method: String },
    #[error("provider authentication attempt not found")]
    AttemptNotFound,
    #[error("provider authentication attempt is not ready")]
    AttemptNotReady,
    #[error("the provider callback listener is unavailable")]
    CallbackUnavailable,
    #[error("provider is not connected")]
    NotConnected,
    #[error("the default provider cannot be disconnected")]
    DefaultInUse,
    #[error("the current default model is unavailable")]
    DefaultUnavailable(Vec<String>),
    #[error("model is not in the connected provider catalog")]
    UnknownModel,
    #[error(transparent)]
    Provider(#[from] ProviderError),
    #[error("provider state failed: {0}")]
    State(String),
}

impl ServiceError {
    pub fn code(&self) -> &'static str {
        match self {
            Self::UnknownProvider(_) | Self::InvalidMethod { .. } => "INVALID_PROVIDER_AUTH",
            Self::AttemptNotFound => "AUTH_ATTEMPT_NOT_FOUND",
            Self::AttemptNotReady => "AUTH_ATTEMPT_NOT_READY",
            Self::CallbackUnavailable => "PROVIDER_UNAVAILABLE",
            Self::NotConnected => "PROVIDER_NOT_CONNECTED",
            Self::DefaultInUse => "DEFAULT_MODEL_IN_USE",
            Self::DefaultUnavailable(_) => "DEFAULT_MODEL_UNAVAILABLE",
            Self::UnknownModel => "MODEL_NOT_AVAILABLE",
            Self::Provider(
                ProviderError::MissingCredentials
                | ProviderError::InvalidCredentials(_)
                | ProviderError::Unauthorized,
            ) => "INVALID_CREDENTIALS",
            Self::Provider(_) => "PROVIDER_UNAVAILABLE",
            Self::State(_) => "PROVIDER_STATE_FAILED",
        }
    }

    pub fn category(&self) -> Option<&'static str> {
        match self {
            Self::Provider(error) => Some(provider_error_code(error)),
            Self::CallbackUnavailable => Some("provider_unavailable"),
            _ => None,
        }
    }
}

pub struct ProviderService {
    db: Db,
    store: Arc<CredentialStore>,
    http: Client,
    endpoints: ProviderEndpoints,
    attempts: Arc<Mutex<HashMap<String, AuthAttempt>>>,
    provider_locks: HashMap<&'static str, Arc<Mutex<()>>>,
    /// The loopback port the callback listener actually bound, or `0` for none.
    ///
    /// A boolean was not enough once the listener could bind more than one
    /// port: the authorization URL has to name the port the browser will be
    /// redirected to, so the flow needs the number rather than the fact.
    oauth_callback_port: AtomicU16,
}

impl ProviderService {
    pub fn native(db: Db, state_home: Option<PathBuf>) -> Result<Arc<Self>, ServiceError> {
        let service = Self::new(
            db,
            CredentialStore::native(state_home)?,
            ProviderEndpoints::from_env(),
        )?;
        service.set_oauth_callback_port(None);
        Ok(service)
    }

    pub fn new(
        db: Db,
        store: CredentialStore,
        endpoints: ProviderEndpoints,
    ) -> Result<Arc<Self>, ServiceError> {
        let referenced = providers::referenced_secrets(&db)
            .map_err(|error| ServiceError::State(error.to_string()))?;
        store.cleanup_unreferenced(&referenced)?;
        let provider_locks = DESCRIPTORS
            .iter()
            .map(|descriptor| (descriptor.id, Arc::new(Mutex::new(()))))
            .collect();
        Ok(Arc::new(Self {
            db,
            store: Arc::new(store),
            http: super::http_client(std::time::Duration::from_secs(90))?,
            endpoints,
            attempts: Arc::new(Mutex::new(HashMap::new())),
            provider_locks,
            oauth_callback_port: AtomicU16::new(0),
        }))
    }

    pub fn descriptors(&self) -> &'static [ProviderDescriptor] {
        &DESCRIPTORS
    }

    /// Record the port the callback listener bound, or `None` when it has none.
    pub fn set_oauth_callback_port(&self, port: Option<u16>) {
        self.oauth_callback_port
            .store(port.unwrap_or(0), Ordering::Release);
    }

    /// The redirect the browser must be sent to, if the listener is up.
    fn oauth_redirect_uri(&self) -> Option<String> {
        match self.oauth_callback_port.load(Ordering::Acquire) {
            0 => None,
            port => Some(format!("http://localhost:{port}/auth/callback")),
        }
    }

    pub async fn start_api_key(
        &self,
        provider_id: &str,
        api_key: String,
    ) -> Result<AttemptView, ServiceError> {
        self.validate_method(provider_id, "api_key")?;
        if api_key.trim().is_empty() || api_key.len() > 16 * 1024 {
            return Err(ServiceError::Provider(ProviderError::InvalidCredentials(
                "API key is empty or too large".to_owned(),
            )));
        }
        let attempt = AuthAttempt {
            id: attempt_id(),
            provider_id: provider_id.to_owned(),
            method: "api_key".to_owned(),
            status: AttemptStatus::Authenticated,
            authorization_url: None,
            verifier: None,
            state: None,
            // An API key attempt never leaves the machine, so it has no redirect.
            redirect_uri: None,
            exchange_in_progress: false,
            credential: Some(Credential::api_key(provider_id, api_key)),
            account_id: None,
            error_code: None,
            expires_at: OffsetDateTime::now_utc() + Duration::minutes(ATTEMPT_TTL_MINUTES),
        };
        let view = AttemptView::from(&attempt);
        self.attempts
            .lock()
            .await
            .insert(attempt.id.clone(), attempt);
        self.schedule_attempt_expiry(view.id.clone(), view.expires_at.clone());
        Ok(view)
    }

    pub async fn start_oauth(&self, provider_id: &str) -> Result<AttemptView, ServiceError> {
        self.validate_method(provider_id, "oauth")?;
        if provider_id != "openai" {
            return Err(ServiceError::InvalidMethod {
                provider: provider_id.to_owned(),
                method: "oauth".to_owned(),
            });
        }
        let Some(redirect_uri) = self.oauth_redirect_uri() else {
            return Err(ServiceError::CallbackUnavailable);
        };
        let pending = oauth::begin(&self.endpoints.openai_oauth, &redirect_uri)?;
        let attempt = AuthAttempt {
            id: attempt_id(),
            provider_id: provider_id.to_owned(),
            method: "oauth".to_owned(),
            status: AttemptStatus::Pending,
            authorization_url: Some(pending.authorization_url),
            verifier: Some(pending.verifier),
            state: Some(pending.state),
            redirect_uri: Some(redirect_uri),
            exchange_in_progress: false,
            credential: None,
            account_id: None,
            error_code: None,
            expires_at: OffsetDateTime::now_utc() + Duration::minutes(ATTEMPT_TTL_MINUTES),
        };
        let view = AttemptView::from(&attempt);
        self.attempts
            .lock()
            .await
            .insert(attempt.id.clone(), attempt);
        self.schedule_attempt_expiry(view.id.clone(), view.expires_at.clone());
        Ok(view)
    }

    pub async fn attempt(&self, id: &str) -> Result<AttemptView, ServiceError> {
        let mut attempts = self.attempts.lock().await;
        let attempt = attempts.get_mut(id).ok_or(ServiceError::AttemptNotFound)?;
        expire_attempt(attempt);
        Ok(AttemptView::from(&*attempt))
    }

    pub async fn complete_oauth_callback(
        &self,
        state: &str,
        code: Option<&str>,
        error: Option<&str>,
    ) -> Result<(), ServiceError> {
        let (id, verifier, redirect_uri) = {
            let mut attempts = self.attempts.lock().await;
            let attempt = attempts
                .values_mut()
                .find(|attempt| attempt.state.as_deref() == Some(state))
                .ok_or(ServiceError::AttemptNotFound)?;
            expire_attempt(attempt);
            if attempt.status != AttemptStatus::Pending || attempt.exchange_in_progress {
                return Err(ServiceError::AttemptNotReady);
            }
            oauth::validate_callback(attempt.state.as_deref().unwrap_or_default(), state)?;
            if error.is_some() || code.is_none() {
                attempt.status = AttemptStatus::Cancelled;
                attempt.error_code = Some("auth_cancelled");
                clear_oauth_material(attempt);
                return Ok(());
            }
            attempt.exchange_in_progress = true;
            (
                attempt.id.clone(),
                attempt
                    .verifier
                    .clone()
                    .ok_or(ServiceError::AttemptNotReady)?,
                attempt
                    .redirect_uri
                    .clone()
                    .ok_or(ServiceError::AttemptNotReady)?,
            )
        };

        let result = oauth::exchange(
            &self.http,
            &self.endpoints.openai_oauth,
            &redirect_uri,
            code.unwrap_or_default(),
            &verifier,
        )
        .await;
        let mut attempts = self.attempts.lock().await;
        let attempt = attempts.get_mut(&id).ok_or(ServiceError::AttemptNotFound)?;
        attempt.exchange_in_progress = false;
        if attempt.status != AttemptStatus::Pending {
            clear_oauth_material(attempt);
            return Err(ServiceError::AttemptNotReady);
        }
        clear_oauth_material(attempt);
        match result {
            Ok(tokens) => match openai::account_id(&tokens.access_token) {
                Ok(account_id) => {
                    attempt.credential = Some(Credential::oauth(
                        "openai",
                        tokens.access_token,
                        tokens.refresh_token,
                        tokens.expires_at,
                    ));
                    attempt.account_id = Some(account_id);
                    attempt.status = AttemptStatus::Authenticated;
                    attempt.error_code = None;
                }
                Err(error) => {
                    attempt.status = AttemptStatus::Failed;
                    attempt.error_code = Some(provider_error_code(&error));
                }
            },
            Err(error) => {
                attempt.status = AttemptStatus::Failed;
                attempt.error_code = Some(provider_error_code(&error));
            }
        }
        Ok(())
    }

    pub async fn commit_attempt(
        &self,
        provider_id: &str,
        attempt_id: &str,
        replacement_default_model: Option<&str>,
    ) -> Result<Value, ServiceError> {
        let descriptor = descriptor(provider_id)?;
        let lock = self.provider_lock(provider_id)?;
        let _guard = lock.lock().await;
        let attempt = {
            let mut attempts = self.attempts.lock().await;
            let attempt = attempts
                .get_mut(attempt_id)
                .ok_or(ServiceError::AttemptNotFound)?;
            expire_attempt(attempt);
            if attempt.provider_id != provider_id || attempt.status != AttemptStatus::Authenticated
            {
                return Err(ServiceError::AttemptNotReady);
            }
            attempt.clone()
        };
        let credential = attempt
            .credential
            .clone()
            .ok_or(ServiceError::AttemptNotReady)?;
        let models = self
            .discover(provider_id, &credential, attempt.account_id.as_deref())
            .await?;
        let current_default = providers::default_model(&self.db)
            .map_err(|error| ServiceError::State(error.to_string()))?;
        let starter = starter_model(descriptor, &models)?;
        let selected = match &current_default {
            Some((provider, model)) if provider == provider_id => {
                if models.iter().any(|candidate| candidate.id == *model)
                    && replacement_default_model.is_none()
                {
                    model.clone()
                } else {
                    let replacement = replacement_default_model.ok_or_else(|| {
                        ServiceError::DefaultUnavailable(
                            models.iter().map(|model| model.id.clone()).collect(),
                        )
                    })?;
                    if !models.iter().any(|candidate| candidate.id == replacement) {
                        return Err(ServiceError::UnknownModel);
                    }
                    replacement.to_owned()
                }
            }
            Some(_) if replacement_default_model.is_some() => {
                return Err(ServiceError::UnknownModel);
            }
            _ => starter,
        };
        self.readiness(
            provider_id,
            &selected,
            &credential,
            attempt.account_id.as_deref(),
        )
        .await?;

        let reference = self.store.write(&credential)?;
        let commit = ConnectionCommit {
            connection: Connection {
                provider_id: provider_id.to_owned(),
                auth_method: credential.auth_method().to_owned(),
                secret_ref: reference.clone(),
                account_id: attempt.account_id.clone(),
                credential_expires_at: credential.expires_at().map(str::to_owned),
            },
            models: models.iter().map(provider_model).collect(),
            default_model: Some(selected),
        };
        let old_reference = match providers::commit_connection(&self.db, &commit) {
            Ok(reference) => reference,
            Err(error) => {
                let _ = self.store.delete(&reference);
                return Err(ServiceError::State(error.to_string()));
            }
        };
        if let Some(old_reference) = old_reference {
            self.remove_obsolete_secret(&old_reference);
        }
        self.attempts.lock().await.remove(attempt_id);
        self.provider_row(provider_id)
    }

    pub fn list_rows(&self) -> Result<Vec<Value>, ServiceError> {
        let default = providers::default_model(&self.db)
            .map_err(|error| ServiceError::State(error.to_string()))?;
        DESCRIPTORS
            .iter()
            .map(|descriptor| self.provider_row_with_default(descriptor.id, default.as_ref()))
            .collect()
    }

    pub async fn refresh_catalog(&self, provider_id: &str) -> Result<Value, ServiceError> {
        let lock = self.provider_lock(provider_id)?;
        let _guard = lock.lock().await;
        let (connection, credential) = self.committed_credential(provider_id)?;
        let models = self
            .discover(provider_id, &credential, connection.account_id.as_deref())
            .await?;
        if self.default_model()?.is_some_and(|(provider, model)| {
            provider == provider_id && !models.iter().any(|candidate| candidate.id == model)
        }) {
            return Err(ServiceError::DefaultUnavailable(
                models.iter().map(|model| model.id.clone()).collect(),
            ));
        }
        providers::replace_catalog(
            &self.db,
            provider_id,
            &models.iter().map(provider_model).collect::<Vec<_>>(),
        )
        .map_err(|error| ServiceError::State(error.to_string()))?;
        self.provider_row(provider_id)
    }

    pub async fn set_default(
        &self,
        provider_id: &str,
        model_id: &str,
    ) -> Result<Value, ServiceError> {
        let lock = self.provider_lock(provider_id)?;
        let _guard = lock.lock().await;
        let (connection, credential) = self.committed_credential(provider_id)?;
        let models = self
            .discover(provider_id, &credential, connection.account_id.as_deref())
            .await?;
        if !models.iter().any(|model| model.id == model_id) {
            return Err(ServiceError::UnknownModel);
        }
        self.readiness(
            provider_id,
            model_id,
            &credential,
            connection.account_id.as_deref(),
        )
        .await?;
        providers::replace_catalog_and_set_default(
            &self.db,
            provider_id,
            &models.iter().map(provider_model).collect::<Vec<_>>(),
            model_id,
        )
        .map_err(|error| ServiceError::State(error.to_string()))?;
        Ok(json!({"provider":provider_id,"model":model_id}))
    }

    pub async fn disconnect(&self, provider_id: &str) -> Result<(), ServiceError> {
        let lock = self.provider_lock(provider_id)?;
        let _guard = lock.lock().await;
        let reference = providers::delete_connection(&self.db, provider_id).map_err(|error| {
            if error.to_string().contains("default") {
                ServiceError::DefaultInUse
            } else {
                ServiceError::State(error.to_string())
            }
        })?;
        if let Some(reference) = reference {
            self.remove_obsolete_secret(&reference);
        }
        Ok(())
    }

    pub fn default_model(&self) -> Result<Option<(String, String)>, ServiceError> {
        providers::default_model(&self.db).map_err(|error| ServiceError::State(error.to_string()))
    }

    pub fn auth_method(&self, provider_id: &str) -> Result<String, ServiceError> {
        let connection = providers::connection(&self.db, provider_id)
            .map_err(|error| ServiceError::State(error.to_string()))?
            .ok_or(ServiceError::NotConnected)?;
        Ok(connection.auth_method)
    }

    pub fn build_client(
        &self,
        provider_id: &str,
        model_id: &str,
    ) -> Result<Box<dyn ModelClient>, ServiceError> {
        let (connection, credential) = self.committed_credential(provider_id)?;
        self.client_for(
            provider_id,
            model_id,
            &credential,
            connection.account_id.as_deref(),
        )
    }

    pub async fn refresh_oauth_credential(&self, provider_id: &str) -> Result<(), ServiceError> {
        if provider_id != "openai" {
            return Err(ServiceError::InvalidMethod {
                provider: provider_id.to_owned(),
                method: "oauth".to_owned(),
            });
        }
        let lock = self.provider_lock(provider_id)?;
        let _guard = lock.lock().await;
        let (connection, credential) = self.committed_credential(provider_id)?;
        let (refresh_token, _) = match credential {
            Credential::Oauth {
                refresh_token: Some(refresh_token),
                access_token,
                ..
            } => (refresh_token, access_token),
            _ => return Err(ServiceError::Provider(ProviderError::Unauthorized)),
        };
        let tokens =
            oauth::refresh(&self.http, &self.endpoints.openai_oauth, &refresh_token).await?;
        let account_id = openai::account_id(&tokens.access_token)?;
        if connection
            .account_id
            .as_deref()
            .is_some_and(|old| old != account_id)
        {
            return Err(ServiceError::Provider(ProviderError::InvalidCredentials(
                "refreshed token belongs to a different ChatGPT account".to_owned(),
            )));
        }
        let refreshed = Credential::oauth(
            provider_id,
            tokens.access_token,
            tokens.refresh_token,
            tokens.expires_at,
        );
        let new_reference = self.store.write(&refreshed)?;
        let replaced = providers::replace_secret_reference(
            &self.db,
            provider_id,
            &connection.secret_ref,
            &new_reference,
            refreshed.expires_at(),
        )
        .map_err(|error| ServiceError::State(error.to_string()))?;
        if !replaced {
            let _ = self.store.delete(&new_reference);
            return Err(ServiceError::State(
                "credential changed during refresh".to_owned(),
            ));
        }
        self.remove_obsolete_secret(&connection.secret_ref);
        Ok(())
    }

    fn provider_row(&self, provider_id: &str) -> Result<Value, ServiceError> {
        let default = providers::default_model(&self.db)
            .map_err(|error| ServiceError::State(error.to_string()))?;
        self.provider_row_with_default(provider_id, default.as_ref())
    }

    fn provider_row_with_default(
        &self,
        provider_id: &str,
        default: Option<&(String, String)>,
    ) -> Result<Value, ServiceError> {
        let descriptor = descriptor(provider_id)?;
        let connection = providers::connection(&self.db, provider_id)
            .map_err(|error| ServiceError::State(error.to_string()))?;
        let catalog = providers::catalog(&self.db, provider_id)
            .map_err(|error| ServiceError::State(error.to_string()))?;
        let connected = connection.is_some();
        let available = connection
            .as_ref()
            .is_some_and(|connection| self.store.read(&connection.secret_ref, provider_id).is_ok());
        let is_default = default.is_some_and(|(provider, _)| provider == provider_id);
        let models = catalog
            .as_ref()
            .map(|catalog| {
                catalog
                    .models
                    .iter()
                    .map(|model| json!({"id":model.id,"name":model.name}))
                    .collect::<Vec<_>>()
            })
            .unwrap_or_default();
        let stale = catalog
            .as_ref()
            .and_then(|catalog| {
                OffsetDateTime::parse(
                    &catalog.expires_at,
                    &time::format_description::well_known::Rfc3339,
                )
                .ok()
            })
            .is_some_and(|expires| expires <= OffsetDateTime::now_utc());
        Ok(json!({
            "id":descriptor.id,
            "name":descriptor.name,
            "kind":"native",
            "available":available,
            "unavailable_reason":if connected && !available { Some("credential_store_failed") } else { None },
            "auth_methods":descriptor.auth_methods,
            "auth_method":connection.as_ref().map(|connection| connection.auth_method.as_str()),
            "connected":connected,
            "is_default":is_default,
            "default_model":if is_default { default.map(|(_, model)| model.as_str()) } else { None },
            "catalog_verified_at":catalog.as_ref().map(|catalog| catalog.verified_at.as_str()),
            "catalog_stale":stale,
            "policy_url":descriptor.policy_url,
            "models":models,
        }))
    }

    async fn discover(
        &self,
        provider_id: &str,
        credential: &Credential,
        account_id: Option<&str>,
    ) -> Result<Vec<CatalogModel>, ServiceError> {
        match (provider_id, credential) {
            ("openai", Credential::ApiKey { api_key, .. }) => Ok(openai::discover_platform_models(
                &self.http,
                api_key,
                &self.endpoints.openai_platform_models,
            )
            .await?),
            ("openai", Credential::Oauth { access_token, .. }) => {
                Ok(openai::discover_chatgpt_models(
                    &self.http,
                    access_token,
                    account_id.ok_or_else(|| {
                        ServiceError::Provider(ProviderError::InvalidCredentials(
                            "ChatGPT credential has no account id".to_owned(),
                        ))
                    })?,
                    &self.endpoints.openai_chatgpt_models,
                )
                .await?)
            }
            ("gemini", Credential::ApiKey { api_key, .. }) => {
                Ok(
                    gemini::discover_models(&self.http, api_key, &self.endpoints.gemini_models)
                        .await?,
                )
            }
            ("anthropic", Credential::ApiKey { api_key, .. }) => Ok(anthropic::discover_models(
                &self.http,
                api_key,
                &self.endpoints.anthropic_models,
            )
            .await?),
            _ => Err(ServiceError::InvalidMethod {
                provider: provider_id.to_owned(),
                method: credential.auth_method().to_owned(),
            }),
        }
    }

    async fn readiness(
        &self,
        provider_id: &str,
        model_id: &str,
        credential: &Credential,
        account_id: Option<&str>,
    ) -> Result<(), ServiceError> {
        let client = self.client_for(provider_id, model_id, credential, account_id)?;
        readiness_of(client.as_ref()).await
    }
}

/// Asked twice before it is refused, because one empty answer does not
/// mean the model cannot answer. A provider may end a turn with nothing in it,
/// and this check treating that as a verdict refused models that worked seconds
/// later on the same account: an intermittent refusal to set a default that is
/// perfectly good. A model that is genuinely unavailable answers nothing both
/// times, so the second ask costs one short request on the rare path and
/// settles the common one.
async fn readiness_of(client: &dyn ModelClient) -> Result<(), ServiceError> {
    let mut last = None;
    for _ in 0..2 {
        let response = client
            .complete(&[Message::text("user", READINESS_PROMPT)], &[], 32)
            .await?;
        if response.usage.input_tokens > 0 && response.usage.output_tokens > 0 {
            return Ok(());
        }
        last = Some(response);
    }
    let usage = last.map(|response| response.usage).unwrap_or_default();
    Err(ServiceError::Provider(ProviderError::InvalidResponse(
        format!(
            "the model answered twice with nothing in it \
             (input {} and output {} tokens the second time)",
            usage.input_tokens, usage.output_tokens
        ),
    )))
}

impl ProviderService {
    fn client_for(
        &self,
        provider_id: &str,
        model_id: &str,
        credential: &Credential,
        account_id: Option<&str>,
    ) -> Result<Box<dyn ModelClient>, ServiceError> {
        match (provider_id, credential) {
            ("openai", Credential::ApiKey { api_key, .. }) => {
                Ok(Box::new(openai::OpenAiResponsesClient::new(
                    model_id,
                    openai::OpenAiAuth::ApiKey(api_key.clone()),
                    &self.endpoints.openai_platform_responses,
                    &self.endpoints.openai_chatgpt_responses,
                )?))
            }
            ("openai", Credential::Oauth { access_token, .. }) => {
                Ok(Box::new(openai::OpenAiResponsesClient::new(
                    model_id,
                    openai::OpenAiAuth::ChatGpt {
                        access_token: access_token.clone(),
                        account_id: account_id
                            .ok_or_else(|| {
                                ServiceError::Provider(ProviderError::InvalidCredentials(
                                    "ChatGPT credential has no account id".to_owned(),
                                ))
                            })?
                            .to_owned(),
                    },
                    &self.endpoints.openai_platform_responses,
                    &self.endpoints.openai_chatgpt_responses,
                )?))
            }
            ("gemini", Credential::ApiKey { api_key, .. }) => {
                Ok(Box::new(gemini::GeminiClient::with_root(
                    model_id,
                    api_key,
                    &self.endpoints.gemini_api_root,
                )?))
            }
            ("anthropic", Credential::ApiKey { api_key, .. }) => {
                Ok(Box::new(anthropic::AnthropicMessagesClient::with_url(
                    model_id,
                    api_key,
                    &self.endpoints.anthropic_messages,
                )?))
            }
            _ => Err(ServiceError::InvalidMethod {
                provider: provider_id.to_owned(),
                method: credential.auth_method().to_owned(),
            }),
        }
    }

    fn committed_credential(
        &self,
        provider_id: &str,
    ) -> Result<(Connection, Credential), ServiceError> {
        descriptor(provider_id)?;
        let connection = providers::connection(&self.db, provider_id)
            .map_err(|error| ServiceError::State(error.to_string()))?
            .ok_or(ServiceError::NotConnected)?;
        let credential = self.store.read(&connection.secret_ref, provider_id)?;
        Ok((connection, credential))
    }

    fn validate_method(&self, provider_id: &str, method: &str) -> Result<(), ServiceError> {
        let descriptor = descriptor(provider_id)?;
        if descriptor.auth_methods.contains(&method) {
            Ok(())
        } else {
            Err(ServiceError::InvalidMethod {
                provider: provider_id.to_owned(),
                method: method.to_owned(),
            })
        }
    }

    fn provider_lock(&self, provider_id: &str) -> Result<Arc<Mutex<()>>, ServiceError> {
        self.provider_locks
            .get(provider_id)
            .cloned()
            .ok_or_else(|| ServiceError::UnknownProvider(provider_id.to_owned()))
    }

    fn remove_obsolete_secret(&self, reference: &str) {
        if let Err(error) = self.store.delete(reference) {
            tracing::warn!(
                category = "credential_cleanup_failed",
                error = %error,
                "an unreferenced provider credential could not be removed"
            );
        }
    }

    fn schedule_attempt_expiry(&self, attempt_id: String, expires_at: String) {
        let attempts = self.attempts.clone();
        tokio::spawn(async move {
            let Ok(expires_at) =
                OffsetDateTime::parse(&expires_at, &time::format_description::well_known::Rfc3339)
            else {
                return;
            };
            let wait = (expires_at - OffsetDateTime::now_utc())
                .try_into()
                .unwrap_or(std::time::Duration::ZERO);
            tokio::time::sleep(wait).await;
            if let Some(attempt) = attempts.lock().await.get_mut(&attempt_id) {
                expire_attempt(attempt);
            }
        });
    }
}

fn descriptor(provider_id: &str) -> Result<&'static ProviderDescriptor, ServiceError> {
    DESCRIPTORS
        .iter()
        .find(|descriptor| descriptor.id == provider_id)
        .ok_or_else(|| ServiceError::UnknownProvider(provider_id.to_owned()))
}

fn starter_model(
    descriptor: &ProviderDescriptor,
    models: &[CatalogModel],
) -> Result<String, ServiceError> {
    for preferred in descriptor.starter_preferences {
        if models.iter().any(|model| model.id == *preferred) {
            return Ok((*preferred).to_owned());
        }
    }
    models.last().map(|model| model.id.clone()).ok_or_else(|| {
        ServiceError::Provider(ProviderError::InvalidResponse(
            "provider catalog is empty".to_owned(),
        ))
    })
}

fn provider_model(model: &CatalogModel) -> ProviderModel {
    ProviderModel {
        id: model.id.clone(),
        name: model.name.clone(),
        capabilities: json!({"text":true,"tools":true}),
    }
}

fn attempt_id() -> String {
    format!("pa_{}", uuid::Uuid::new_v4().simple())
}

fn expire_attempt(attempt: &mut AuthAttempt) {
    if attempt.expires_at <= OffsetDateTime::now_utc()
        && matches!(
            attempt.status,
            AttemptStatus::Pending | AttemptStatus::Authenticated
        )
    {
        attempt.status = AttemptStatus::Failed;
        attempt.error_code = Some("auth_timeout");
        attempt.credential = None;
        clear_oauth_material(attempt);
    }
}

fn clear_oauth_material(attempt: &mut AuthAttempt) {
    attempt.authorization_url = None;
    attempt.verifier = None;
    attempt.state = None;
}

fn provider_error_code(error: &ProviderError) -> &'static str {
    match error {
        ProviderError::MissingCredentials
        | ProviderError::InvalidCredentials(_)
        | ProviderError::Unauthorized => "invalid_credentials",
        ProviderError::Forbidden => "consent_required",
        ProviderError::QuotaExhausted => "quota_exhausted",
        ProviderError::RateLimited => "rate_limited",
        ProviderError::ModelUnavailable => "model_unavailable",
        ProviderError::Unavailable | ProviderError::Request(_) => "provider_unavailable",
        ProviderError::InvalidResponse(_) => "invalid_provider_response",
        ProviderError::CredentialStore(_) => "credential_store_failed",
        ProviderError::UnknownProvider(_) => "invalid_provider_response",
    }
}

#[cfg(test)]
mod endpoint_config_tests {
    use super::ProviderEndpoints;

    /// The env lock keeps these two from racing each other, because
    /// `std::env` is process wide.
    static ENV_LOCK: std::sync::Mutex<()> = std::sync::Mutex::new(());

    #[test]
    fn an_override_is_used_verbatim() {
        let _guard = ENV_LOCK.lock().unwrap_or_else(|error| error.into_inner());
        unsafe {
            std::env::set_var(
                "VADGR_OPENAI_RESPONSES_URL",
                "http://127.0.0.1:9/v1/responses",
            )
        };
        let endpoints = ProviderEndpoints::from_env();
        assert_eq!(
            endpoints.openai_platform_responses,
            "http://127.0.0.1:9/v1/responses"
        );
        // Anything not overridden keeps its published value.
        assert_eq!(
            endpoints.anthropic_messages,
            ProviderEndpoints::default().anthropic_messages
        );
        unsafe { std::env::remove_var("VADGR_OPENAI_RESPONSES_URL") };
    }

    #[test]
    fn an_empty_or_blank_override_is_ignored_rather_than_used() {
        // An empty variable is a shell accident, not an instruction to send
        // requests to the empty string.
        let _guard = ENV_LOCK.lock().unwrap_or_else(|error| error.into_inner());
        let published = ProviderEndpoints::default().gemini_api_root;
        for value in ["", "   "] {
            unsafe { std::env::set_var("VADGR_GEMINI_API_ROOT", value) };
            assert_eq!(ProviderEndpoints::from_env().gemini_api_root, published);
        }
        unsafe { std::env::remove_var("VADGR_GEMINI_API_ROOT") };
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::engine::types::{ModelResponse, StopReason, Usage};
    use std::sync::Mutex;

    /// Answers from a fixed script, so a test can say what the provider does on
    /// the first ask and what it does on the second.
    struct ScriptedModel(Mutex<std::collections::VecDeque<Usage>>);

    #[async_trait::async_trait]
    impl ModelClient for ScriptedModel {
        async fn complete(
            &self,
            _messages: &[Message],
            _tools: &[crate::engine::types::ToolSpec],
            _max_tokens: u32,
        ) -> Result<ModelResponse, ProviderError> {
            let usage = self.0.lock().unwrap().pop_front().unwrap_or_default();
            Ok(ModelResponse {
                content: Vec::new(),
                stop_reason: Some(StopReason::EndTurn),
                usage,
            })
        }
    }

    fn scripted(usages: Vec<Usage>) -> ScriptedModel {
        ScriptedModel(Mutex::new(usages.into()))
    }

    fn spent(input: u64, output: u64) -> Usage {
        Usage {
            input_tokens: input,
            output_tokens: output,
        }
    }

    /// `0.4.9` left this open: one empty turn from the provider refused a model
    /// that answered perfectly seconds later.
    #[tokio::test]
    async fn one_empty_answer_does_not_condemn_a_working_model() {
        let model = scripted(vec![spent(0, 0), spent(12, 3)]);
        readiness_of(&model)
            .await
            .expect("the second answer settles it");
    }

    #[tokio::test]
    async fn a_model_that_answers_nothing_twice_is_refused() {
        let model = scripted(vec![spent(0, 0), spent(0, 0)]);
        let error = readiness_of(&model).await.expect_err("two empty answers");
        assert!(
            error.to_string().contains("twice"),
            "the message says it asked twice: {error}"
        );
    }

    #[tokio::test]
    async fn methods_are_provider_owned_and_api_keys_are_staged_without_echo() {
        let directory = tempfile::tempdir().unwrap();
        let service = ProviderService::new(
            Db::open(":memory:").unwrap(),
            CredentialStore::new(directory.path().join("credentials")).unwrap(),
            ProviderEndpoints::default(),
        )
        .unwrap();
        let attempt = service
            .start_api_key("anthropic", "secret-value".to_owned())
            .await
            .unwrap();
        assert_eq!(attempt.status, "authenticated");
        assert!(
            !serde_json::to_string(&attempt)
                .unwrap()
                .contains("secret-value")
        );
        assert!(service.start_oauth("gemini").await.is_err());
    }

    #[tokio::test]
    async fn an_unavailable_callback_blocks_only_oauth_start() {
        let directory = tempfile::tempdir().unwrap();
        let service = ProviderService::new(
            Db::open(":memory:").unwrap(),
            CredentialStore::new(directory.path().join("credentials")).unwrap(),
            ProviderEndpoints::default(),
        )
        .unwrap();
        service.set_oauth_callback_port(None);

        let error = service.start_oauth("openai").await.unwrap_err();
        assert!(matches!(error, ServiceError::CallbackUnavailable));
        assert_eq!(error.code(), "PROVIDER_UNAVAILABLE");
        assert_eq!(error.category(), Some("provider_unavailable"));
        assert!(
            service
                .start_api_key("openai", "secret".to_owned())
                .await
                .is_ok()
        );
    }

    #[test]
    fn descriptor_order_and_starter_policy_are_stable() {
        assert_eq!(
            DESCRIPTORS.map(|descriptor| descriptor.id),
            ["openai", "gemini", "anthropic"]
        );
        let models = vec![
            CatalogModel {
                id: "gpt-old".to_owned(),
                name: "Old".to_owned(),
            },
            CatalogModel {
                id: "gpt-5.6-sol".to_owned(),
                name: "Sol".to_owned(),
            },
        ];
        assert_eq!(
            starter_model(&DESCRIPTORS[0], &models).unwrap(),
            "gpt-5.6-sol"
        );
    }

    #[test]
    fn expired_attempts_fail_closed_and_discard_staged_credentials() {
        let mut attempt = AuthAttempt {
            id: "pa_expired".to_owned(),
            provider_id: "openai".to_owned(),
            method: "api_key".to_owned(),
            status: AttemptStatus::Authenticated,
            authorization_url: Some("https://auth.example".to_owned()),
            redirect_uri: None,
            verifier: Some("verifier".to_owned()),
            state: Some("state".to_owned()),
            exchange_in_progress: false,
            credential: Some(Credential::api_key("openai", "secret")),
            account_id: None,
            error_code: None,
            expires_at: OffsetDateTime::now_utc() - Duration::seconds(1),
        };

        expire_attempt(&mut attempt);

        assert_eq!(attempt.status, AttemptStatus::Failed);
        assert_eq!(attempt.error_code, Some("auth_timeout"));
        assert!(attempt.credential.is_none());
        assert!(attempt.authorization_url.is_none());
        assert!(attempt.verifier.is_none());
        assert!(attempt.state.is_none());
    }

    /// The browser must be sent to the port the listener actually bound.
    ///
    /// The redirect used to be a constant, so when the preferred port was taken
    /// and the listener bound the other registered one, the authorization URL
    /// still named the port nothing was serving. The person approved the
    /// sign-in and the redirect landed nowhere.
    #[tokio::test]
    async fn the_authorization_url_names_the_port_the_listener_bound() {
        let directory = tempfile::tempdir().unwrap();
        let service = ProviderService::new(
            Db::open(":memory:").unwrap(),
            CredentialStore::new(directory.path().join("credentials")).unwrap(),
            ProviderEndpoints::default(),
        )
        .unwrap();

        service.set_oauth_callback_port(Some(1457));
        let pending = service.start_oauth("openai").await.unwrap();
        let url = url::Url::parse(pending.authorization_url.as_deref().unwrap()).unwrap();
        let redirect = url
            .query_pairs()
            .find(|(key, _)| key == "redirect_uri")
            .map(|(_, value)| value.into_owned())
            .expect("the authorization URL carries a redirect");

        assert_eq!(
            redirect, "http://localhost:1457/auth/callback",
            "the redirect must name the bound port, not the preferred one"
        );
    }

    /// With no listener there is no port, and the flow refuses rather than
    /// sending someone to a browser whose redirect cannot be answered.
    #[tokio::test]
    async fn no_bound_port_refuses_the_attempt() {
        let directory = tempfile::tempdir().unwrap();
        let service = ProviderService::new(
            Db::open(":memory:").unwrap(),
            CredentialStore::new(directory.path().join("credentials")).unwrap(),
            ProviderEndpoints::default(),
        )
        .unwrap();

        service.set_oauth_callback_port(None);
        assert!(matches!(
            service.start_oauth("openai").await,
            Err(ServiceError::CallbackUnavailable)
        ));
    }

    #[tokio::test]
    async fn cancelled_oauth_attempt_never_becomes_authenticated() {
        let directory = tempfile::tempdir().unwrap();
        let service = ProviderService::new(
            Db::open(":memory:").unwrap(),
            CredentialStore::new(directory.path().join("credentials")).unwrap(),
            ProviderEndpoints::default(),
        )
        .unwrap();
        // The listener state is a precondition, not a default: a service with
        // no bound callback port refuses to start an OAuth attempt.
        service.set_oauth_callback_port(Some(1455));
        let pending = service.start_oauth("openai").await.unwrap();
        let url = url::Url::parse(pending.authorization_url.as_deref().unwrap()).unwrap();
        let state = url
            .query_pairs()
            .find(|(key, _)| key == "state")
            .map(|(_, value)| value.into_owned())
            .unwrap();

        service
            .complete_oauth_callback(&state, None, Some("access_denied"))
            .await
            .unwrap();

        let cancelled = service.attempt(&pending.id).await.unwrap();
        assert_eq!(cancelled.status, "cancelled");
        assert_eq!(cancelled.error_code, Some("auth_cancelled"));
        {
            let attempts = service.attempts.lock().await;
            let stored = attempts.get(&pending.id).unwrap();
            assert!(stored.authorization_url.is_none());
            assert!(stored.verifier.is_none());
            assert!(stored.state.is_none());
        }
        assert!(
            service
                .commit_attempt("openai", &pending.id, None)
                .await
                .is_err()
        );
    }
}
