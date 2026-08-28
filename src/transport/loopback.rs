//! Loopback transport: the on-box owner surface, registered on every machine.
//!
//! Binds to 127.0.0.1 and authorizes only loopback peers. Its `Reach` is
//! `Local`: there is no address a remote phone could reach, so it never
//! appears in the pairing report. It is the one transport that grants the
//! local bypass, which is what keeps gate 0 a question with one honest owner.

use super::{Gate1, Peer, Reach, Scope, Transport, public_diagnostics};
use axum::Router;
use futures_util::future::BoxFuture;
use serde_json::{Value, json};

pub struct LoopbackTransport;

/// Whether a stamped identity is a loopback address. Shared with the gate's
/// tests; the product path asks the transport, never this directly.
pub fn is_loopback_identity(identity: &str) -> bool {
    identity
        .parse::<std::net::IpAddr>()
        .is_ok_and(|address| address.is_loopback())
        || identity.eq_ignore_ascii_case("localhost")
        || identity.eq_ignore_ascii_case("testclient")
}

impl Transport for LoopbackTransport {
    fn name(&self) -> &'static str {
        "loopback"
    }

    fn label(&self) -> &'static str {
        "Loopback"
    }

    fn serve(
        &self,
        app: Router,
        port: u16,
        hosts: &[String],
    ) -> BoxFuture<'static, anyhow::Result<()>> {
        // The daemon's --host override wins where it names loopback
        // addresses; the rest of the override belongs to the transports that
        // advertised those hosts.
        let mut mine: Vec<String> = hosts
            .iter()
            .filter(|h| is_loopback_identity(h))
            .cloned()
            .collect();
        if mine.is_empty() && hosts.is_empty() {
            mine = self.bind_hosts();
        }
        Box::pin(super::serve_tcp("loopback", app, mine, port))
    }

    fn bind_hosts(&self) -> Vec<String> {
        vec!["127.0.0.1".to_string()]
    }

    fn reach(&self) -> Reach {
        Reach::Local
    }

    fn grants_local_bypass(&self) -> bool {
        true
    }

    /// A loopback peer is authorized; anything off the machine is not. Gate 0
    /// admits loopback before this is ever asked, but the port answers the
    /// question the same way whoever asks it.
    fn authorizes(&self, peer: &Peer, _ctx: Gate1<'_>) -> bool {
        is_loopback_identity(&peer.identity)
    }

    /// An IP is asserted by whoever sent the packet, so a loopback claim
    /// binds nothing: that is exactly the shipped flow.
    fn bindable_identity(&self, _peer: &Peer) -> Option<String> {
        None
    }

    fn diagnostics(&self, scope: Scope) -> Value {
        match scope {
            Scope::Public => public_diagnostics(self.name(), true),
            Scope::Full => json!({
                "name": self.name(),
                "available": true,
                "advertise_host": Value::Null,
                "bind_host": "127.0.0.1",
            }),
        }
    }
}
