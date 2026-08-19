//! The surviving runs surface, minus everything that needs a loop.

use crate::error::{ApiError, ApiResult};
use crate::state::AppState;
use axum::Json;
use axum::extract::rejection::JsonRejection;
use axum::extract::{Path, Query, State};
use axum::http::StatusCode;
use axum::response::{IntoResponse, Response};
use serde::Deserialize;
use serde_json::{Value, json};

#[derive(Deserialize)]
pub struct ListQuery {
    pub status: Option<String>,
}

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
pub struct StartBody {
    pub task: String,
    pub provider: Option<String>,
    pub model: Option<String>,
}

pub async fn start_run(
    State(state): State<AppState>,
    body: Result<Json<StartBody>, JsonRejection>,
) -> Response {
    let Json(body) = match body {
        Ok(body) => body,
        Err(rejection) => return super::validation_error(rejection).into_response(),
    };
    if body.task.trim().is_empty() {
        return semantic_validation("task must contain a non-whitespace character");
    }
    if body.provider.is_some() != body.model.is_some() {
        return semantic_validation("provider and model must be supplied together");
    }
    match state
        .supervisor
        .create(crate::engine::supervisor::StartRun {
            task: body.task,
            provider: body.provider,
            model: body.model,
        })
        .await
    {
        Ok(row) => (StatusCode::ACCEPTED, Json(row)).into_response(),
        Err(error) => ApiError::internal(error).into_response(),
    }
}

pub async fn list_runs(
    State(state): State<AppState>,
    Query(q): Query<ListQuery>,
) -> ApiResult<Json<Vec<Value>>> {
    let rows =
        crate::db::runs::list_all(&state.db, q.status.as_deref()).map_err(ApiError::internal)?;
    Ok(Json(rows))
}

pub async fn get_run(
    State(state): State<AppState>,
    Path(run_id): Path<String>,
) -> ApiResult<Json<Value>> {
    match crate::db::runs::get(&state.db, &run_id).map_err(ApiError::internal)? {
        Some(run) => Ok(Json(run)),
        None => Err(ApiError::run_not_found(&run_id)),
    }
}

/// Cancel an active run and record the published terminal state.
pub async fn cancel_run(
    State(state): State<AppState>,
    Path(run_id): Path<String>,
) -> ApiResult<Json<Value>> {
    match state.supervisor.cancel(&run_id).await {
        Ok(row) => Ok(Json(row)),
        Err(crate::engine::supervisor::RunError::NotFound) => Err(ApiError::run_not_found(&run_id)),
        Err(crate::engine::supervisor::RunError::NotActive) => Err(ApiError::run_not_active()),
        Err(error) => Err(ApiError::internal(error)),
    }
}

pub async fn resume_run(
    State(state): State<AppState>,
    Path(run_id): Path<String>,
) -> ApiResult<Json<Value>> {
    match state.supervisor.resume(&run_id).await {
        Ok(row) => Ok(Json(row)),
        Err(crate::engine::supervisor::RunError::NotFound) => Err(ApiError::run_not_found(&run_id)),
        Err(crate::engine::supervisor::RunError::NotResumable(status)) => {
            Err(ApiError::run_not_resumable(&status))
        }
        Err(error) => Err(ApiError::internal(error)),
    }
}

fn semantic_validation(message: &str) -> Response {
    (
        StatusCode::UNPROCESSABLE_ENTITY,
        Json(json!({"detail":[{"type":"value_error","msg":message}]})),
    )
        .into_response()
}
