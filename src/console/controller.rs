use crate::install::InstallStatus;
use anyhow::{Context, Result, anyhow};
use serde::{Deserialize, Serialize};
use serde_json::{Value, json};

const MAX_CONSOLE_RESPONSE_BYTES: u64 = 4 * 1024 * 1024;

#[derive(Clone, Debug, Default, Deserialize, Serialize)]
pub struct MachineSnapshot {
    pub id: String,
    pub name: String,
    pub platform: String,
    pub daemon_version: String,
    pub transport: Value,
    pub default_provider: Option<String>,
    pub default_model: Option<String>,
    pub role_prompt: String,
    pub autonomy: Value,
    pub workspace: Option<String>,
    pub granted_skills: Vec<String>,
    pub granted_mcp_servers: Vec<String>,
}

#[derive(Clone, Debug, Default, Deserialize, Serialize)]
pub struct HealthSnapshot {
    pub status: String,
    pub version: String,
    #[serde(default)]
    pub modules: Value,
}

#[derive(Clone, Debug, Default, Deserialize, Serialize)]
pub struct DeviceSnapshot {
    pub id: String,
    #[serde(alias = "machine_name")]
    pub name: String,
    pub paired_at: String,
    pub last_seen: Option<String>,
    #[serde(default)]
    pub connected: bool,
    #[serde(default)]
    pub transports: Vec<TransportSnapshot>,
}

#[derive(Clone, Debug, Default, Deserialize, Serialize)]
pub struct TransportSnapshot {
    pub kind: String,
    pub label: String,
    pub status: String,
    #[serde(default)]
    pub detail: Option<String>,
}

#[derive(Clone, Debug, Default, Deserialize, Serialize)]
pub struct ProviderSnapshot {
    pub id: String,
    pub name: String,
    pub connected: bool,
    #[serde(default)]
    pub available: bool,
    #[serde(default)]
    pub auth_methods: Vec<String>,
    #[serde(default)]
    pub auth_method: Option<String>,
    #[serde(default)]
    pub models: Vec<ModelSnapshot>,
    #[serde(default)]
    pub default_model: Option<String>,
    #[serde(default)]
    pub catalog_verified_at: Option<String>,
    #[serde(default)]
    pub catalog_stale: bool,
    #[serde(default)]
    pub unavailable_reason: Option<String>,
}

#[derive(Clone, Debug, Default, Deserialize, Serialize)]
pub struct ModelSnapshot {
    pub id: String,
    #[serde(default)]
    pub name: String,
}

#[derive(Clone, Debug, Default, Deserialize, Serialize)]
pub struct PairingSession {
    #[serde(rename = "pairing_token")]
    pub code: String,
    pub machine_name: String,
    #[serde(default)]
    pub transports: Value,
}

#[derive(Clone, Debug, Default, Serialize)]
pub struct MachineEdit {
    pub name: String,
    pub role_prompt: String,
    pub autonomy: Value,
    pub workspace: Option<String>,
    pub granted_skills: Vec<String>,
    pub granted_mcp_servers: Vec<String>,
}

pub trait ConsoleController: Send + Sync {
    fn install_status(&self) -> Result<InstallStatus>;
    fn health(&self) -> Result<HealthSnapshot>;
    fn machine(&self) -> Result<MachineSnapshot>;
    fn update_machine(&self, edit: &MachineEdit) -> Result<MachineSnapshot>;
    fn devices(&self) -> Result<Vec<DeviceSnapshot>>;
    fn providers(&self) -> Result<Vec<ProviderSnapshot>>;
    fn start_pairing(&self) -> Result<PairingSession>;
    fn cancel_pairing(&self) -> Result<()>;
    fn revoke_device(&self, id: &str) -> Result<()>;
    fn refresh_provider(&self, id: &str) -> Result<()>;
    fn connect_api_key(&self, id: &str, api_key: String) -> Result<()>;
    fn connect_oauth(&self, id: &str) -> Result<()>;
    fn set_default_model(&self, provider: &str, model: &str) -> Result<()>;
    fn disconnect_provider(&self, id: &str) -> Result<()>;
    fn restart_daemon(&self) -> Result<()>;
    fn set_launch_at_login(&self, enabled: bool) -> Result<()>;
    fn check_for_updates(&self) -> Result<crate::install::UpdateCheck>;
    fn apply_update(&self) -> Result<crate::install::UpdateCheck>;
    fn rollback_installation(&self) -> Result<()>;
    fn repair_installation(&self) -> Result<()>;
    fn open_legal_notices(&self) -> Result<()>;
    fn uninstall(&self, purge_owner_state: bool) -> Result<()>;
}

