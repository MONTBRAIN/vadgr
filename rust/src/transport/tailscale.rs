//! Tailscale, and the loopback transport that stands in when it is off.
//!
//! The LocalAPI client is the whole trick and it is small: HTTP/1.0 over an
//! `AF_UNIX` socket with the fixed `Host: local-tailscaled.sock` sentinel.
//! HTTP/1.0 because the Go server chunks otherwise, and this parser does not
//! want to speak chunked. On Windows the same request goes over a named pipe;
//! that path is a `0.5.0` concern, when a Windows artifact first exists to run
//! it, and until then it reports unavailable rather than pretending.

use super::Transport;
use serde_json::{json, Value};
use std::io::{Read, Write};
use std::time::Duration;

const SOCKET_PATH: &str = "/var/run/tailscale/tailscaled.sock";

/// The tailnet's CGNAT range, `100.64.0.0/10`. The fallback when WhoIs cannot
/// answer, and the reason a source outside it is refused before any token work.
fn in_tailnet_cgnat(host: &str) -> bool {
    let ip: std::net::IpAddr = match host.parse() {
        Ok(v) => v,
        Err(_) => return false,
    };
    match ip {
        std::net::IpAddr::V4(v4) => {
            let o = v4.octets();
            o[0] == 100 && (64..128).contains(&o[1])
        }
        std::net::IpAddr::V6(_) => false,
    }
}

fn local_api_get(path: &str) -> Option<Value> {
    #[cfg(unix)]
    {
        use std::os::unix::net::UnixStream;
        let mut sock = UnixStream::connect(SOCKET_PATH).ok()?;
        sock.set_read_timeout(Some(Duration::from_secs(2))).ok()?;
        sock.set_write_timeout(Some(Duration::from_secs(2))).ok()?;
        let req = format!(
            "GET {path} HTTP/1.0\r\nHost: local-tailscaled.sock\r\nConnection: close\r\n\r\n"
        );
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
    #[cfg(not(unix))]
    {
        let _ = path;
        None
    }
}

pub struct TailscaleTransport;

impl TailscaleTransport {
    fn status_json(&self) -> Option<Value> {
        local_api_get("/localapi/v0/status")
    }

    fn is_available(&self) -> bool {
        match self.status_json() {
            // `BackendState == "Running"` means up and logged in. A missing
            // field is treated as running, which is what the Python does.
            Some(s) => match s.get("BackendState").and_then(|v| v.as_str()) {
                None | Some("Running") => true,
                Some(_) => false,
            },
            None => false,
        }
    }

    fn self_ip(&self) -> Option<String> {
        let s = self.status_json()?;
        s.get("Self")?
            .get("TailscaleIPs")?
            .as_array()?
            .iter()
            .filter_map(|v| v.as_str())
            .find(|ip| ip.parse::<std::net::Ipv4Addr>().is_ok())
            .map(|s| s.to_string())
    }

    fn magic_dns(&self) -> Option<String> {
        let s = self.status_json()?;
        let name = s.get("Self")?.get("DNSName")?.as_str()?;
        let trimmed = name.trim_end_matches('.');
        if trimmed.is_empty() { None } else { Some(trimmed.to_string()) }
    }
}

impl Transport for TailscaleTransport {
    fn name(&self) -> &'static str { "tailscale" }

    fn advertise_host(&self) -> Option<String> {
        if !self.is_available() {
            return None;
        }
        self.magic_dns().or_else(|| self.self_ip())
    }

    /// **The F2 fix, reproduced rather than the bug it replaced.** The daemon
    /// binds what the transport advertises, so the address the QR carries is
    /// one the daemon answers on.
    fn bind_host(&self) -> String {
        self.self_ip().unwrap_or_else(|| "127.0.0.1".to_string())
    }

    fn is_authorized_source(&self, host: &str) -> bool {
        if local_api_get(&format!("/localapi/v0/whois?addr={host}")).is_some() {
            return true;
        }
        in_tailnet_cgnat(host)
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

pub struct LoopbackTransport;

impl Transport for LoopbackTransport {
    fn name(&self) -> &'static str { "loopback" }
    fn advertise_host(&self) -> Option<String> { None }
    fn bind_host(&self) -> String { "127.0.0.1".to_string() }
    /// Nothing off the machine is a peer here, so gate 1 refuses everything
    /// that is not loopback - which gate 0 has already passed.
    fn is_authorized_source(&self, _host: &str) -> bool { false }
    fn status(&self) -> Value {
        json!({
            "name": self.name(),
            "available": true,
            "advertise_host": Value::Null,
            "bind_host": "127.0.0.1",
        })
    }
}

pub fn create(name: &str) -> anyhow::Result<Box<dyn Transport>> {
    match name.trim().to_lowercase().as_str() {
        "tailscale" => Ok(Box::new(TailscaleTransport)),
        "loopback" => Ok(Box::new(LoopbackTransport)),
        other => anyhow::bail!(
            "Unknown VADGR_TRANSPORT={other:?}. Expected 'loopback' or 'tailscale'."
        ),
    }
}
