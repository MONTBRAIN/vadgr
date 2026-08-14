//! Both sockets: the CLI's `/api/ws/runs/{run_id}` raw stream and the phone's
//! quarantined `/api/runs/{run_id}/stream`, which speaks the published frame
//! vocabulary. Same machinery, different framing - collapsing them into one
//! handler would put internal event names on the phone's wire.
//!
//! Auth failures and missing runs accept the upgrade and then close with a
//! stable code. A source outside the selected transport still fails at HTTP
//! because it is not allowed to open a socket.

use crate::auth::gate;
use crate::state::AppState;
use axum::extract::ws::{CloseFrame, Message, WebSocket, WebSocketUpgrade};
use axum::extract::{ConnectInfo, Path, Query, State};
use axum::http::{HeaderMap, StatusCode};
use axum::response::{IntoResponse, Response};
use serde::Deserialize;
use serde_json::{Value, json};
use std::net::SocketAddr;
use tokio::sync::broadcast;

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
enum AdmissionError {
    Source,
    Auth,
    MissingRun,
    Internal,
}

impl AdmissionError {
    fn close(self) -> Option<(u16, &'static str)> {
        match self {
            Self::Auth => Some((4401, "Unauthorized")),
            Self::MissingRun => Some((4004, "Run not found")),
            Self::Source | Self::Internal => None,
        }
    }
}

#[derive(Deserialize)]
pub struct WsAuth {
    /// A browser cannot set a header on a websocket, and neither can every
    /// client library, so the token may ride as a query parameter. A client
    /// that can set headers sends `Authorization: Bearer` instead; both
    /// daemons accept either, and the gate is the same comparison either way.
    token: Option<String>,
}

/// On success: the owning device id, or `None` for a loopback caller.
fn authorize(
    state: &AppState,
    peer: &SocketAddr,
    token: Option<&str>,
) -> Result<Option<String>, AdmissionError> {
    let host = peer.ip().to_string();
    // Gate 0: loopback bypass - the CLI connects with no token.
    if gate::is_loopback(&host) {
        return Ok(None);
    }
    // Gate 1: network authorization, before any token work.
    if !state.transport.is_authorized_source(&host) {
        return Err(AdmissionError::Source);
    }
    // Gate 2: token.
    let token = token.ok_or(AdmissionError::Auth)?;
    match gate::authenticate_device(state, token) {
        Ok(Some(device_id)) => Ok(Some(device_id)),
        Ok(None) => Err(AdmissionError::Auth),
        Err(_) => Err(AdmissionError::Internal),
    }
}

/// Query token first, `Authorization: Bearer` as the fallback - the same two
/// places the Python routes look, in the same order.
fn token_from(auth: &WsAuth, headers: &HeaderMap) -> Option<String> {
    auth.token.clone().or_else(|| gate::extract_bearer(headers))
}

/// The shared admission path: both gates, then the run lookup.
fn admit(
    state: &AppState,
    peer: &SocketAddr,
    run_id: &str,
    token: Option<&str>,
) -> Result<Option<String>, AdmissionError> {
    let device_id = authorize(state, peer, token)?;
    match crate::db::runs::get(&state.db, run_id) {
        Ok(Some(_)) => Ok(device_id),
        Ok(None) => Err(AdmissionError::MissingRun),
        Err(_) => Err(AdmissionError::Internal),
    }
}

fn refusal_response(ws: WebSocketUpgrade, error: AdmissionError) -> Response {
    match error {
        AdmissionError::Source => StatusCode::FORBIDDEN.into_response(),
        AdmissionError::Internal => StatusCode::INTERNAL_SERVER_ERROR.into_response(),
        _ => {
            let (code, reason) = error.close().expect("socket close error");
            ws.on_upgrade(move |mut socket| async move {
                let _ = socket
                    .send(Message::Close(Some(CloseFrame {
                        code,
                        reason: reason.into(),
                    })))
                    .await;
            })
        }
    }
}

/// The on-box stream the CLI watches: internal events, verbatim. Send-only,
/// like the Python route: answering a gate is `POST`, never a socket frame.
pub async fn run_websocket(
    ws: WebSocketUpgrade,
    State(state): State<AppState>,
    ConnectInfo(peer): ConnectInfo<SocketAddr>,
    Path(run_id): Path<String>,
    Query(auth): Query<WsAuth>,
    headers: HeaderMap,
) -> Response {
    let token = token_from(&auth, &headers);
    match admit(&state, &peer, &run_id, token.as_deref()) {
        // The CLI socket is not device-tracked, so revoking a phone never
        // touches it: loopback callers have no device to revoke.
        Ok(_) => ws.on_upgrade(move |socket| pump(socket, state, run_id, None, Framing::Raw)),
        Err(error) => refusal_response(ws, error),
    }
}

/// The phone's stream: every frame is a published `RunEvent`, and the socket
/// is dropped the moment its device is revoked.
pub async fn run_stream(
    ws: WebSocketUpgrade,
    State(state): State<AppState>,
    ConnectInfo(peer): ConnectInfo<SocketAddr>,
    Path(run_id): Path<String>,
    Query(auth): Query<WsAuth>,
    headers: HeaderMap,
) -> Response {
    let token = token_from(&auth, &headers);
    match admit(&state, &peer, &run_id, token.as_deref()) {
        Ok(device_id) => {
            ws.on_upgrade(move |socket| pump(socket, state, run_id, device_id, Framing::RunEvents))
        }
        Err(error) => refusal_response(ws, error),
    }
}