pub struct HttpConsoleController {
    base_url: String,
}

impl HttpConsoleController {
    pub fn new(base_url: impl Into<String>) -> Result<Self> {
        Ok(Self {
            base_url: base_url.into().trim_end_matches('/').to_owned(),
        })
    }

    fn url(&self, path: &str) -> String {
        format!("{}{path}", self.base_url)
    }

    fn read<T: serde::de::DeserializeOwned>(&self, path: &str) -> Result<T> {
        self.send(reqwest::Method::GET, path, None)
    }

    fn send<T: serde::de::DeserializeOwned>(
        &self,
        method: reqwest::Method,
        path: &str,
        body: Option<Value>,
    ) -> Result<T> {
        let url = self.url(path);
        let runtime = tokio::runtime::Builder::new_current_thread()
            .enable_all()
            .build()
            .context("starting the console network worker")?;
        runtime.block_on(async move {
            let client = reqwest::Client::builder()
                .timeout(std::time::Duration::from_secs(30))
                .build()?;
            let mut request = client.request(method, url);
            if let Some(body) = body {
                request = request.json(&body);
            }
            let response = request.send().await.context("the daemon did not answer")?;
            decode_response(response).await
        })
    }

    fn send_empty(&self, method: reqwest::Method, path: &str, body: Option<Value>) -> Result<()> {
        let url = self.url(path);
        let runtime = tokio::runtime::Builder::new_current_thread()
            .enable_all()
            .build()
            .context("starting the console network worker")?;
        runtime.block_on(async move {
            let client = reqwest::Client::builder()
                .timeout(std::time::Duration::from_secs(30))
                .build()?;
            let mut request = client.request(method, url);
            if let Some(body) = body {
                request = request.json(&body);
            }
            let response = request.send().await.context("the daemon did not answer")?;
            decode_empty_response(response).await
        })
    }

    fn delete_idempotent(&self, path: &str) -> Result<()> {
        let url = self.url(path);
        let runtime = tokio::runtime::Builder::new_current_thread()
            .enable_all()
            .build()
            .context("starting the console network worker")?;
        runtime.block_on(async move {
            let response = reqwest::Client::builder()
                .timeout(std::time::Duration::from_secs(30))
                .build()?
                .delete(url)
                .send()
                .await
                .context("the daemon did not answer")?;
            if response.status().is_success() || response.status() == reqwest::StatusCode::NOT_FOUND
            {
                return Ok(());
            }
            decode_empty_response(response).await
        })
    }
}

async fn response_bytes(response: reqwest::Response) -> Result<(reqwest::StatusCode, Vec<u8>)> {
    let status = response.status();
    if let Some(length) = response.content_length() {
        anyhow::ensure!(
            length <= MAX_CONSOLE_RESPONSE_BYTES,
            "the daemon response exceeded the console limit"
        );
    }
    let bytes = response
        .bytes()
        .await
        .context("reading the daemon response")?;
    anyhow::ensure!(
        bytes.len() as u64 <= MAX_CONSOLE_RESPONSE_BYTES,
        "the daemon response exceeded the console limit"
    );
    Ok((status, bytes.to_vec()))
}

async fn decode_response<T: serde::de::DeserializeOwned>(response: reqwest::Response) -> Result<T> {
    let (status, bytes) = response_bytes(response).await?;
    if !status.is_success() {
        return Err(daemon_error(status, &bytes));
    }
    serde_json::from_slice(&bytes).context("the daemon returned an invalid response")
}

async fn decode_empty_response(response: reqwest::Response) -> Result<()> {
    let (status, bytes) = response_bytes(response).await?;
    if status.is_success() {
        return Ok(());
    }
    Err(daemon_error(status, &bytes))
}

fn daemon_error(status: reqwest::StatusCode, bytes: &[u8]) -> anyhow::Error {
    let message = serde_json::from_slice::<Value>(bytes)
        .ok()
        .and_then(|value| {
            value
                .get("error")
                .and_then(|error| error.get("message"))
                .and_then(Value::as_str)
                .map(str::to_owned)
        })
        .filter(|value| !value.trim().is_empty())
        .unwrap_or_else(|| format!("the daemon refused the request ({status})"));
    anyhow!(message)
}

impl ConsoleController for HttpConsoleController {
    fn install_status(&self) -> Result<InstallStatus> {
        crate::install::status()
    }

