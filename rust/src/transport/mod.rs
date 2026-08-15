//! The transport port: the only abstraction routes and the gate depend on.
//!
//! Every adapter answers the same five questions the same way, so callers
//! never branch on the concrete type. The tailscale adapter's LocalAPI client
//! is its own port and is injected, which is what keeps the adapter testable
//! without a live tailscaled.

pub mod loopback;
pub mod tailscale;

pub use loopback::LoopbackTransport;
pub use tailscale::{TailscaleTransport, TailscaledLocalApi};

use serde_json::Value;
use std::net::{IpAddr, SocketAddr};

pub trait Transport: Send + Sync {
    fn name(&self) -> &'static str;

    /// Interface the daemon binds. The transport's own address, never
    /// `0.0.0.0`. Errs when the transport is unavailable - callers check
    /// `is_available()` first, and a caller that does not gets a refusal
    /// rather than a silent bind to the wrong interface.
    fn bind_host(&self) -> anyhow::Result<String>;

    /// The host a QR may advertise, or `None` when nothing reachable exists.
    /// `None` is what makes `POST /api/auth/pair` refuse with
    /// `TRANSPORT_UNREACHABLE` rather than hand out a localhost QR no phone
    /// could use.
    fn advertise_host(&self) -> Option<String>;

    /// Transport up and ready (for tailscale: tailscaled running + logged in).
    fn is_available(&self) -> bool;

    /// Gate 1: is this connection from an allowed peer?
    fn is_authorized_source(&self, host: &str) -> bool;

    /// Diagnostics for `GET /api/health`.
    fn status(&self) -> Value;
}

/// The Python launcher always keeps the local CLI address open. A live
/// transport adds its address; an unavailable one leaves loopback working and
/// makes pairing report the transport failure through its normal route.
pub fn bind_hosts(transport: &dyn Transport) -> Vec<String> {
    match transport.bind_host() {
        Ok(primary) if primary == "127.0.0.1" => vec![primary],
        Ok(primary) => vec![primary, "127.0.0.1".to_string()],
        Err(error) => {
            tracing::warn!(%error, "transport unavailable; binding loopback only");
            vec!["127.0.0.1".to_string()]
        }
    }
}

/// Turn a transport-owned IP and port into a listener address. Constructing a
/// `SocketAddr` instead of concatenating strings keeps IPv6 valid on every OS.
pub fn listener_address(host: &str, port: u16) -> anyhow::Result<SocketAddr> {
    let ip: IpAddr = host
        .parse()
        .map_err(|_| anyhow::anyhow!("transport returned an invalid bind address: {host:?}"))?;
    Ok(SocketAddr::new(ip, port))
}

/// Build the configured transport. The tailscale adapter gets the real
/// LocalAPI client here; tests construct it with a fake instead.
pub fn create(name: &str) -> anyhow::Result<Box<dyn Transport>> {
    match name.trim().to_lowercase().as_str() {
        "tailscale" => Ok(Box::new(TailscaleTransport::new(
            TailscaledLocalApi::from_env(),
        ))),
        "loopback" => Ok(Box::new(LoopbackTransport)),
        other => {
            anyhow::bail!("Unknown VADGR_TRANSPORT={other:?}. Expected 'loopback' or 'tailscale'.")
        }
    }
}
