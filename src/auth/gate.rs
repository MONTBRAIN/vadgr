//! The gates, ported from the Python daemon's middleware.
//!
//! The class there was called `TwoGateMiddleware` and it enforces **three**
//! numbered gates: 0 local bypass, 1 network authorization, 2 token. The name
//! is the documents' ("the two-gate middleware") and the numbering is the
//! code's.
//!
//! Order is the security property. What the gate reads is the `Peer` stamp
//! the accepting transport put on the request, never a socket address: gate 0
//! and gate 1 are questions the registry dispatches to the transport that
//! stamped it, so no branch here names one. A request with no stamp, or a
//! stamp naming a transport this build does not have, is refused - the only
//! safe reading of "I do not know who this is" is not "this is the owner's
//! own terminal".
//!
//! The helpers here are shared with the websocket handler. That handler owns
//! admission because an accepted socket can return the published close code.

use crate::error::ApiError;
use crate::state::AppState;
use crate::transport::{Gate1, Peer};
use axum::extract::State;
use axum::http::{HeaderMap, Request};
use axum::middleware::Next;
use axum::response::{IntoResponse, Response};

/// Answerable with no token on every transport: claim is how a token comes to
/// exist, health is the phone's connectivity probe, and neither hands
/// anything out.
const UNAUTHENTICATED_PATHS: [&str; 2] = ["/api/health", "/api/auth/claim"];

/// Answerable with no token, but only from an authorized peer. Minting is an
/// owner action taken on the machine, and the response body is a credential:
/// an unbound peer admitted to it would mint a code of its own, superseding
/// the owner's, and read the replacement out of the response.
const PEER_ONLY_PATHS: [&str; 1] = ["/api/auth/pair"];

/// Answerable from any peer its transport admitted, bound or not, but never
/// without a valid device token. Adoption is how a device with no binding on
/// a transport writes one, so gate 1, which on the built-in
/// transport **is** that binding, cannot be its precondition; gate 2 alone
/// carries it. Gate 0 is skipped too, in the strict direction: the route
/// binds an identity to the device that owns the token, so even the owner's
/// terminal needs a token here, and a caller with none is `401`, not
/// admitted as nobody.
const TOKEN_ONLY_PATHS: [&str; 1] = ["/api/devices/self/transports"];

fn is_websocket_path(path: &str) -> bool {
    (path.starts_with("/api/runs/") && path.ends_with("/stream"))
        || path.starts_with("/api/ws/runs/")
}

/// The bearer token, however the client spelt the scheme. The scheme is
/// case-insensitive and the split is on whitespace, both of which the shipped extractor
/// extractor forgives; a port that only took `Bearer<space>` would turn a
/// lowercase `bearer` into `MISSING_TOKEN` where the other daemon answers
/// `INVALID_TOKEN`. A non-bearer authorization header is skipped, not a stop:
/// a later header may still carry the token.
pub fn extract_bearer(headers: &HeaderMap) -> Option<String> {
    for value in headers.get_all(axum::http::header::AUTHORIZATION) {
        let Ok(raw) = value.to_str() else { continue };
        let raw = raw.trim();
        let Some(split) = raw.find(char::is_whitespace) else {
            continue;
        };
        let (scheme, rest) = raw.split_at(split);
        if !scheme.eq_ignore_ascii_case("bearer") {
            continue;
        }
        let token = rest.trim();
        if !token.is_empty() {
            return Some(token.to_string());
        }
    }
    None
}

/// Gate 2, shared by HTTP and the websocket handshake: the device row the
/// token hashes to, or `None`. A hit touches `last_seen`; the touch is
/// best-effort bookkeeping and a failure is logged, never fatal.
pub fn authenticate_device(
    state: &AppState,
    token: &str,
) -> Result<Option<String>, rusqlite::Error> {
    if token.is_empty() {
        return Ok(None);
    }
    let hash = super::tokens::hash_token(token);
    let Some(device_id) = crate::db::devices::find_by_token_hash(&state.db, &hash)? else {
        return Ok(None);
    };
    if let Err(err) = crate::db::devices::touch_last_seen(&state.db, &device_id) {
        tracing::warn!(%device_id, %err, "touching last_seen failed");
    }
    Ok(Some(device_id))
}

pub async fn gate<B>(State(state): State<AppState>, req: Request<B>, next: Next) -> Response
where
    B: Into<axum::body::Body>,
{
    let path = req.uri().path().to_string();
    let (parts, body) = req.into_parts();
    let req = Request::from_parts(parts, body.into());

    // The socket routes own their admission, because an accepted socket can
    // answer with the published close code; the unauthenticated pair must
    // keep answering a phone whose pairing this machine has forgotten.
    if UNAUTHENTICATED_PATHS.contains(&path.as_str()) || is_websocket_path(&path) {
        return next.run(req).await;
    }

    // No stamp, or a stamp from a transport this build does not have, is a
    // wiring defect and is refused rather than assumed to be loopback.
    let Some(peer) = req.extensions().get::<Peer>().cloned() else {
        return ApiError::source_not_authorized().into_response();
    };

    // Token-only paths go straight to gate 2. Everything else takes gate 0
    // and gate 1 in order, exactly as before this set existed.
    if !TOKEN_ONLY_PATHS.contains(&path.as_str()) {
        // Gate 0: the transport's own answer about its peers.
        if state.transports.grants_local_bypass(&peer) {
            return next.run(req).await;
        }

        // Gate 1: network authorization, before any token work. A source that
        // is not a peer on the transport it arrived over never reaches the
        // token comparison at all.
        if !state.transports.authorizes(
            &peer,
            Gate1 {
                db: &state.db,
                pairing: &state.pairing,
            },
        ) {
            return ApiError::source_not_authorized().into_response();
        }

        // Peer-only paths take gate 0 and gate 1 and skip gate 2: minting
        // needs no token, and it needs an authorized peer.
        if PEER_ONLY_PATHS.contains(&path.as_str()) {
            return next.run(req).await;
        }
    }

    // Gate 2: token.
    let presented = extract_bearer(req.headers());
    let device = match &presented {
        Some(token) => match authenticate_device(&state, token) {
            Ok(device) => device,
            // A storage failure is not "you authenticated as nobody": telling
            // a paired phone INVALID_TOKEN over a database hiccup would send
            // its owner back through pairing for nothing.
            Err(err) => return ApiError::internal(err).into_response(),
        },
        None => None,
    };

    match device {
        Some(_) => next.run(req).await,
        // **The two 401 codes stay two codes.** They say "you did not
        // authenticate" and "you authenticated as nobody", and the phone acts
        // differently on each: one is a client bug, the other is a pairing the
        // machine has forgotten.
        None if presented.is_some() => ApiError::invalid_token().into_response(),
        None => ApiError::missing_token().into_response(),
    }
}

#[cfg(test)]
mod tests {
    use super::is_websocket_path;

    #[test]
    fn only_socket_routes_defer_admission_to_the_upgrade_handler() {
        assert!(is_websocket_path("/api/runs/r1/stream"));
        assert!(is_websocket_path("/api/ws/runs/r1"));
        assert!(!is_websocket_path("/api/runs/r1"));
        assert!(!is_websocket_path("/api/health"));
    }
}
