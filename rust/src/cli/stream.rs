//! Watching a run over its public socket.
//!
//! Ported from `cli/stream.py`, and this is the one file the design marks as
//! **improved rather than ported**. The Python consumer handles three event
//! types. The daemon publishes twelve. A cancelled run therefore said nothing at
//! all to someone watching from the terminal, which is the defect the migration
//! ratchet requires fixing rather than carrying.

use std::time::{Duration, Instant};

use futures_util::StreamExt;
use tokio_tungstenite::tungstenite::Message;

use crate::output;

/// How a watch ended, and the exit code it implies.
#[derive(Debug, PartialEq, Eq)]
pub enum Outcome {
    Completed,
    Failed,
    Cancelled,
    /// The watch timed out. The run keeps going without us.
    Detached,
    /// The socket dropped. We do not know how the run ended.
    Unknown,
}

impl Outcome {
    pub fn exit_code(&self) -> i32 {
        match self {
            // A cancellation is what the owner asked for, so it is not a failure.
            Self::Completed | Self::Cancelled => 0,
            Self::Failed => 1,
            // "Still running" and "we lost the socket" are not failures of the
            // run, and a script that treats them as one would kill work that is
            // fine.
            Self::Detached | Self::Unknown => 0,
        }
    }
}

/// Every event type the daemon publishes on the mobile route.
///
/// Listed exhaustively on purpose. The Python consumer matched three and let the
/// rest fall through, so `run_cancelled` arrived and produced silence.
pub fn describe(event_type: &str, data: &serde_json::Value) -> Option<String> {
    let text = |k: &str| data.get(k).and_then(|v| v.as_str()).unwrap_or("");
    Some(match event_type {
        "run_started" => "Run started".to_owned(),
        "run_resumed" => "Run resumed from its journal".to_owned(),
        "agent_started" => {
            let name = text("name");
            if name.is_empty() {
                "Running...".to_owned()
            } else {
                format!("Running {name}...")
            }
        }
        "agent_log" => text("message").to_owned(),
        "todos" => "Updated its plan".to_owned(),
        "agent_completed" => "Finished the work".to_owned(),
        "agent_failed" => format!("Step failed: {}", text("error")),
        "agent_cancelled" => "Cancelling...".to_owned(),
        // The three terminal frames are handled by the caller, which needs the
        // outcome rather than a line of prose.
        "run_completed" | "run_failed" | "run_cancelled" => return None,
        _ => return None,
    })
}

/// Whether an event type ends the watch, and how.
pub fn terminal_outcome(event_type: &str) -> Option<Outcome> {
    match event_type {
        "run_completed" => Some(Outcome::Completed),
        "run_failed" => Some(Outcome::Failed),
        "run_cancelled" => Some(Outcome::Cancelled),
        _ => None,
    }
}