    fn health(&self) -> Result<HealthSnapshot> {
        self.read("/api/health")
    }

    fn machine(&self) -> Result<MachineSnapshot> {
        self.read("/api/machine")
    }

    fn update_machine(&self, edit: &MachineEdit) -> Result<MachineSnapshot> {
        self.send(
            reqwest::Method::PATCH,
            "/api/machine",
            Some(serde_json::to_value(edit)?),
        )
    }

    fn devices(&self) -> Result<Vec<DeviceSnapshot>> {
        self.read("/api/devices")
    }

    fn providers(&self) -> Result<Vec<ProviderSnapshot>> {
        let rows: Vec<Value> = self.read("/api/providers")?;
        rows.into_iter().map(normalize_provider).collect()
    }

    fn start_pairing(&self) -> Result<PairingSession> {
        self.send(reqwest::Method::POST, "/api/auth/pair", None)
    }

    fn cancel_pairing(&self) -> Result<()> {
        self.delete_idempotent("/api/auth/pair")
    }

    fn revoke_device(&self, id: &str) -> Result<()> {
        self.send_empty(reqwest::Method::DELETE, &format!("/api/devices/{id}"), None)
    }

    fn refresh_provider(&self, id: &str) -> Result<()> {
        self.send_empty(
            reqwest::Method::POST,
            &format!("/api/providers/{id}/catalog-refresh"),
            None,
        )
    }

    fn connect_api_key(&self, id: &str, api_key: String) -> Result<()> {
        let attempt: Value = self.send(
            reqwest::Method::POST,
            &format!("/api/providers/{id}/auth-attempts"),
            Some(json!({"method": "api_key", "api_key": api_key})),
        )?;
        let attempt_id = attempt
            .get("id")
            .and_then(Value::as_str)
            .ok_or_else(|| anyhow!("the daemon returned no authentication attempt id"))?;
        self.send_empty(
            reqwest::Method::PUT,
            &format!("/api/providers/{id}/connection"),
            Some(json!({"attempt_id": attempt_id})),
        )
    }

    fn connect_oauth(&self, id: &str) -> Result<()> {
        let attempt: Value = self.send(
            reqwest::Method::POST,
            &format!("/api/providers/{id}/auth-attempts"),
            Some(json!({"method": "oauth", "flow": "browser"})),
        )?;
        let attempt_id = attempt
            .get("id")
            .and_then(Value::as_str)
            .ok_or_else(|| anyhow!("the daemon returned no authentication attempt id"))?
            .to_owned();
        let authorization_url = attempt
            .get("authorization_url")
            .and_then(Value::as_str)
            .ok_or_else(|| anyhow!("the daemon returned no authorization URL"))?;
        open_authorization_url(authorization_url)?;

        let started = std::time::Instant::now();
        while started.elapsed() < std::time::Duration::from_secs(600) {
            let current: Value = self.read(&format!("/api/provider-auth/{attempt_id}"))?;
            match current.get("status").and_then(Value::as_str) {
                Some("authenticated") => {
                    return self.send_empty(
                        reqwest::Method::PUT,
                        &format!("/api/providers/{id}/connection"),
                        Some(json!({"attempt_id": attempt_id})),
                    );
                }
                Some("failed") | Some("cancelled") => {
                    let code = current
                        .get("error_code")
                        .and_then(Value::as_str)
                        .unwrap_or("sign-in failed");
                    return Err(anyhow!("provider sign-in failed: {code}"));
                }
                _ => std::thread::sleep(std::time::Duration::from_millis(500)),
            }
        }
        Err(anyhow!("provider sign-in timed out"))
    }

    fn set_default_model(&self, provider: &str, model: &str) -> Result<()> {
        self.send_empty(
            reqwest::Method::PUT,
            "/api/default-model",
            Some(json!({"provider": provider, "model": model})),
        )
    }

    fn disconnect_provider(&self, id: &str) -> Result<()> {
        self.send_empty(
            reqwest::Method::DELETE,
            &format!("/api/providers/{id}/connection"),
            None,
        )
    }

    fn restart_daemon(&self) -> Result<()> {
        let executable = std::env::current_exe().context("finding the Vadgr executable")?;
        let status = std::process::Command::new(executable)
            .arg("restart")
            .status()
            .context("starting the Vadgr restart command")?;
        if !status.success() {
            return Err(anyhow!("Vadgr did not restart successfully"));
        }
        Ok(())
    }

