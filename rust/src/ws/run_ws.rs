//! Both sockets. The CLI's `/api/ws/runs/{run_id}` and the phone's
//! quarantined `/api/runs/{run_id}/stream`.
//!
//! **The refusal happens before accept.** A socket cannot answer `401` once the
//! handshake has completed, so a caller that fails the gate is refused at the
//! HTTP layer and never upgraded. `E2E/0.4.1` recorded a close-before-accept
//! defect here; this release reproduces today's behaviour, including the parts
//! a later minor fixes.

use crate::state::AppState;
use axum::extract::ws::{Message, WebSocket, WebSocketUpgrade};
use axum::extract::{ConnectInfo, Path, Query, State};
use axum::http::StatusCode;
use axum::response::Response;
use serde::Deserialize;
use std::net::SocketAddr;

#[derive(Deserialize)]
pub struct WsAuth {
    /// A browser cannot set a header on a websocket, and neither can every
    /// client library, so the token rides as a query parameter here. The phone
    /// and the CLI both use it, and the gate is the same comparison either way.
    token: Option<String>,
}

fn is_loopback(addr: &SocketAddr) -> bool {
    addr.ip().is_loopback()
}

/// The pre-accept gate, returning `Err(status)` rather than closing a socket
/// that was never opened.
fn authorize(state: &AppState, peer: &SocketAddr, token: Option<&str>) -> Result<Option<String>, StatusCode> {
    if is_loopback(peer) {
        return Ok(None);
    }
    if !state.transport.is_authorized_source(&peer.ip().to_string()) {
        return Err(StatusCode::FORBIDDEN);
    }
    let token = token.ok_or(StatusCode::UNAUTHORIZED)?;
    let hash = crate::auth::tokens::hash_token(token);
    match crate::db::devices::find_by_token_hash(&state.db, &hash) {
        Ok(Some(device_id)) => Ok(Some(device_id)),
        _ => Err(StatusCode::UNAUTHORIZED),
    }
}

pub async fn run_stream(
    ws: WebSocketUpgrade,
    State(state): State<AppState>,
    ConnectInfo(peer): ConnectInfo<SocketAddr>,
    Path(run_id): Path<String>,
    Query(auth): Query<WsAuth>,
) -> Response {
    match authorize(&state, &peer, auth.token.as_deref()) {
        Ok(device_id) => ws.on_upgrade(move |socket| pump(socket, state, run_id, device_id)),
        Err(status) => status.into_response(),
    }
}

use axum::response::IntoResponse;

async fn pump(mut socket: WebSocket, state: AppState, run_id: String, device_id: Option<String>) {
    let (mut rx, replay) = state.ws.connect(&run_id);
    if let Some(id) = device_id {
        // The sender is what revocation drops; holding it here is what makes
        // `DELETE /api/devices/{id}` reach a live socket.
        let (tx, _) = tokio::sync::broadcast::channel(1);
        state.ws.register_device_socket(&id, tx);
    }

    // Replay first, in order, before any live frame.
    for event in replay {
        if socket.send(Message::Text(event.to_string().into())).await.is_err() {
            return;
        }
    }

    loop {
        tokio::select! {
            incoming = socket.recv() => {
                // The client says nothing on this socket; a close is the only
                // message that matters.
                if incoming.is_none() { return; }
            }
            event = rx.recv() => {
                match event {
                    Ok(e) => {
                        if socket.send(Message::Text(e.to_string().into())).await.is_err() {
                            return;
                        }
                    }
                    // Lagged means this client fell far enough behind that the
                    // channel dropped frames for it. Python's sequential send
                    // delays every other subscriber instead; both are the
                    // buffer's consequence and 0.6.0 reshapes it.
                    Err(tokio::sync::broadcast::error::RecvError::Lagged(_)) => continue,
                    Err(_) => return,
                }
            }
        }
    }
}
