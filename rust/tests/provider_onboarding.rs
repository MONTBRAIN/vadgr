use axum::body::{Body, to_bytes};
use axum::extract::{Request, State};
use axum::http::{HeaderMap, StatusCode};
use axum::response::{IntoResponse, Response};
use axum::{Json, Router};
use base64::Engine;
use base64::engine::general_purpose::URL_SAFE_NO_PAD;
use serde_json::{Value, json};
use std::path::Path;
use std::sync::atomic::{AtomicBool, AtomicUsize, Ordering};
use std::sync::{Arc, Mutex};
use tokio::net::TcpListener;
use vadgr_daemon::db::Db;
use vadgr_daemon::db::providers;
use vadgr_daemon::engine::provider::ModelFactory;
use vadgr_daemon::engine::provider::NativeModelFactory;
use vadgr_daemon::engine::provider::credentials::CredentialStore;
use vadgr_daemon::engine::provider::oauth::OAuthDescriptor;
use vadgr_daemon::engine::provider::service::{ProviderEndpoints, ProviderService};
use vadgr_daemon::engine::types::Message;

#[derive(Clone, Debug)]
struct RecordedRequest {
    path: String,
    headers: HeaderMap,
    body: String,
}

#[derive(Clone, Default)]
struct FakeState {
    requests: Arc<Mutex<Vec<RecordedRequest>>>,
    reject_original_access_token: Arc<AtomicBool>,
    reject_openai_model: Arc<AtomicBool>,
    openai_catalog_failures: Arc<AtomicUsize>,
}

#[tokio::test]
async fn provider_connections_coexist_and_database_never_stores_secrets() {
    let (base_url, fake, task) = fake_provider().await;
    let directory = tempfile::tempdir().unwrap();
    let db_path = directory.path().join("vadgr.db");
    let db = Db::open(&db_path).unwrap();
    let credential_directory = directory.path().join("state/credentials");
    let service = ProviderService::new(
        db.clone(),
        CredentialStore::new(credential_directory.clone()).unwrap(),
        endpoints(&base_url),
    )
    .unwrap();

    let openai = service
        .start_api_key("openai", "openai-secret-test".to_owned())
        .await
        .unwrap();
    service
        .commit_attempt("openai", &openai.id, None)
        .await
        .unwrap();
    assert_eq!(
        service.default_model().unwrap(),
        Some(("openai".to_owned(), "gpt-5.6-sol".to_owned()))
    );

    let gemini = service
        .start_api_key("gemini", "gemini-secret-test".to_owned())
        .await
        .unwrap();
    service
        .commit_attempt("gemini", &gemini.id, None)
        .await
        .unwrap();
    let anthropic = service
        .start_api_key("anthropic", "anthropic-secret-test".to_owned())
        .await
        .unwrap();
    service
        .commit_attempt("anthropic", &anthropic.id, None)
        .await
        .unwrap();

    let rows = service.list_rows().unwrap();
    assert_eq!(
        rows.iter().filter(|row| row["connected"] == true).count(),
        3
    );
    assert_eq!(providers::connections(&db).unwrap().len(), 3);
    assert!(providers::catalog(&db, "openai").unwrap().is_some());
    assert!(providers::catalog(&db, "gemini").unwrap().is_some());
    assert!(providers::catalog(&db, "anthropic").unwrap().is_some());

    service
        .set_default("gemini", "gemini-2.5-flash")
        .await
        .unwrap();
    assert_eq!(
        service.default_model().unwrap(),
        Some(("gemini".to_owned(), "gemini-2.5-flash".to_owned()))
    );
    service.disconnect("openai").await.unwrap();
    assert!(providers::connection(&db, "openai").unwrap().is_none());
    assert!(providers::connection(&db, "gemini").unwrap().is_some());
    assert!(providers::connection(&db, "anthropic").unwrap().is_some());

    let database_bytes = database_files(&db_path);
    for secret in [
        "openai-secret-test",
        "gemini-secret-test",
        "anthropic-secret-test",
    ] {
        assert!(
            !database_bytes
                .windows(secret.len())
                .any(|bytes| bytes == secret.as_bytes())
        );
        assert!(!serde_json::to_string(&rows).unwrap().contains(secret));
    }
    let credential_bytes = credential_files(&credential_directory);
    assert!(
        credential_bytes
            .windows("gemini-secret-test".len())
            .any(|bytes| { bytes == b"gemini-secret-test" })
    );
    assert!(
        credential_bytes
            .windows("anthropic-secret-test".len())
            .any(|bytes| { bytes == b"anthropic-secret-test" })
    );

    let requests = fake.requests.lock().unwrap();
    assert!(requests.iter().any(|request| {
        request.path == "/openai/responses"
            && request.headers.get("authorization").unwrap() == "Bearer openai-secret-test"
    }));
    assert!(requests.iter().any(|request| {
        request.path.starts_with("/gemini/models/")
            && request.headers.get("x-goog-api-key").unwrap() == "gemini-secret-test"
    }));
    assert!(requests.iter().any(|request| {
        request.path == "/anthropic/messages"
            && request.headers.get("x-api-key").unwrap() == "anthropic-secret-test"
    }));
    task.abort();
}

