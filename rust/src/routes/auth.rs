//! Pairing: mint a one-time code, redeem it for a persistent token.

use crate::auth::pairing::ClaimResult;
use crate::auth::tokens;
use crate::error::{ApiError, ApiResult};
use crate::state::AppState;
use axum::extract::State;
use axum::http::StatusCode;
use axum::Json;
use serde::Deserialize;
use serde_json::{json, Value};

fn machine_name() -> String {
    std::fs::read_to_string("/etc/hostname")
        .ok()
        .map(|s| s.trim().to_string())
        .filter(|s| !s.is_empty())
        .unwrap_or_else(|| "vadgr".to_string())
}

/// Refuses `503` when the transport cannot advertise a reachable host: we never
/// hand out a localhost QR a phone could not use.
pub async fn pair(State(state): State<AppState>) -> ApiResult<Json<Value>> {
    let host = match state.transport.advertise_host() {
        Some(h) => h,
        None => {
            return Err(ApiError::new(
                StatusCode::SERVICE_UNAVAILABLE,
                "TRANSPORT_UNREACHABLE",
                "Transport cannot advertise a reachable address. Enable Tailscale \
                 (VADGR_TRANSPORT=tailscale) to pair over your tailnet.",
            )
            .with_details(json!({ "transport": state.transport.name() })))
        }
    };

    let code = state.pairing.mint();
    // **The field on the wire stays `pairing_token`.** Only the value it
    // carries changed shape at `0.4.3`; renaming the field would break the
    // shipped CLI and the shipped phone.
    Ok(Json(json!({
        "host": host,
        "port": state.config.port,
        "pairing_token": code,
        "machine_name": machine_name(),
    })))
}

#[derive(Deserialize)]
pub struct ClaimBody {
    pub pairing_token: String,
    pub device_name: String,
}

/// The plaintext token is returned exactly once; only its hash is stored.
pub async fn claim(
    State(state): State<AppState>,
    Json(body): Json<ClaimBody>,
) -> ApiResult<Json<Value>> {
    match state.pairing.redeem(&body.pairing_token) {
        // 429, fired exactly once, at the moment the cap acts. That is the one
        // moment "too many attempts" is a fact distinct from "not claimable",
        // and what lets the phone say the code is dead rather than inviting
        // another retype. No `retry_after`: the recovery is a new code, not
        // waiting.
        ClaimResult::RateLimited => Err(ApiError::new(
            StatusCode::TOO_MANY_REQUESTS,
            "RATE_LIMITED",
            "Too many failed attempts. That pairing code is no longer valid; \
             generate a new one on the machine.",
        )),
        // 410 rather than 401, and the split is the point: the phone tells the
        // owner to ask for a new code instead of that they mistyped this one.
        ClaimResult::Expired => Err(ApiError::new(
            StatusCode::GONE,
            "PAIRING_CODE_EXPIRED",
            "That pairing code has expired. Generate a new one on the machine.",
        )),
        ClaimResult::Invalid => Err(ApiError::new(
            StatusCode::UNAUTHORIZED,
            "PAIRING_CODE_INVALID",
            "That pairing code is wrong or has already been used.",
        )),
        ClaimResult::Ok => {
            let token = tokens::generate_token();
            let device = crate::db::devices::create(
                &state.db,
                &body.device_name,
                &tokens::hash_token(&token),
            )
            .map_err(|e| {
                ApiError::new(StatusCode::INTERNAL_SERVER_ERROR, "INTERNAL", e.to_string())
            })?;
            Ok(Json(json!({
                "token": token,
                "device_id": device.get("id").and_then(|v| v.as_str()).unwrap_or_default(),
            })))
        }
    }
}
