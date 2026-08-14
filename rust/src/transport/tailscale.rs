//! Tailscale transport: exposes the API over the tailnet only.
//!
//! Reachability and peer identity come from the tailscaled **LocalAPI**: an
//! HTTP/1.0 request over an `AF_UNIX` socket with the fixed
//! `Host: local-tailscaled.sock` sentinel. HTTP/1.0 because the Go server
//! chunks otherwise, and this parser does not want to speak chunked. On
//! Windows the same request goes over the tailscaled named pipe. The Rust CI
//! builds and tests this module on Linux, Windows and macOS.
//!
//! The LocalAPI client is injected so the adapter is unit-testable with a
//! fake WhoIs / status: no live tailnet needed.
//!
//! Authorization is structural-and-checked: bind only to the node's 100.x
//! interface (so non-tailnet peers cannot even connect at the socket level),
//! and additionally verify each peer is a tailnet member via WhoIs, falling
//! back to the 100.64.0.0/10 CGNAT range when WhoIs is unavailable.

use super::Transport;
use serde_json::{Value, json};

const SOCKET_PATH: &str = "/var/run/tailscale/tailscaled.sock";

/// The slice of the tailscaled LocalAPI this adapter needs.
pub trait LocalApi: Send + Sync {
    /// Parsed tailscaled status, or `None` when unavailable / logged out.
    fn status(&self) -> Option<Value>;
    /// Identity of a peer by IP, or `None` if not a tailnet member.
    fn whois(&self, peer_ip: &str) -> Option<Value>;
}

/// Talks to the real tailscaled LocalAPI over its unix socket.
pub struct TailscaledLocalApi {
    #[cfg(unix)]
    socket_path: String,
    #[cfg(windows)]
    pipe_path: String,
}

impl TailscaledLocalApi {
    pub fn new(socket_path: impl Into<String>) -> Self {
        #[cfg(unix)]
        let socket_path = socket_path.into();
        #[cfg(windows)]
        drop(socket_path);
        Self {
            #[cfg(unix)]
            socket_path,
            #[cfg(windows)]
            pipe_path: std::env::var("VADGR_TAILSCALED_PIPE").unwrap_or_else(|_| {
                r"\\.\pipe\ProtectedPrefix\Administrators\Tailscale\tailscaled".to_string()
            }),
        }
    }

    /// The default socket path, overridable the same way the Python daemon
    /// allows: `VADGR_TAILSCALED_SOCKET`.
    pub fn from_env() -> Self {
        Self::new(
            std::env::var("VADGR_TAILSCALED_SOCKET").unwrap_or_else(|_| SOCKET_PATH.to_string()),
        )
    }

    fn get(&self, path: &str) -> Option<Value> {
        let req = format!(
            "GET {path} HTTP/1.0\r\nHost: local-tailscaled.sock\r\nConnection: close\r\n\r\n"
        );
        #[cfg(unix)]
        {
            use std::io::{Read, Write};
            use std::os::unix::net::UnixStream;
            use std::time::Duration;

            let mut sock = UnixStream::connect(&self.socket_path).ok()?;
            sock.set_read_timeout(Some(Duration::from_secs(2))).ok()?;
            sock.set_write_timeout(Some(Duration::from_secs(2))).ok()?;
            sock.write_all(req.as_bytes()).ok()?;
            let mut raw = Vec::new();
            sock.read_to_end(&mut raw).ok()?;
            let sep = raw.windows(4).position(|w| w == b"\r\n\r\n")?;
            let (head, body) = raw.split_at(sep);
            let status_line = head.split(|b| *b == b'\r').next()?;
            if !status_line.windows(5).any(|w| w == b" 200 ") {
                return None;
            }
            serde_json::from_slice(&body[4..]).ok()
        }
        #[cfg(windows)]
        {
            use std::io::{Read, Write};
            use std::os::windows::fs::OpenOptionsExt;

            const SECURITY_SQOS_PRESENT: u32 = 0x0010_0000;
            const SECURITY_IMPERSONATION: u32 = 0x0002_0000;
            let mut pipe = std::fs::OpenOptions::new()
                .read(true)
                .write(true)
                .custom_flags(SECURITY_SQOS_PRESENT | SECURITY_IMPERSONATION)
                .open(&self.pipe_path)
                .ok()?;
            pipe.write_all(req.as_bytes()).ok()?;
            let mut raw = Vec::new();
            pipe.read_to_end(&mut raw).ok()?;
            let sep = raw.windows(4).position(|w| w == b"\r\n\r\n")?;
            let (head, body) = raw.split_at(sep);
            let status_line = head.split(|b| *b == b'\r').next()?;
            if !status_line.windows(5).any(|w| w == b" 200 ") {
                return None;
            }
            serde_json::from_slice(&body[4..]).ok()
        }
    }
}

