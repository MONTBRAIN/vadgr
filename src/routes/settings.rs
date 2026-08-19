//! The computer-use setting.
//!
//! `GET` serves the daemon-owned state read at startup. `PUT` writes that state
//! and replaces the cached response with the result.

use crate::error::{ApiError, ApiResult};
use crate::state::AppState;
use axum::Json;
use axum::extract::State;
use axum::extract::rejection::JsonRejection;
use axum::response::{IntoResponse, Response};
use serde::Deserialize;
use serde_json::Value;

pub async fn get_computer_use(State(state): State<AppState>) -> Json<Value> {
    Json(state.computer_use_status.read().unwrap().clone())
}

/// Strict, like the Python body it mirrors: an undeclared field is a 422, not
/// silently dropped.
#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Update {
    pub enabled: bool,
}

pub async fn put_computer_use(
    State(state): State<AppState>,
    body: Result<Json<Update>, JsonRejection>,
) -> Response {
    let Json(body) = match body {
        Ok(body) => body,
        Err(rejection) => return super::validation_error(rejection).into_response(),
    };
    update(state, body.enabled).await.into_response()
}

async fn update(state: AppState, enabled: bool) -> ApiResult<Json<Value>> {
    let service = state.computer_use_setup.clone();
    let result = tokio::task::spawn_blocking(move || {
        if enabled {
            service.enable()
        } else {
            service.disable()
        }
    })
    .await
    .map_err(ApiError::internal)?
    .map_err(ApiError::internal)?;
    *state.computer_use_status.write().unwrap() = result.clone();
    Ok(Json(result))
}
