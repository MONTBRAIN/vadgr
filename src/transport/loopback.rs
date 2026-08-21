//! Loopback transport: the dev / single-machine default.
//!
//! Binds to 127.0.0.1 and authorizes only loopback peers. It deliberately
//! cannot advertise a host: there is no address a remote phone could reach,
//! so `advertise_host()` returns `None` and the pair endpoint refuses rather
//! than handing out a useless localhost QR.

use super::Transport;
use serde_json::{Value, json};

pub struct LoopbackTransport;

impl Transport for LoopbackTransport {
    fn name(&self) -> &'static str {
        "loopback"
    }

    fn bind_host(&self) -> anyhow::Result<String> {
        Ok("127.0.0.1".to_string())
    }

    fn advertise_host(&self) -> Option<String> {
        None
    }

    fn is_available(&self) -> bool {
        true
    }

    /// A loopback peer is authorized; anything off the machine is not. Gate 0
    /// admits loopback before this is ever asked, but the port answers the
    /// question the same way whoever asks it.
    fn is_authorized_source(&self, host: &str) -> bool {
        host.parse::<std::net::IpAddr>()
            .is_ok_and(|address| address.is_loopback())
    }

    fn status(&self) -> Value {
        json!({
            "name": self.name(),
            "available": true,
            "advertise_host": Value::Null,
            "bind_host": "127.0.0.1",
        })
    }
}
