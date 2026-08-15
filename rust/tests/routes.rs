//! The router, driven end to end in-process: the gate's outcomes, the routes
//! that ship, and the routes deliberately held for the engine's release.

use axum::body::Body;
use axum::http::{Request, StatusCode};
use http_body_util::BodyExt;
use serde_json::Value;
use std::net::SocketAddr;
use std::sync::Arc;
use std::sync::RwLock;
use tower::ServiceExt;
use vadgr_daemon::auth::pairing::PairingStore;
use vadgr_daemon::computer_use_setup::SetupService;
use vadgr_daemon::config::Config;
use vadgr_daemon::db::Db;
use vadgr_daemon::state::AppState;
use vadgr_daemon::transport::{LoopbackTransport, Transport};
use vadgr_daemon::ws::manager::ConnectionManager;

/// A transport that calls every non-loopback source a peer, so gate 1 passes
/// and gate 2 is what the test is actually exercising.
struct EveryoneIsAPeer;
impl Transport for EveryoneIsAPeer {
    fn name(&self) -> &'static str {
        "test"
    }
    fn advertise_host(&self) -> Option<String> {
        Some("machine.tail.ts.net".into())
    }
    fn bind_host(&self) -> anyhow::Result<String> {
        Ok("100.64.0.1".into())
    }
    fn is_available(&self) -> bool {
        true
    }
    fn is_authorized_source(&self, _h: &str) -> bool {
        true
    }
    fn status(&self) -> Value {
        serde_json::json!({"name": "test", "available": true})
    }
}

fn state_with(transport: Box<dyn Transport>) -> AppState {
    let db = Db::open(":memory:").unwrap();
    db.with(|c| {
        c.execute_batch("INSERT INTO runs (id, title, status) VALUES ('r1','a task','running');")
    })
    .unwrap();
    AppState {
        db,
        config: Arc::new(Config::from_env()),
        transport: Arc::from(transport),
        pairing: Arc::new(PairingStore::new(300)),
        ws: Arc::new(ConnectionManager::new()),
        providers: Arc::new(vec![serde_json::json!({
            "id": "cached",
            "name": "Cached provider",
            "available": true,
            "models": [],
        })]),
        computer_use_setup: Arc::new(SetupService::new(
            std::env::temp_dir()
                .join(format!("vadgr-route-test-{}", uuid::Uuid::new_v4()))
                .join("settings.json"),
            None,
            true,
        )),
        computer_use_status: Arc::new(RwLock::new(serde_json::json!({
            "enabled": true,
            "venv_ready": true,
            "daemon": "running",
            "platform": "wsl2",
        }))),
    }
}

fn app(state: AppState) -> axum::Router {
    vadgr_daemon::routes::router(state.clone()).layer(axum::middleware::from_fn_with_state(
        state,
        vadgr_daemon::auth::gate::gate,
    ))
}

/// Requests arrive from a tailnet address unless a test says otherwise, so the
/// gate is exercised rather than skipped. A test that always came from loopback
/// would pass through gate 0 and prove nothing about the other two.
async fn send(state: AppState, req: Request<Body>, from: &str) -> (StatusCode, Value) {
    let peer = SocketAddr::new(from.parse().unwrap(), 5555);
    let res = app(state)
        .layer(axum::Extension(peer))
        .into_service::<Body>()
        .oneshot({
            let mut r = req;
            r.extensions_mut().insert(axum::extract::ConnectInfo(peer));
            r
        })
        .await
        .unwrap();
    let status = res.status();
    let bytes = res.into_body().collect().await.unwrap().to_bytes();
    let body = serde_json::from_slice(&bytes).unwrap_or(Value::Null);
    (status, body)
}

fn get(path: &str) -> Request<Body> {
    Request::builder().uri(path).body(Body::empty()).unwrap()
}

fn get_with_token(path: &str, token: &str) -> Request<Body> {
    Request::builder()
        .uri(path)
        .header("authorization", format!("Bearer {token}"))
        .body(Body::empty())
        .unwrap()
}

// ---------------------------------------------------------------- the gates

#[tokio::test]
async fn health_answers_without_a_token_because_it_is_the_probe() {
    let (status, body) = send(
        state_with(Box::new(EveryoneIsAPeer)),
        get("/api/health"),
        "100.64.0.9",
    )
    .await;
    assert_eq!(status, StatusCode::OK);
    assert_eq!(body["status"], "healthy");
    assert_eq!(body["version"], "0.4.5");
    assert_eq!(body["modules"]["computer_use"], true);
    assert!(["linux", "macos", "windows", "wsl"].contains(&body["platform"].as_str().unwrap()));
}

