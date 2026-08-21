//! `vadgr runs resume` prints the run it just resumed.
//!
//! Regression test for a real defect, found by driving the CLI on Windows rather
//! than by a unit test. The command printed one line, `Resuming run <id>`, and
//! stopped. That line says the daemon accepted the request; it says nothing
//! about the run. The owner had to type `vadgr runs get <id>` to learn whether
//! the run went back to `running`, which provider it uses, or what it is doing.
//!
//! The row it prints is the block `vadgr runs get` prints, from the same
//! printer, so the two commands cannot describe the same run differently.

use axum::{Json, Router, routing::get, routing::post};
use serde_json::json;
use std::process::Command;
use tokio::net::TcpListener;

const RUN_ID: &str = "run-0123456789abcdef0123456789abcdef";

/// A daemon stub that accepts a resume and then reports the run as running.
///
/// Three routes, because that is what the command touches: the listing resolves
/// the id prefix, the resume is the request itself, and the detail is the row
/// under test.
async fn resuming_daemon() -> (String, tokio::task::JoinHandle<()>) {
    let listener = TcpListener::bind("127.0.0.1:0").await.unwrap();
    let address = listener.local_addr().unwrap();
    let row = json!({
        "id": RUN_ID,
        "agent_name": "restart the failed deploy",
        "status": "running",
        "provider": "gemini",
        "model": "gemini-2.0-flash",
        "started_at": "2026-08-20T10:00:00+00:00",
        "outputs": {},
    });
    let listed = row.clone();
    let app = Router::new()
        .route(
            "/api/runs",
            get(move || async move { Json(json!([listed])) }),
        )
        .route(
            &format!("/api/runs/{RUN_ID}/resume"),
            post(|| async { Json(json!({"message": "Run resumed", "id": RUN_ID})) }),
        )
        .route(
            &format!("/api/runs/{RUN_ID}"),
            get(move || async move { Json(row) }),
        );
    let task = tokio::spawn(async move {
        axum::serve(listener, app).await.unwrap();
    });
    (format!("http://{address}"), task)
}

#[tokio::test(flavor = "multi_thread")]
async fn resume_prints_the_row_it_resumed() {
    let (base_url, server) = resuming_daemon().await;
    let home = std::env::temp_dir().join(format!("vadgr-cli-resume-{}", std::process::id()));

    // Off the runtime thread: a blocking `output()` here would stop the stub
    // above from ever being polled, and the CLI would time out against a server
    // that never got to answer.
    let out = tokio::task::spawn_blocking(move || {
        Command::new(env!("CARGO_BIN_EXE_vadgr"))
            // The eight characters `vadgr runs list` prints, which is the only
            // form of a run id anybody types.
            .args(["runs", "resume", "run-0123"])
            .env("VADGR_HOME", &home)
            .env("VADGR_API_URL", &base_url)
            .output()
            .expect("the CLI binary runs")
    })
    .await
    .expect("the CLI call completes");

    let stdout = String::from_utf8_lossy(&out.stdout).into_owned();
    assert!(
        out.status.success(),
        "an accepted resume exits 0: {}",
        String::from_utf8_lossy(&out.stderr)
    );
    assert!(
        stdout.contains("Resuming run"),
        "the resume must still say it was accepted, got:\n{stdout}"
    );

    // The defect: everything below this line was missing.
    for expected in [
        "Run ID",
        RUN_ID,
        "restart the failed deploy",
        "Status",
        "running",
        "Provider",
        "gemini",
        "Model",
        "gemini-2.0-flash",
    ] {
        assert!(
            stdout.contains(expected),
            "the resumed run's row must carry {expected:?}, got:\n{stdout}"
        );
    }

    server.abort();
}
