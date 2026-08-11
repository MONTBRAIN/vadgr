use crate::error::{ApiError, ApiResult};
use crate::state::AppState;
use axum::extract::{Path, State};
use axum::Json;
use serde_json::{json, Value};

pub async fn list_devices(State(state): State<AppState>) -> ApiResult<Json<Vec<Value>>> {
    crate::db::devices::list_all(&state.db)
        .map(Json)
        .map_err(|e| ApiError::new(axum::http::StatusCode::INTERNAL_SERVER_ERROR, "INTERNAL", e.to_string()))
}

/// Revoke a device. Future requests with its token fail gate 2, and **any live
/// sockets it holds are dropped now**: revocation that only applied to the next
/// request would leave a socket streaming to a phone the owner just unpaired.
pub async fn revoke_device(
    State(state): State<AppState>,
    Path(device_id): Path<String>,
) -> ApiResult<Json<Value>> {
    let deleted = crate::db::devices::delete(&state.db, &device_id).map_err(|e| {
        ApiError::new(axum::http::StatusCode::INTERNAL_SERVER_ERROR, "INTERNAL", e.to_string())
    })?;
    if !deleted {
        return Err(ApiError::device_not_found(&device_id));
    }
    state.ws.disconnect_device(&device_id);
    Ok(Json(json!({ "status": "revoked", "device_id": device_id })))
}
