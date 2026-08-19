//! `--json` means a stdout a script can parse, with nothing else on it.
//!
//! Regression test for a real defect, found by driving the CLI on Windows
//! rather than by a unit test. `vadgr run <task> --background --json` printed
//! the run row and then a friendly `Watch it with: ...` line on the same
//! stream, so the output the flag calls machine readable was invalid JSON and
//! `jq` failed on it.
//!
//! The hint itself is wanted: it is what a person needs after starting a
//! background run. It just cannot share stdout with the object.

use axum::{Json, Router, routing::post};
use serde_json::{Value, json};
use std::process::Command;
use tokio::net::TcpListener;

/// A daemon stub that accepts a run and answers with a row, which is all the
/// CLI needs to reach the printing path under test.
async fn accepting_daemon() -> (String, tokio::task::JoinHandle<()>) {
    let listener = TcpListener::bind("127.0.0.1:0").await.unwrap();
    let address = listener.local_addr().unwrap();
    let app = Router::new().route(
        "/api/runs",
        post(|| async {
            Json(json!({
                "id": "run-0123456789abcdef0123456789abcdef",
                "status": "queued",
                "inputs": {"task": "a task"},
                "outputs": {},
            }))
        }),
    );
    let task = tokio::spawn(async move {
        axum::serve(listener, app).await.unwrap();
    });
    (format!("http://{address}"), task)
}

#[tokio::test(flavor = "multi_thread")]
async fn background_json_output_is_parseable_on_its_own() {
    let (base_url, server) = accepting_daemon().await;
    let home = std::env::temp_dir().join(format!("vadgr-cli-json-{}", std::process::id()));

    // Off the runtime thread: a blocking `output()` here would stop the stub
    // above from ever being polled, and the CLI would time out against a server
    // that never got to answer.
    let out = tokio::task::spawn_blocking(move || {
        Command::new(env!("CARGO_BIN_EXE_vadgr"))
            .args(["run", "a task", "--background", "--json"])
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
        "the CLI should accept the run: {}",
        String::from_utf8_lossy(&out.stderr)
    );

    let parsed: Result<Value, _> = serde_json::from_str(&stdout);
    assert!(
        parsed.is_ok(),
        "stdout under --json must parse on its own, got:\n{stdout}"
    );
    assert_eq!(
        parsed.unwrap().get("id").and_then(Value::as_str),
        Some("run-0123456789abcdef0123456789abcdef"),
        "the parsed row must carry the id the daemon returned"
    );
    assert!(
        !stdout.contains("Watch it with"),
        "the hint belongs off the JSON stream, got:\n{stdout}"
    );

    server.abort();
}

/// A watched run under `--json` puts exactly one document on stdout.
///
/// `--background --json` was fixed at `0.4.8` after a Windows pass found the
/// watch hint printed beside the object. The watched path kept the same defect
/// for longer, because nothing parsed its whole stdout: the run object went out
/// first and the watcher's own "Run completed" summary and results link
/// followed it, so `jq` failed on output the CLI had just called machine
/// readable. The document a script wants there is the finished run, so that is
/// what it prints, once.
#[test]
fn the_watched_json_path_writes_one_document_and_the_summary_is_not_on_stdout() {
    let source = std::fs::read_to_string(
        std::path::Path::new(env!("CARGO_MANIFEST_DIR")).join("src/cli/main.rs"),
    )
    .expect("the CLI entry point is in the repository");

    // The watcher is told to stay quiet exactly when the output is machine read.
    assert!(
        source.contains("stream::follow(client.base_url(), &run_id, RUN_WATCH_TIMEOUT, as_json)"),
        "the watcher must be silenced under --json"
    );
    // And the queued row is printed only for a background run, which is the one
    // case where no later document exists.
    assert!(
        source.contains("if as_json {\n        if background {"),
        "a watched --json run must not print the queued row before the final one"
    );

    let stream = std::fs::read_to_string(
        std::path::Path::new(env!("CARGO_MANIFEST_DIR")).join("src/cli/stream.rs"),
    )
    .expect("the watcher is in the repository");
    assert!(
        !stream.contains("anstream::println!(\"{}\", output::success"),
        "the watcher's summary must go through the quiet guard, never straight to stdout"
    );
}