/// What a socket puts on the wire for one internal event.
enum Framing {
    /// The internal event, verbatim: the CLI reads the daemon's own names.
    Raw,
    /// The published `RunEvent` vocabulary; an event with no member there is
    /// dropped, not leaked.
    RunEvents,
}

impl Framing {
    fn frame(&self, event: &Value) -> Option<String> {
        match self {
            Framing::Raw => Some(event.to_string()),
            Framing::RunEvents => to_run_event(event).map(|v| v.to_string()),
        }
    }
}

/// Map internal broadcast event types to the published `RunEvent` vocabulary.
///
/// Every key here is a name the daemon actually broadcasts - the map was
/// rebuilt from the emitting code once already, after a version of it carried
/// five names nothing emitted and a phone heard silence between `started` and
/// `completed`.
const EVENT_TYPE_MAP: [(&str, &str); 8] = [
    ("run_started", "started"),
    ("agent_started", "tool_call"),
    ("agent_log", "output"),
    ("agent_completed", "output"),
    ("awaiting", "paused"),
    ("agent_failed", "failed"),
    ("run_completed", "completed"),
    ("run_failed", "failed"),
];

/// Broadcast, understood, and deliberately not translatable yet: neither has
/// a member in the published vocabulary, and inventing one here would be a
/// published frame name chosen in the wrong place. Listed rather than left to
/// the fallthrough so a type nobody has considered can be told apart from one
/// that is waiting on a decision.
const NOT_YET_ON_THIS_STREAM: [&str; 2] = ["todos", "run_resumed"];

/// One internal event as a `RunEvent`, or `None` when it has no member in the
/// published vocabulary.
pub fn to_run_event(internal: &Value) -> Option<Value> {
    let kind = internal.get("type").and_then(|v| v.as_str());
    let mapped = kind.and_then(|k| {
        EVENT_TYPE_MAP
            .iter()
            .find(|(from, _)| *from == k)
            .map(|(_, to)| *to)
    });
    let Some(mapped) = mapped else {
        if !kind.is_some_and(|k| NOT_YET_ON_THIS_STREAM.contains(&k)) {
            tracing::warn!(
                ?kind,
                "run stream: no RunEvent for broadcast type; dropped. Add it to \
                 EVENT_TYPE_MAP or to NOT_YET_ON_THIS_STREAM."
            );
        }
        return None;
    };
    // The broadcast's own timestamp when it carries a well-formed one, the
    // clock otherwise - the Python translator's exact fallback.
    let timestamp = internal
        .get("timestamp")
        .and_then(|v| v.as_str())
        .filter(|s| {
            time::OffsetDateTime::parse(s, &time::format_description::well_known::Rfc3339).is_ok()
        })
        .map(str::to_string)
        .unwrap_or_else(crate::db::now_iso);
    Some(json!({
        "type": mapped,
        "timestamp": timestamp,
        "payload": internal.get("data").cloned().unwrap_or_else(|| json!({})),
    }))
}

async fn pump(
    mut socket: WebSocket,
    state: AppState,
    run_id: String,
    device_id: Option<String>,
    framing: Framing,
) {
    let (mut rx, replay) = state.ws.connect(&run_id);

    // The revocation watch. A socket with no device gets a channel that never
    // fires; the sender lives here so it cannot close underneath the select.
    let _keep_alive: Option<broadcast::Sender<()>>;
    let mut revoked = match &device_id {
        Some(id) => {
            _keep_alive = None;
            state.ws.watch_device(id)
        }
        None => {
            let (tx, rx) = broadcast::channel(1);
            _keep_alive = Some(tx);
            rx
        }
    };

    // Replay first, in order, before any live frame.
    for event in replay {
        if let Some(text) = framing.frame(&event)
            && socket.send(Message::Text(text.into())).await.is_err()
        {
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
                        if let Some(text) = framing.frame(&e)
                            && socket.send(Message::Text(text.into())).await.is_err()
                        {
                            return;
                        }
                    }
                    // Lagged means this client fell far enough behind that the
                    // channel dropped frames for it. Python's sequential send
                    // delays every other subscriber instead; both are the
                    // buffer's consequence and 0.6.0 reshapes it.
                    Err(broadcast::error::RecvError::Lagged(_)) => continue,
                    Err(_) => return,
                }
            }
            _ = revoked.recv() => {
                // The device was just unpaired. Close now, with the same close
                // the Python manager sends, rather than streaming on until the
                // next reconnect fails the gate.
                let _ = socket
                    .send(Message::Close(Some(CloseFrame {
                        code: 4003,
                        reason: "Device revoked".into(),
                    })))
                    .await;
                return;
            }
        }
    }
}

#[cfg(test)]
mod tests {
    use super::AdmissionError;

    #[test]
    fn rejected_upgrades_have_stable_close_codes() {
        assert_eq!(AdmissionError::Auth.close(), Some((4401, "Unauthorized")));
        assert_eq!(
            AdmissionError::MissingRun.close(),
            Some((4004, "Run not found"))
        );
        assert_eq!(AdmissionError::Source.close(), None);
    }
}