#[tokio::test]
async fn a_peer_with_no_token_gets_missing_token() {
    let (status, body) = send(
        state_with(Box::new(EveryoneIsAPeer)),
        get("/api/runs"),
        "100.64.0.9",
    )
    .await;
    assert_eq!(status, StatusCode::UNAUTHORIZED);
    assert_eq!(body["error"]["code"], "MISSING_TOKEN");
}

#[tokio::test]
async fn a_peer_with_a_token_nobody_knows_gets_invalid_token() {
    let (status, body) = send(
        state_with(Box::new(EveryoneIsAPeer)),
        get_with_token("/api/runs", "not-a-real-token"),
        "100.64.0.9",
    )
    .await;
    assert_eq!(status, StatusCode::UNAUTHORIZED);
    assert_eq!(body["error"]["code"], "INVALID_TOKEN");
}

#[tokio::test]
async fn a_source_that_is_not_a_peer_never_reaches_the_token_check() {
    // Gate 1 refuses before any token work, which is the ordering that makes
    // the token comparison unreachable from off the tailnet.
    let (status, body) = send(
        state_with(Box::new(LoopbackTransport)),
        get_with_token("/api/runs", "anything"),
        "203.0.113.7",
    )
    .await;
    assert_eq!(status, StatusCode::FORBIDDEN);
    assert_eq!(body["error"]["code"], "SOURCE_NOT_AUTHORIZED");
}

#[tokio::test]
async fn loopback_passes_without_a_token() {
    let (status, _) = send(
        state_with(Box::new(LoopbackTransport)),
        get("/api/runs"),
        "127.0.0.1",
    )
    .await;
    assert_eq!(status, StatusCode::OK);
}

#[tokio::test]
async fn ipv6_loopback_passes_without_a_token() {
    let (status, _) = send(
        state_with(Box::new(LoopbackTransport)),
        get("/api/runs"),
        "::1",
    )
    .await;
    assert_eq!(status, StatusCode::OK);
}

#[tokio::test]
async fn a_paired_device_reaches_the_route() {
    let state = state_with(Box::new(EveryoneIsAPeer));
    let token = "a-known-token";
    vadgr_daemon::db::devices::create(
        &state.db,
        "my-phone",
        &vadgr_daemon::auth::tokens::hash_token(token),
    )
    .unwrap();
    let (status, body) = send(state, get_with_token("/api/runs", token), "100.64.0.9").await;
    assert_eq!(status, StatusCode::OK);
    assert!(body.is_array());
}

#[tokio::test]
async fn the_bearer_scheme_is_case_insensitive_like_the_python_extractor() {
    // `bearer x` is a presented token, not an absent one. A port that only
    // took `Bearer<space>` would answer MISSING_TOKEN where the other daemon
    // answers INVALID_TOKEN, and the phone reads those as different failures.
    let state = state_with(Box::new(EveryoneIsAPeer));
    let token = "a-known-token";
    vadgr_daemon::db::devices::create(
        &state.db,
        "my-phone",
        &vadgr_daemon::auth::tokens::hash_token(token),
    )
    .unwrap();

    let (status, _) = send(
        state.clone(),
        get_with_scheme("/api/runs", "bearer", token),
        "100.64.0.9",
    )
    .await;
    assert_eq!(status, StatusCode::OK);

    let (status, body) = send(
        state,
        get_with_scheme("/api/runs", "BEARER", "wrong-token"),
        "100.64.0.9",
    )
    .await;
    assert_eq!(status, StatusCode::UNAUTHORIZED);
    assert_eq!(body["error"]["code"], "INVALID_TOKEN");
}

fn get_with_scheme(path: &str, scheme: &str, token: &str) -> Request<Body> {
    Request::builder()
        .uri(path)
        .header("authorization", format!("{scheme} {token}"))
        .body(Body::empty())
        .unwrap()
}

#[tokio::test]
async fn a_claim_body_with_an_undeclared_field_is_a_422() {
    // Python bodies are strict: a typo or a stale field announces itself
    // instead of being silently dropped.
    let state = state_with(Box::new(EveryoneIsAPeer));
    let claim = Request::builder()
        .method("POST")
        .uri("/api/auth/claim")
        .header("content-type", "application/json")
        .body(Body::from(
            serde_json::json!({
                "pairing_token": "AAAA-AAAA",
                "device_name": "my-phone",
                "cache_enabled": true,
            })
            .to_string(),
        ))
        .unwrap();
    let (status, _) = send(state, claim, "100.64.0.9").await;
    assert_eq!(status, StatusCode::UNPROCESSABLE_ENTITY);
}

