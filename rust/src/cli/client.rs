//! The CLI's HTTP boundary.
//!
//! Ported from `cli/client.py`, and the design calls this the riskiest file in
//! the port: every behaviour a script depends on lives here, and none of it is
//! visible in the command tree.

use std::net::{SocketAddr, TcpStream, ToSocketAddrs};
use std::time::Duration;

/// Fifteen seconds for an ordinary call.
const TIMEOUT: Duration = Duration::from_secs(15);
/// Two minutes for the calls that wait on a provider.
const LONG_TIMEOUT: Duration = Duration::from_secs(120);
/// The reachability probe answers in milliseconds or not at all.
const CONNECT_TIMEOUT: Duration = Duration::from_millis(1500);

const LOOPBACK_HOSTS: [&str; 3] = ["127.0.0.1", "localhost", "::1"];

/// The daemon could not be reached.
///
/// **Its own exit code, and that is the contract.** "It is down" and "it ran and
/// said no" are different problems, and a script branches on them: the first is
/// retried after a start, the second never is. Collapsing them into one code
/// makes that branch impossible to write.
#[derive(Debug)]
pub struct DaemonUnreachable {
    pub base_url: String,
}

impl DaemonUnreachable {
    pub const EXIT_CODE: i32 = 3;
}

impl std::fmt::Display for DaemonUnreachable {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        write!(
            f,
            "API is not running at {}. Start it with: vadgr start",
            self.base_url
        )
    }
}

/// A structured daemon error that a command can recover from **by code**.
///
/// `details` is load-bearing rather than decoration: the provider commands read
/// `details["category"]` to choose which recovery menu to offer. A port that
/// keeps only the message turns that branch into string matching.
#[derive(Debug)]
pub struct ApiClientError {
    pub message: String,
    pub status: u16,
    pub code: Option<String>,
    pub details: serde_json::Value,
}

impl ApiClientError {
    pub const EXIT_CODE: i32 = 1;

    /// The recovery category, when the daemon named one.
    pub fn category(&self) -> Option<&str> {
        self.details.get("category").and_then(|v| v.as_str())
    }
}

impl std::fmt::Display for ApiClientError {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        f.write_str(&self.message)
    }
}

#[derive(Debug)]
pub enum ClientError {
    Unreachable(DaemonUnreachable),
    Api(ApiClientError),
}

impl ClientError {
    /// The exit code this failure leaves the process with.
    pub fn exit_code(&self) -> i32 {
        match self {
            Self::Unreachable(_) => DaemonUnreachable::EXIT_CODE,
            Self::Api(_) => ApiClientError::EXIT_CODE,
        }
    }
}

impl std::fmt::Display for ClientError {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            Self::Unreachable(e) => e.fmt(f),
            Self::Api(e) => e.fmt(f),
        }
    }
}

/// Whether the pre-request reachability probe applies to this URL.
///
/// **Loopback with an explicit port, and nothing else.** The probe exists for
/// the local daemon and is only ever allowed to make the answer *faster*, never
/// to invent a failure the request itself would not have hit.
///
/// Two ways a broader probe would do exactly that. `--api-url` can point at an
/// `https://` host with no port, where testing `port or 80` would probe 80 while
/// the request goes to 443 and report a live machine as down. And a remote host
/// over a tailnet can be reachable-but-slow, which is normal for it rather than
/// a failure to report early.
pub fn should_probe(base_url: &str) -> bool {
    let Ok(url) = url::Url::parse(base_url) else {
        return false;
    };
    let Some(port) = url.port() else {
        return false;
    };
    let _ = port;
    url.host_str().is_some_and(|h| LOOPBACK_HOSTS.contains(&h))
}

/// Whether anything is listening, answered in milliseconds.
///
/// On Linux and macOS a closed local port is refused instantly and this is
/// redundant. **On WSL2 it is not**: an IPv4 loopback connect to a port nothing
/// listens on is swallowed rather than refused, so the connect runs to the full
/// timeout. Measured at 15 s for `vadgr health` against a dead daemon, where
/// `::1` refuses the same port in under a millisecond. WSL2 is a platform this
/// daemon claims, and "your daemon is down" should not take fifteen seconds to
/// say on it.
pub fn port_is_open(host: &str, port: u16) -> bool {
    let Ok(addrs) = (host, port).to_socket_addrs() else {
        return false;
    };
    let addrs: Vec<SocketAddr> = addrs.collect();
    addrs
        .iter()
        .any(|a| TcpStream::connect_timeout(a, CONNECT_TIMEOUT).is_ok())
}

/// The HTTP client, holding its base URL as a value.
///
/// Taking the base URL and the underlying client by value rather than reading
/// them from ambient context is what makes every command testable against a stub
/// without a live daemon, which is what the Python tests already do.
pub struct Client {
    base_url: String,
    http: reqwest::Client,
}

impl Client {
    pub fn new(base_url: impl Into<String>) -> Self {
        Self {
            base_url: base_url.into().trim_end_matches('/').to_owned(),
            http: reqwest::Client::builder()
                .timeout(TIMEOUT)
                .build()
                .expect("the HTTP client builds"),
        }
    }