impl LocalApi for TailscaledLocalApi {
    fn status(&self) -> Option<Value> {
        self.get("/localapi/v0/status")
    }

    fn whois(&self, peer_ip: &str) -> Option<Value> {
        self.get(&format!("/localapi/v0/whois?addr={peer_ip}"))
    }
}

/// The tailnet's CGNAT range, `100.64.0.0/10`. The fallback when WhoIs cannot
/// answer, and the reason a source outside it is refused before any token work.
fn in_tailnet_cgnat(ip: std::net::IpAddr) -> bool {
    match ip {
        std::net::IpAddr::V4(v4) => {
            let o = v4.octets();
            o[0] == 100 && (64..128).contains(&o[1])
        }
        std::net::IpAddr::V6(_) => false,
    }
}

pub struct TailscaleTransport<A: LocalApi> {
    api: A,
}

impl<A: LocalApi> TailscaleTransport<A> {
    pub fn new(api: A) -> Self {
        Self { api }
    }

    fn self_ip(&self) -> Option<String> {
        let s = self.api.status()?;
        let ips: Vec<&str> = s
            .get("Self")?
            .get("TailscaleIPs")?
            .as_array()?
            .iter()
            .filter_map(|v| v.as_str())
            .collect();
        ips.iter()
            .find(|ip| ip.parse::<std::net::Ipv4Addr>().is_ok())
            .or_else(|| ips.first())
            .map(|s| s.to_string())
    }

    fn magic_dns(&self) -> Option<String> {
        let s = self.api.status()?;
        let name = s.get("Self")?.get("DNSName")?.as_str()?;
        let trimmed = name.trim_end_matches('.');
        if trimmed.is_empty() {
            None
        } else {
            Some(trimmed.to_string())
        }
    }
}

impl<A: LocalApi> Transport for TailscaleTransport<A> {
    fn name(&self) -> &'static str {
        "tailscale"
    }

    /// **The F2 fix, reproduced rather than the bug it replaced.** The daemon
    /// binds what the transport advertises, so the address the QR carries is
    /// one the daemon answers on. Unavailable is an error, not a silent fall
    /// back to loopback: binding an interface the transport did not name is
    /// the exact bug the fix removed.
    fn bind_host(&self) -> anyhow::Result<String> {
        self.self_ip().ok_or_else(|| {
            anyhow::anyhow!(
                "Tailscale transport unavailable: tailscaled not running or logged out."
            )
        })
    }

    fn advertise_host(&self) -> Option<String> {
        if !self.is_available() {
            return None;
        }
        self.magic_dns().or_else(|| self.self_ip())
    }

    fn is_available(&self) -> bool {
        let Some(s) = self.api.status() else {
            return false;
        };
        // `BackendState == "Running"` means up and logged in. A missing field
        // is treated as running, which is what the Python does.
        match s.get("BackendState") {
            None | Some(Value::Null) => {}
            Some(state) if state.as_str() == Some("Running") => {}
            Some(_) => return false,
        }
        self.self_ip().is_some()
    }

    fn is_authorized_source(&self, host: &str) -> bool {
        // A string that is not an address is refused before anything is asked
        // about it: garbage never earns a WhoIs roundtrip.
        let Ok(ip) = host.parse::<std::net::IpAddr>() else {
            return false;
        };
        // Prefer an authoritative WhoIs identity check.
        if self.api.whois(host).is_some() {
            return true;
        }
        // Fall back to the CGNAT range when WhoIs is unavailable.
        in_tailnet_cgnat(ip)
    }

    fn status(&self) -> Value {
        let available = self.is_available();
        json!({
            "name": self.name(),
            "available": available,
            "advertise_host": if available { self.advertise_host() } else { None },
            "bind_host": self.self_ip(),
        })
    }
}
