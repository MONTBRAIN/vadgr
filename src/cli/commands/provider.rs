//! `vadgr provider` and `vadgr model`.
//!
//! Three things in here are behaviours rather than shapes, and each is invisible
//! in the command tree: the OAuth poll and its deadline, the recovery menu keyed
//! on the daemon's own error code, and the replacement-default flow that appears
//! only when a connection would otherwise strand the machine default.

use std::time::{Duration, Instant};

use serde_json::{Value, json};

use crate::client::{Client, ClientError};
use crate::error::CliError;
use crate::output;
use crate::prompt;

/// The three providers, their display names, and what each accepts.
///
/// An array rather than a map: the order is the order a person is offered them,
/// and a map would make that an accident.
pub const PROVIDERS: [(&str, &str, &str); 3] = [
    ("openai", "OpenAI", "ChatGPT or API key"),
    ("gemini", "Google Gemini", "API key"),
    ("anthropic", "Anthropic", "API key"),
];

/// The environment a key is read from, in the order the old CLI read them.
const KEY_ENVIRONMENTS: [(&str, &[&str]); 3] = [
    ("openai", &["OPENAI_API_KEY"]),
    ("gemini", &["GEMINI_API_KEY", "GOOGLE_API_KEY"]),
    ("anthropic", &["ANTHROPIC_API_KEY"]),
];

/// How long a browser sign-in may take before the CLI stops waiting.
const OAUTH_DEADLINE: Duration = Duration::from_secs(600);
/// How often the CLI asks the daemon whether the browser has finished.
const OAUTH_POLL: Duration = Duration::from_millis(500);

pub fn is_known(provider: &str) -> bool {
    PROVIDERS.iter().any(|(id, _, _)| *id == provider)
}

pub fn display_name(provider: &str) -> &str {
    PROVIDERS
        .iter()
        .find(|(id, _, _)| *id == provider)
        .map(|(_, name, _)| *name)
        .unwrap_or(provider)
}

fn choose_provider() -> Result<String, CliError> {
    anstream::println!("Choose a provider");
    for (index, (_, name, detail)) in PROVIDERS.iter().enumerate() {
        anstream::println!("  {}. {name}  {detail}", index + 1);
    }
    let selected = prompt::select("Select", PROVIDERS.len())?;
    Ok(PROVIDERS[selected - 1].0.to_owned())
}

fn choose_openai_method() -> Result<String, CliError> {
    anstream::println!("\nSign in to OpenAI");
    anstream::println!("  1. Continue with ChatGPT");
    anstream::println!("  2. Use an API key");
    let selected = prompt::select("Select", 2)?;
    Ok(if selected == 1 { "chatgpt" } else { "api-key" }.to_owned())
}

/// The key already in the environment, if one is.
///
/// The name is reported and the value never is, which is the same rule the
/// runbooks hold evidence to.
fn detected_key(provider: &str) -> Option<(&'static str, String)> {
    KEY_ENVIRONMENTS
        .iter()
        .find(|(id, _)| *id == provider)
        .and_then(|(_, names)| {
            names.iter().find_map(|name| {
                std::env::var(name)
                    .ok()
                    .filter(|v| !v.is_empty())
                    .map(|v| (*name, v))
            })
        })
}

fn api_key(provider: &str) -> Result<String, CliError> {
    if let Some((name, value)) = detected_key(provider) {
        anstream::println!("{}", output::info(&format!("Using {name}.")));
        return Ok(value);
    }
    prompt::secret(&format!("{} API key", display_name(provider)))
}

/// Whether this Linux is WSL.
///
/// Read from the kernel release rather than from an environment variable, which
/// a user can set to anything.
fn is_wsl() -> bool {
    #[cfg(target_os = "linux")]
    {
        std::fs::read_to_string("/proc/sys/kernel/osrelease")
            .map(|s| s.to_lowercase().contains("microsoft"))
            .unwrap_or(false)
    }
    #[cfg(not(target_os = "linux"))]
    {
        false
    }
}

