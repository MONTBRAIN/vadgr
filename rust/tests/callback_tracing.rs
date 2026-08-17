//! The OAuth callback must never write its query into the log.
//!
//! The callback listener was untraced, which made a live authorization
//! unverifiable. Adding the default HTTP span fixed that and put the
//! authorization code in the daemon log, because the default span records the
//! whole URI. This asserts the span carries the path and nothing after it.

use std::sync::{Arc, Mutex};
use tracing::subscriber::with_default;
use tracing_subscriber::fmt::MakeWriter;
use vadgr_daemon::routes::providers::callback_span;

#[derive(Clone, Default)]
struct Capture(Arc<Mutex<Vec<u8>>>);

impl std::io::Write for Capture {
    fn write(&mut self, buffer: &[u8]) -> std::io::Result<usize> {
        self.0.lock().unwrap().extend_from_slice(buffer);
        Ok(buffer.len())
    }
    fn flush(&mut self) -> std::io::Result<()> {
        Ok(())
    }
}

impl<'a> MakeWriter<'a> for Capture {
    type Writer = Self;
    fn make_writer(&'a self) -> Self::Writer {
        self.clone()
    }
}

#[test]
fn the_callback_span_records_the_path_and_not_the_query() {
    let capture = Capture::default();
    let subscriber = tracing_subscriber::fmt()
        .with_writer(capture.clone())
        .with_ansi(false)
        .finish();

    let secret_code = "live-authorization-code-that-must-not-be-logged";
    let request = axum::http::Request::builder()
        .method("GET")
        .uri(format!(
            "/auth/callback?code={secret_code}&state=live-state-value&scope=openid"
        ))
        .body(())
        .unwrap();

    with_default(subscriber, || {
        let span = callback_span(&request);
        let _entered = span.enter();
        tracing::info!("finished processing request");
    });

    let logged = String::from_utf8(capture.0.lock().unwrap().clone()).unwrap();

    assert!(
        logged.contains("/auth/callback"),
        "the span must still identify the route, got: {logged}"
    );
    assert!(
        !logged.contains(secret_code),
        "the authorization code reached the log: {logged}"
    );
    assert!(
        !logged.contains("live-state-value"),
        "the OAuth state reached the log: {logged}"
    );
    assert!(
        !logged.contains("code="),
        "the query reached the log: {logged}"
    );
}
