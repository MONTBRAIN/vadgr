//! Pairing: mint a one-time code, redeem it for a persistent token.

use crate::auth::pairing::ClaimResult;
use crate::auth::tokens;
use crate::error::{ApiError, ApiResult};
use crate::state::AppState;
use crate::transport::Peer;
use axum::extract::State;
use axum::extract::rejection::JsonRejection;
use axum::http::StatusCode;
use axum::response::{IntoResponse, Response};
use axum::{Extension, Json};
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

/// Refuses `503` only when no supported transport can reach a phone, which on
/// a machine running normally does not happen: the local-only override is
/// set, or every transport is down at once. The message says which, and the
/// details carry the report so the caller sees the supported list with no
/// addresses in it.
///
/// The route is peer-only, not public: it needs no token, and the gate asked
/// gate 0 or gate 1 first, because the response body is a fresh pairing
/// credential and minting supersedes the outstanding one.
pub async fn pair(State(state): State<AppState>) -> ApiResult<Json<Value>> {
    let report = state.transports.report();
    if !state.transports.any_reachable() {
        let message = if state.config.local_only {
            "This daemon is running local only (VADGR_TRANSPORT=loopback), so no \
             transport can reach a phone. Remove that setting and start it again."
                .to_string()
        } else {
            let clauses = state.transports.unavailable_clauses().join(" ");
            format!("No transport can reach a phone right now. {clauses}")
        };
        return Err(ApiError::new(
            StatusCode::SERVICE_UNAVAILABLE,
            "TRANSPORT_UNREACHABLE",
            message,
        )
        .with_details(json!({ "transports": report })));
    }

    let code = state.pairing.mint();
    // **The field on the wire stays `pairing_token`.** Only the value it
    // carries changed shape at `0.4.3`; renaming the field would break the
    // shipped CLI and the shipped phone.
    let mut body = json!({
        "pairing_token": code,
        "machine_name": machine_name(),
        "transports": report,
    });
    // The top-level `host` and `port` are the tailscale entry's own fields,
    // produced from that entry so the two cannot drift, and absent when it
    // has no address. Kept for two named released consumers - the shipped CLI
    // print and the released mobile scanner - with removal at `0.6.0`, when
    // the report has a released reader.
    if let Some(entry) = body["transports"].get("tailscale").cloned()
        && entry.is_object()
    {
        if let Some(host) = entry.get("host") {
            body["host"] = host.clone();
        }
        if let Some(port) = entry.get("port") {
            body["port"] = port.clone();
        }
    }
    Ok(Json(body))
}

pub async fn cancel_pairing(
    State(state): State<AppState>,
    peer: Option<Extension<Peer>>,
) -> ApiResult<Json<Value>> {
    let Some(Extension(peer)) = peer else {
        return Err(ApiError::source_not_authorized());
    };
    if !state.transports.grants_local_bypass(&peer) {
        return Err(ApiError::source_not_authorized());
    }
    if !state.pairing.cancel() {
        return Err(ApiError::new(
            StatusCode::NOT_FOUND,
            "PAIRING_WINDOW_NOT_FOUND",
            "No pairing window is open.",
        ));
    }
    Ok(Json(json!({"status": "cancelled"})))
}

/// Strict, like every request body on this surface: an undeclared field is a 422, not
/// silently dropped, so a typo or a stale field announces itself.
#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
pub struct ClaimBody {
    pub pairing_token: String,
    pub device_name: String,
}

/// The characters a device name may not carry. An attacker chooses this value
/// and a terminal renders it: `ESC [` can repaint the owner's terminal, and a
/// bidi override can make one device read as another.
fn device_name_rejection(name: &str) -> Option<&'static str> {
    if name.is_empty() {
        return Some("device_name must not be empty");
    }
    if name.chars().count() > 64 {
        return Some("device_name must be 64 characters or fewer");
    }
    let forbidden = |c: char| {
        c.is_control()
            || ('\u{0080}'..='\u{009F}').contains(&c)
            || matches!(c, '\u{200E}' | '\u{200F}')
            || ('\u{202A}'..='\u{202E}').contains(&c)
            || ('\u{2066}'..='\u{2069}').contains(&c)
    };
    if name.chars().any(forbidden) {
        return Some("device_name must not carry control or directional characters");
    }
    None
}