/// The program that opens a URL in the owner's browser, and its fixed arguments.
///
/// **No shell may sit between this and the browser.** An authorization URL is
/// mostly `&`, and `cmd /C start` reads `&` as a command separator: the URL is
/// not quoted on the way through, because quoting only covers arguments holding
/// spaces, so the browser received everything up to the first `&` and nothing
/// after it. That dropped `client_id`, `redirect_uri` and the PKCE challenge,
/// and the provider rejected the request for a missing parameter, which reads
/// as a defect in what was sent rather than in how it was opened.
/// `FileProtocolHandler` passes the string to the default browser untouched.
fn browser_command() -> (&'static str, Vec<&'static str>) {
    if cfg!(target_os = "macos") {
        ("open", vec![])
    } else if cfg!(target_os = "windows") {
        ("rundll32.exe", vec!["url.dll,FileProtocolHandler"])
    } else {
        ("xdg-open", vec![])
    }
}

/// Open the authorization URL in the owner's real browser.
///
/// **WSL is the case that needs its own path.** There is no browser inside the
/// distribution, so the URL is handed to Windows through `powershell.exe`, and
/// it goes in on **stdin** rather than as an argument: an authorization URL
/// carries a state parameter, and a command line is visible in a process
/// listing.
fn launch_authorization_url(url: &str) -> bool {
    use std::io::Write;
    use std::process::{Command, Stdio};

    if is_wsl() {
        let command = "$url = [Console]::In.ReadToEnd(); \
                       if ([string]::IsNullOrWhiteSpace($url)) { exit 2 }; \
                       Start-Process -FilePath $url";
        let spawned = Command::new("powershell.exe")
            .args([
                "-NoLogo",
                "-NoProfile",
                "-NonInteractive",
                "-Command",
                command,
            ])
            .stdin(Stdio::piped())
            .stdout(Stdio::null())
            .stderr(Stdio::null())
            .spawn();
        if let Ok(mut child) = spawned {
            if let Some(mut stdin) = child.stdin.take() {
                let _ = stdin.write_all(url.as_bytes());
            }
            if child.wait().is_ok_and(|status| status.success()) {
                return true;
            }
        }
    }

    let (program, args) = browser_command();
    Command::new(program)
        .args(args)
        .arg(url)
        .stdout(Stdio::null())
        .stderr(Stdio::null())
        .status()
        .map(|s| s.success())
        .unwrap_or(false)
}

/// Wait for the browser half of the OAuth flow.
///
/// The deadline is the CLI's, not the daemon's: the attempt stays where it is
/// and the owner can start again. Ten minutes is long enough for a password
/// manager and a second factor.
async fn poll_oauth(client: &Client, attempt: &Value) -> Result<Value, CliError> {
    let authorization_url = attempt
        .get("authorization_url")
        .and_then(|v| v.as_str())
        .ok_or_else(|| {
            CliError::Failed("The daemon did not return an authorization URL.".to_owned())
        })?;
    let id = attempt
        .get("id")
        .and_then(|v| v.as_str())
        .ok_or_else(|| CliError::Failed("The daemon did not return an attempt id.".to_owned()))?;

    anstream::println!("\nOpening your browser...");
    if !launch_authorization_url(authorization_url) {
        anstream::println!("Open this URL:\n  {authorization_url}");
    }

    let started = Instant::now();
    while started.elapsed() < OAUTH_DEADLINE {
        let current = client.get(&format!("/api/provider-auth/{id}")).await?;
        match current.get("status").and_then(|v| v.as_str()) {
            Some("authenticated") => return Ok(current),
            Some("failed") | Some("cancelled") => {
                let code = current
                    .get("error_code")
                    .and_then(|v| v.as_str())
                    .unwrap_or("sign-in failed");
                return Err(CliError::Failed(format!("OpenAI sign-in failed: {code}.")));
            }
            _ => {}
        }
        tokio::time::sleep(OAUTH_POLL).await;
    }
    Err(CliError::Failed("OpenAI sign-in timed out.".to_owned()))
}

/// Choose a new machine default when the connection would strand the old one.
fn pick_replacement(models: &[String]) -> Result<String, CliError> {
    if models.is_empty() {
        return Err(CliError::Failed(
            "The new credential has no compatible model.".to_owned(),
        ));
    }
    anstream::println!("\nChoose a replacement for the current default");
    for (index, model) in models.iter().enumerate() {
        anstream::println!("  {}. {model}", index + 1);
    }
    let selected = prompt::select("Select", models.len())?;
    Ok(models[selected - 1].clone())
}

