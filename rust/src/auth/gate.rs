//! The gates, ported from `api/auth/middleware.py`.
//!
//! The class there is called `TwoGateMiddleware` and it enforces **three**
//! numbered gates: 0 loopback, 1 network authorization, 2 token. The name is
//! the documents' ("the two-gate middleware") and the numbering is the code's;
//! this port keeps the behaviour of the code and does not reconcile the naming,
//! because a rename is not what this release is for.
//!
//! Order is the security property, and the three public paths bypass all of it.

use crate::error::ApiError;
use crate::state::AppState;
use axum::extract::{ConnectInfo, State};
use axum::http::Request;
use axum::middleware::Next;
use axum::response::{IntoResponse, Response};
use std::net::SocketAddr;

/// `/api/health` is the phone's post-pair connectivity probe and the two
/// pairing routes are what a phone has before it has a token. They bypass every
/// gate, which is why the set is short and stated in one place.
const PUBLIC_PATHS: [&str; 3] = ["/api/health", "/api/auth/pair", "/api/auth/claim"];

fn is_loopback(host: &str) -> bool {
    let h = host.to_lowercase();
    matches!(h.as_str(), "127.0.0.1" | "::1" | "localhost" | "testclient") || h.starts_with("127.")
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

    if PUBLIC_PATHS.contains(&path.as_str()) {
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
    let presented = req
        .headers()
        .get(axum::http::header::AUTHORIZATION)
        .and_then(|v| v.to_str().ok())
        .and_then(|v| v.strip_prefix("Bearer "))
        .map(|s| s.trim().to_string())
        .filter(|s| !s.is_empty());

    let device = match &presented {
        Some(token) => {
            let hash = super::tokens::hash_token(token);
            crate::db::devices::find_by_token_hash(&state.db, &hash).ok().flatten()
        }
        None => None,
    };

    match device {
        Some(device_id) => {
            let _ = crate::db::devices::touch_last_seen(&state.db, &device_id);
            next.run(req).await
        }
        // **The two 401 codes stay two codes.** They say "you did not
        // authenticate" and "you authenticated as nobody", and the phone acts
        // differently on each: one is a client bug, the other is a pairing the
        // machine has forgotten.
        None if presented.is_some() => ApiError::invalid_token().into_response(),
        None => ApiError::missing_token().into_response(),
    }
}