    fn set_launch_at_login(&self, enabled: bool) -> Result<()> {
        crate::install::set_launch_at_login(enabled)
    }

    fn check_for_updates(&self) -> Result<crate::install::UpdateCheck> {
        crate::install::check_for_updates()
    }

    fn apply_update(&self) -> Result<crate::install::UpdateCheck> {
        crate::install::apply_update()
    }

    fn rollback_installation(&self) -> Result<()> {
        crate::install::rollback()
    }

    fn repair_installation(&self) -> Result<()> {
        crate::install::repair()
    }

    fn open_legal_notices(&self) -> Result<()> {
        crate::install::open_legal()
    }

    fn uninstall(&self, purge_owner_state: bool) -> Result<()> {
        crate::install::uninstall(purge_owner_state)
    }
}

fn normalize_provider(value: Value) -> Result<ProviderSnapshot> {
    let id = value
        .get("id")
        .or_else(|| value.get("provider_id"))
        .and_then(Value::as_str)
        .ok_or_else(|| anyhow!("a provider row has no id"))?
        .to_owned();
    let name = value
        .get("name")
        .and_then(Value::as_str)
        .unwrap_or(&id)
        .to_owned();
    let connected = value
        .get("connected")
        .and_then(Value::as_bool)
        .unwrap_or_else(|| value.get("status").and_then(Value::as_str) == Some("connected"));
    let models = value
        .get("models")
        .and_then(Value::as_array)
        .map(|rows| {
            rows.iter()
                .filter_map(|row| serde_json::from_value(row.clone()).ok())
                .collect()
        })
        .unwrap_or_default();
    Ok(ProviderSnapshot {
        id,
        name,
        connected,
        available: value
            .get("available")
            .and_then(Value::as_bool)
            .unwrap_or(connected),
        auth_methods: value
            .get("auth_methods")
            .and_then(Value::as_array)
            .map(|methods| {
                methods
                    .iter()
                    .filter_map(Value::as_str)
                    .map(str::to_owned)
                    .collect()
            })
            .unwrap_or_default(),
        auth_method: value
            .get("auth_method")
            .and_then(Value::as_str)
            .map(str::to_owned),
        models,
        default_model: value
            .get("default_model")
            .and_then(Value::as_str)
            .map(str::to_owned),
        catalog_verified_at: value
            .get("catalog_verified_at")
            .and_then(Value::as_str)
            .map(str::to_owned),
        catalog_stale: value
            .get("catalog_stale")
            .and_then(Value::as_bool)
            .unwrap_or(false),
        unavailable_reason: value
            .get("unavailable_reason")
            .and_then(Value::as_str)
            .map(str::to_owned),
    })
}

fn open_authorization_url(url: &str) -> Result<()> {
    let (program, arguments): (&str, &[&str]) = if cfg!(target_os = "macos") {
        ("open", &[])
    } else if cfg!(target_os = "windows") {
        ("rundll32.exe", &["url.dll,FileProtocolHandler"])
    } else {
        ("xdg-open", &[])
    };
    let status = std::process::Command::new(program)
        .args(arguments)
        .arg(url)
        .stdout(std::process::Stdio::null())
        .stderr(std::process::Stdio::null())
        .status()
        .context("opening the provider sign-in page")?;
    if !status.success() {
        return Err(anyhow!("the provider sign-in page did not open"));
    }
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn provider_rows_accept_the_shipped_wire_shape() {
        let row = normalize_provider(json!({
            "provider_id": "openai",
            "name": "OpenAI",
            "status": "connected",
            "available": true,
            "auth_methods": ["oauth", "api_key"],
            "auth_method": "oauth",
            "models": [{"id": "gpt-test", "name": "GPT Test"}],
            "default_model": "gpt-test"
        }))
        .unwrap();
        assert_eq!(row.id, "openai");
        assert!(row.connected);
        assert!(row.available);
        assert_eq!(row.auth_methods, ["oauth", "api_key"]);
        assert_eq!(row.models[0].id, "gpt-test");
    }

    #[test]
    fn daemon_failures_keep_the_safe_server_message() {
        let error = daemon_error(
            reqwest::StatusCode::UNPROCESSABLE_ENTITY,
            br#"{"error":{"code":"VALIDATION","message":"workspace must be absolute","details":{}}}"#,
        );
        assert_eq!(error.to_string(), "workspace must be absolute");
        let fallback = daemon_error(reqwest::StatusCode::BAD_GATEWAY, b"not json");
        assert!(fallback.to_string().contains("502 Bad Gateway"));
    }
}