/// What the owner wants to do about a refused connection.
///
/// **Keyed on the daemon's error code and category, never on its message.** The
/// menu offered after a bad API key is not the menu offered after a provider
/// outage, and a port that matched on the sentence would silently offer the
/// wrong one the first time the wording changed.
fn recovery_action(
    provider: &str,
    auth: &str,
    error: &crate::client::ApiClientError,
) -> Result<&'static str, CliError> {
    let reason = error
        .category()
        .unwrap_or("connection failed")
        .replace('_', " ");
    anstream::println!(
        "\n{} could not complete the connection: {reason}.",
        display_name(provider)
    );

    let mut choices: Vec<(&'static str, &'static str)> = vec![("retry", "Try again")];
    if provider == "openai" && auth == "chatgpt" {
        choices.push(("api-key", "Use an API key"));
    } else if error.code.as_deref() == Some("INVALID_CREDENTIALS") {
        choices.push(("new-key", "Enter another API key"));
    }
    choices.push(("provider", "Choose another provider"));
    choices.push(("exit", "Exit"));

    for (index, (_, label)) in choices.iter().enumerate() {
        let marker = if index == 0 { ">" } else { " " };
        anstream::println!("{marker} {}. {label}", index + 1);
    }
    let selected = prompt::select("Select", choices.len())?;
    Ok(choices[selected - 1].0)
}

type Connect<'a> =
    std::pin::Pin<Box<dyn std::future::Future<Output = Result<Value, CliError>> + 'a>>;

/// Connect one provider, all the way to a saved connection.
///
/// Boxed because it calls itself: every recovery choice except `retry` is the
/// same flow started again with different answers, which is the shape the menu
/// implies.
pub fn connect<'a>(
    client: &'a Client,
    provider: Option<String>,
    auth: Option<String>,
    replacement_default_model: Option<String>,
) -> Connect<'a> {
    Box::pin(async move {
        let provider = match provider {
            Some(p) => p,
            None => choose_provider()?,
        };
        if !is_known(&provider) {
            return Err(CliError::Usage(format!("Unknown provider: {provider}")));
        }

        let auth = if provider == "openai" {
            let chosen = match auth {
                Some(a) => a,
                None => choose_openai_method()?,
            };
            if chosen != "chatgpt" && chosen != "api-key" {
                return Err(CliError::Usage(
                    "OpenAI supports --auth chatgpt or --auth api-key.".to_owned(),
                ));
            }
            chosen
        } else {
            match auth.as_deref() {
                None | Some("api-key") => "api-key".to_owned(),
                Some(_) => {
                    return Err(CliError::Usage(format!(
                        "{} supports API keys only.",
                        display_name(&provider)
                    )));
                }
            }
        };

        let attempt = if auth == "chatgpt" {
            let attempt = client
                .post(
                    &format!("/api/providers/{provider}/auth-attempts"),
                    Some(json!({"method": "oauth", "flow": "browser"})),
                )
                .await?;
            poll_oauth(client, &attempt).await?;
            attempt
        } else {
            client
                .post(
                    &format!("/api/providers/{provider}/auth-attempts"),
                    Some(json!({"method": "api_key", "api_key": api_key(&provider)?})),
                )
                .await?
        };
        let attempt_id = attempt
            .get("id")
            .and_then(|v| v.as_str())
            .ok_or_else(|| CliError::Failed("The daemon did not return an attempt id.".to_owned()))?
            .to_owned();

        anstream::println!("{}", output::info("Checking the connection..."));
        let mut body = json!({"attempt_id": attempt_id});
        if let Some(model) = replacement_default_model {
            body["replacement_default_model"] = Value::String(model);
        }

        let row = loop {
            let attempted = client
                .put(
                    &format!("/api/providers/{provider}/connection"),
                    Some(body.clone()),
                )
                .await;
            match attempted {
                Ok(row) => break row,
                Err(ClientError::Api(error)) => {
                    if error.code.as_deref() == Some("DEFAULT_MODEL_UNAVAILABLE")
                        && body.get("replacement_default_model").is_none()
                    {
                        let models: Vec<String> = error
                            .details
                            .get("models")
                            .and_then(|v| v.as_array())
                            .map(|a| {
                                a.iter()
                                    .filter_map(|m| m.as_str().map(str::to_owned))
                                    .collect()
                            })
                            .unwrap_or_default();
                        body["replacement_default_model"] =
                            Value::String(pick_replacement(&models)?);
                        continue;
                    }
                    let recoverable = matches!(
                        error.code.as_deref(),
                        Some("INVALID_CREDENTIALS") | Some("PROVIDER_UNAVAILABLE")
                    );
                    if !recoverable {
                        return Err(CliError::Client(ClientError::Api(error)));
                    }
                    match recovery_action(&provider, &auth, &error)? {
                        "retry" => continue,
                        "api-key" => {
                            return connect(
                                client,
                                Some("openai".to_owned()),
                                Some("api-key".to_owned()),
                                None,
                            )
                            .await;
                        }
                        "new-key" => {
                            return connect(
                                client,
                                Some(provider.clone()),
                                Some("api-key".to_owned()),
                                None,
                            )
                            .await;
                        }
                        "provider" => return connect(client, None, None, None).await,
                        _ => {
                            return Err(CliError::Failed(
                                "The provider connection was not saved.".to_owned(),
                            ));
                        }
                    }
                }
                Err(other) => return Err(CliError::Client(other)),
            }
        };

        report_connection(client, &row).await?;
        Ok(row)
    })
}

