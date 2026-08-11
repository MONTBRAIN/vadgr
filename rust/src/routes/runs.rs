//! The surviving runs surface, minus everything that needs a loop.

use crate::error::{ApiError, ApiResult};
use crate::state::AppState;
use axum::extract::{Path, Query, State};
use axum::Json;
use serde::Deserialize;
use serde_json::Value;

#[derive(Deserialize)]
pub struct ListQuery {
    pub status: Option<String>,
}

pub async fn list_runs(
    State(state): State<AppState>,
    Query(q): Query<ListQuery>,
) -> ApiResult<Json<Vec<Value>>> {
    let rows = crate::db::runs::list_all(&state.db, q.status.as_deref())
        .map_err(ApiError::internal)?;
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

/// Cancel, and it ports **completely** rather than partially.
///
/// The Python route signals the asyncio task if one exists and then writes
/// `failed`. With no engine there is never a task, and the Python daemon takes
/// exactly the same branch when the task is absent - so this is the same
/// behaviour, not a reduced one.
///
/// It still records `failed` rather than a `cancelled` state, which is wrong
/// and is deliberately left wrong: nothing writes `cancelled` today, the phone
/// draws what the daemon sends, and the split arrives at `0.6.0`.
pub async fn cancel_run(
    State(state): State<AppState>,
    Path(run_id): Path<String>,
) -> ApiResult<Json<Value>> {
    let run = crate::db::runs::get(&state.db, &run_id)
        .map_err(ApiError::internal)?
        .ok_or_else(|| ApiError::run_not_found(&run_id))?;

    let status = run.get("status").and_then(|v| v.as_str()).unwrap_or("");
    if matches!(status, "completed" | "failed") {
        return Err(ApiError::run_not_active());
    }

    let updated = crate::db::runs::update_status(&state.db, &run_id, "failed")
        .map_err(ApiError::internal)?
        .ok_or_else(|| ApiError::run_not_found(&run_id))?;
    Ok(Json(updated))
}
