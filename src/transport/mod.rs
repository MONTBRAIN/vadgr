//! The transport port: the only abstraction routes and the gate depend on.
//!
//! Every adapter answers the same nine questions the same way, so callers
//! never branch on the concrete type. The tailscale adapter's LocalAPI client
//! is its own port and is injected, which is what keeps the adapter testable
//! without a live tailscaled.
//!
//! The registry below is the one place a transport is named. Adding a
//! transport is one module plus one line in [`Transports::from_config`]; no
//! route, gate, schema or report changes shape when one arrives.

pub mod iroh;
pub mod loopback;
pub mod tailscale;
mod tcp;

pub use iroh::IrohTransport;
pub use loopback::LoopbackTransport;
pub use tailscale::{TailscaleTransport, TailscaledLocalApi};

use crate::auth::pairing::PairingStore;
use crate::config::Config;
use crate::db::Db;
use crate::ws::manager::ConnectionManager;
use axum::Router;
use futures_util::future::BoxFuture;
use serde_json::{Map, Value, json};
use std::net::{IpAddr, SocketAddr};
use std::sync::Arc;

/// Who a request is from, in the vocabulary of the transport that accepted it.
///
/// The identity is a string only its own transport can read: an IP for a
/// socket transport, an endpoint id for the built-in one. Keeping it opaque is
/// what stops a second reader growing a match on transport names, and it is
/// why the gate asks the registry rather than inspecting this.
#[derive(Clone, Debug)]
pub struct Peer {
    /// `Transport::name` of the transport that stamped this. Only a transport
    /// stamps, and each stamps its own, so the field cannot name a transport
    /// the request did not arrive over.
    pub transport: &'static str,
    pub identity: String,
}

/// How a peer reaches a transport. Three answers and no exception, because a
/// caller that has to catch a failure to learn "not right now" is a caller
/// that will forget to.
pub enum Reach {
    /// Never carries a phone, so it is not in the report a phone reads. The
    /// loopback transport, whose address reaches nobody off this machine.
    Local,
    /// Dialable now, in this transport's own address form. The object's keys
    /// are this transport's alone; a unit test over the registry refuses two
    /// transports that claim the same key, because the pairing deep link
    /// flattens every form into one query string.
    At(Value),
    /// Supported, and nothing to hand out right now. The reason is this
    /// transport's own words, printed by `vadgr pair` and carried in the
    /// health block. It is never the phone's words: the app writes its own.
    Unavailable(&'static str),
}

/// The two things a transport may need to answer gate 1, and nothing else.
/// Tailscale reads neither; the built-in transport reads both. Passing the
/// whole `AppState` would hand every future transport the run supervisor.
pub struct Gate1<'a> {
    pub db: &'a Db,
    pub pairing: &'a PairingStore,
}

/// How much of itself a transport tells a caller at `GET /api/health`.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Scope {
    /// Loopback, an authorized peer, or an authenticated device.
    Full,
    /// Everyone else, including an unbound peer inside a pairing window.
    Public,
}

/// What a serving transport needs from the daemon and the CLI's probe does
/// not: the binding table, the pairing window, and the revocation watch.
/// `None` builds a registry that can answer names, labels and bind hosts but
/// refuses to serve, which is exactly what `vadgr start`'s port probe wants.
#[derive(Clone)]
pub struct TransportRuntime {
    pub db: Db,
    pub pairing: Arc<PairingStore>,
    pub ws: Arc<ConnectionManager>,
}

/// One way of reaching this machine.
///
/// Nine questions, each with a caller in this release. A method with no caller
/// is not on this list, and no caller reaches around the trait to ask a
/// transport's name and then branch on it.
pub trait Transport: Send + Sync {
    /// The name this transport is known by on the wire: its key in every
    /// report, the value stored beside a bound peer identity, and the
    /// `transport` value in a peer stamp. Stable once shipped, because a
    /// paired phone stores it.
    fn name(&self) -> &'static str;

    /// What a person is told this transport is called, in the terminal.
    /// Separate from `name` because one is a key and the other is words a
    /// person reads. The phone owns its own mapping; `vadgr pair` uses this
    /// one.
    fn label(&self) -> &'static str;

    /// Carry requests for `app` until the process ends. The transport binds
    /// whatever it binds and stamps every request it accepts with a `Peer` of
    /// its own making. `hosts` is the daemon's `--host` override, empty when
    /// none was given; a transport that binds no address of the daemon's
    /// choosing ignores it, the way the shipped loop provider ignores a
    /// timeout it has no use for.
    fn serve(
        &self,
        app: Router,
        port: u16,
        hosts: &[String],
    ) -> BoxFuture<'static, anyhow::Result<()>>;

    /// The local hosts this transport listens on at the daemon's port. It
    /// feeds the port probe `vadgr start` runs before it spawns anything,
    /// which is why it is a value and never an error: a transport that is
    /// down listens on nothing and says so, rather than failing the probe for
    /// every other transport.
    fn bind_hosts(&self) -> Vec<String>;

    /// How a peer reaches me, in my own address form.
    fn reach(&self) -> Reach;

    /// Gate 0. True only for a transport whose peers are the owner at the
    /// machine: the loopback transport today, a local socket transport later.
    /// A transport that answers true is saying its peers need no token at
    /// all, so the answer is written in the implementation rather than
    /// inferred.
    fn grants_local_bypass(&self) -> bool;