    pub fn base_url(&self) -> &str {
        &self.base_url
    }

    pub async fn get(&self, path: &str) -> Result<serde_json::Value, ClientError> {
        self.request(reqwest::Method::GET, path, None, TIMEOUT)
            .await
    }

    pub async fn post(
        &self,
        path: &str,
        body: Option<serde_json::Value>,
    ) -> Result<serde_json::Value, ClientError> {
        self.request(reqwest::Method::POST, path, body, TIMEOUT)
            .await
    }

    /// A POST that waits on a provider, so it takes the long timeout.
    pub async fn post_long(
        &self,
        path: &str,
        body: Option<serde_json::Value>,
    ) -> Result<serde_json::Value, ClientError> {
        self.request(reqwest::Method::POST, path, body, LONG_TIMEOUT)
            .await
    }

    pub async fn put(
        &self,
        path: &str,
        body: Option<serde_json::Value>,
    ) -> Result<serde_json::Value, ClientError> {
        self.request(reqwest::Method::PUT, path, body, LONG_TIMEOUT)
            .await
    }

    pub async fn delete(&self, path: &str) -> Result<serde_json::Value, ClientError> {
        self.request(reqwest::Method::DELETE, path, None, TIMEOUT)
            .await
    }

    /// Whether the daemon answers its health route.
    pub async fn is_running(&self) -> bool {
        self.get("/api/health").await.is_ok()
    }

    fn unreachable(&self) -> ClientError {
        ClientError::Unreachable(DaemonUnreachable {
            base_url: self.base_url.clone(),
        })
    }

    async fn request(
        &self,
        method: reqwest::Method,
        path: &str,
        body: Option<serde_json::Value>,
        timeout: Duration,
    ) -> Result<serde_json::Value, ClientError> {
        if should_probe(&self.base_url) {
            let url = url::Url::parse(&self.base_url).expect("a probed base URL parses");
            let host = url.host_str().unwrap_or("127.0.0.1");
            let port = url.port().expect("should_probe required a port");
            if !port_is_open(host, port) {
                return Err(self.unreachable());
            }
        }

        let mut req = self
            .http
            .request(method, format!("{}{path}", self.base_url))
            .timeout(timeout);
        if let Some(b) = body {
            req = req.json(&b);
        }

        let response = match req.send().await {
            Ok(r) => r,
            Err(e) if e.is_connect() || e.is_timeout() => return Err(self.unreachable()),
            Err(e) => {
                return Err(ClientError::Api(ApiClientError {
                    message: e.to_string(),
                    status: 0,
                    code: None,
                    details: serde_json::Value::Null,
                }));
            }
        };

        let status = response.status().as_u16();
        let payload: serde_json::Value = response.json().await.unwrap_or(serde_json::Value::Null);

        if (200..300).contains(&status) {
            return Ok(payload);
        }

        // The daemon's error envelope, kept whole. `details` reaches the command
        // that has to branch on it.
        let error = payload.get("error");
        Err(ClientError::Api(ApiClientError {
            message: error
                .and_then(|e| e.get("message"))
                .and_then(|m| m.as_str())
                .unwrap_or("the daemon returned an error")
                .to_owned(),
            status,
            code: error
                .and_then(|e| e.get("code"))
                .and_then(|c| c.as_str())
                .map(str::to_owned),
            details: error
                .and_then(|e| e.get("details"))
                .cloned()
                .unwrap_or(serde_json::Value::Null),
        }))
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn the_probe_applies_to_loopback_with_an_explicit_port() {
        assert!(should_probe("http://127.0.0.1:8000"));
        assert!(should_probe("http://localhost:8000"));
    }

    /// The narrowness is the point, not an omission.
    #[test]
    fn the_probe_does_not_apply_where_it_would_invent_a_failure() {
        // An https host with no port: probing `port or 80` would test 80 while
        // the request goes to 443, and report a live machine as down.
        assert!(!should_probe("https://machine.example.com"));
        // A remote host is allowed to be reachable-but-slow.
        assert!(!should_probe("http://100.64.0.1:8000"));
        assert!(!should_probe("http://machine.tail1234.ts.net:8000"));
    }

    #[test]
    fn the_two_failures_carry_different_exit_codes() {
        let down = ClientError::Unreachable(DaemonUnreachable {
            base_url: "http://127.0.0.1:8000".into(),
        });
        let refused = ClientError::Api(ApiClientError {
            message: "no".into(),
            status: 400,
            code: Some("BAD".into()),
            details: serde_json::Value::Null,
        });
        assert_eq!(down.exit_code(), 3, "down is retried after a start");
        assert_eq!(refused.exit_code(), 1, "refused never is");
        assert_ne!(down.exit_code(), refused.exit_code());
    }

    #[test]
    fn a_daemon_error_keeps_the_category_a_command_branches_on() {
        let e = ApiClientError {
            message: "could not connect".into(),
            status: 503,
            code: Some("PROVIDER_UNAVAILABLE".into()),
            details: serde_json::json!({ "category": "provider_unavailable" }),
        };
        assert_eq!(e.category(), Some("provider_unavailable"));
    }
}
