//! Pairing: mint a one-time code, redeem it for a persistent token.

use crate::auth::pairing::ClaimResult;
use crate::auth::tokens;
use crate::error::{ApiError, ApiResult};
use crate::state::AppState;
use axum::Json;
use axum::extract::State;
use axum::extract::rejection::JsonRejection;
use axum::http::StatusCode;
use axum::response::{IntoResponse, Response};
use serde::Deserialize;
use serde_json::{Value, json};

fn machine_name_from(value: Result<std::ffi::OsString, std::io::Error>) -> String {
    value
        .ok()
        .map(|s| s.to_string_lossy().trim().to_string())
        .filter(|s| !s.is_empty())
        .unwrap_or_else(|| "vadgr".to_string())
}

fn machine_name() -> String {
    machine_name_from(hostname::get())
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
            .with_details(json!({ "transport": state.transport.name() })));
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

/// Strict, like every request body on this surface: an undeclared field is a 422, not
/// silently dropped, so a typo or a stale field announces itself.
#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
pub struct ClaimBody {
    pub pairing_token: String,
    pub device_name: String,
}

/// The plaintext token is returned exactly once; only its hash is stored.
pub async fn claim(
    State(state): State<AppState>,
    body: Result<Json<ClaimBody>, JsonRejection>,
) -> Response {
    let Json(body) = match body {
        Ok(body) => body,
        Err(rejection) => return super::validation_error(rejection).into_response(),
    };
    claim_valid(state, body).await.into_response()
}

async fn claim_valid(state: AppState, body: ClaimBody) -> ApiResult<Json<Value>> {
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
            .map_err(ApiError::internal)?;
            Ok(Json(json!({
                "token": token,
                "device_id": device.get("id").and_then(|v| v.as_str()).unwrap_or_default(),
            })))
        }
    }
}

#[cfg(test)]
mod tests {
    use super::machine_name_from;

    #[test]
    fn the_platform_hostname_is_used_without_reading_a_unix_file() {
        let name = machine_name_from(Ok("review-host".into()));
        assert_eq!(name, "review-host");
    }

    #[test]
    fn an_unavailable_or_empty_hostname_has_the_existing_fallback() {
        assert_eq!(machine_name_from(Ok("  ".into())), "vadgr");
        assert_eq!(
            machine_name_from(Err(std::io::Error::other("no hostname"))),
            "vadgr"
        );
    }
}