    /// Gate 1, my own question about my own peer. Tailscale asks the tailnet;
    /// the built-in transport asks the binding.
    fn authorizes(&self, peer: &Peer, ctx: Gate1<'_>) -> bool;

    /// What a claim arriving over me may bind to the new device row, and
    /// `None` when I prove nothing about who my peers are. A value rather
    /// than a refusal, so the claim handler has one path.
    fn bindable_identity(&self, peer: &Peer) -> Option<String>;

    /// What I say about myself at `GET /api/health`, at the scope the caller
    /// earned.
    fn diagnostics(&self, scope: Scope) -> Value;
}

/// Every transport this build supports. **The one place a transport is
/// named**, and the second half of "a fourth transport is a module plus a
/// line".
pub struct Transports(Vec<Arc<dyn Transport>>);

impl Transports {
    /// The supported list. `VADGR_TRANSPORT=loopback` is the local-only
    /// override and the only value it takes; `Config` already refused
    /// anything else at boot. `runtime` is `None` for the CLI's probe, which
    /// reads names, labels and bind hosts and never serves.
    pub fn from_config(config: &Config, port: u16, runtime: Option<TransportRuntime>) -> Self {
        let mut members: Vec<Arc<dyn Transport>> = vec![Arc::new(LoopbackTransport)];
        if !config.local_only {
            members.push(Arc::new(IrohTransport::new(
                config.credentials_dir().join(iroh::SECRET_KEY_FILE),
                config.relays.clone(),
                runtime,
            )));
            members.push(Arc::new(TailscaleTransport::new(
                TailscaledLocalApi::from_env(),
                port,
            )));
        }
        Self(members)
    }

    /// A registry the caller assembled, which is how tests drive the gate
    /// with a scripted transport.
    pub fn new(members: Vec<Arc<dyn Transport>>) -> Self {
        Self(members)
    }

    pub fn iter(&self) -> impl Iterator<Item = &Arc<dyn Transport>> {
        self.0.iter()
    }

    /// The transport that stamped a peer. `None` only when a request carries
    /// a stamp naming a transport this build does not have, which is a wiring
    /// defect and is refused rather than assumed.
    pub fn of(&self, peer: &Peer) -> Option<&dyn Transport> {
        self.0
            .iter()
            .find(|t| t.name() == peer.transport)
            .map(AsRef::as_ref)
    }

    /// Gate 0, dispatched to the transport the request arrived over. Absent
    /// or unknown transport: false.
    pub fn grants_local_bypass(&self, peer: &Peer) -> bool {
        self.of(peer).is_some_and(|t| t.grants_local_bypass())
    }

    /// Gate 1, dispatched the same way. Absent or unknown transport: false.
    pub fn authorizes(&self, peer: &Peer, ctx: Gate1<'_>) -> bool {
        self.of(peer).is_some_and(|t| t.authorizes(peer, ctx))
    }

    /// The report a phone reads: one member per transport that can carry a
    /// phone, keyed by wire name, valued with that transport's address form
    /// or `null` when it has none right now. **Adding a transport adds a
    /// member**, and no consumer changes shape.
    pub fn report(&self) -> Map<String, Value> {
        let mut report = Map::new();
        for t in &self.0 {
            match t.reach() {
                Reach::Local => {}
                Reach::At(form) => {
                    report.insert(t.name().to_string(), form);
                }
                Reach::Unavailable(_) => {
                    report.insert(t.name().to_string(), Value::Null);
                }
            }
        }
        report
    }

    /// Is any member of the report dialable right now? `false` is the only
    /// thing that makes `POST /api/auth/pair` answer `503`.
    pub fn any_reachable(&self) -> bool {
        self.0.iter().any(|t| matches!(t.reach(), Reach::At(_)))
    }

    /// One entry per registered transport, this one including the local
    /// ones, at the scope the caller earned.
    pub fn diagnostics(&self, scope: Scope) -> Map<String, Value> {
        let mut all = Map::new();
        for t in &self.0 {
            all.insert(t.name().to_string(), t.diagnostics(scope));
        }
        all
    }

    /// Every local address the members listen on, deduplicated. The port
    /// probe `vadgr start` runs binds exactly this set.
    pub fn bind_hosts(&self) -> Vec<String> {
        let mut hosts = Vec::new();
        for t in &self.0 {
            for host in t.bind_hosts() {
                if !hosts.contains(&host) {
                    hosts.push(host);
                }
            }
        }
        hosts
    }

    /// One clause per transport that is supported and not dialable right now,
    /// in that transport's own words. This is the `503`'s message body when
    /// nothing can reach a phone.
    pub fn unavailable_clauses(&self) -> Vec<String> {
        self.0
            .iter()
            .filter_map(|t| match t.reach() {
                Reach::Unavailable(words) => Some(format!("{}: {words}.", t.label())),
                _ => None,
            })
            .collect()
    }

    /// The person-facing label for a wire name, or the name itself for a
    /// transport this build does not know.
    pub fn label_for<'a>(&self, name: &'a str) -> &'a str
    where
        'static: 'a,
    {
        self.0
            .iter()
            .find(|t| t.name() == name)
            .map(|t| t.label())
            .unwrap_or(name)
    }
}

pub(crate) use tcp::serve_tcp;
pub use tcp::stamped;

/// Diagnostics every transport shares at the public scope: a caller who has
/// proved nothing learns that a transport exists and whether it is up, and
/// nothing about where it is.
pub(crate) fn public_diagnostics(name: &str, available: bool) -> Value {
    json!({ "name": name, "available": available })
}

/// Turn a transport-owned IP and port into a listener address. Constructing a
/// `SocketAddr` instead of concatenating strings keeps IPv6 valid on every OS.
pub fn listener_address(host: &str, port: u16) -> anyhow::Result<SocketAddr> {
    let ip: IpAddr = host
        .parse()
        .map_err(|_| anyhow::anyhow!("transport returned an invalid bind address: {host:?}"))?;
    Ok(SocketAddr::new(ip, port))
}
