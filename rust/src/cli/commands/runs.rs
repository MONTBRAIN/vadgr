//! `vadgr runs`: list, get, cancel, resume.
//!
//! Ported from `cli/commands/runs.py`. The exit code a terminal run status
//! implies is part of the contract the recorded sweep asserts, so it lives here
//! in one place rather than at each call site.

use crate::client::{Client, ClientError};
use crate::output;

/// The exit code a finished run leaves behind.
///
/// A script runs `vadgr run` and branches on this, so the mapping is a contract
/// rather than a convenience. `cancelled` is deliberately not a failure: the
/// owner asked for it.
pub fn exit_code_for(status: &str) -> i32 {
    match status {
        "completed" => 0,
        "cancelled" => 0,
        _ => 1,
    }
}

fn truncate(text: &str, width: usize) -> String {
    // Count characters, not bytes. A task sentence carries accented text and
    // emoji, and slicing by byte splits them into replacement characters.
    let chars: Vec<char> = text.chars().collect();
    if chars.len() <= width {
        return text.to_owned();
    }
    let cut: String = chars[..width.saturating_sub(1)].iter().collect();
    format!("{cut}\u{2026}")
}

pub async fn list(client: &Client) -> Result<(), ClientError> {
    let body = client.get("/api/runs").await?;
    let empty = Vec::new();
    let runs = body.as_array().unwrap_or(&empty);
    if runs.is_empty() {
        anstream::println!("{}", output::info("No runs yet."));
        return Ok(());
    }
    let rows: Vec<Vec<String>> = runs
        .iter()
        .map(|r| {
            let id = r.get("id").and_then(|v| v.as_str()).unwrap_or("-");
            let task = r.get("agent_name").and_then(|v| v.as_str()).unwrap_or("-");
            let status = r.get("status").and_then(|v| v.as_str()).unwrap_or("-");
            vec![
                id.chars().take(8).collect(),
                truncate(task, 60),
                output::format_status(status),
            ]
        })
        .collect();
    anstream::println!(
        "{}",
        output::render_table(&["Run ID", "Task", "Status"], &rows)
    );
    Ok(())
}

pub async fn get(client: &Client, run_id: &str) -> Result<(), ClientError> {
    let body = client.get(&format!("/api/runs/{run_id}")).await?;
    let field = |k: &str| {
        body.get(k)
            .and_then(|v| v.as_str())
            .unwrap_or("-")
            .to_owned()
    };
    let pairs = vec![
        ("Run".to_owned(), field("id")),
        ("Status".to_owned(), output::format_status(&field("status"))),
        ("Provider".to_owned(), field("provider")),
        ("Model".to_owned(), field("model")),
        ("Started".to_owned(), field("started_at")),
        ("Completed".to_owned(), field("completed_at")),
    ];
    anstream::println!("{}", output::render_kv(&pairs));
    Ok(())
}

pub async fn cancel(client: &Client, run_id: &str) -> Result<(), ClientError> {
    client
        .post(&format!("/api/runs/{run_id}/cancel"), None)
        .await?;
    anstream::println!("{}", output::success(&format!("Cancelled run {run_id}")));
    Ok(())
}

pub async fn resume(client: &Client, run_id: &str) -> Result<(), ClientError> {
    client
        .post(&format!("/api/runs/{run_id}/resume"), None)
        .await?;
    anstream::println!("{}", output::success(&format!("Resumed run {run_id}")));
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn a_completed_run_exits_zero_and_a_failed_one_does_not() {
        assert_eq!(exit_code_for("completed"), 0);
        assert_eq!(exit_code_for("failed"), 1);
    }

    /// A cancellation is what the owner asked for, so it is not a failure.
    #[test]
    fn a_cancelled_run_is_not_a_failure() {
        assert_eq!(exit_code_for("cancelled"), 0);
    }

    /// Truncation counts characters, because a task sentence is prose.
    #[test]
    fn truncation_does_not_split_a_character() {
        let task = "reinicia el servidor de producción con cuidado";
        let out = truncate(task, 20);
        assert_eq!(out.chars().count(), 20);
        assert!(out.ends_with('\u{2026}'));
        assert!(!out.contains('\u{fffd}'), "no replacement character");
    }

    #[test]
    fn truncation_leaves_a_short_task_alone() {
        assert_eq!(truncate("short", 20), "short");
    }

    #[test]
    fn emoji_survive_truncation_whole() {
        let out = truncate("deploy 🚀🚀🚀 to production now please", 10);
        assert_eq!(out.chars().count(), 10);
        assert!(!out.contains('\u{fffd}'));
    }
}