#[tokio::test]
async fn owned_chatgpt_oauth_calls_openai_directly_with_vadgr_identity() {
    let (base_url, fake, task) = fake_provider().await;
    let directory = tempfile::tempdir().unwrap();
    let db = Db::open(directory.path().join("vadgr.db")).unwrap();
    let service = ProviderService::new(
        db.clone(),
        CredentialStore::new(directory.path().join("state/credentials")).unwrap(),
        endpoints(&base_url),
    )
    .unwrap();

    let attempt = service.start_oauth("openai").await.unwrap();
    let authorization_url = url::Url::parse(attempt.authorization_url.as_deref().unwrap()).unwrap();
    let state = authorization_url
        .query_pairs()
        .find(|(key, _)| key == "state")
        .map(|(_, value)| value.into_owned())
        .unwrap();
    assert_eq!(
        authorization_url
            .query_pairs()
            .find(|(key, _)| key == "originator")
            .map(|(_, value)| value.into_owned())
            .as_deref(),
        Some("vadgr")
    );

    service
        .complete_oauth_callback(&state, Some("authorization-code"), None)
        .await
        .unwrap();
    assert_eq!(
        service.attempt(&attempt.id).await.unwrap().status,
        "authenticated"
    );
    service
        .commit_attempt("openai", &attempt.id, None)
        .await
        .unwrap();

    let connection = providers::connection(&db, "openai").unwrap().unwrap();
    assert_eq!(connection.auth_method, "oauth");
    assert_eq!(connection.account_id.as_deref(), Some("acct-test"));
    assert!(!connection.secret_ref.contains("access-token"));

    let requests = fake.requests.lock().unwrap();
    let token = requests
        .iter()
        .find(|request| request.path == "/oauth/token")
        .unwrap();
    assert!(token.body.contains("grant_type=authorization_code"));
    assert!(token.body.contains("code_verifier="));
    let models = requests
        .iter()
        .find(|request| request.path == "/chatgpt/models")
        .unwrap();
    assert_eq!(models.headers.get("originator").unwrap(), "vadgr");
    assert_eq!(
        models.headers.get("chatgpt-account-id").unwrap(),
        "acct-test"
    );
    let readiness = requests
        .iter()
        .find(|request| request.path == "/chatgpt/responses")
        .unwrap();
    assert_eq!(readiness.headers.get("originator").unwrap(), "vadgr");
    assert_eq!(
        readiness.headers.get("chatgpt-account-id").unwrap(),
        "acct-test"
    );
    assert!(
        readiness
            .headers
            .get("user-agent")
            .unwrap()
            .to_str()
            .unwrap()
            .starts_with("vadgr/")
    );
    assert!(!readiness.body.contains("OpenClaw"));
    assert!(!readiness.body.contains("Codex CLI"));
    task.abort();
}

#[tokio::test]
async fn chatgpt_unauthorized_refreshes_the_committed_credential_and_retries_once() {
    let (base_url, fake, task) = fake_provider().await;
    let directory = tempfile::tempdir().unwrap();
    let db = Db::open(directory.path().join("vadgr.db")).unwrap();
    let service = ProviderService::new(
        db.clone(),
        CredentialStore::new(directory.path().join("state/credentials")).unwrap(),
        endpoints(&base_url),
    )
    .unwrap();

    let attempt = service.start_oauth("openai").await.unwrap();
    let authorization_url = url::Url::parse(attempt.authorization_url.as_deref().unwrap()).unwrap();
    let state = authorization_url
        .query_pairs()
        .find(|(key, _)| key == "state")
        .map(|(_, value)| value.into_owned())
        .unwrap();
    service
        .complete_oauth_callback(&state, Some("authorization-code"), None)
        .await
        .unwrap();
    service
        .commit_attempt("openai", &attempt.id, None)
        .await
        .unwrap();
    let original_reference = providers::connection(&db, "openai")
        .unwrap()
        .unwrap()
        .secret_ref;

    fake.reject_original_access_token
        .store(true, Ordering::SeqCst);
    let factory = NativeModelFactory::new(service);
    let client = factory.build("openai", "gpt-5.6-sol").await.unwrap();
    let response = client
        .complete(&[Message::text("user", "Reply with OK.")], &[], 32)
        .await
        .unwrap();
    assert_eq!(response.usage.input_tokens, 2);

    let refreshed_reference = providers::connection(&db, "openai")
        .unwrap()
        .unwrap()
        .secret_ref;
    assert_ne!(refreshed_reference, original_reference);
    let requests = fake.requests.lock().unwrap();
    assert_eq!(
        requests
            .iter()
            .filter(|request| {
                request.path == "/oauth/token" && request.body.contains("grant_type=refresh_token")
            })
            .count(),
        1
    );
    assert!(requests.iter().any(|request| {
        request.path == "/chatgpt/responses"
            && request
                .headers
                .get("authorization")
                .unwrap()
                .to_str()
                .unwrap()
                == format!("Bearer {}", chatgpt_access_token("refreshed"))
    }));
    task.abort();
}