/// Follow a run to its terminal frame.
pub async fn follow(api_url: &str, run_id: &str, timeout: Duration) -> Outcome {
    let ws_url = format!(
        "{}/api/ws/runs/{run_id}",
        api_url
            .replacen("http://", "ws://", 1)
            .replacen("https://", "wss://", 1)
    );

    let Ok((mut socket, _)) = tokio_tungstenite::connect_async(&ws_url).await else {
        anstream::println!(
            "  Could not connect to the run stream. The run continues in the background."
        );
        anstream::println!("  See the run: vadgr runs get {run_id}");
        return Outcome::Unknown;
    };

    let started = Instant::now();
    let spinner = output::status::Spinner::start("Starting...");

    loop {
        if started.elapsed() > timeout {
            spinner.stop();
            anstream::println!(
                "  Timed out after {}. The run continues in the background.",
                output::format_duration(timeout.as_secs_f64())
            );
            return Outcome::Detached;
        }

        let next = tokio::time::timeout(Duration::from_secs(3), socket.next()).await;
        let raw = match next {
            Err(_) => continue,
            Ok(None) => {
                spinner.stop();
                anstream::println!("  The run stream closed. The run continues in the background.");
                anstream::println!("  See the run: vadgr runs get {run_id}");
                return Outcome::Unknown;
            }
            Ok(Some(Err(_))) => {
                spinner.stop();
                anstream::println!("  Lost the run stream. The run continues in the background.");
                return Outcome::Unknown;
            }
            Ok(Some(Ok(Message::Text(t)))) => t.to_string(),
            Ok(Some(Ok(_))) => continue,
        };

        let Ok(event) = serde_json::from_str::<serde_json::Value>(&raw) else {
            continue;
        };
        let event_type = event.get("type").and_then(|v| v.as_str()).unwrap_or("");
        let data = event
            .get("data")
            .cloned()
            .unwrap_or(serde_json::Value::Null);

        if let Some(outcome) = terminal_outcome(event_type) {
            spinner.stop();
            let elapsed = output::format_duration(started.elapsed().as_secs_f64());
            match outcome {
                Outcome::Completed => {
                    anstream::println!(
                        "{}",
                        output::success(&format!("Run completed ({elapsed})"))
                    );
                }
                Outcome::Failed => {
                    let error = data
                        .get("error")
                        .and_then(|v| v.as_str())
                        .unwrap_or("Unknown error");
                    anstream::println!(
                        "{}",
                        output::error(&format!("Run failed ({elapsed}): {error}"))
                    );
                    anstream::println!("  See the run: vadgr runs get {run_id}");
                }
                // The frame this port exists to handle.
                Outcome::Cancelled => {
                    anstream::println!(
                        "{}",
                        output::warning(&format!("Run cancelled ({elapsed})"))
                    );
                }
                _ => {}
            }
            return outcome;
        }

        if let Some(line) = describe(event_type, &data) {
            if !line.is_empty() {
                spinner.update(line);
            }
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    /// The regression this release fixes: a cancelled run must end the watch and
    /// say so. Against the Python consumer's three types this is `None`.
    #[test]
    fn a_cancelled_run_is_a_terminal_outcome() {
        assert_eq!(terminal_outcome("run_cancelled"), Some(Outcome::Cancelled));
    }

    #[test]
    fn the_three_terminal_frames_end_the_watch() {
        assert_eq!(terminal_outcome("run_completed"), Some(Outcome::Completed));
        assert_eq!(terminal_outcome("run_failed"), Some(Outcome::Failed));
        assert_eq!(terminal_outcome("run_cancelled"), Some(Outcome::Cancelled));
        assert_eq!(terminal_outcome("agent_started"), None);
    }

    /// Every type the daemon publishes is either described or terminal. A type
    /// that is neither is one a watcher would sit silently through.
    #[test]
    fn every_published_event_type_is_handled() {
        let published = [
            "run_started",
            "run_resumed",
            "run_completed",
            "run_failed",
            "run_cancelled",
            "agent_started",
            "agent_log",
            "agent_completed",
            "agent_failed",
            "agent_cancelled",
            "todos",
        ];
        let null = serde_json::Value::Null;
        for t in published {
            let handled = describe(t, &null).is_some() || terminal_outcome(t).is_some();
            assert!(handled, "{t} is published but the watcher ignores it");
        }
    }

    #[test]
    fn a_cancellation_is_not_a_failed_exit() {
        assert_eq!(Outcome::Cancelled.exit_code(), 0);
        assert_eq!(Outcome::Completed.exit_code(), 0);
        assert_eq!(Outcome::Failed.exit_code(), 1);
    }

    /// Losing the socket says nothing about the run, so it must not be reported
    /// as a failure.
    #[test]
    fn losing_the_stream_does_not_fail_the_run() {
        assert_eq!(Outcome::Unknown.exit_code(), 0);
        assert_eq!(Outcome::Detached.exit_code(), 0);
    }
}
