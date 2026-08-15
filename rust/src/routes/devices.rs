use crate::error::{ApiError, ApiResult};
use crate::state::AppState;
use axum::Json;
use axum::extract::{Path, State};
use serde_json::{Value, json};

pub async fn list_devices(State(state): State<AppState>) -> ApiResult<Json<Vec<Value>>> {
    crate::db::devices::list_all(&state.db)
        .map(Json)
        .map_err(ApiError::internal)
}

/// Revoke a device. Future requests with its token fail gate 2, and **any live
/// sockets it holds are dropped now**: revocation that only applied to the next
/// request would leave a socket streaming to a phone the owner just unpaired.
pub async fn revoke_device(
    State(state): State<AppState>,
    Path(device_id): Path<String>,
) -> ApiResult<Json<Value>> {
    let deleted = crate::db::devices::delete(&state.db, &device_id).map_err(ApiError::internal)?;
    if !deleted {
        return Err(ApiError::device_not_found(&device_id));
    }
    state.ws.disconnect_device(&device_id);
    Ok(Json(json!({ "status": "revoked", "device_id": device_id })))
}