#[tokio::test]
async fn catalog_discovery_retries_transient_failures_with_a_fixed_bound() {
    let (base_url, fake, task) = fake_provider().await;
    fake.openai_catalog_failures.store(2, Ordering::SeqCst);
    let directory = tempfile::tempdir().unwrap();
    let service = ProviderService::new(
        Db::open(directory.path().join("vadgr.db")).unwrap(),
        CredentialStore::new(directory.path().join("state/credentials")).unwrap(),
        endpoints(&base_url),
    )
    .unwrap();

    let attempt = service
        .start_api_key("openai", "openai-secret-test".to_owned())
        .await
        .unwrap();
    service
        .commit_attempt("openai", &attempt.id, None)
        .await
        .unwrap();

    assert_eq!(
        fake.requests
            .lock()
            .unwrap()
            .iter()
            .filter(|request| request.path == "/openai/models")
            .count(),
        3
    );
    task.abort();
}

#[tokio::test]
async fn model_unavailable_triggers_a_catalog_refresh_without_hiding_the_error() {
    let (base_url, fake, task) = fake_provider().await;
    let directory = tempfile::tempdir().unwrap();
    let service = ProviderService::new(
        Db::open(directory.path().join("vadgr.db")).unwrap(),
        CredentialStore::new(directory.path().join("state/credentials")).unwrap(),
        endpoints(&base_url),
    )
    .unwrap();
    let attempt = service
        .start_api_key("openai", "openai-secret-test".to_owned())
        .await
        .unwrap();
    service
        .commit_attempt("openai", &attempt.id, None)
        .await
        .unwrap();

    fake.reject_openai_model.store(true, Ordering::SeqCst);
    let client = NativeModelFactory::new(service)
        .build("openai", "gpt-5.6-sol")
        .await
        .unwrap();
    let error = client
        .complete(&[Message::text("user", "test")], &[], 32)
        .await
        .unwrap_err();

    assert!(matches!(
        error,
        vadgr_daemon::engine::types::ProviderError::ModelUnavailable
    ));
    assert_eq!(
        fake.requests
            .lock()
            .unwrap()
            .iter()
            .filter(|request| request.path == "/openai/models")
            .count(),
        2
    );
    task.abort();
}

async fn fake_provider() -> (String, FakeState, tokio::task::JoinHandle<()>) {
    let state = FakeState::default();
    let listener = TcpListener::bind("127.0.0.1:0").await.unwrap();
    let address = listener.local_addr().unwrap();
    let app = Router::new()
        .fallback(fake_response)
        .with_state(state.clone());
    let task = tokio::spawn(async move {
        axum::serve(listener, app).await.unwrap();
    });
    (format!("http://{address}"), state, task)
}