/// Say what the machine can do now, which is not the same as what was connected.
async fn report_connection(client: &Client, row: &Value) -> Result<(), CliError> {
    let name = row
        .get("name")
        .and_then(|v| v.as_str())
        .unwrap_or("provider");
    if row.get("is_default").and_then(|v| v.as_bool()) == Some(true) {
        let model_id = row
            .get("default_model")
            .and_then(|v| v.as_str())
            .unwrap_or("unknown");
        let model_name = row
            .get("models")
            .and_then(|v| v.as_array())
            .and_then(|models| {
                models
                    .iter()
                    .find(|m| m.get("id").and_then(|v| v.as_str()) == Some(model_id))
                    .and_then(|m| m.get("name").and_then(|v| v.as_str()))
            })
            .unwrap_or(model_id);
        anstream::println!(
            "{}",
            output::success(&format!("Ready: {name}, {model_name}"))
        );
        return Ok(());
    }

    anstream::println!("{}", output::success(&format!("Connected: {name}")));
    let count = row
        .get("models")
        .and_then(|v| v.as_array())
        .map(|m| m.len())
        .unwrap_or(0);
    anstream::println!("Models available: {count}");

    let rows = client.get("/api/providers").await?;
    let default = rows
        .as_array()
        .and_then(|items| {
            items
                .iter()
                .find(|item| item.get("is_default").and_then(|v| v.as_bool()) == Some(true))
        })
        .cloned();
    if let Some(default) = default {
        let default_name = default.get("name").and_then(|v| v.as_str()).unwrap_or("-");
        let default_model = default
            .get("default_model")
            .and_then(|v| v.as_str())
            .unwrap_or("unknown");
        anstream::println!("Default remains: {default_name} / {default_model}");
    }
    Ok(())
}

pub async fn login(
    client: &Client,
    provider: Option<String>,
    auth: Option<String>,
    replacement_default_model: Option<String>,
) -> Result<(), CliError> {
    connect(client, provider, auth, replacement_default_model).await?;
    Ok(())
}

pub async fn logout(client: &Client, provider: &str) -> Result<(), CliError> {
    if !is_known(provider) {
        return Err(CliError::Usage(format!("Unknown provider: {provider}")));
    }
    client
        .delete(&format!("/api/providers/{provider}/connection"))
        .await?;
    anstream::println!(
        "{}",
        output::success(&format!("Disconnected: {}", display_name(provider)))
    );
    Ok(())
}

pub async fn status(
    client: &Client,
    refresh: bool,
    provider: Option<String>,
) -> Result<(), CliError> {
    if let Some(p) = provider.as_deref().filter(|p| !is_known(p)) {
        return Err(CliError::Usage(format!("Unknown provider: {p}")));
    }
    if refresh {
        let rows = client.get("/api/providers").await?;
        let targets: Vec<String> = match provider.clone() {
            Some(p) => vec![p],
            None => rows
                .as_array()
                .map(|items| {
                    items
                        .iter()
                        .filter(|r| r.get("connected").and_then(|v| v.as_bool()) == Some(true))
                        .filter_map(|r| r.get("id").and_then(|v| v.as_str()).map(str::to_owned))
                        .collect()
                })
                .unwrap_or_default(),
        };
        for target in targets {
            client
                .post_long(&format!("/api/providers/{target}/catalog-refresh"), None)
                .await?;
        }
    }
    let rows = client.get("/api/providers").await?;
    print_provider_rows(&rows, provider.as_deref(), false);
    Ok(())
}

