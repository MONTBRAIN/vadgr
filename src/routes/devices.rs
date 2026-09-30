use crate::db::devices::Adoption;
use crate::error::{ApiError, ApiResult};
use crate::state::AppState;
use crate::transport::Peer;
use axum::extract::{Path, State};
use axum::http::HeaderMap;
use axum::{Extension, Json};
use serde_json::{Value, json};

pub async fn list_devices(State(state): State<AppState>) -> ApiResult<Json<Vec<Value>>> {
    let mut devices = crate::db::devices::list_all(&state.db).map_err(ApiError::internal)?;
    for device in &mut devices {
        let Some(id) = device.get("id").and_then(Value::as_str) else {
            continue;
        };
        let connected = state.ws.device_connected(id);
        let bound =
            crate::db::devices::transport_names(&state.db, id).map_err(ApiError::internal)?;
        let transports =
            bound
                .into_iter()
                .filter_map(|name| {
                    state.transports.iter().find(|item| item.name() == name).map(|item| {
                    let diagnostics = item.diagnostics(crate::transport::Scope::Full);
                    let available = diagnostics
                        .get("available")
                        .and_then(Value::as_bool)
                        .unwrap_or(false);
                    json!({
                        "kind": item.name(),
                        "label": item.label(),
                        "status": if available { "available" } else { "unavailable" },
                        "detail": diagnostics.get("path").or_else(|| diagnostics.get("mode")),
                    })
                })
                })
                .collect::<Vec<_>>();
        device["transports"] = json!(transports);
        device["connected"] = json!(connected);
    }
    Ok(Json(devices))
}

/// Adopt the transport this request arrived on: bind the identity
/// the accepting transport stamped on it to the device that owns the token.
///
/// The route takes no body at all, and that is the security property: the
/// identity bound is the `Peer` stamp the handshake proved, never a field
/// the caller sent, which is the rule the claim already follows. The gate
/// ran gate 2 to admit the request; the handler reads the same header again
/// because *which device* adopts is the token's answer, and a device revoked
/// while dialing must land on `INVALID_TOKEN` here rather than on a binding.
pub async fn adopt_transport(
    State(state): State<AppState>,
    peer: Option<Extension<Peer>>,
    headers: HeaderMap,
) -> ApiResult<Json<Value>> {
    let Some(token) = crate::auth::gate::extract_bearer(&headers) else {
        return Err(ApiError::missing_token());
    };
    let device_id = crate::auth::gate::authenticate_device(&state, &token)
        .map_err(ApiError::internal)?
        .ok_or_else(ApiError::invalid_token)?;
    // No stamp, or a stamp naming a transport this build does not have, is
    // the same wiring defect the gate refuses; refused again here rather
    // than assumed, in case the layers are ever miswired.
    let Some(Extension(peer)) = peer else {
        return Err(ApiError::source_not_authorized());
    };
    let Some(transport) = state.transports.of(&peer) else {
        return Err(ApiError::source_not_authorized());
    };
    // Loopback and Tailscale prove nothing about who their peers are, so
    // they have no identity to bind and need none: their gate 1 never reads
    // the binding table.
    let Some(identity) = transport.bindable_identity(&peer) else {
        return Err(ApiError::transport_proves_no_identity());
    };
    match crate::db::devices::adopt_peer(&state.db, &device_id, transport.name(), &identity)
        .map_err(ApiError::internal)?
    {
        Adoption::DifferentIdentity => Err(ApiError::transport_already_adopted()),
        outcome => {
            if outcome == Adoption::Written {
                // The on-machine record that a device changed transport, the
                // same detection surface the claim's "device paired" line is.
                tracing::info!(
                    device_id = %device_id,
                    transport = %transport.name(),
                    "transport adopted"
                );
            }
            Ok(Json(
                json!({ "transport": transport.name(), "adopted": true }),
            ))
        }
    }
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
