//! `vadgr health`, `vadgr providers`, `vadgr computer-use`.
//!
//! Ported from `cli/commands/info.py`: the read-only views of what the daemon
//! currently is.

use crate::client::{Client, ClientError};
use crate::output;

pub async fn health(client: &Client) -> Result<(), ClientError> {
    let body = client.get("/api/health").await?;
    let field = |k: &str| {
        body.get(k)
            .and_then(|v| v.as_str())
            .unwrap_or("-")
            .to_owned()
    };
    let cua = body
        .get("modules")
        .and_then(|m| m.get("computer_use"))
        .and_then(|v| v.as_bool())
        .map(|b| if b { "available" } else { "disabled" })
        .unwrap_or("-")
        .to_owned();
    let pairs = vec![
        ("Status".to_owned(), output::format_status(&field("status"))),
        ("Version".to_owned(), field("version")),
        ("Platform".to_owned(), field("platform")),
        ("Computer use".to_owned(), cua),
    ];
    anstream::println!("{}", output::render_kv(&pairs));
    Ok(())
}

pub async fn providers(client: &Client) -> Result<(), ClientError> {
    let body = client.get("/api/providers").await?;
    let empty = Vec::new();
    let list = body.as_array().unwrap_or(&empty);
    let rows: Vec<Vec<String>> = list
        .iter()
        .map(|p| {
            let connected = p
                .get("connected")
                .and_then(|v| v.as_bool())
                .unwrap_or(false);
            let default = p
                .get("is_default")
                .and_then(|v| v.as_bool())
                .unwrap_or(false);
            let models = p
                .get("models")
                .and_then(|v| v.as_array())
                .map(|m| m.len())
                .unwrap_or(0);
            vec![
                p.get("name")
                    .and_then(|v| v.as_str())
                    .unwrap_or("-")
                    .to_owned(),
                output::format_status(if connected { "ready" } else { "disabled" }),
                if default {
                    "default".to_owned()
                } else {
                    String::new()
                },
                models.to_string(),
            ]
        })
        .collect();
    anstream::println!(
        "{}",
        output::render_table(&["Provider", "State", "", "Models"], &rows)
    );
    Ok(())
}

pub async fn computer_use_status(client: &Client) -> Result<(), ClientError> {
    let body = client.get("/api/settings/computer-use").await?;
    let enabled = body
        .get("enabled")
        .and_then(|v| v.as_bool())
        .unwrap_or(false);
    let pairs = vec![(
        "Computer use".to_owned(),
        output::format_status(if enabled { "ready" } else { "disabled" }),
    )];
    anstream::println!("{}", output::render_kv(&pairs));
    Ok(())
}

pub async fn computer_use_set(client: &Client, enabled: bool) -> Result<(), ClientError> {
    client
        .put(
            "/api/settings/computer-use",
            Some(serde_json::json!({ "enabled": enabled })),
        )
        .await?;
    anstream::println!(
        "{}",
        output::success(if enabled {
            "Computer use enabled."
        } else {
            "Computer use disabled."
        })
    );
    Ok(())
}