pub async fn model_list(client: &Client) -> Result<(), CliError> {
    let rows = client.get("/api/providers").await?;
    print_provider_rows(&rows, None, true);
    Ok(())
}

/// Every connected `provider/model` pair, in catalog order.
fn model_choices(rows: &Value) -> Vec<(String, String, String, String)> {
    rows.as_array()
        .map(|items| {
            items
                .iter()
                .filter(|r| r.get("connected").and_then(|v| v.as_bool()) == Some(true))
                .flat_map(|r| {
                    let provider_id = r
                        .get("id")
                        .and_then(|v| v.as_str())
                        .unwrap_or("")
                        .to_owned();
                    let provider_name = r
                        .get("name")
                        .and_then(|v| v.as_str())
                        .unwrap_or("")
                        .to_owned();
                    r.get("models")
                        .and_then(|v| v.as_array())
                        .cloned()
                        .unwrap_or_default()
                        .into_iter()
                        .map(move |m| {
                            (
                                provider_id.clone(),
                                m.get("id")
                                    .and_then(|v| v.as_str())
                                    .unwrap_or("")
                                    .to_owned(),
                                provider_name.clone(),
                                m.get("name")
                                    .and_then(|v| v.as_str())
                                    .unwrap_or("")
                                    .to_owned(),
                            )
                        })
                        .collect::<Vec<_>>()
                })
                .collect()
        })
        .unwrap_or_default()
}

pub async fn model_default(client: &Client, selection: Option<String>) -> Result<(), CliError> {
    let rows = client.get("/api/providers").await?;
    let choices = model_choices(&rows);
    if choices.is_empty() {
        return Err(CliError::Failed(
            "No connected models are available.".to_owned(),
        ));
    }

    let (provider, model) = match selection {
        Some(selection) => {
            let (provider, model) = selection.split_once('/').ok_or_else(|| {
                CliError::Usage("MODEL must be a connected provider/model pair.".to_owned())
            })?;
            if !choices
                .iter()
                .any(|(p, m, _, _)| p == provider && m == model)
            {
                return Err(CliError::Usage(
                    "MODEL must be a connected provider/model pair.".to_owned(),
                ));
            }
            (provider.to_owned(), model.to_owned())
        }
        None => {
            anstream::println!("Choose the machine default");
            for (index, (_, _, provider_name, model_name)) in choices.iter().enumerate() {
                anstream::println!("  {}. {provider_name} / {model_name}", index + 1);
            }
            let selected = prompt::select("Select", choices.len())?;
            let (provider, model, _, _) = &choices[selected - 1];
            (provider.clone(), model.clone())
        }
    };

    anstream::println!("{}", output::info("Checking the model..."));
    let result = client
        .put(
            "/api/default-model",
            Some(json!({"provider": provider, "model": model})),
        )
        .await?;
    let provider = result
        .get("provider")
        .and_then(|v| v.as_str())
        .unwrap_or(&provider);
    let model = result
        .get("model")
        .and_then(|v| v.as_str())
        .unwrap_or(&model);
    anstream::println!(
        "{}",
        output::success(&format!("Default: {provider} / {model}"))
    );
    Ok(())
}

/// The provider listing both `provider status` and `model list` print.
fn print_provider_rows(rows: &Value, provider: Option<&str>, connected_only: bool) {
    for line in provider_lines(rows, provider, connected_only) {
        anstream::println!("{line}");
    }
}

