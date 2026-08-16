use crate::auth::gate::is_loopback;
use crate::engine::provider::service::ServiceError;
use crate::error::{ApiError, ApiResult};
use crate::state::AppState;
use axum::extract::rejection::JsonRejection;
use axum::extract::{ConnectInfo, Path, Query, State};
use axum::http::StatusCode;
use axum::response::{Html, IntoResponse, Redirect, Response};
use axum::{Json, Router};
use serde::Deserialize;
use serde_json::{Value, json};
use std::net::SocketAddr;

pub async fn list_providers(State(state): State<AppState>) -> ApiResult<Json<Vec<Value>>> {
    Ok(Json(state.providers.list_rows().map_err(service_error)?))
}

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
pub struct StartAttemptBody {
    pub method: String,
    #[serde(default)]
    pub flow: Option<String>,
    #[serde(default)]
    pub api_key: Option<String>,
}

pub async fn start_attempt(
    State(state): State<AppState>,
    Path(provider_id): Path<String>,
    ConnectInfo(peer): ConnectInfo<SocketAddr>,
    body: Result<Json<StartAttemptBody>, JsonRejection>,
) -> Response {
    if let Err(error) = require_loopback(peer) {
        return error.into_response();
    }
    let Json(body) = match body {
        Ok(body) => body,
        Err(rejection) => return super::validation_error(rejection).into_response(),
    };
    let result = match body.method.as_str() {
        "api_key" if body.flow.is_none() => match body.api_key {
            Some(api_key) => state.providers.start_api_key(&provider_id, api_key).await,
            None => return semantic_validation("api_key is required for the api_key method"),
        },
        "oauth"
            if body.api_key.is_none() && body.flow.as_deref().unwrap_or("browser") == "browser" =>
        {
            state.providers.start_oauth(&provider_id).await
        }
        "oauth" if body.flow.as_deref() == Some("device_code") => {
            return invalid_auth("Device-code sign-in is not enabled for this account.");
        }
        _ => return invalid_auth("method and flow do not form a supported sign-in request"),
    };
    match result {
        Ok(attempt) => {
            let status = if attempt.status == "pending" {
                StatusCode::ACCEPTED
            } else {
                StatusCode::OK
            };
            (status, Json(attempt)).into_response()
        }
        Err(error) => service_error(error).into_response(),
    }
}

pub async fn get_attempt(
    State(state): State<AppState>,
    Path(attempt_id): Path<String>,
    ConnectInfo(peer): ConnectInfo<SocketAddr>,
) -> ApiResult<Json<impl serde::Serialize>> {
    require_loopback(peer)?;
    Ok(Json(
        state
            .providers
            .attempt(&attempt_id)
            .await
            .map_err(service_error)?,
    ))
}

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
pub struct CommitBody {
    pub attempt_id: String,
    #[serde(default)]
    pub replacement_default_model: Option<String>,
}

pub async fn commit_connection(
    State(state): State<AppState>,
    Path(provider_id): Path<String>,
    ConnectInfo(peer): ConnectInfo<SocketAddr>,
    body: Result<Json<CommitBody>, JsonRejection>,
) -> Response {
    if let Err(error) = require_loopback(peer) {
        return error.into_response();
    }
    let Json(body) = match body {
        Ok(body) => body,
        Err(rejection) => return super::validation_error(rejection).into_response(),
    };
    match state
        .providers
        .commit_attempt(
            &provider_id,
            &body.attempt_id,
            body.replacement_default_model.as_deref(),
        )
        .await
    {
        Ok(row) => Json(row).into_response(),
        Err(error) => service_error(error).into_response(),
    }
}

pub async fn delete_connection(
    State(state): State<AppState>,
    Path(provider_id): Path<String>,
    ConnectInfo(peer): ConnectInfo<SocketAddr>,
) -> Response {
    if let Err(error) = require_loopback(peer) {
        return error.into_response();
    }
    match state.providers.disconnect(&provider_id).await {
        Ok(()) => StatusCode::NO_CONTENT.into_response(),
        Err(error) => service_error(error).into_response(),
    }
}

pub async fn refresh_catalog(
    State(state): State<AppState>,
    Path(provider_id): Path<String>,
    ConnectInfo(peer): ConnectInfo<SocketAddr>,
) -> Response {
    if let Err(error) = require_loopback(peer) {
        return error.into_response();
    }
    match state.providers.refresh_catalog(&provider_id).await {
        Ok(row) => Json(row).into_response(),
        Err(error) => service_error(error).into_response(),
    }
}

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
pub struct DefaultModelBody {
    pub provider: String,
    pub model: String,
}

pub async fn put_default_model(
    State(state): State<AppState>,
    ConnectInfo(peer): ConnectInfo<SocketAddr>,
    body: Result<Json<DefaultModelBody>, JsonRejection>,
) -> Response {
    if let Err(error) = require_loopback(peer) {
        return error.into_response();
    }
    let Json(body) = match body {
        Ok(body) => body,
        Err(rejection) => return super::validation_error(rejection).into_response(),
    };
    match state
        .providers
        .set_default(&body.provider, &body.model)
        .await
    {
        Ok(default) => Json(default).into_response(),
        Err(error) => service_error(error).into_response(),
    }
}