#[tokio::test]
async fn malformed_json_and_a_missing_content_type_are_422_like_python() {
    for claim in [
        Request::builder()
            .method("POST")
            .uri("/api/auth/claim")
            .header("content-type", "application/json")
            .body(Body::from("{"))
            .unwrap(),
        Request::builder()
            .method("POST")
            .uri("/api/auth/claim")
            .body(Body::from(r#"{"pairing_token":"x","device_name":"x"}"#))
            .unwrap(),
    ] {
        let (status, body) = send(state_with(Box::new(EveryoneIsAPeer)), claim, "100.64.0.9").await;
        assert_eq!(status, StatusCode::UNPROCESSABLE_ENTITY);
        assert!(body["detail"].is_array());
    }
}

#[tokio::test]
async fn the_settings_read_returns_the_python_status_shape() {
    let (status, body) = send(
        state_with(Box::new(LoopbackTransport)),
        get("/api/settings/computer-use"),
        "127.0.0.1",
    )
    .await;
    assert_eq!(status, StatusCode::OK);
    let keys: Vec<&str> = body
        .as_object()
        .unwrap()
        .keys()
        .map(String::as_str)
        .collect();
    assert_eq!(keys, vec!["daemon", "enabled", "platform", "venv_ready"]);
}

#[tokio::test]
async fn the_settings_write_uses_the_service_injected_into_application_state() {
    let directory = tempfile::tempdir().unwrap();
    let settings_path = directory.path().join("settings.json");
    let mut state = state_with(Box::new(LoopbackTransport));
    state.computer_use_setup = Arc::new(SetupService::new(settings_path.clone(), None, true));
    let request = Request::builder()
        .method("PUT")
        .uri("/api/settings/computer-use")
        .header("content-type", "application/json")
        .body(Body::from(r#"{"enabled":false}"#))
        .unwrap();

    let (status, body) = send(state, request, "127.0.0.1").await;

    assert_eq!(status, StatusCode::OK);
    assert_eq!(body["enabled"], false);
    let written: Value = serde_json::from_slice(&std::fs::read(settings_path).unwrap()).unwrap();
    assert_eq!(written["computer_use"]["enabled"], false);
}

#[tokio::test]
async fn provider_reads_use_the_catalog_cached_at_startup() {
    let (status, body) = send(
        state_with(Box::new(LoopbackTransport)),
        get("/api/providers"),
        "127.0.0.1",
    )
    .await;
    assert_eq!(status, StatusCode::OK);
    assert_eq!(body[0]["id"], "cached");
    assert_eq!(body[0]["available"], true);
}

#[tokio::test]
async fn computer_use_status_does_not_claim_an_engine_is_available() {
    let (status, body) = send(
        state_with(Box::new(LoopbackTransport)),
        get("/api/computer-use/status"),
        "127.0.0.1",
    )
    .await;
    assert_eq!(status, StatusCode::OK);
    assert_eq!(body["available"], false);
    assert!(["native", "wsl2"].contains(&body["platform"].as_str().unwrap()));
}

async fn websocket_attempt(state: AppState, path: &str) -> Vec<u8> {
    use tokio::io::{AsyncReadExt, AsyncWriteExt};

    let listener = tokio::net::TcpListener::bind("127.0.0.1:0").await.unwrap();
    let address = listener.local_addr().unwrap();
    let server = tokio::spawn(async move {
        axum::serve(
            listener,
            app(state).into_make_service_with_connect_info::<SocketAddr>(),
        )
        .await
        .unwrap();
    });
    let mut stream = tokio::net::TcpStream::connect(address).await.unwrap();
    stream
        .write_all(
            format!(
                "GET {path} HTTP/1.1\r\nHost: {address}\r\nConnection: Upgrade\r\nUpgrade: websocket\r\nSec-WebSocket-Version: 13\r\nSec-WebSocket-Key: dGhlIHNhbXBsZSBub25jZQ==\r\n\r\n"
            )
            .as_bytes(),
        )
        .await
        .unwrap();
    let mut response = Vec::new();
    tokio::time::timeout(
        std::time::Duration::from_secs(1),
        stream.read_to_end(&mut response),
    )
    .await
    .unwrap()
    .unwrap();
    server.abort();
    response
}

#[tokio::test]
async fn a_missing_run_accepts_the_socket_before_closing() {
    let missing_response = websocket_attempt(
        state_with(Box::new(LoopbackTransport)),
        "/api/ws/runs/missing",
    )
    .await;
    assert!(missing_response.starts_with(b"HTTP/1.1 101 Switching Protocols"));
    assert!(
        missing_response
            .windows(2)
            .any(|bytes| bytes == 4004_u16.to_be_bytes())
    );
}

// ---------------------------------------------------------------- the routes

#[tokio::test]
async fn a_run_that_is_not_there_is_run_not_found() {
    let (status, body) = send(
        state_with(Box::new(LoopbackTransport)),
        get("/api/runs/nope"),
        "127.0.0.1",
    )
    .await;
    assert_eq!(status, StatusCode::NOT_FOUND);
    assert_eq!(body["error"]["code"], "RUN_NOT_FOUND");
}

#[tokio::test]
async fn cancel_records_cancelled_and_a_second_cancel_is_run_not_active() {
    let state = state_with(Box::new(LoopbackTransport));
    let post = |p: &str| {
        Request::builder()
            .method("POST")
            .uri(p)
            .body(Body::empty())
            .unwrap()
    };

    let (status, body) = send(state.clone(), post("/api/runs/r1/cancel"), "127.0.0.1").await;
    assert_eq!(status, StatusCode::OK);
    assert_eq!(body["status"], "cancelled");

    let (status, body) = send(state, post("/api/runs/r1/cancel"), "127.0.0.1").await;
    assert_eq!(status, StatusCode::CONFLICT);
    assert_eq!(body["error"]["code"], "RUN_NOT_ACTIVE");
}

#[tokio::test]
async fn revoking_a_device_that_is_not_there_is_device_not_found() {
    let req = Request::builder()
        .method("DELETE")
        .uri("/api/devices/nope")
        .body(Body::empty())
        .unwrap();
    let (status, body) = send(state_with(Box::new(LoopbackTransport)), req, "127.0.0.1").await;
    assert_eq!(status, StatusCode::NOT_FOUND);
    assert_eq!(body["error"]["code"], "DEVICE_NOT_FOUND");
}

#[tokio::test]
async fn pairing_refuses_when_the_transport_cannot_advertise() {
    // We never hand out a localhost QR a phone could not use.
    let req = Request::builder()
        .method("POST")
        .uri("/api/auth/pair")
        .body(Body::empty())
        .unwrap();
    let (status, body) = send(state_with(Box::new(LoopbackTransport)), req, "127.0.0.1").await;
    assert_eq!(status, StatusCode::SERVICE_UNAVAILABLE);
    assert_eq!(body["error"]["code"], "TRANSPORT_UNREACHABLE");
    // The one error that carries a non-empty `details`, and the phone prints it.
    assert_eq!(body["error"]["details"]["transport"], "loopback");
}

#[tokio::test]
async fn pair_then_claim_mints_a_token_and_the_wire_field_keeps_its_name() {
    let state = state_with(Box::new(EveryoneIsAPeer));
    let req = Request::builder()
        .method("POST")
        .uri("/api/auth/pair")
        .body(Body::empty())
        .unwrap();
    let (status, body) = send(state.clone(), req, "100.64.0.9").await;
    assert_eq!(status, StatusCode::OK);
    // The field on the wire stays `pairing_token`; only the value's shape
    // changed. Renaming it would break the shipped CLI and the shipped phone.
    let code = body["pairing_token"].as_str().unwrap().to_string();

    let claim = Request::builder()
        .method("POST")
        .uri("/api/auth/claim")
        .header("content-type", "application/json")
        .body(Body::from(
            serde_json::json!({ "pairing_token": code, "device_name": "my-phone" }).to_string(),
        ))
        .unwrap();
    let (status, body) = send(state, claim, "100.64.0.9").await;
    assert_eq!(status, StatusCode::OK);
    assert!(body["token"].as_str().unwrap().len() > 20);
    assert!(body["device_id"].as_str().is_some());
}

// ------------------------------------------------- what this release holds

#[tokio::test]
async fn starting_a_run_is_absent_rather_than_stubbed() {
    // A 501, a plausible 202 with no run behind it, or a row nothing will pick
    // up are three ways of lying to the sweep. Absent is honest.
    //
    // **405 and not 404, and the difference is the honest one.** `/api/runs`
    // exists here, for `GET`; what does not exist is `POST` on it. A 404 would
    // claim the path is unknown, which is false and would make the held row
    // indistinguishable from a genuinely deleted surface in the sweep's probe
    // set. The spec said 404 before this test was run against the code.
    let req = Request::builder()
        .method("POST")
        .uri("/api/runs")
        .header("content-type", "application/json")
        .body(Body::from(r#"{"task":"do a thing"}"#))
        .unwrap();
    let (status, _) = send(state_with(Box::new(LoopbackTransport)), req, "127.0.0.1").await;
    assert_eq!(
        status,
        StatusCode::METHOD_NOT_ALLOWED,
        "the trigger arrives with the engine; the path exists for GET"
    );
}

#[tokio::test]
async fn resume_is_held_too_because_its_success_path_needs_a_loop() {
    // Its validation paths port cleanly and its success path cannot: without an
    // engine this daemon has no way to make the success response true. Half a
    // route would give the sweep matching error rows and a lying
    // success row.
    //
    // 404 here rather than 405, and for the same reason the trigger is 405:
    // this path is registered for no method at all.
    let req = Request::builder()
        .method("POST")
        .uri("/api/runs/r1/resume")
        .body(Body::empty())
        .unwrap();
    let (status, _) = send(state_with(Box::new(LoopbackTransport)), req, "127.0.0.1").await;
    assert_eq!(status, StatusCode::NOT_FOUND);
}