async fn fake_response(State(state): State<FakeState>, request: Request) -> Response {
    let path = request.uri().path().to_owned();
    let headers = request.headers().clone();
    let body = to_bytes(request.into_body(), 1024 * 1024).await.unwrap();
    let body = String::from_utf8_lossy(&body).into_owned();
    state.requests.lock().unwrap().push(RecordedRequest {
        path: path.clone(),
        headers: headers.clone(),
        body: body.clone(),
    });

    if path == "/openai/models"
        && state
            .openai_catalog_failures
            .fetch_update(Ordering::SeqCst, Ordering::SeqCst, |remaining| {
                remaining.checked_sub(1)
            })
            .is_ok()
    {
        return StatusCode::SERVICE_UNAVAILABLE.into_response();
    }
    if path == "/openai/responses" && state.reject_openai_model.load(Ordering::SeqCst) {
        return StatusCode::NOT_FOUND.into_response();
    }

    match path.as_str() {
        "/oauth/token" => Json(json!({
            "access_token": if body.contains("grant_type=refresh_token") {
                chatgpt_access_token("refreshed")
            } else {
                chatgpt_access_token("initial")
            },
            "refresh_token": "refresh-token-test",
            "expires_in": 3600,
            "provider_extension": "accepted"
        }))
        .into_response(),
        "/openai/models" => Json(json!({
            "data":[{"id":"gpt-5.6-sol"},{"id":"whisper-1"}]
        }))
        .into_response(),
        "/openai/responses" => Json(openai_response()).into_response(),
        "/chatgpt/models" => Json(json!({
            "models":[{
                "slug":"gpt-5.6-sol",
                "display_name":"GPT 5.6 Sol",
                "visibility":"list",
                "show_in_picker":true
            }]
        }))
        .into_response(),
        "/chatgpt/responses"
            if state.reject_original_access_token.load(Ordering::SeqCst)
                && headers.get("authorization").is_some_and(|header| {
                    header.to_str().ok().is_some_and(|value| {
                        value == format!("Bearer {}", chatgpt_access_token("initial"))
                    })
                }) =>
        {
            StatusCode::UNAUTHORIZED.into_response()
        }
        "/chatgpt/responses" => (
            [("content-type", "text/event-stream")],
            format!(
                "data: {}\n\n",
                json!({"type":"response.completed","response":openai_response()})
            ),
        )
            .into_response(),
        "/gemini/models" => Json(json!({
            "models":[{
                "name":"models/gemini-2.5-flash",
                "displayName":"Gemini 2.5 Flash",
                "supportedGenerationMethods":["generateContent"]
            }]
        }))
        .into_response(),
        value if value.starts_with("/gemini/models/") => Json(json!({
            "candidates":[{"content":{"parts":[{"text":"OK"}]},"finishReason":"STOP"}],
            "usageMetadata":{"promptTokenCount":2,"candidatesTokenCount":1}
        }))
        .into_response(),
        "/anthropic/models" => Json(json!({
            "data":[{"id":"claude-sonnet-4-5","display_name":"Claude Sonnet 4.5"}]
        }))
        .into_response(),
        "/anthropic/messages" => Json(json!({
            "content":[{"type":"text","text":"OK"}],
            "stop_reason":"end_turn",
            "usage":{"input_tokens":2,"output_tokens":1}
        }))
        .into_response(),
        _ => (StatusCode::NOT_FOUND, Body::empty()).into_response(),
    }
}

fn openai_response() -> Value {
    json!({
        "status":"completed",
        "output":[{"type":"message","content":[{"type":"output_text","text":"OK"}]}],
        "usage":{"input_tokens":2,"output_tokens":1}
    })
}

fn chatgpt_access_token(signature: &str) -> String {
    let header = URL_SAFE_NO_PAD.encode(br#"{"alg":"none"}"#);
    let payload = URL_SAFE_NO_PAD
        .encode(br#"{"https://api.openai.com/auth":{"chatgpt_account_id":"acct-test"}}"#);
    format!("{header}.{payload}.{signature}")
}

fn endpoints(base_url: &str) -> ProviderEndpoints {
    let authorize_url = Box::leak(format!("{base_url}/oauth/authorize").into_boxed_str());
    let token_url = Box::leak(format!("{base_url}/oauth/token").into_boxed_str());
    ProviderEndpoints {
        openai_oauth: OAuthDescriptor {
            authorize_url,
            token_url,
            client_id: "vadgr-test-client",
            redirect_uri: "http://localhost:1455/auth/callback",
            scopes: &["openid", "offline_access"],
            authorize_parameters: &[("originator", "vadgr")],
        },
        openai_platform_responses: format!("{base_url}/openai/responses"),
        openai_platform_models: format!("{base_url}/openai/models"),
        openai_chatgpt_responses: format!("{base_url}/chatgpt/responses"),
        openai_chatgpt_models: format!("{base_url}/chatgpt/models"),
        gemini_api_root: format!("{base_url}/gemini"),
        gemini_models: format!("{base_url}/gemini/models"),
        anthropic_messages: format!("{base_url}/anthropic/messages"),
        anthropic_models: format!("{base_url}/anthropic/models"),
    }
}

fn database_files(path: &Path) -> Vec<u8> {
    [
        path.to_path_buf(),
        Path::new(&format!("{}-wal", path.display())).to_path_buf(),
        Path::new(&format!("{}-shm", path.display())).to_path_buf(),
    ]
    .iter()
    .filter_map(|candidate| std::fs::read(candidate).ok())
    .flatten()
    .collect()
}

fn credential_files(directory: &Path) -> Vec<u8> {
    std::fs::read_dir(directory)
        .unwrap()
        .filter_map(Result::ok)
        .filter_map(|entry| std::fs::read(entry.path()).ok())
        .flatten()
        .collect()
}
