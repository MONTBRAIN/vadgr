//! `vadgr health`, `vadgr providers`, `vadgr computer-use`.
//!
//! The read-only views of what the daemon currently is, plus the one pair of
//! commands that change a setting.
//!
//! **The recorded sweep asserts argv, exit code and whether output was produced,
//! and not one word of what is printed.** So this is the easiest file in the CLI
//! to change by accident and still pass every check. What it prints is asserted
//! against the bytes the product shipped, never against what the code does.

use crate::client::Client;
use crate::error::CliError;
use crate::output;

pub async fn health(client: &Client) -> Result<(), CliError> {
    let body = client.get("/api/health").await?;
    let field = |k: &str| {
        body.get(k)
            .and_then(|v| v.as_str())
            .unwrap_or("unknown")
            .to_owned()
    };
    anstream::println!(
        "{}",
        output::render_kv(&[
            ("Status".to_owned(), output::format_status(&field("status"))),
            ("Version".to_owned(), field("version")),
            ("Platform".to_owned(), field("platform")),
        ])
    );

    if let Some(modules) = body
        .get("modules")
        .and_then(|v| v.as_object())
        .filter(|m| !m.is_empty())
    {
        anstream::println!("\nModules:");
        for (name, available) in modules {
            let state = module_state(available.as_bool().unwrap_or(false));
            anstream::println!("  {name}: {}", output::format_status(state));
        }
    }
    Ok(())
}

pub async fn providers(client: &Client) -> Result<(), CliError> {
    let body = client.get("/api/providers").await?;
    let empty = Vec::new();
    let list = body.as_array().unwrap_or(&empty);
    if list.is_empty() {
        anstream::println!("No providers configured.");
        return Ok(());
    }

    for provider in list {
        let name = provider.get("name").and_then(|v| v.as_str()).unwrap_or("-");
        let id = provider.get("id").and_then(|v| v.as_str()).unwrap_or("-");
        let available = if provider.get("connected").and_then(|v| v.as_bool()) == Some(true) {
            "connected"
        } else {
            "not connected"
        };
        let default = if provider.get("is_default").and_then(|v| v.as_bool()) == Some(true) {
            " (default)"
        } else {
            ""
        };
        anstream::println!(
            "  {name} ({id}) -- {}{default}",
            output::format_status(available)
        );
        if let Some(models) = provider.get("models").and_then(|v| v.as_array()) {
            for model in models {
                let model_name = model.get("name").and_then(|v| v.as_str()).unwrap_or("-");
                let model_id = model.get("id").and_then(|v| v.as_str()).unwrap_or("-");
                anstream::println!("    - {model_name} ({model_id})");
            }
        }
        anstream::println!();
    }
    Ok(())
}

pub async fn computer_use_status(client: &Client) -> Result<(), CliError> {
    let body = client.get("/api/settings/computer-use").await?;
    let enabled = body.get("enabled").and_then(|v| v.as_bool()) == Some(true);
    anstream::println!(
        "  Computer use: {}",
        output::format_status(if enabled { "enabled" } else { "disabled" })
    );
    if let Some(daemon) = body.get("daemon").and_then(|v| v.as_str()) {
        anstream::println!("  Daemon: {}", output::format_status(daemon));
    }
    Ok(())
}

/// Enabling can install a daemon, which is why it waits and why it says which
/// of the three outcomes happened rather than reporting a flat success.
pub async fn computer_use_enable(client: &Client) -> Result<(), CliError> {
    let spinner =
        output::status::Spinner::start("Setting up computer use (this may take a minute)...");
    let result = client
        .put(
            "/api/settings/computer-use",
            Some(serde_json::json!({"enabled": true})),
        )
        .await;
    spinner.stop();
    let result = result?;

    match result.get("daemon").and_then(|v| v.as_str()) {
        Some("running") => anstream::println!(
            "{}",
            output::success("Computer use enabled (Windows daemon running)")
        ),
        Some("stopped") => anstream::println!(
            "{}",
            output::warning("Computer use enabled but daemon did not start. Run: vadgr-cua doctor")
        ),
        _ => anstream::println!("{}", output::success("Computer use enabled")),
    }
    Ok(())
}

pub async fn computer_use_disable(client: &Client) -> Result<(), CliError> {
    let spinner = output::status::Spinner::start("Disabling computer use...");
    let result = client
        .put(
            "/api/settings/computer-use",
            Some(serde_json::json!({"enabled": false})),
        )
        .await;
    spinner.stop();
    result?;
    anstream::println!("{}", output::success("Computer use disabled"));
    Ok(())
}

/// The word the module block prints for one module's availability.
///
/// The daemon reports whether a module is usable, never why. It answers `false`
/// for a module that is absent and for one the owner turned off, so a line
/// reading "not found" told a user who had just run `vadgr computer-use
/// disable` that their installation was missing. The rendering states what the
/// daemon said and adds no cause of its own.
fn module_state(available: bool) -> &'static str {
    if available {
        "available"
    } else {
        "unavailable"
    }
}

#[cfg(test)]
mod tests {
    use super::module_state;

    #[test]
    fn a_module_the_daemon_calls_false_is_never_reported_as_missing() {
        assert_eq!(module_state(true), "available");
        assert_eq!(module_state(false), "unavailable");
        assert_ne!(
            module_state(false),
            "not found",
            "false means unusable, which is not the same claim as absent"
        );
    }
}
