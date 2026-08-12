//! The error envelope, constructed in exactly one place.
//!
//! The `0.4.5` conformance sweep compares every HTTP row on method, path,
//! status **and** code, and a second construction site is where a key goes
//! missing between them. So every error in this daemon is an [`ApiError`] and
//! every one of them serialises through [`ApiError::into_response`].
//!
//! `details` is always present and defaults to `{}` - never omitted, never
//! null. Python's `ErrorResponse` declares `details: dict = {}` and always
//! emits it, and a client reading `details` on a serialiser that drops empty
//! maps is exactly the difference this release exists to rule out.

use axum::http::StatusCode;
use axum::response::{IntoResponse, Response};
use serde::Serialize;
use serde_json::{Value, json};

#[derive(Debug, Serialize)]
pub struct ApiError {
    #[serde(skip)]
    pub status: StatusCode,
    pub code: &'static str,
    pub message: String,
    pub details: Value,
}

impl ApiError {
    pub fn new(status: StatusCode, code: &'static str, message: impl Into<String>) -> Self {
        Self {
            status,
            code,
            message: message.into(),
            details: json!({}),
        }
    }

    /// The only error that carries a non-empty `details` today: pairing refuses
    /// with the transport's name in it, and the phone prints that name.
    pub fn with_details(mut self, details: Value) -> Self {
        self.details = details;
        self
    }

    /// A storage failure surfacing as a response. One constructor, because the
    /// same mapping written inline at each call site is how three of them
    /// drift apart.
    pub fn internal(err: impl std::fmt::Display) -> Self {
        Self::new(
            StatusCode::INTERNAL_SERVER_ERROR,
            "INTERNAL",
            err.to_string(),
        )
    }

    pub fn run_not_found(run_id: &str) -> Self {
        Self::new(
            StatusCode::NOT_FOUND,
            "RUN_NOT_FOUND",
            format!("Run with id '{run_id}' not found"),
        )
    }

    pub fn device_not_found(device_id: &str) -> Self {
        Self::new(
            StatusCode::NOT_FOUND,
            "DEVICE_NOT_FOUND",
            format!("Device '{device_id}' not found."),
        )
    }

    pub fn run_not_active() -> Self {
        Self::new(
            StatusCode::CONFLICT,
            "RUN_NOT_ACTIVE",
            "Run is already finished",
        )
    }

    // The two gate messages are Python's, verbatim, and they are deliberately
    // the SAME string for both codes. Splitting them would read better and is
    // exactly the redesign a faithful port must not smuggle in: the codes carry
    // the difference, the message is prose, and a reader comparing the two
    // daemons should find nothing here to explain.
    pub fn missing_token() -> Self {
        Self::new(
            StatusCode::UNAUTHORIZED,
            "MISSING_TOKEN",
            "A valid Bearer token is required.",
        )
    }

    pub fn invalid_token() -> Self {
        Self::new(
            StatusCode::UNAUTHORIZED,
            "INVALID_TOKEN",
            "A valid Bearer token is required.",
        )
    }

    pub fn source_not_authorized() -> Self {
        Self::new(
            StatusCode::FORBIDDEN,
            "SOURCE_NOT_AUTHORIZED",
            "Source is not an authorized peer on this transport.",
        )
    }
}

impl IntoResponse for ApiError {
    fn into_response(self) -> Response {
        let body = json!({
            "error": {
                "code": self.code,
                "message": self.message,
                "details": self.details,
            }
        });
        (self.status, axum::Json(body)).into_response()
    }
}

pub type ApiResult<T> = Result<T, ApiError>;
