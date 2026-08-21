//! The stable error envelope used by released clients.
//!
//! An unexplained status, code or field change stops the migration. The suite
//! asserts `details` **present**
//! rather than merely correct: the envelope declares `details` as an object and always
//! emits it, and a serialiser that drops empty maps is exactly the difference
//! this release exists to rule out.

use axum::http::StatusCode;
use axum::response::IntoResponse;
use http_body_util::BodyExt;
use vadgr_daemon::error::ApiError;

async fn body_of(e: ApiError) -> (StatusCode, serde_json::Value) {
    let r = e.into_response();
    let status = r.status();
    let bytes = r.into_body().collect().await.unwrap().to_bytes();
    (status, serde_json::from_slice(&bytes).unwrap())
}

#[tokio::test]
async fn details_is_present_and_empty_not_omitted() {
    let (_, v) = body_of(ApiError::run_not_found("r1")).await;
    let details = v["error"].get("details").expect("details must be present");
    assert!(details.is_object());
    assert_eq!(details.as_object().unwrap().len(), 0);
}

#[tokio::test]
async fn the_envelope_has_exactly_three_keys_under_error() {
    let (_, v) = body_of(ApiError::run_not_found("r1")).await;
    let obj = v["error"].as_object().unwrap();
    let mut keys: Vec<_> = obj.keys().map(|s| s.as_str()).collect();
    keys.sort();
    assert_eq!(keys, vec!["code", "details", "message"]);
    // and nothing beside `error` at the top level
    assert_eq!(v.as_object().unwrap().len(), 1);
}

#[tokio::test]
async fn every_code_carries_the_status_it_shipped_with() {
    // Read from api/routes/ rather than from the API reference: the sweep compares
    // against the daemon, and a right status with a wrong code is a defect it
    // would otherwise wave through.
    let cases: Vec<(ApiError, StatusCode, &str)> = vec![
        (
            ApiError::run_not_found("r"),
            StatusCode::NOT_FOUND,
            "RUN_NOT_FOUND",
        ),
        (
            ApiError::device_not_found("d"),
            StatusCode::NOT_FOUND,
            "DEVICE_NOT_FOUND",
        ),
        (
            ApiError::run_not_active(),
            StatusCode::CONFLICT,
            "RUN_NOT_ACTIVE",
        ),
        (
            ApiError::missing_token(),
            StatusCode::UNAUTHORIZED,
            "MISSING_TOKEN",
        ),
        (
            ApiError::invalid_token(),
            StatusCode::UNAUTHORIZED,
            "INVALID_TOKEN",
        ),
        (
            ApiError::source_not_authorized(),
            StatusCode::FORBIDDEN,
            "SOURCE_NOT_AUTHORIZED",
        ),
    ];
    for (err, status, code) in cases {
        let (got_status, v) = body_of(err).await;
        assert_eq!(got_status, status, "status for {code}");
        assert_eq!(v["error"]["code"], code);
    }
}

#[tokio::test]
async fn the_two_401s_stay_two_codes() {
    // They say "you did not authenticate" and "you authenticated as nobody".
    // The phone acts differently on each: one is a client bug, the other is a
    // pairing the machine has forgotten. Collapsing them would simplify the
    // gate and show up in the sweep as two rows becoming one.
    let (s1, v1) = body_of(ApiError::missing_token()).await;
    let (s2, v2) = body_of(ApiError::invalid_token()).await;
    assert_eq!(s1, s2);
    assert_ne!(v1["error"]["code"], v2["error"]["code"]);
}

#[tokio::test]
async fn the_gate_messages_are_verbatim() {
    // Messages are not contract - the codes are - so this is not the sweep's
    // stop condition. It is here because a gratuitous difference is one a
    // reader has to stop and explain, and the port has nothing to gain from it.
    for e in [ApiError::missing_token(), ApiError::invalid_token()] {
        let (_, v) = body_of(e).await;
        assert_eq!(v["error"]["message"], "A valid Bearer token is required.");
    }
    let (_, v) = body_of(ApiError::source_not_authorized()).await;
    assert_eq!(
        v["error"]["message"],
        "Source is not an authorized peer on this transport."
    );
}
