//! Machine configuration commands over the same loopback API as the console.

use serde_json::{Value, json};

use crate::client::Client;
use crate::error::CliError;
use crate::output;

pub async fn show(client: &Client, as_json: bool) -> Result<(), CliError> {
    let machine = client.get("/api/machine").await?;
    if as_json {
        anstream::println!(
            "{}",
            serde_json::to_string_pretty(&machine).unwrap_or_else(|_| machine.to_string())
        );
        return Ok(());
    }
    let text = |key: &str| {
        machine
            .get(key)
            .and_then(Value::as_str)
            .unwrap_or("none")
            .to_owned()
    };
    let default = machine
        .get("default_provider")
        .and_then(Value::as_str)
        .zip(machine.get("default_model").and_then(Value::as_str))
        .map(|(provider, model)| format!("{provider}/{model}"))
        .unwrap_or_else(|| "none".to_owned());
    anstream::println!(
        "{}",
        output::render_kv(&[
            ("Name".to_owned(), text("name")),
            ("ID".to_owned(), text("id")),
            ("Platform".to_owned(), text("platform")),
            ("Version".to_owned(), text("daemon_version")),
            ("Default".to_owned(), default),
            ("Workspace".to_owned(), text("workspace")),
            (
                "Autonomy".to_owned(),
                nested_text(&machine, "autonomy", "mode")
            ),
        ])
    );
    Ok(())
}

pub async fn get(client: &Client, key: &str) -> Result<(), CliError> {
    let machine = client.get("/api/machine").await?;
    let value = value_at(&machine, key)?;
    anstream::println!("{key}  {}", display_value(value));
    Ok(())
}

pub async fn set(client: &Client, key: &str, value: &str) -> Result<(), CliError> {
    let before = client.get("/api/machine").await?;
    let old = value_at(&before, key).map(display_value)?;
    let body = patch_value(key, value)?;
    let after = client.patch("/api/machine", Some(body)).await?;
    let new = value_at(&after, key).map(display_value)?;
    anstream::println!("{key}  {old} -> {new}");
    Ok(())
}

fn patch_value(key: &str, value: &str) -> Result<Value, CliError> {
    let patch = match key {
        "name" => json!({"name": value}),
        "role_prompt" => json!({"role_prompt": nullable(value)}),
        "autonomy.mode" => json!({"autonomy": {"mode": value}}),
        "workspace" => json!({"workspace": nullable(value)}),
        "granted_skills" | "granted_mcp_servers" => {
            let values: Vec<String> = serde_json::from_str(value)
                .map_err(|_| CliError::Usage(format!("{key} value must be a JSON string array")))?;
            json!({key: values})
        }
        "default_model" => {
            let Some((provider, model)) = value.split_once('/') else {
                return Err(CliError::Usage(
                    "default_model value must be provider/model".to_owned(),
                ));
            };
            json!({"default_provider": provider, "default_model": model})
        }
        _ => {
            return Err(CliError::Usage(format!("unknown machine setting: {key}")));
        }
    };
    Ok(patch)
}

fn nullable(value: &str) -> Value {
    if value == "null" {
        Value::Null
    } else {
        Value::String(value.to_owned())
    }
}

fn value_at<'a>(machine: &'a Value, key: &str) -> Result<&'a Value, CliError> {
    let value = match key {
        "autonomy.mode" => machine.get("autonomy").and_then(|value| value.get("mode")),
        "default_model" => machine.get("default_model"),
        "name" | "role_prompt" | "workspace" | "granted_skills" | "granted_mcp_servers" => {
            machine.get(key)
        }
        _ => None,
    };
    value.ok_or_else(|| CliError::Usage(format!("unknown machine setting: {key}")))
}

fn display_value(value: &Value) -> String {
    value
        .as_str()
        .map(str::to_owned)
        .unwrap_or_else(|| value.to_string())
}

fn nested_text(value: &Value, object: &str, key: &str) -> String {
    value
        .get(object)
        .and_then(|value| value.get(key))
        .and_then(Value::as_str)
        .unwrap_or("none")
        .to_owned()
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn config_keys_build_only_declared_machine_patches() {
        assert_eq!(
            patch_value("autonomy.mode", "paranoid").unwrap(),
            json!({"autonomy": {"mode": "paranoid"}})
        );
        assert_eq!(
            patch_value("default_model", "anthropic/model-a").unwrap(),
            json!({"default_provider": "anthropic", "default_model": "model-a"})
        );
        assert!(patch_value("transport", "tailscale").is_err());
    }
}