#[derive(Deserialize)]
pub struct CallbackQuery {
    pub state: String,
    pub code: Option<String>,
    pub error: Option<String>,
}

pub async fn oauth_callback(
    State(state): State<AppState>,
    Query(query): Query<CallbackQuery>,
) -> Redirect {
    let accepted = query.error.is_none() && query.code.is_some();
    let result = state
        .providers
        .complete_oauth_callback(&query.state, query.code.as_deref(), query.error.as_deref())
        .await;
    if result.is_ok() && accepted {
        Redirect::to("/auth/complete")
    } else {
        Redirect::to("/auth/failed")
    }
}

pub async fn oauth_complete() -> Html<&'static str> {
    Html(
        "<!doctype html><title>Vadgr connected</title><p>Connection received. You can close this window.</p>",
    )
}

pub async fn oauth_failed() -> (StatusCode, Html<&'static str>) {
    (
        StatusCode::BAD_REQUEST,
        Html(
            "<!doctype html><title>Vadgr sign-in failed</title><p>The sign-in response was not accepted. Return to the terminal.</p>",
        ),
    )
}

pub fn callback_router(state: AppState) -> Router {
    Router::new()
        .route("/auth/callback", axum::routing::get(oauth_callback))
        .route("/auth/complete", axum::routing::get(oauth_complete))
        .route("/auth/failed", axum::routing::get(oauth_failed))
        .with_state(state)
}

fn require_loopback(peer: SocketAddr) -> ApiResult<()> {
    if is_loopback(&peer.ip().to_string()) {
        Ok(())
    } else {
        Err(ApiError::source_not_authorized())
    }
}

fn service_error(error: ServiceError) -> ApiError {
    let status = match &error {
        ServiceError::UnknownProvider(_) | ServiceError::InvalidMethod { .. } => {
            StatusCode::BAD_REQUEST
        }
        ServiceError::AttemptNotFound => StatusCode::NOT_FOUND,
        ServiceError::NotConnected
        | ServiceError::DefaultInUse
        | ServiceError::DefaultUnavailable(_)
        | ServiceError::AttemptNotReady => StatusCode::CONFLICT,
        ServiceError::UnknownModel => StatusCode::UNPROCESSABLE_ENTITY,
        ServiceError::CallbackUnavailable => StatusCode::SERVICE_UNAVAILABLE,
        ServiceError::Provider(
            crate::engine::types::ProviderError::MissingCredentials
            | crate::engine::types::ProviderError::InvalidCredentials(_)
            | crate::engine::types::ProviderError::Unauthorized,
        ) => StatusCode::UNAUTHORIZED,
        ServiceError::Provider(_) => StatusCode::SERVICE_UNAVAILABLE,
        ServiceError::State(_) => StatusCode::INTERNAL_SERVER_ERROR,
    };
    let details = match &error {
        ServiceError::DefaultUnavailable(models) => json!({"models":models}),
        _ if error.category().is_some() => json!({"category":error.category()}),
        _ => json!({}),
    };
    ApiError::new(status, error.code(), error.to_string()).with_details(details)
}

fn invalid_auth(message: &str) -> Response {
    ApiError::new(StatusCode::BAD_REQUEST, "INVALID_PROVIDER_AUTH", message).into_response()
}

fn semantic_validation(message: &str) -> Response {
    (
        StatusCode::UNPROCESSABLE_ENTITY,
        Json(json!({"detail":[{"type":"value_error","msg":message}]})),
    )
        .into_response()
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::engine::types::ProviderError;
    use http_body_util::BodyExt;

    #[tokio::test]
    async fn provider_failures_use_the_contract_status_code_and_category() {
        let response =
            service_error(ServiceError::Provider(ProviderError::QuotaExhausted)).into_response();
        assert_eq!(response.status(), StatusCode::SERVICE_UNAVAILABLE);
        let bytes = response.into_body().collect().await.unwrap().to_bytes();
        let body: Value = serde_json::from_slice(&bytes).unwrap();
        assert_eq!(body["error"]["code"], "PROVIDER_UNAVAILABLE");
        assert_eq!(body["error"]["details"]["category"], "quota_exhausted");
    }

    #[tokio::test]
    async fn invalid_credentials_are_distinct_from_provider_outages() {
        let response =
            service_error(ServiceError::Provider(ProviderError::Unauthorized)).into_response();
        assert_eq!(response.status(), StatusCode::UNAUTHORIZED);
        let bytes = response.into_body().collect().await.unwrap().to_bytes();
        let body: Value = serde_json::from_slice(&bytes).unwrap();
        assert_eq!(body["error"]["code"], "INVALID_CREDENTIALS");
        assert_eq!(body["error"]["details"]["category"], "invalid_credentials");
    }
}
