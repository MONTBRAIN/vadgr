//! The gates, ported from `api/auth/middleware.py`.
//!
//! The class there is called `TwoGateMiddleware` and it enforces **three**
//! numbered gates: 0 loopback, 1 network authorization, 2 token. The name is
//! the documents' ("the two-gate middleware") and the numbering is the code's;
//! this port keeps the behaviour of the code and does not reconcile the naming,
//! because a rename is not what this release is for.
//!
//! Order is the security property, and the three public paths bypass all of it.
//! The helpers here are shared with the websocket handler. That handler owns
//! admission because an accepted socket can return the published close code.

use crate::error::ApiError;
use crate::state::AppState;
use axum::extract::{ConnectInfo, State};
use axum::http::{HeaderMap, Request};
use axum::middleware::Next;
use axum::response::{IntoResponse, Response};
use std::net::SocketAddr;

/// `/api/health` is the phone's post-pair connectivity probe and the two
/// pairing routes are what a phone has before it has a token. They bypass every
/// gate, which is why the set is short and stated in one place.
const PUBLIC_PATHS: [&str; 3] = ["/api/health", "/api/auth/pair", "/api/auth/claim"];

fn is_websocket_path(path: &str) -> bool {
    (path.starts_with("/api/runs/") && path.ends_with("/stream"))
        || path.starts_with("/api/ws/runs/")
}

pub fn is_loopback(host: &str) -> bool {
    host.parse::<std::net::IpAddr>()
        .is_ok_and(|address| address.is_loopback())
        || host.eq_ignore_ascii_case("localhost")
        || host.eq_ignore_ascii_case("testclient")
}

/// The bearer token, however the client spelt the scheme. The scheme is
/// case-insensitive and the split is on whitespace, both of which the Python
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

pub async fn gate<B>(
    State(state): State<AppState>,
    ConnectInfo(peer): ConnectInfo<SocketAddr>,
    req: Request<B>,
    next: Next,
) -> Response
where
    B: Into<axum::body::Body>,
{
    let path = req.uri().path().to_string();
    let (parts, body) = req.into_parts();
    let req = Request::from_parts(parts, body.into());

    if PUBLIC_PATHS.contains(&path.as_str()) || is_websocket_path(&path) {
        return next.run(req).await;
    }

    let host = peer.ip().to_string();

    // Gate 0: loopback bypass.
    if is_loopback(&host) {
        return next.run(req).await;
    }

    // Gate 1: network authorization, before any token work. A source that is
    // not a peer on this transport never reaches the token comparison at all.
    if !state.transport.is_authorized_source(&host) {
        return ApiError::source_not_authorized().into_response();
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
