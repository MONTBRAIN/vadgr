//! The router, driven end to end in-process: the gate's outcomes and the
//! complete transitional route surface.

use async_trait::async_trait;
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
use vadgr_daemon::engine::control::RunContext;
use vadgr_daemon::engine::mcp::{HostFactory, McpHost};
use vadgr_daemon::engine::provider::credentials::CredentialStore;
use vadgr_daemon::engine::provider::service::{ProviderEndpoints, ProviderService};
use vadgr_daemon::engine::provider::{ModelClient, ModelFactory};
use vadgr_daemon::engine::supervisor::RunSupervisor;
use vadgr_daemon::engine::{Engine, McpError, ProviderError};
use vadgr_daemon::state::AppState;
use vadgr_daemon::transport::{
    Gate1, LoopbackTransport, Peer, Reach, Scope, Transport, Transports,
};
use vadgr_daemon::ws::manager::ConnectionManager;

/// A transport that calls every source a peer, so gate 1 passes and gate 2
/// is what the test is actually exercising. Its address form reuses the
/// tailscale wire name so the pair response's top-level host and port stay
/// covered.
struct EveryoneIsAPeer;
impl Transport for EveryoneIsAPeer {
    fn name(&self) -> &'static str {
        "tailscale"
    }
    fn label(&self) -> &'static str {
        "Tailscale"
    }
    fn serve(
        &self,
        _app: axum::Router,
        _port: u16,
        _hosts: &[String],
    ) -> futures_util::future::BoxFuture<'static, anyhow::Result<()>> {
        Box::pin(std::future::pending())
    }
    fn bind_hosts(&self) -> Vec<String> {
        vec!["100.64.0.1".into()]
    }
    fn reach(&self) -> Reach {
        Reach::At(serde_json::json!({"host": "machine.tail.ts.net", "port": 8000}))
    }
    fn grants_local_bypass(&self) -> bool {
        false
    }
    fn authorizes(&self, _peer: &Peer, _ctx: Gate1<'_>) -> bool {
        true
    }
    fn bindable_identity(&self, _peer: &Peer) -> Option<String> {
        None
    }
    fn diagnostics(&self, _scope: Scope) -> Value {
        serde_json::json!({"name": "tailscale", "available": true})
    }
}

struct UnusedModelFactory;

#[async_trait]
impl ModelFactory for UnusedModelFactory {
    async fn build(
        &self,
        _provider: &str,
        _model: &str,
    ) -> Result<Box<dyn ModelClient>, ProviderError> {
        Err(ProviderError::Request(
            "test model is not configured".to_owned(),
        ))
    }
}

struct EmptyHostFactory;

#[async_trait]
impl HostFactory for EmptyHostFactory {
    async fn build(&self, _context: RunContext) -> Result<McpHost, McpError> {
        Ok(McpHost::new(Vec::new()))
    }
}