/// Render the provider rows before writing them, so the two default facts stay
/// independently testable: which provider is default, and which model it uses.
fn provider_lines(rows: &Value, provider: Option<&str>, connected_only: bool) -> Vec<String> {
    let empty = Vec::new();
    let items = rows.as_array().unwrap_or(&empty);
    let shown: Vec<&Value> = items
        .iter()
        .filter(|r| provider.is_none_or(|p| r.get("id").and_then(|v| v.as_str()) == Some(p)))
        .filter(|r| !connected_only || r.get("connected").and_then(|v| v.as_bool()) == Some(true))
        .collect();
    if shown.is_empty() {
        return vec!["No connected providers.".to_owned()];
    }
    let mut lines = Vec::new();
    for row in shown {
        let name = row.get("name").and_then(|v| v.as_str()).unwrap_or("-");
        let state = if row.get("connected").and_then(|v| v.as_bool()) == Some(true) {
            "connected"
        } else {
            "not connected"
        };
        let suffix = if row.get("is_default").and_then(|v| v.as_bool()) == Some(true) {
            " (default)"
        } else {
            ""
        };
        let stale = if row.get("catalog_stale").and_then(|v| v.as_bool()) == Some(true) {
            " (stale)"
        } else {
            ""
        };
        lines.push(format!("{name}: {state}{suffix}{stale}"));
        let default_model = (row.get("is_default").and_then(|v| v.as_bool()) == Some(true))
            .then(|| row.get("default_model").and_then(|v| v.as_str()))
            .flatten();
        if let Some(models) = row.get("models").and_then(|v| v.as_array()) {
            for model in models {
                let id = model.get("id").and_then(|v| v.as_str()).unwrap_or("-");
                let model_name = model.get("name").and_then(|v| v.as_str()).unwrap_or("-");
                let model_suffix = if default_model == Some(id) {
                    " (default)"
                } else {
                    ""
                };
                lines.push(format!("  {id}  {model_name}{model_suffix}"));
            }
        }
    }
    lines
}

#[cfg(test)]
mod tests {
    use super::{browser_command, provider_lines};
    use serde_json::json;

    #[test]
    fn the_model_list_marks_exactly_one_default_model_and_keeps_the_provider_marker() {
        let rows = json!([
            {
                "id": "openai",
                "name": "OpenAI",
                "connected": true,
                "is_default": false,
                "default_model": null,
                "catalog_stale": false,
                "models": [
                    {"id": "gpt-fast", "name": "GPT Fast"}
                ]
            },
            {
                "id": "gemini",
                "name": "Google Gemini",
                "connected": true,
                "is_default": true,
                "default_model": "gemini-fast",
                "catalog_stale": false,
                "models": [
                    {"id": "gemini-fast", "name": "Gemini Fast"},
                    {"id": "gemini-pro", "name": "Gemini Pro"}
                ]
            }
        ]);

        let lines = provider_lines(&rows, None, true);
        let provider_markers: Vec<_> = lines
            .iter()
            .filter(|line| !line.starts_with("  ") && line.ends_with(" (default)"))
            .map(String::as_str)
            .collect();
        let model_markers: Vec<_> = lines
            .iter()
            .filter(|line| line.starts_with("  ") && line.ends_with(" (default)"))
            .map(String::as_str)
            .collect();

        assert_eq!(
            provider_markers,
            vec!["Google Gemini: connected (default)"],
            "the provider-level default remains visible"
        );
        assert_eq!(
            model_markers,
            vec!["  gemini-fast  Gemini Fast (default)"],
            "exactly the selected provider/model pair is marked"
        );
    }

    /// The browser is opened without a shell, on every platform.
    ///
    /// An authorization URL carries its parameters after `&`, and a shell reads
    /// `&` as a separator. Opening one through `cmd` delivered only the part
    /// before the first `&`, so the provider saw a request with no `client_id`
    /// and refused it for a missing parameter. The defect was invisible from
    /// the CLI's own output, which printed the whole URL correctly.
    #[test]
    fn the_browser_is_opened_without_a_shell() {
        let (program, args) = browser_command();

        assert_ne!(program, "cmd", "a shell splits the URL on its ampersands");
        assert_ne!(program, "sh");
        assert!(
            !args.contains(&"start"),
            "`start` is the shell builtin that ate the query string"
        );
        assert!(
            !args.contains(&"/C") && !args.contains(&"-c"),
            "passing the URL as a shell command line reparses it"
        );
    }

    /// The URL is the last argument and nothing is appended after it, so no
    /// separator can be read as part of the address.
    #[test]
    fn the_launcher_takes_fixed_arguments_only() {
        let (_, args) = browser_command();
        assert!(
            args.iter().all(|arg| !arg.contains("://")),
            "the URL is supplied by the caller, never baked into the arguments"
        );
    }
}