/// The plaintext token is returned exactly once; only its hash is stored.
pub async fn claim(
    State(state): State<AppState>,
    peer: Option<Extension<Peer>>,
    body: Result<Json<ClaimBody>, JsonRejection>,
) -> Response {
    let Json(body) = match body {
        Ok(body) => body,
        Err(rejection) => return super::validation_error(rejection).into_response(),
    };
    let device_name = body
        .device_name
        .trim_matches(|c: char| c.is_ascii_whitespace());
    if let Some(reason) = device_name_rejection(device_name) {
        // The same transitional 422 shape the strict body produces, naming
        // the field, so no new status or code appears on the wire.
        return (
            StatusCode::UNPROCESSABLE_ENTITY,
            Json(json!({
                "detail": [{
                    "type": "value_error",
                    "loc": ["body", "device_name"],
                    "msg": reason,
                }]
            })),
        )
            .into_response();
    }
    let device_name = device_name.to_string();
    claim_valid(
        state,
        peer.as_deref().cloned(),
        &body.pairing_token,
        device_name,
    )
    .await
    .into_response()
}

async fn claim_valid(
    state: AppState,
    peer: Option<Peer>,
    pairing_token: &str,
    device_name: String,
) -> ApiResult<Json<Value>> {
    let outcome = state.pairing.redeem(pairing_token);
    // Every arm below announces the transition as the last thing it does, so
    // a reaper woken by it sees the binding this claim wrote. See
    // `PairingStore::settled`. A `let` rather than a guard object because the
    // announcement must land after the binding, not at an arbitrary drop.
    let response = match outcome {
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
            let device =
                crate::db::devices::create(&state.db, &device_name, &tokens::hash_token(&token))
                    .map_err(ApiError::internal)?;
            let device_id = device
                .get("id")
                .and_then(|v| v.as_str())
                .unwrap_or_default()
                .to_string();
            // A claim binds what the transport proved, and nothing else: the
            // identity is the stamp the accepting transport put on this very
            // request, never a body field. Transports that prove nothing
            // about their peers answer `None` and bind nothing, which is
            // exactly the shipped flow.
            let mut over = "unknown";
            if let Some(peer) = &peer {
                over = peer.transport;
                if let Some(transport) = state.transports.of(peer)
                    && let Some(identity) = transport.bindable_identity(peer)
                {
                    crate::db::devices::bind_peer(
                        &state.db,
                        &device_id,
                        transport.name(),
                        &identity,
                    )
                    .map_err(ApiError::internal)?;
                }
            }
            // The one on-machine record that a pairing happened at all; the
            // owner's detection surface when a QR was photographed.
            tracing::info!(
                device_id = %device_id,
                device_name = %device_name,
                transport = %over,
                "device paired"
            );
            Ok(Json(json!({
                "token": token,
                "device_id": device_id,
                "machine_name": machine_name(),
                "transports": state.transports.report(),
            })))
        }
    };
    // Now, and not before: the binding above decides whether the connection
    // this response is travelling on survives the window it arrived on.
    state.pairing.settled(outcome);
    response
}

#[cfg(test)]
mod tests {
    use super::{device_name_rejection, machine_name_from};

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

    /// A person names their own phone: spaces, accents and emoji all pass.
    #[test]
    fn ordinary_names_pass() {
        for name in [
            "Santiago iPhone",
            "teléfono de mamá",
            "📱 mine",
            &"a".repeat(64),
        ] {
            assert_eq!(device_name_rejection(name), None, "{name:?}");
        }
    }

    /// An attacker chooses this value and a terminal renders it.
    #[test]
    fn control_and_directional_names_are_refused() {
        for name in [
            "",
            &"a".repeat(65) as &str,
            "esc\u{001B}[2Jname",
            "c1\u{0085}name",
            "del\u{007F}name",
            "bidi\u{202E}name",
            "isolate\u{2066}name",
            "mark\u{200F}name",
        ] {
            assert!(device_name_rejection(name).is_some(), "{name:?}");
        }
    }
}