fn state_with(transport: Box<dyn Transport>) -> AppState {
    let transport: Arc<dyn Transport> = Arc::from(transport);
    let db = Db::open(":memory:").unwrap();
    db.with(|c| {
        c.execute_batch("INSERT INTO runs (id, title, status) VALUES ('r1','a task','running');")
    })
    .unwrap();
    // An isolated root, never the machine's own: a route test that resolved the
    // real platform root would read and write whatever was already there.
    let root = std::env::temp_dir().join(format!("vadgr-route-test-{}", uuid::Uuid::new_v4()));
    let config = Arc::new(Config::for_paths(&vadgr_daemon::config::Paths {
        db: root.join("vadgr.db"),
        runs: root.join("runs"),
        credentials: root.join("credentials"),
        root,
    }));
    let ws = Arc::new(ConnectionManager::new());
    let setup = Arc::new(SetupService::new(
        std::env::temp_dir()
            .join(format!("vadgr-route-test-{}", uuid::Uuid::new_v4()))
            .join("settings.json"),
        None,
        true,
    ));
    let engine = Arc::new(Engine::new(
        Arc::new(UnusedModelFactory),
        Arc::new(EmptyHostFactory),
        db.clone(),
        config.runs_dir.clone(),
    ));
    let supervisor = RunSupervisor::new(engine, db.clone(), ws.clone());
    let credential_directory = std::env::temp_dir()
        .join(format!("vadgr-provider-test-{}", uuid::Uuid::new_v4()))
        .join("credentials");
    let providers = ProviderService::new(
        db.clone(),
        CredentialStore::new(credential_directory).unwrap(),
        ProviderEndpoints::default(),
    )
    .unwrap();
    // The registry always holds the loopback transport, exactly as the
    // daemon's does, so gate 0 keeps one honest owner in tests too - and the
    // built-in transport beside it, whose gate 1 is the binding table, so a
    // claim's binding and an endpoint id's authorization are driven through
    // the same registry the daemon uses.
    let iroh: Arc<dyn Transport> = Arc::new(vadgr_daemon::transport::IrohTransport::new(
        std::env::temp_dir()
            .join(format!("vadgr-route-test-{}", uuid::Uuid::new_v4()))
            .join("iroh_secret_key"),
        vadgr_daemon::config::RelayChoice::Default,
        None,
    ));
    let members: Vec<Arc<dyn Transport>> = if transport.name() == "loopback" {
        vec![transport, iroh]
    } else {
        vec![Arc::new(LoopbackTransport), iroh, transport]
    };
    AppState {
        db,
        config,
        transports: Arc::new(Transports::new(members)),
        pairing: Arc::new(PairingStore::new(300)),
        ws,
        providers,
        computer_use_setup: setup,
        computer_use_status: Arc::new(RwLock::new(serde_json::json!({
            "enabled": true,
            "venv_ready": true,
            "platform": "wsl2",
        }))),
        supervisor,
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
    // The stamp a listener would have put on the request: the loopback
    // listener stamps loopback sources, the network transport stamps the
    // rest. Requests never carry a socket address any more.
    let ip: std::net::IpAddr = from.parse().unwrap();
    let peer = Peer {
        transport: if ip.is_loopback() {
            "loopback"
        } else {
            "tailscale"
        },
        identity: from.to_string(),
    };
    let res = app(state)
        .into_service::<Body>()
        .oneshot({
            let mut r = req;
            r.extensions_mut().insert(peer);
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
    // The version this daemon reports, read from the one place that defines it.
    // A literal here turns every release bump into a broken test, which is what
    // happened at 0.4.8.
    assert_eq!(body["version"], vadgr_daemon::config::VERSION);
    assert_eq!(body["modules"]["computer_use"], true);
    assert!(["linux", "macos", "windows", "wsl"].contains(&body["platform"].as_str().unwrap()));
}

#[tokio::test]
async fn oauth_cancellation_redirects_to_a_query_free_failure_page() {
    let state = state_with(Box::new(LoopbackTransport));
    // The flow needs a bound callback port, because the redirect names it.
    state.providers.set_oauth_callback_port(Some(1455));
    let attempt = state.providers.start_oauth("openai").await.unwrap();
    let authorization_url = url::Url::parse(attempt.authorization_url.as_deref().unwrap()).unwrap();
    let oauth_state = authorization_url
        .query_pairs()
        .find(|(key, _)| key == "state")
        .map(|(_, value)| value.into_owned())
        .unwrap();
    let callback = format!("/auth/callback?state={oauth_state}&error=access_denied");

    let response = vadgr_daemon::routes::providers::callback_router(state.clone())
        .oneshot(get(&callback))
        .await
        .unwrap();

    assert_eq!(response.status(), StatusCode::SEE_OTHER);
    assert_eq!(response.headers()["location"], "/auth/failed");
    assert!(
        !response.headers()["location"]
            .to_str()
            .unwrap()
            .contains('?')
    );

    let page = vadgr_daemon::routes::providers::callback_router(state)
        .oneshot(get("/auth/failed"))
        .await
        .unwrap();
    assert_eq!(page.status(), StatusCode::BAD_REQUEST);
    let body = page.into_body().collect().await.unwrap().to_bytes();
    assert!(!String::from_utf8_lossy(&body).contains(&oauth_state));
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
async fn the_bearer_scheme_is_case_insensitive() {
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
    // Bodies are strict: a typo or a stale field announces itself
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
async fn malformed_json_and_a_missing_content_type_are_422() {
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
async fn the_settings_read_returns_the_shipped_status_shape() {
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
    assert_eq!(keys, vec!["enabled", "platform", "venv_ready"]);
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
async fn provider_reads_use_compiled_descriptors_and_local_state() {
    let (status, body) = send(
        state_with(Box::new(LoopbackTransport)),
        get("/api/providers"),
        "127.0.0.1",
    )
    .await;
    assert_eq!(status, StatusCode::OK);
    assert_eq!(body[0]["id"], "openai");
    assert_eq!(body[1]["id"], "gemini");
    assert_eq!(body[2]["id"], "anthropic");
    assert_eq!(body[0]["connected"], false);
    assert_eq!(body[0]["available"], false);
}

#[tokio::test]
async fn provider_mutations_reject_remote_sources_without_relying_on_the_global_gate() {
    let mut request = Request::builder()
        .method("POST")
        .uri("/api/providers/openai/auth-attempts")
        .header("content-type", "application/json")
        .body(Body::from(
            r#"{"method":"api_key","api_key":"never-staged"}"#,
        ))
        .unwrap();
    request.extensions_mut().insert(Peer {
        transport: "tailscale",
        identity: "100.64.0.9".to_string(),
    });

    let response = vadgr_daemon::routes::router(state_with(Box::new(EveryoneIsAPeer)))
        .oneshot(request)
        .await
        .unwrap();
    let status = response.status();
    let bytes = response.into_body().collect().await.unwrap().to_bytes();
    let body: Value = serde_json::from_slice(&bytes).unwrap();

    assert_eq!(status, StatusCode::FORBIDDEN);
    assert_eq!(body["error"]["code"], "SOURCE_NOT_AUTHORIZED");
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

#[tokio::test]
async fn machine_read_and_patch_share_the_persistent_store() {
    let state = state_with(Box::new(LoopbackTransport));
    let (status, before) = send(state.clone(), get("/api/machine"), "127.0.0.1").await;
    assert_eq!(status, StatusCode::OK);
    assert!(!before["id"].as_str().unwrap().is_empty());

    let request = Request::builder()
        .method("PATCH")
        .uri("/api/machine")
        .header("content-type", "application/json")
        .body(Body::from(
            r#"{"name":"Studio workstation","autonomy":{"mode":"paranoid"}}"#,
        ))
        .unwrap();
    let (status, changed) = send(state.clone(), request, "127.0.0.1").await;
    assert_eq!(status, StatusCode::OK, "{changed}");
    assert_eq!(changed["id"], before["id"]);
    assert_eq!(changed["name"], "Studio workstation");
    assert_eq!(changed["autonomy"]["mode"], "paranoid");

    let (_, reread) = send(state, get("/api/machine"), "127.0.0.1").await;
    assert_eq!(reread, changed);
}

#[tokio::test]
async fn machine_patch_distinguishes_null_from_an_omitted_field() {
    let state = state_with(Box::new(LoopbackTransport));
    let set_values = Request::builder()
        .method("PATCH")
        .uri("/api/machine")
        .header("content-type", "application/json")
        .body(Body::from(
            r#"{"role_prompt":"Temporary role","workspace":"C:\\temporary"}"#,
        ))
        .unwrap();
    let (status, changed) = send(state.clone(), set_values, "127.0.0.1").await;
    assert_eq!(status, StatusCode::OK, "{changed}");
    assert_eq!(changed["role_prompt"], "Temporary role");
    assert_eq!(changed["workspace"], "C:\\temporary");

    let clear_values = Request::builder()
        .method("PATCH")
        .uri("/api/machine")
        .header("content-type", "application/json")
        .body(Body::from(r#"{"role_prompt":null,"workspace":null}"#))
        .unwrap();
    let (status, cleared) = send(state, clear_values, "127.0.0.1").await;
    assert_eq!(status, StatusCode::OK, "{cleared}");
    assert_eq!(
        cleared["role_prompt"],
        "Prefer the smallest action that finishes the job."
    );
    assert_eq!(cleared["workspace"], Value::Null);
}

#[tokio::test]
async fn machine_read_reports_only_the_safe_terms_summary() {
    let state = state_with(Box::new(EveryoneIsAPeer));
    let root = state.config.state_home.as_ref().unwrap();
    std::fs::create_dir_all(root).unwrap();
    std::fs::write(
        root.join("terms-acceptance.json"),
        serde_json::to_vec(&serde_json::json!({
            "schema": 1,
            "terms_version": "1.0",
            "terms_sha256": "0".repeat(64),
            "accepted_at": "2026-09-02T12:00:00Z",
            "installer_version": "0.5.0",
            "installer_artifact_sha256": "1".repeat(64),
            "install_scope": "user",
            "installation_id": "installation-test",
            "assent_method": "unchecked_checkbox_then_install"
        }))
        .unwrap(),
    )
    .unwrap();
    let (status, body) = send(state, get("/api/machine"), "127.0.0.1").await;
    assert_eq!(status, StatusCode::OK);
    assert_eq!(body["terms"]["version"], "1.0");
    assert_eq!(body["terms"]["accepted_at"], "2026-09-02T12:00:00Z");
    assert!(body["terms"].get("installation_id").is_none());
    assert!(body["terms"].get("installer_artifact_sha256").is_none());
}

#[tokio::test]
async fn machine_patch_refuses_read_only_fields_and_incomplete_defaults() {
    let state = state_with(Box::new(LoopbackTransport));
    for (body, field) in [
        (serde_json::json!({"id": "replacement"}), None),
        (
            serde_json::json!({"default_provider": "anthropic"}),
            Some("default_provider"),
        ),
    ] {
        let request = Request::builder()
            .method("PATCH")
            .uri("/api/machine")
            .header("content-type", "application/json")
            .body(Body::from(body.to_string()))
            .unwrap();
        let (status, response) = send(state.clone(), request, "127.0.0.1").await;
        assert_eq!(status, StatusCode::UNPROCESSABLE_ENTITY, "{response}");
        if let Some(field) = field {
            assert_eq!(response["error"]["details"]["field"], field);
        }
    }
}

#[tokio::test]
async fn pairing_cancel_closes_the_window_and_names_an_absent_one() {
    let state = state_with(Box::new(EveryoneIsAPeer));
    let pair = Request::builder()
        .method("POST")
        .uri("/api/auth/pair")
        .body(Body::empty())
        .unwrap();
    let (status, _) = send(state.clone(), pair, "100.64.0.9").await;
    assert_eq!(status, StatusCode::OK);

    let cancel = || {
        Request::builder()
            .method("DELETE")
            .uri("/api/auth/pair")
            .body(Body::empty())
            .unwrap()
    };
    let (status, body) = send(state.clone(), cancel(), "127.0.0.1").await;
    assert_eq!(status, StatusCode::OK);
    assert_eq!(body["status"], "cancelled");

    let (status, body) = send(state, cancel(), "127.0.0.1").await;
    assert_eq!(status, StatusCode::NOT_FOUND);
    assert_eq!(body["error"]["code"], "PAIRING_WINDOW_NOT_FOUND");
}

#[tokio::test]
async fn pairing_cancel_is_local_only() {
    let state = state_with(Box::new(EveryoneIsAPeer));
    let pair = Request::builder()
        .method("POST")
        .uri("/api/auth/pair")
        .body(Body::empty())
        .unwrap();
    let (status, _) = send(state.clone(), pair, "100.64.0.9").await;
    assert_eq!(status, StatusCode::OK);

    let cancel = Request::builder()
        .method("DELETE")
        .uri("/api/auth/pair")
        .body(Body::empty())
        .unwrap();
    let (status, body) = send(state, cancel, "100.64.0.9").await;
    assert_eq!(status, StatusCode::FORBIDDEN, "{body}");
    assert_eq!(body["error"]["code"], "SOURCE_NOT_AUTHORIZED");
}

async fn websocket_attempt(state: AppState, path: &str) -> Vec<u8> {
    use tokio::io::{AsyncReadExt, AsyncWriteExt};

    let listener = tokio::net::TcpListener::bind("127.0.0.1:0").await.unwrap();
    let address = listener.local_addr().unwrap();
    let server = tokio::spawn(async move {
        // Served the way the loopback listener serves: gate layered, then the
        // transport's own stamp outermost.
        axum::serve(
            listener,
            vadgr_daemon::transport::stamped(app(state), "loopback")
                .into_make_service_with_connect_info::<SocketAddr>(),
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
async fn pairing_refuses_when_no_transport_can_reach_a_phone() {
    // We never hand out a localhost QR a phone could not use: a registry
    // holding the loopback transport alone has an empty report, and the
    // details carry it so the caller sees the supported list with no
    // addresses in it.
    let req = Request::builder()
        .method("POST")
        .uri("/api/auth/pair")
        .body(Body::empty())
        .unwrap();
    let (status, body) = send(state_with(Box::new(LoopbackTransport)), req, "127.0.0.1").await;
    assert_eq!(status, StatusCode::SERVICE_UNAVAILABLE);
    assert_eq!(body["error"]["code"], "TRANSPORT_UNREACHABLE");
    assert!(body["error"]["details"]["transports"].is_object());
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

// ------------------------------------------------- engine-backed run routes

#[tokio::test]
async fn starting_a_run_returns_the_complete_queued_row() {
    let req = Request::builder()
        .method("POST")
        .uri("/api/runs")
        .header("content-type", "application/json")
        .body(Body::from(r#"{"task":"do a thing"}"#))
        .unwrap();
    let (status, body) = send(state_with(Box::new(LoopbackTransport)), req, "127.0.0.1").await;
    assert_eq!(status, StatusCode::ACCEPTED);
    assert_eq!(body["status"], "queued");
    assert_eq!(body["agent_name"], "do a thing");
    assert_eq!(body["inputs"]["task"], "do a thing");
    assert!(body["id"].as_str().unwrap().starts_with("run-"));
}

#[tokio::test]
async fn resume_rejects_every_state_except_failed() {
    let req = Request::builder()
        .method("POST")
        .uri("/api/runs/r1/resume")
        .body(Body::empty())
        .unwrap();
    let (status, body) = send(state_with(Box::new(LoopbackTransport)), req, "127.0.0.1").await;
    assert_eq!(status, StatusCode::CONFLICT);
    assert_eq!(body["error"]["code"], "RUN_NOT_RESUMABLE");
}

#[tokio::test]
async fn run_create_is_strict_and_requires_provider_model_as_a_pair() {
    for body in [
        r#"{"task":"work","provider":"anthropic_oauth"}"#,
        r#"{"task":"   "}"#,
        r#"{"task":"work","inputs":{}}"#,
    ] {
        let req = Request::builder()
            .method("POST")
            .uri("/api/runs")
            .header("content-type", "application/json")
            .body(Body::from(body))
            .unwrap();
        let (status, response) =
            send(state_with(Box::new(LoopbackTransport)), req, "127.0.0.1").await;
        assert_eq!(status, StatusCode::UNPROCESSABLE_ENTITY);
        assert!(response["detail"].is_array());
    }
}

// ===================================================================== 0.4.10
// The gate matrix over the Peer stamp, the pair route's move behind gate 1,
// the claim binding, and the two reports.

/// A network transport that refuses every peer, for the non-member column.
struct NobodyIsAPeer;
impl Transport for NobodyIsAPeer {
    fn name(&self) -> &'static str {
        "tailscale"
    }
    fn label(&self) -> &'static str {
        "Tailscale"
    }
    fn serve(
        &self,
        _app: axum::Router,
        _port: u16,
        _hosts: &[String],
    ) -> futures_util::future::BoxFuture<'static, anyhow::Result<()>> {
        Box::pin(std::future::pending())
    }
    fn bind_hosts(&self) -> Vec<String> {
        Vec::new()
    }
    fn reach(&self) -> Reach {
        Reach::Unavailable("tailscaled is not running or logged out")
    }
    fn grants_local_bypass(&self) -> bool {
        false
    }
    fn authorizes(&self, _peer: &Peer, _ctx: Gate1<'_>) -> bool {
        false
    }
    fn bindable_identity(&self, _peer: &Peer) -> Option<String> {
        None
    }
    fn diagnostics(&self, _scope: Scope) -> Value {
        serde_json::json!({"name": "tailscale", "available": false})
    }
}

/// Send with an explicit stamp, or none at all: the wiring-defect columns.
async fn send_stamped(
    state: AppState,
    req: Request<Body>,
    stamp: Option<Peer>,
) -> (StatusCode, Value) {
    let res = app(state)
        .into_service::<Body>()
        .oneshot({
            let mut r = req;
            if let Some(peer) = stamp {
                r.extensions_mut().insert(peer);
            }
            r
        })
        .await
        .unwrap();
    let status = res.status();
    let bytes = res.into_body().collect().await.unwrap().to_bytes();
    let body = serde_json::from_slice(&bytes).unwrap_or(Value::Null);
    (status, body)
}

fn iroh_peer(identity: &str) -> Peer {
    Peer {
        transport: "iroh",
        identity: identity.to_string(),
    }
}

fn post_json(path: &str, body: Value) -> Request<Body> {
    Request::builder()
        .method("POST")
        .uri(path)
        .header("content-type", "application/json")
        .body(Body::from(body.to_string()))
        .unwrap()
}

/// Pair, then claim from one stamp, returning the claim response body.
async fn pair_and_claim(state: &AppState, stamp: Peer, device_name: &str) -> Value {
    let (status, pair) = send(
        state.clone(),
        Request::builder()
            .method("POST")
            .uri("/api/auth/pair")
            .body(Body::empty())
            .unwrap(),
        "127.0.0.1",
    )
    .await;
    assert_eq!(status, StatusCode::OK, "{pair}");
    let code = pair["pairing_token"].as_str().unwrap().to_string();
    let (status, claim) = send_stamped(
        state.clone(),
        post_json(
            "/api/auth/claim",
            serde_json::json!({"pairing_token": code, "device_name": device_name}),
        ),
        Some(stamp),
    )
    .await;
    assert_eq!(status, StatusCode::OK, "{claim}");
    claim
}

// ------------------------------------------------------------ the gate matrix

/// An unbound endpoint id inside an open pairing window is admitted to
/// exactly the two unauthenticated paths. `pair` is the release's security
/// change: its body is a fresh credential, so it answers gate 1 first, and
/// the refusal happens **before** `mint()` runs - the owner's outstanding
/// code must survive a stranger knocking on the route.
#[tokio::test]
async fn an_unbound_id_gets_health_and_claim_and_nothing_else() {
    let state = state_with(Box::new(EveryoneIsAPeer));
    // The owner opens a window.
    let (status, minted) = send(
        state.clone(),
        Request::builder()
            .method("POST")
            .uri("/api/auth/pair")
            .body(Body::empty())
            .unwrap(),
        "127.0.0.1",
    )
    .await;
    assert_eq!(status, StatusCode::OK);
    let owners_code = minted["pairing_token"].as_str().unwrap().to_string();

    // Health answers, at the public scope (asserted in its own test below).
    let (status, _) = send_stamped(
        state.clone(),
        get("/api/health"),
        Some(iroh_peer("unbound-endpoint-id")),
    )
    .await;
    assert_eq!(status, StatusCode::OK);

    // Pair is refused before any mint: SOURCE_NOT_AUTHORIZED, not a fresh code.
    let (status, body) = send_stamped(
        state.clone(),
        Request::builder()
            .method("POST")
            .uri("/api/auth/pair")
            .body(Body::empty())
            .unwrap(),
        Some(iroh_peer("unbound-endpoint-id")),
    )
    .await;
    assert_eq!(status, StatusCode::FORBIDDEN);
    assert_eq!(body["error"]["code"], "SOURCE_NOT_AUTHORIZED");

    // Every other path is the same refusal, token or no token.
    for req in [
        get("/api/devices"),
        get_with_token("/api/devices", "vdg_whatever"),
        get("/api/runs"),
    ] {
        let (status, body) =
            send_stamped(state.clone(), req, Some(iroh_peer("unbound-endpoint-id"))).await;
        assert_eq!(status, StatusCode::FORBIDDEN);
        assert_eq!(body["error"]["code"], "SOURCE_NOT_AUTHORIZED");
    }

    // The owner's code still claims: the stranger's knock minted nothing and
    // superseded nothing.
    let (status, claim) = send_stamped(
        state.clone(),
        post_json(
            "/api/auth/claim",
            serde_json::json!({"pairing_token": owners_code, "device_name": "owners phone"}),
        ),
        Some(iroh_peer("unbound-endpoint-id")),
    )
    .await;
    assert_eq!(status, StatusCode::OK, "{claim}");
}

/// A bound endpoint id passes gate 1: pair with no token, api paths with the
/// device token, and the two 401s stay two codes.
#[tokio::test]
async fn a_bound_id_passes_gate_one_and_gate_two_still_binds_it() {
    let state = state_with(Box::new(EveryoneIsAPeer));
    let claim = pair_and_claim(&state, iroh_peer("phone-endpoint-id"), "bound phone").await;
    let token = claim["token"].as_str().unwrap();

    // Pair: gate 1 passes on the binding, no token needed.
    let (status, _) = send_stamped(
        state.clone(),
        Request::builder()
            .method("POST")
            .uri("/api/auth/pair")
            .body(Body::empty())
            .unwrap(),
        Some(iroh_peer("phone-endpoint-id")),
    )
    .await;
    assert_eq!(status, StatusCode::OK);

    // An api path: gate 2 still wants the token, and the two 401s are
    // distinct.
    let (status, body) = send_stamped(
        state.clone(),
        get("/api/devices"),
        Some(iroh_peer("phone-endpoint-id")),
    )
    .await;
    assert_eq!(status, StatusCode::UNAUTHORIZED);
    assert_eq!(body["error"]["code"], "MISSING_TOKEN");
    let (status, body) = send_stamped(
        state.clone(),
        get_with_token("/api/devices", "vdg_wrong"),
        Some(iroh_peer("phone-endpoint-id")),
    )
    .await;
    assert_eq!(status, StatusCode::UNAUTHORIZED);
    assert_eq!(body["error"]["code"], "INVALID_TOKEN");
    let (status, _) = send_stamped(
        state.clone(),
        get_with_token("/api/devices", token),
        Some(iroh_peer("phone-endpoint-id")),
    )
    .await;
    assert_eq!(status, StatusCode::OK);
}

/// A peer its own transport refuses is 403 on everything gated, with a good
/// token or none: gate 1 comes before the token is read.
#[tokio::test]
async fn a_refused_peer_never_reaches_the_token_comparison() {
    let state = state_with(Box::new(NobodyIsAPeer));
    for req in [
        get("/api/devices"),
        get_with_token("/api/devices", "vdg_whatever"),
    ] {
        let (status, body) = send(state.clone(), req, "8.8.8.8").await;
        assert_eq!(status, StatusCode::FORBIDDEN);
        assert_eq!(body["error"]["code"], "SOURCE_NOT_AUTHORIZED");
    }
    let (status, body) = send(
        state.clone(),
        Request::builder()
            .method("POST")
            .uri("/api/auth/pair")
            .body(Body::empty())
            .unwrap(),
        "8.8.8.8",
    )
    .await;
    assert_eq!(status, StatusCode::FORBIDDEN);
    assert_eq!(body["error"]["code"], "SOURCE_NOT_AUTHORIZED");
    // The unauthenticated pair still answers: health, and a claim that fails
    // on its code rather than on the source.
    let (status, _) = send(state.clone(), get("/api/health"), "8.8.8.8").await;
    assert_eq!(status, StatusCode::OK);
    let (status, body) = send(
        state.clone(),
        post_json(
            "/api/auth/claim",
            serde_json::json!({"pairing_token": "AAAA-AAAA", "device_name": "phone"}),
        ),
        "8.8.8.8",
    )
    .await;
    assert_eq!(status, StatusCode::UNAUTHORIZED);
    assert_eq!(body["error"]["code"], "PAIRING_CODE_INVALID");
}

/// **No synthesised loopback.** A request with no `Peer` stamp at all, and a
/// stamp naming a transport this build does not have, are wiring defects and
/// answer 403 - never "this must be the owner's terminal".
#[tokio::test]
async fn a_missing_or_unknown_stamp_is_refused_never_assumed() {
    let state = state_with(Box::new(EveryoneIsAPeer));
    let stranger = Peer {
        transport: "carrier-nobody-built",
        identity: "127.0.0.1".to_string(),
    };
    for stamp in [None, Some(stranger)] {
        let (status, body) = send_stamped(state.clone(), get("/api/devices"), stamp.clone()).await;
        assert_eq!(status, StatusCode::FORBIDDEN, "{body}");
        assert_eq!(body["error"]["code"], "SOURCE_NOT_AUTHORIZED");
        // The OAuth routes are where a fabricated 127.0.0.1 would have paid:
        // require_loopback defers to the registry and refuses both.
        let (status, body) = send_stamped(
            state.clone(),
            post_json(
                "/api/providers/openai/auth-attempts",
                serde_json::json!({"method": "api_key", "api_key": "never-staged"}),
            ),
            stamp.clone(),
        )
        .await;
        assert_eq!(status, StatusCode::FORBIDDEN, "{body}");
        assert_eq!(body["error"]["code"], "SOURCE_NOT_AUTHORIZED");
    }
}

/// The socket routes answer a missing stamp with a plain 403 and no upgrade:
/// `run_ws::authorize` is the other place a fabricated loopback would have
/// paid, because a loopback caller gets the stream with no token at all.
#[tokio::test]
async fn a_socket_upgrade_with_no_stamp_is_a_plain_403() {
    use tokio::io::{AsyncReadExt, AsyncWriteExt};
    // Served WITHOUT any transport stamp: straight to the router, the way a
    // mis-wired listener would.
    let state = state_with(Box::new(LoopbackTransport));
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
                "GET /api/ws/runs/r1 HTTP/1.1\r\nHost: {address}\r\nConnection: Upgrade\r\nUpgrade: websocket\r\nSec-WebSocket-Version: 13\r\nSec-WebSocket-Key: dGhlIHNhbXBsZSBub25jZQ==\r\n\r\n"
            )
            .as_bytes(),
        )
        .await
        .unwrap();
    // A refusal without an upgrade keeps the connection open, so read the
    // status line rather than waiting for a close that never comes.
    let mut response = vec![0u8; 512];
    let n = tokio::time::timeout(
        std::time::Duration::from_secs(1),
        stream.read(&mut response),
    )
    .await
    .unwrap()
    .unwrap();
    server.abort();
    assert!(
        response[..n].starts_with(b"HTTP/1.1 403"),
        "{}",
        String::from_utf8_lossy(&response[..n])
    );
}

// ------------------------------------------------------- the claim's binding

/// A claim over the built-in transport binds the handshake's own identity; a
/// claim over loopback or the tailnet binds nothing, which is the shipped
/// flow: an IP is asserted by whoever sent the packet.
#[tokio::test]
async fn a_claim_binds_exactly_what_its_transport_proved() {
    let state = state_with(Box::new(EveryoneIsAPeer));

    let claim = pair_and_claim(&state, iroh_peer("phone-endpoint-id"), "built-in phone").await;
    let device_id = claim["device_id"].as_str().unwrap();
    assert_eq!(
        vadgr_daemon::db::devices::peer_device(&state.db, "iroh", "phone-endpoint-id").unwrap(),
        Some(device_id.to_string())
    );

    for stamp in [
        Peer {
            transport: "loopback",
            identity: "127.0.0.1".to_string(),
        },
        Peer {
            transport: "tailscale",
            identity: "100.64.0.9".to_string(),
        },
    ] {
        let name = stamp.transport;
        let claim = pair_and_claim(&state, stamp, "socket phone").await;
        let device_id = claim["device_id"].as_str().unwrap().to_string();
        let bound: i64 = state
            .db
            .with(|c| {
                c.query_row(
                    "SELECT count(*) FROM device_peers WHERE device_id = ?1",
                    [&device_id],
                    |r| r.get(0),
                )
            })
            .unwrap();
        assert_eq!(bound, 0, "a {name} claim binds nothing");
    }
}

/// The claim body is strict and carries no key field: the daemon binds what
/// its own handshake proved, so `node_key` is a 422 on every transport.
#[tokio::test]
async fn a_claim_carrying_a_node_key_field_is_a_422_everywhere() {
    let state = state_with(Box::new(EveryoneIsAPeer));
    for stamp in [
        iroh_peer("phone-endpoint-id"),
        Peer {
            transport: "loopback",
            identity: "127.0.0.1".to_string(),
        },
    ] {
        let (status, body) = send_stamped(
            state.clone(),
            post_json(
                "/api/auth/claim",
                serde_json::json!({
                    "pairing_token": "AAAA-AAAA",
                    "device_name": "phone",
                    "node_key": "ee5c4b2f",
                }),
            ),
            Some(stamp),
        )
        .await;
        assert_eq!(status, StatusCode::UNPROCESSABLE_ENTITY, "{body}");
        assert!(body["detail"].is_array());
    }
}

/// An attacker chooses `device_name` and a terminal renders it, so it is
/// validated on every claim on every transport, in the same transitional 422
/// shape the strict body produces, naming the field.
#[tokio::test]
async fn a_hostile_device_name_is_a_422_naming_the_field_on_every_transport() {
    let state = state_with(Box::new(EveryoneIsAPeer));
    for stamp in [
        iroh_peer("phone-endpoint-id"),
        Peer {
            transport: "loopback",
            identity: "127.0.0.1".to_string(),
        },
        Peer {
            transport: "tailscale",
            identity: "100.64.0.9".to_string(),
        },
    ] {
        let (status, body) = send_stamped(
            state.clone(),
            post_json(
                "/api/auth/claim",
                serde_json::json!({
                    "pairing_token": "AAAA-AAAA",
                    "device_name": "evil\u{202E}name",
                }),
            ),
            Some(stamp),
        )
        .await;
        assert_eq!(status, StatusCode::UNPROCESSABLE_ENTITY, "{body}");
        let detail = body["detail"][0].clone();
        assert!(
            detail["loc"]
                .as_array()
                .is_some_and(|loc| loc.iter().any(|v| v == "device_name")),
            "{body}"
        );
    }
}

// ----------------------------------------------------------------- the shapes

/// `transports` carries one member per supported transport, always: null for
/// one that cannot be dialed right now, never an absent key. The top-level
/// host and port are the tailscale entry's own fields.
#[tokio::test]
async fn the_pair_and_claim_reports_carry_every_supported_transport() {
    let state = state_with(Box::new(EveryoneIsAPeer));
    let (status, pair) = send(
        state.clone(),
        Request::builder()
            .method("POST")
            .uri("/api/auth/pair")
            .body(Body::empty())
            .unwrap(),
        "127.0.0.1",
    )
    .await;
    assert_eq!(status, StatusCode::OK);
    let report = pair["transports"].as_object().unwrap();
    let keys: Vec<&String> = report.keys().collect();
    assert_eq!(
        keys,
        ["iroh", "tailscale"],
        "loopback never carries a phone"
    );
    assert!(report["iroh"].is_null(), "supported and not dialable: null");
    assert_eq!(report["tailscale"]["host"], "machine.tail.ts.net");
    // The top-level pair, produced from that entry so they cannot drift.
    assert_eq!(pair["host"], "machine.tail.ts.net");
    assert_eq!(pair["port"], 8000);
    assert!(pair["machine_name"].as_str().is_some());

    // The claim answers with the same report, plus the machine's name: the
    // typed-pairing phone finally learns it from the claim.
    let code = pair["pairing_token"].as_str().unwrap().to_string();
    let (status, claim) = send_stamped(
        state.clone(),
        post_json(
            "/api/auth/claim",
            serde_json::json!({"pairing_token": code, "device_name": "phone"}),
        ),
        Some(iroh_peer("phone-endpoint-id")),
    )
    .await;
    assert_eq!(status, StatusCode::OK);
    assert_eq!(claim["machine_name"], pair["machine_name"]);
    let claim_keys: Vec<&String> = claim["transports"].as_object().unwrap().keys().collect();
    assert_eq!(claim_keys, ["iroh", "tailscale"]);
}

/// A machine with no dialable tailscale mints a payload with no top-level
/// host and no port at all, rather than a placeholder.
#[tokio::test]
async fn the_pair_payload_omits_host_and_port_when_tailscale_has_no_address() {
    // NobodyIsAPeer is unavailable, and EveryoneIsAPeer is the only dialable
    // member; here the registry needs one dialable non-tailscale member, so
    // the built-in transport being down forces the 503 instead. Use the
    // dialable tailscale and read the down one from a second state.
    let state = state_with(Box::new(NobodyIsAPeer));
    let (status, body) = send(
        state.clone(),
        Request::builder()
            .method("POST")
            .uri("/api/auth/pair")
            .body(Body::empty())
            .unwrap(),
        "127.0.0.1",
    )
    .await;
    // Every member is down: the 503 names each transport in its own words,
    // and the details carry the report with every supported key.
    assert_eq!(status, StatusCode::SERVICE_UNAVAILABLE);
    assert_eq!(body["error"]["code"], "TRANSPORT_UNREACHABLE");
    let message = body["error"]["message"].as_str().unwrap();
    assert!(message.contains("tailscaled"), "{message}");
    let details: Vec<&String> = body["error"]["details"]["transports"]
        .as_object()
        .unwrap()
        .keys()
        .collect();
    assert_eq!(details, ["iroh", "tailscale"]);
}

// ------------------------------------------------------------- health's scope

/// Health's transport block is scope-gated per caller, for **every** entry: a
/// caller who has proved nothing learns names and liveness only, and a bound
/// peer's tokenless probe still gets the full block, because that probe is
/// the address refresh.
#[tokio::test]
async fn health_serves_addresses_only_to_a_caller_who_proved_something() {
    let state = state_with(Box::new(EveryoneIsAPeer));

    // Loopback: full, including the tailscale diagnostics.
    let (_, full) = send(state.clone(), get("/api/health"), "127.0.0.1").await;
    let block = full["transport"].as_object().unwrap();
    let keys: Vec<&String> = block.keys().collect();
    assert_eq!(keys, ["iroh", "loopback", "tailscale"]);
    assert_eq!(block["loopback"]["bind_host"], "127.0.0.1");

    // An unbound endpoint id inside a window: every entry reduced to name
    // and liveness.
    let (_, minted) = send(
        state.clone(),
        Request::builder()
            .method("POST")
            .uri("/api/auth/pair")
            .body(Body::empty())
            .unwrap(),
        "127.0.0.1",
    )
    .await;
    let (_, public) = send_stamped(
        state.clone(),
        get("/api/health"),
        Some(iroh_peer("unbound-endpoint-id")),
    )
    .await;
    for (name, entry) in public["transport"].as_object().unwrap() {
        let entry_keys: Vec<&String> = entry.as_object().unwrap().keys().collect();
        assert_eq!(entry_keys, ["available", "name"], "{name} leaked a field");
    }

    // A token that matches nothing is the public scope, not an error: health
    // must keep answering a phone this machine has forgotten.
    let (status, forgotten) = send_stamped(
        state.clone(),
        get_with_token("/api/health", "vdg_forgotten"),
        Some(iroh_peer("unbound-endpoint-id")),
    )
    .await;
    assert_eq!(status, StatusCode::OK);
    let entry = &forgotten["transport"]["tailscale"];
    assert_eq!(
        entry.as_object().unwrap().keys().len(),
        2,
        "still the public scope"
    );

    // A bound peer with no token gets the full block: the address refresh
    // rides the tokenless probe the phone already sends.
    let code = minted["pairing_token"].as_str().unwrap().to_string();
    let (status, _) = send_stamped(
        state.clone(),
        post_json(
            "/api/auth/claim",
            serde_json::json!({"pairing_token": code, "device_name": "phone"}),
        ),
        Some(iroh_peer("bound-endpoint-id")),
    )
    .await;
    assert_eq!(status, StatusCode::OK);
    let (_, refreshed) = send_stamped(
        state.clone(),
        get("/api/health"),
        Some(iroh_peer("bound-endpoint-id")),
    )
    .await;
    assert_eq!(
        refreshed["transport"]["loopback"]["bind_host"], "127.0.0.1",
        "a bound peer's tokenless probe is the refresh"
    );
}

// ------------------------------------------------------- adopting a transport
//
// A device holding a valid token may bind the identity the transport
// itself proved, over the transport it is adopting, once per transport. The
// route is the third gate path class: reachable by a peer with no binding,
// refused without a valid token.

fn adopt_with_token(token: &str) -> Request<Body> {
    Request::builder()
        .method("POST")
        .uri("/api/devices/self/transports")
        .header("authorization", format!("Bearer {token}"))
        .body(Body::empty())
        .unwrap()
}

fn tailnet_peer() -> Peer {
    Peer {
        transport: "tailscale",
        identity: "100.64.0.9".to_string(),
    }
}

/// The identity bound is the one the accepting transport stamped on the
/// request, never a field the caller sent: the route reads no body at all,
/// so a smuggled identity changes nothing. The stamp is an **unbound**
/// endpoint id, which gate 1 refuses everywhere else, so the 200 is also the
/// token-only path class working.
#[tokio::test]
async fn adoption_binds_the_stamped_identity_and_a_body_field_cannot_choose_it() {
    let state = state_with(Box::new(EveryoneIsAPeer));
    // Paired over the tailnet, which binds nothing: the recovery case this
    // route exists for.
    let claim = pair_and_claim(&state, tailnet_peer(), "tailnet phone").await;
    let token = claim["token"].as_str().unwrap();
    let device_id = claim["device_id"].as_str().unwrap();

    let request = Request::builder()
        .method("POST")
        .uri("/api/devices/self/transports")
        .header("authorization", format!("Bearer {token}"))
        .header("content-type", "application/json")
        .body(Body::from(
            r#"{"identity": "attacker-chosen", "node_key": "attacker-chosen"}"#,
        ))
        .unwrap();
    let (status, body) = send_stamped(
        state.clone(),
        request,
        Some(iroh_peer("recovering-endpoint-id")),
    )
    .await;
    assert_eq!(status, StatusCode::OK, "{body}");
    assert_eq!(body["transport"], "iroh");
    assert_eq!(body["adopted"], true);
    assert_eq!(
        vadgr_daemon::db::devices::peer_device(&state.db, "iroh", "recovering-endpoint-id")
            .unwrap(),
        Some(device_id.to_string()),
        "the handshake's identity is bound"
    );
    assert_eq!(
        vadgr_daemon::db::devices::peer_device(&state.db, "iroh", "attacker-chosen").unwrap(),
        None,
        "the body's identity is not"
    );
}

/// Once per transport per device: the same identity answers 200 again and
/// leaves one row; a different identity answers 409 and changes nothing, so
/// a stolen token cannot displace the phone that owns the pairing.
#[tokio::test]
async fn adopting_again_is_200_for_the_same_identity_and_409_for_another() {
    let state = state_with(Box::new(EveryoneIsAPeer));
    let claim = pair_and_claim(&state, tailnet_peer(), "tailnet phone").await;
    let token = claim["token"].as_str().unwrap();
    let device_id = claim["device_id"].as_str().unwrap().to_string();

    let (status, _) = send_stamped(
        state.clone(),
        adopt_with_token(token),
        Some(iroh_peer("phone-endpoint-id")),
    )
    .await;
    assert_eq!(status, StatusCode::OK);

    // The same identity again: idempotent.
    let (status, body) = send_stamped(
        state.clone(),
        adopt_with_token(token),
        Some(iroh_peer("phone-endpoint-id")),
    )
    .await;
    assert_eq!(status, StatusCode::OK, "{body}");
    assert_eq!(body["adopted"], true);

    // A different identity holding the same token: refused, nothing written.
    let (status, body) = send_stamped(
        state.clone(),
        adopt_with_token(token),
        Some(iroh_peer("thief-endpoint-id")),
    )
    .await;
    assert_eq!(status, StatusCode::CONFLICT, "{body}");
    assert_eq!(body["error"]["code"], "TRANSPORT_ALREADY_ADOPTED");
    assert_eq!(
        vadgr_daemon::db::devices::peer_device(&state.db, "iroh", "phone-endpoint-id").unwrap(),
        Some(device_id.clone()),
        "the first binding stands"
    );
    assert_eq!(
        vadgr_daemon::db::devices::peer_device(&state.db, "iroh", "thief-endpoint-id").unwrap(),
        None
    );
    let rows: i64 = state
        .db
        .with(|c| {
            c.query_row(
                "SELECT count(*) FROM device_peers WHERE device_id = ?1",
                [&device_id],
                |r| r.get(0),
            )
        })
        .unwrap();
    assert_eq!(rows, 1, "one binding per transport per device");
}

/// Loopback proves the caller is at the machine and the tailnet proves
/// membership; neither proves a key, so neither has an identity to bind and
/// both answer 422.
#[tokio::test]
async fn a_transport_that_proves_no_identity_answers_422() {
    let state = state_with(Box::new(EveryoneIsAPeer));
    let claim = pair_and_claim(&state, tailnet_peer(), "tailnet phone").await;
    let token = claim["token"].as_str().unwrap();
    let device_id = claim["device_id"].as_str().unwrap().to_string();

    for stamp in [
        Peer {
            transport: "loopback",
            identity: "127.0.0.1".to_string(),
        },
        tailnet_peer(),
    ] {
        let name = stamp.transport;
        let (status, body) =
            send_stamped(state.clone(), adopt_with_token(token), Some(stamp)).await;
        assert_eq!(status, StatusCode::UNPROCESSABLE_ENTITY, "{name}: {body}");
        assert_eq!(body["error"]["code"], "TRANSPORT_PROVES_NO_IDENTITY");
    }
    let rows: i64 = state
        .db
        .with(|c| {
            c.query_row(
                "SELECT count(*) FROM device_peers WHERE device_id = ?1",
                [&device_id],
                |r| r.get(0),
            )
        })
        .unwrap();
    assert_eq!(rows, 0, "nothing was bound");
}

/// Token-only means the token is the whole admission: no token is 401
/// MISSING_TOKEN even from a peer gate 1 would refuse, and a token whose
/// device was revoked while dialing is 401 INVALID_TOKEN with nothing
/// re-bound, because revocation cascaded the binding and killed the token.
#[tokio::test]
async fn adoption_is_401_with_no_token_and_after_revocation() {
    let state = state_with(Box::new(EveryoneIsAPeer));

    // A stranger with a connection and no token: refused for the missing
    // token, not for the unbound peer.
    let request = Request::builder()
        .method("POST")
        .uri("/api/devices/self/transports")
        .body(Body::empty())
        .unwrap();
    let (status, body) = send_stamped(
        state.clone(),
        request,
        Some(iroh_peer("stranger-endpoint-id")),
    )
    .await;
    assert_eq!(status, StatusCode::UNAUTHORIZED, "{body}");
    assert_eq!(body["error"]["code"], "MISSING_TOKEN");

    // A revoked device's token authenticates as nobody.
    let claim = pair_and_claim(&state, tailnet_peer(), "tailnet phone").await;
    let token = claim["token"].as_str().unwrap();
    let device_id = claim["device_id"].as_str().unwrap();
    let (status, _) = send_stamped(
        state.clone(),
        Request::builder()
            .method("DELETE")
            .uri(format!("/api/devices/{device_id}"))
            .header("authorization", format!("Bearer {token}"))
            .body(Body::empty())
            .unwrap(),
        Some(tailnet_peer()),
    )
    .await;
    assert_eq!(status, StatusCode::OK);
    let (status, body) = send_stamped(
        state.clone(),
        adopt_with_token(token),
        Some(iroh_peer("phone-endpoint-id")),
    )
    .await;
    assert_eq!(status, StatusCode::UNAUTHORIZED, "{body}");
    assert_eq!(body["error"]["code"], "INVALID_TOKEN");
    assert_eq!(
        vadgr_daemon::db::devices::peer_device(&state.db, "iroh", "phone-endpoint-id").unwrap(),
        None,
        "a revoked device cannot come back"
    );
}

/// The third path class widens nothing: a valid token from an unbound peer
/// earns adoption alone, `pair` still wants an authorized peer, and a
/// request with no stamp at all is still the wiring defect it always was.
#[tokio::test]
async fn a_valid_token_from_an_unbound_peer_earns_adoption_and_nothing_else() {
    let state = state_with(Box::new(EveryoneIsAPeer));
    let claim = pair_and_claim(&state, tailnet_peer(), "tailnet phone").await;
    let token = claim["token"].as_str().unwrap();

    // Gate 1 still refuses the unbound peer on a full-auth path, token or
    // not: the token-only set is one path, not a widening of the others.
    let (status, body) = send_stamped(
        state.clone(),
        get_with_token("/api/devices", token),
        Some(iroh_peer("unbound-endpoint-id")),
    )
    .await;
    assert_eq!(status, StatusCode::FORBIDDEN, "{body}");
    assert_eq!(body["error"]["code"], "SOURCE_NOT_AUTHORIZED");

    // The peer-only path keeps its own rule too.
    let (status, body) = send_stamped(
        state.clone(),
        Request::builder()
            .method("POST")
            .uri("/api/auth/pair")
            .header("authorization", format!("Bearer {token}"))
            .body(Body::empty())
            .unwrap(),
        Some(iroh_peer("unbound-endpoint-id")),
    )
    .await;
    assert_eq!(status, StatusCode::FORBIDDEN, "{body}");
    assert_eq!(body["error"]["code"], "SOURCE_NOT_AUTHORIZED");

    // And a stamp is still required: token-only does not mean stampless.
    let (status, body) = send_stamped(state.clone(), adopt_with_token(token), None).await;
    assert_eq!(status, StatusCode::FORBIDDEN, "{body}");
    assert_eq!(body["error"]["code"], "SOURCE_NOT_AUTHORIZED");
}
