//! The built-in transport: HTTP over QUIC streams, one association per phone.
//!
//! The machine's identity is a public key, a relay is the rendezvous point,
//! and the phone dials the endpoint id the pairing QR carried. Every request
//! served here rides a bidirectional stream on one QUIC association and goes
//! through the **same** router as every socket request: same paths, same
//! statuses, same frames, upgrades included.
//!
//! Who gets a connection at all is this module's own rule, because it is an
//! answer only a transport that proves identities in a handshake can give:
//! a peer whose endpoint id is bound to a paired device, always; an unbound
//! peer, while a pairing code is outstanding or, on a machine with a paired
//! device, to reach transport adoption, into a small number of
//! slots, for at most a minute, and even then the gate serves it only the
//! routes its class earns. The identity is what the TLS 1.3 handshake proved
//! (raw public keys, RFC 7250), so the checks that need the id run after the
//! handshake completes; the pre-handshake refusal covers the machine that
//! could admit nobody: no window, no bound peer, and no device rows at all.

use super::{Gate1, Peer, Reach, Scope, Transport, TransportRuntime, public_diagnostics};
use crate::auth::pairing::WindowId;
use crate::config::RelayChoice;
use axum::Router;
use futures_util::future::BoxFuture;
use iroh::endpoint::presets;
use iroh::{Endpoint, RelayMode, SecretKey};
use serde_json::{Value, json};
use std::net::SocketAddr;
use std::path::{Path, PathBuf};
use std::sync::atomic::{AtomicU64, AtomicUsize, Ordering};
use std::sync::{Arc, Mutex, OnceLock, RwLock};
use std::time::Duration;
use tokio::task::JoinSet;

/// The key file below the credentials directory. The identity must be stable:
/// a new key is a new machine as far as every paired phone is concerned, so
/// the file is never regenerated while it exists.
pub const SECRET_KEY_FILE: &str = "iroh_secret_key";

/// One protocol on the wire: HTTP/1.1 per stream.
const ALPN: &[u8] = b"vadgr/http/1";

/// At most this many concurrent connections from unbound endpoint ids. At the
/// cap a new one is refused and **no existing one is dropped to make room**:
/// evicting would let anyone holding the endpoint id push the owner's
/// in-progress pairing out, turning a limit meant to protect pairing into a
/// tool for stopping it.
pub(crate) const MAX_UNBOUND: usize = 4;

/// The adoption slots, a separate partition with the same shape: refusal at
/// the cap, never eviction. Adopt admissions counting against the pairing
/// slots would let anyone holding the endpoint id starve the owner's open
/// window from a machine that has ever paired, so the two classes never
/// share a count.
pub(crate) const MAX_ADOPTING: usize = 4;

/// Bound peers have their own, generous limit, so a paired phone that
/// reconnects across a network change is never refused because a stranger is
/// knocking.
pub(crate) const MAX_BOUND: usize = 64;

/// An unbound connection's hard lifetime from accept, independent of the
/// window. A claim is one request over an already-established association,
/// so this is generous for the work, and it stops a silent knocker holding a
/// slot for a whole five-minute window.
pub(crate) const UNBOUND_LIFETIME: Duration = Duration::from_secs(60);

/// Application close codes, so a dialer that reads them can tell the cases
/// apart. They are this transport's own vocabulary, not HTTP's.
const CLOSE_WINDOW_ENDED: u32 = 4001;
const CLOSE_NOT_AUTHORIZED: u32 = 4002;
const CLOSE_BUSY: u32 = 4003;
const CLOSE_REVOKED: u32 = 4004;

/// The words this transport gives out when it cannot carry a phone, printed
/// by `vadgr pair`, carried in the `503` and in the health block.
const NOT_STARTED: &str = "the endpoint has not started";
const KEY_UNREADABLE: &str = "the endpoint did not start (the secret key file could not be read)";
const ENDPOINT_FAILED: &str = "the endpoint did not start";

pub struct IrohTransport {
    shared: Arc<Shared>,
}

struct Shared {
    key_path: PathBuf,
    relays: RelayChoice,
    runtime: Option<TransportRuntime>,
    endpoint: OnceLock<Endpoint>,
    /// Why nothing is served, in this transport's own words. `None` once the
    /// endpoint is up.
    down: RwLock<Option<&'static str>>,
    unbound: Mutex<Vec<UnboundEntry>>,
    bound: AtomicUsize,
}

/// One live connection from an unbound endpoint id, and how it was admitted.
/// Admission is a property of a moment and a connection outlives moments, so
/// the ledger is what lets the reaper close exactly the connections whose
/// moment has passed.
struct UnboundEntry {
    /// Distinguishes this connection in the ledger; ids and windows can both
    /// repeat across reconnects.
    seq: u64,
    id: String,
    admission: UnboundAdmission,
    conn: iroh::endpoint::Connection,
}

static ENTRY_SEQ: AtomicU64 = AtomicU64::new(0);

impl IrohTransport {
    pub fn new(key_path: PathBuf, relays: RelayChoice, runtime: Option<TransportRuntime>) -> Self {
        Self {
            shared: Arc::new(Shared {
                key_path,
                relays,
                runtime,
                endpoint: OnceLock::new(),
                down: RwLock::new(Some(NOT_STARTED)),
                unbound: Mutex::new(Vec::new()),
                bound: AtomicUsize::new(0),
            }),
        }
    }
}

impl Transport for IrohTransport {
    fn name(&self) -> &'static str {
        "iroh"
    }

    fn label(&self) -> &'static str {
        "Built-in"
    }

    /// The endpoint binds its own UDP socket and takes no part in the
    /// daemon's TCP port, which is why `bind_hosts` is empty and the port
    /// probe never sees this transport. `hosts` and `port` are the daemon's
    /// socket concerns and are ignored here.
    fn serve(
        &self,
        app: Router,
        _port: u16,
        _hosts: &[String],
    ) -> BoxFuture<'static, anyhow::Result<()>> {
        let shared = self.shared.clone();
        Box::pin(async move { shared.run(app).await })
    }

    fn bind_hosts(&self) -> Vec<String> {
        Vec::new()
    }

    fn reach(&self) -> Reach {
        if let Some(reason) = *self.shared.down.read().expect("down lock poisoned") {
            return Reach::Unavailable(reason);
        }
        let Some(endpoint) = self.shared.endpoint.get() else {
            return Reach::Unavailable(NOT_STARTED);
        };
        let addr = endpoint.addr();
        Reach::At(address_form(
            endpoint.id().to_string(),
            self.shared.relay_urls(),
            select_direct(&addr.ip_addrs().copied().collect::<Vec<_>>()),
        ))
    }

    fn grants_local_bypass(&self) -> bool {
        false
    }

    /// Gate 1: the handshake-proven endpoint id must be bound to a paired
    /// device on this machine. Unbound ids never pass here; the two routes
    /// they may answer during a window skip the gates entirely.
    fn authorizes(&self, peer: &Peer, ctx: Gate1<'_>) -> bool {
        crate::db::devices::peer_device(ctx.db, "iroh", &peer.identity)
            .ok()
            .flatten()
            .is_some()
    }

    /// The one transport that proves an identity, so the one whose claims
    /// bind one: the stamp carries the id the handshake proved.
    fn bindable_identity(&self, peer: &Peer) -> Option<String> {
        Some(peer.identity.clone())
    }

    fn diagnostics(&self, scope: Scope) -> Value {
        let down = *self.shared.down.read().expect("down lock poisoned");
        let available = down.is_none() && self.shared.endpoint.get().is_some();
        match scope {
            Scope::Public => public_diagnostics(self.name(), available),
            Scope::Full => {
                let mut block = json!({
                    "name": self.name(),
                    "available": available,
                });
                if let Some(endpoint) = self.shared.endpoint.get() {
                    let addr = endpoint.addr();
                    block["node"] = json!(endpoint.id().to_string());
                    block["relays"] = json!(self.shared.relay_urls());
                    block["direct"] =
                        json!(select_direct(&addr.ip_addrs().copied().collect::<Vec<_>>()));
                }
                if let Some(reason) = down {
                    block["reason"] = json!(reason);
                }
                block
            }
        }
    }
}

impl Shared {
    /// The relay list a phone should know: what the endpoint reports once it
    /// is up, the configured choice before then.
    fn relay_urls(&self) -> Vec<String> {
        if let Some(endpoint) = self.endpoint.get() {
            let from_addr: Vec<String> = endpoint
                .addr()
                .relay_urls()
                .map(ToString::to_string)
                .collect();
            if !from_addr.is_empty() {
                return from_addr;
            }
        }
        match &self.relays {
            RelayChoice::Custom(urls) => urls.clone(),
            RelayChoice::Disabled => Vec::new(),
            RelayChoice::Default => RelayMode::Default
                .relay_map()
                .urls::<Vec<_>>()
                .iter()
                .map(ToString::to_string)
                .collect(),
        }
    }

    async fn run(self: Arc<Self>, app: Router) -> anyhow::Result<()> {
        let Some(runtime) = self.runtime.clone() else {
            anyhow::bail!(
                "the built-in transport was built without its runtime; only the daemon serves it"
            );
        };
        let key = match load_or_create_key(&self.key_path) {
            Ok(key) => key,
            Err(error) => {
                *self.down.write().expect("down lock poisoned") = Some(KEY_UNREADABLE);
                return Err(error.context(format!(
                    "reading the endpoint secret key at {}",
                    self.key_path.display()
                )));
            }
        };
        let relay_mode = relay_mode(&self.relays)?;
        let endpoint = match Endpoint::builder(presets::N0)
            .secret_key(key)
            .alpns(vec![ALPN.to_vec()])
            .relay_mode(relay_mode)
            .bind()
            .await
        {
            Ok(endpoint) => endpoint,
            Err(error) => {
                *self.down.write().expect("down lock poisoned") = Some(ENDPOINT_FAILED);
                return Err(anyhow::Error::new(error).context("binding the iroh endpoint"));
            }
        };
        tracing::info!(
            node = %endpoint.id(),
            relays = ?self.relay_urls(),
            direct = ?select_direct(&endpoint.addr().ip_addrs().copied().collect::<Vec<_>>()),
            "built-in transport up"
        );
        self.endpoint
            .set(endpoint.clone())
            .map_err(|_| anyhow::anyhow!("the built-in transport was served twice"))?;
        *self.down.write().expect("down lock poisoned") = None;

        tokio::spawn(reaper(self.clone(), runtime.clone()));

        while let Some(incoming) = endpoint.accept().await {
            // QUIC address validation first: an unvalidated address is
            // answered with a retry, which costs one packet and makes the
            // peer prove it can receive at the address it claimed. A retried
            // attempt occupies no slot.
            if !incoming.remote_addr_validated() {
                if let Err(error) = incoming.retry() {
                    tracing::debug!(%error, "retry on an already-validated incoming");
                }
                continue;
            }
            // The identity is proven by the handshake, so identity checks run
            // after it. What can be refused before it is the machine that
            // could admit nobody: no pairing window open, no endpoint id
            // bound to any device, and no device rows at all. On that machine
            // the handshake never completes, which is the out-of-the-box
            // posture. A machine that has paired anything completes the
            // handshake instead and refuses at the route, which is what makes
            // transport adoption reachable.
            if refuse_before_handshake(
                runtime.pairing.window().is_some(),
                crate::db::devices::any_peer_bound(&runtime.db, "iroh").unwrap_or(false),
                crate::db::devices::any_devices(&runtime.db).unwrap_or(false),
            ) {
                incoming.refuse();
                continue;
            }
            let accepting = match incoming.accept() {
                Ok(accepting) => accepting,
                Err(error) => {
                    tracing::debug!(%error, "incoming connection failed to accept");
                    continue;
                }
            };
            tokio::spawn(connection(
                self.clone(),
                runtime.clone(),
                app.clone(),
                accepting,
            ));
        }
        Ok(())
    }
}

/// Closes every unbound connection whose admitting window has ended, keeping
/// any whose identity is now bound: that connection belongs to the phone that
/// just paired, and dropping it a millisecond after its `200` would be the
/// release's first bug. Woken on every window transition, and by a timer at
/// the outstanding code's deadline, because expiry is evaluated lazily in the
/// store and an expiring window must close connections at the expiry.
async fn reaper(shared: Arc<Shared>, runtime: TransportRuntime) {
    let mut transitions = runtime.pairing.subscribe();
    loop {
        let deadline = runtime
            .pairing
            .window()
            .map(|(_, deadline)| tokio::time::Instant::from_std(deadline));
        tokio::select! {
            changed = transitions.changed() => {
                if changed.is_err() {
                    return;
                }
            }
            _ = async {
                match deadline {
                    Some(instant) => tokio::time::sleep_until(instant).await,
                    None => std::future::pending().await,
                }
            } => {}
        }
        let live = runtime.pairing.window().map(|(id, _)| id);
        let mut ledger = shared.unbound.lock().expect("unbound lock poisoned");
        ledger.retain(|entry| {
            let bound_now = is_bound(&runtime.db, &entry.id);
            if unbound_conn_lives(entry.admission, live, bound_now) {
                return true;
            }
            tracing::info!(
                peer = %entry.id,
                admission = ?entry.admission,
                "unbound connection closed: the window that admitted it ended"
            );
            entry
                .conn
                .close(CLOSE_WINDOW_ENDED.into(), b"pairing window ended");
            false
        });
    }
}

async fn connection(
    shared: Arc<Shared>,
    runtime: TransportRuntime,
    app: Router,
    accepting: iroh::endpoint::Accepting,
) {
    let conn = match accepting.await {
        Ok(conn) => conn,
        Err(error) => {
            tracing::debug!(%error, "incoming connection failed its handshake");
            return;
        }
    };
    let id = conn.remote_id().to_string();
    let bound = is_bound(&runtime.db, &id);
    let live = runtime.pairing.window().map(|(window, _)| window);
    let any_devices = crate::db::devices::any_devices(&runtime.db).unwrap_or(false);
    let (window_count, adopting_count) = {
        let ledger = shared.unbound.lock().expect("unbound lock poisoned");
        let windowed = ledger
            .iter()
            .filter(|e| matches!(e.admission, UnboundAdmission::Window(_)))
            .count();
        (windowed, ledger.len() - windowed)
    };
    let bound_count = shared.bound.load(Ordering::SeqCst);
    match admit(
        bound,
        live,
        any_devices,
        window_count,
        adopting_count,
        bound_count,
    ) {
        Admit::Bound => {
            shared.bound.fetch_add(1, Ordering::SeqCst);
            // Revocation cuts the network path, not only the token: the
            // moment this device's row goes, no new stream is accepted. The
            // streams already being served drain before the connection is
            // closed, because one of them may carry the successful revoke
            // response itself. Live run streams receive the same signal and
            // close through their own device watch while the drain happens.
            let device = crate::db::devices::peer_device(&runtime.db, "iroh", &id)
                .ok()
                .flatten();
            let revoked = device.as_deref().map(|d| runtime.ws.watch_device(d));
            if serve_streams(&conn, &runtime, app, &id, None, revoked).await {
                conn.close(CLOSE_REVOKED.into(), b"device revoked");
            }
            shared.bound.fetch_sub(1, Ordering::SeqCst);
        }
        Admit::Unbound(admission) => {
            let seq = ENTRY_SEQ.fetch_add(1, Ordering::SeqCst);
            shared
                .unbound
                .lock()
                .expect("unbound lock poisoned")
                .push(UnboundEntry {
                    seq,
                    id: id.clone(),
                    admission,
                    conn: conn.clone(),
                });
            let lifetime = async {
                tokio::time::sleep(UNBOUND_LIFETIME).await;
                // A connection whose claim or adoption succeeded was promoted
                // and is no longer on the clock.
                if is_bound(&runtime.db, &id) {
                    std::future::pending::<()>().await;
                }
            };
            tokio::select! {
                _ = serve_streams(&conn, &runtime, app, &id, Some(admission), None) => {}
                () = lifetime => {
                    tracing::info!(
                        peer = %id,
                        "unbound connection closed: it reached its lifetime without being claimed"
                    );
                    conn.close(CLOSE_WINDOW_ENDED.into(), b"unbound connection lifetime");
                }
            }
            shared
                .unbound
                .lock()
                .expect("unbound lock poisoned")
                .retain(|entry| entry.seq != seq);
        }
        Admit::RefuseOutsideWindow => {
            conn.close(CLOSE_NOT_AUTHORIZED.into(), b"not an authorized peer");
        }
        Admit::RefuseUnboundCap => {
            // Each refusal is logged with the peer id: the residual here is
            // denial of pairing by someone who already holds the endpoint id,
            // and the owner's recovery is a new mint or the other transport.
            tracing::warn!(peer = %id, "unbound connection refused: the pairing slots are full");
            conn.close(CLOSE_BUSY.into(), b"pairing slots are full");
        }
        Admit::RefuseAdoptCap => {
            tracing::warn!(peer = %id, "unbound connection refused: the adoption slots are full");
            conn.close(CLOSE_BUSY.into(), b"adoption slots are full");
        }
        Admit::RefuseBoundCap => {
            tracing::warn!(peer = %id, "bound connection refused: the connection cap is reached");
            conn.close(CLOSE_BUSY.into(), b"connection cap reached");
        }
    }
}

/// One HTTP/1.1 connection per accepted stream, over the same router as every
/// socket request, upgrades enabled so the run WebSocket rides a stream like
/// any request. Every request is stamped with this transport's own `Peer` and
/// **never** a socket address: a fabricated loopback address would hand a
/// remote peer the OAuth routes and the tokenless CLI socket in one move.
async fn serve_streams(
    conn: &iroh::endpoint::Connection,
    runtime: &TransportRuntime,
    app: Router,
    id: &str,
    admitted: Option<UnboundAdmission>,
    mut revoked: Option<tokio::sync::broadcast::Receiver<()>>,
) -> bool {
    let mut active = JoinSet::new();
    let was_revoked = loop {
        let accepted = tokio::select! {
            pair = conn.accept_bi() => Some(pair),
            _ = wait_for_revocation(&mut revoked) => break true,
            _ = active.join_next(), if !active.is_empty() => None,
        };
        let Some(accepted) = accepted else {
            continue;
        };
        let (send, recv) = match accepted {
            Ok(pair) => pair,
            Err(_) => break false,
        };
        // The close is the timely path and this re-check is the correct one:
        // a stream on a connection whose window has ended is dropped with no
        // HTTP response, even if the close raced.
        let bound_now = is_bound(&runtime.db, id);
        let live = runtime.pairing.window().map(|(window, _)| window);
        if !stream_may_serve(bound_now, admitted, live) {
            drop((send, recv));
            continue;
        }
        let peer = Peer {
            transport: "iroh",
            identity: id.to_string(),
        };
        let app = app.clone().layer(axum::Extension(peer));
        active.spawn(async move {
            let io = hyper_util::rt::TokioIo::new(tokio::io::join(recv, send));
            let service = hyper_util::service::TowerToHyperService::new(app);
            if let Err(error) = hyper::server::conn::http1::Builder::new()
                .serve_connection(io, service)
                .with_upgrades()
                .await
            {
                // Routine at the end of a stream: a client that read its
                // response and dropped its read half leaves hyper unable to
                // finish flushing, which is not a fault.
                tracing::debug!(%error, "stream-served connection ended");
            }
        });
    };
    drain_active_streams(&mut active).await;
    was_revoked
}

async fn wait_for_revocation(revoked: &mut Option<tokio::sync::broadcast::Receiver<()>>) {
    match revoked {
        Some(watch) => {
            let _ = watch.recv().await;
        }
        None => std::future::pending().await,
    }
}

async fn drain_active_streams(active: &mut JoinSet<()>) {
    while active.join_next().await.is_some() {}
}

// --------------------------------------------------------------- the policy
//
// Pure, so the admission matrix is a unit test with no endpoint and no
// network. The functions above are wiring; these are the rule.

/// Why a connection from an unbound endpoint id was admitted. The two
/// classes share the machinery (a small cap, refusal at it, the 60 second
/// lifetime, promotion once the identity is bound) and nothing else: their
/// caps are separate partitions, and only the window class dies with a
/// window.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub(crate) enum UnboundAdmission {
    /// Under a live pairing window, to reach the claim.
    Window(WindowId),
    /// On a machine with at least one paired device, to reach
    /// `POST /api/devices/self/transports`. The gate still refuses
    /// everything a valid token does not earn.
    Adoption,
}

#[derive(Debug, PartialEq, Eq)]
pub(crate) enum Admit {
    Bound,
    Unbound(UnboundAdmission),
    /// No live pairing window and no paired device: an unbound id gets no
    /// connection at all.
    RefuseOutsideWindow,
    /// The pairing slots are full. The new connection is refused and no
    /// existing one is evicted.
    RefuseUnboundCap,
    /// The adoption slots are full: the same refusal-not-eviction rule, in
    /// its own partition so adopt admissions never starve a pairing window.
    RefuseAdoptCap,
    RefuseBoundCap,
}

pub(crate) fn admit(
    bound: bool,
    live_window: Option<WindowId>,
    any_devices: bool,
    window_count: usize,
    adopting_count: usize,
    bound_count: usize,
) -> Admit {
    if bound {
        if bound_count >= MAX_BOUND {
            return Admit::RefuseBoundCap;
        }
        return Admit::Bound;
    }
    match live_window {
        Some(_) if window_count >= MAX_UNBOUND => Admit::RefuseUnboundCap,
        Some(window) => Admit::Unbound(UnboundAdmission::Window(window)),
        // No window, but this machine has paired: the handshake completes so
        // adoption is reachable, and the refusal of everything else moves to
        // the route.
        None if any_devices && adopting_count >= MAX_ADOPTING => Admit::RefuseAdoptCap,
        None if any_devices => Admit::Unbound(UnboundAdmission::Adoption),
        None => Admit::RefuseOutsideWindow,
    }
}

/// Whether the accept loop refuses an incoming attempt before its handshake.
/// True only on the machine that could admit nobody: no pairing window open,
/// no endpoint id bound to any device, and no device rows at all. The third
/// clause is transport adoption's: a machine that has ever paired completes
/// the handshake
/// and refuses at the route instead, and a machine that never has keeps the
/// out-of-the-box posture byte for byte.
pub(crate) fn refuse_before_handshake(
    window_open: bool,
    any_peer_bound: bool,
    any_devices: bool,
) -> bool {
    !window_open && !any_peer_bound && !any_devices
}

/// Whether an unbound connection survives the window transitioning to
/// `live`. A promoted connection (its identity is now bound) is kept: it
/// belongs to the phone that just paired or adopted. A **new** mint does not
/// rescue an old window connection: a fresh window is a fresh admission, and
/// the peer may dial again. An adoption connection was never a window's, so
/// no transition closes it; its bound is the 60 second lifetime.
pub(crate) fn unbound_conn_lives(
    admission: UnboundAdmission,
    live: Option<WindowId>,
    bound_now: bool,
) -> bool {
    bound_now
        || match admission {
            UnboundAdmission::Window(admitted) => live == Some(admitted),
            UnboundAdmission::Adoption => true,
        }
}

/// Whether one accepted stream is served. `admitted` is `None` for a
/// connection admitted as bound; such a connection keeps serving only while
/// the binding stands, so a revoked device's streams die here as well as at
/// the close. An adoption connection serves until its close: what each
/// stream's request earns is the gate's question, and the connection itself
/// is on the 60 second clock.
pub(crate) fn stream_may_serve(
    bound_now: bool,
    admitted: Option<UnboundAdmission>,
    live: Option<WindowId>,
) -> bool {
    if bound_now {
        return true;
    }
    match admitted {
        Some(UnboundAdmission::Window(window)) => live == Some(window),
        Some(UnboundAdmission::Adoption) => true,
        None => false,
    }
}

// ------------------------------------------------------------ the identity

/// The built-in transport's address form. Its keys are this transport's
/// alone: the pairing deep link flattens every form into one query string,
/// so a key shared with another transport would collide there.
fn address_form(node: String, relays: Vec<String>, direct: Vec<String>) -> Value {
    json!({ "node": node, "relays": relays, "direct": direct })
}

fn is_bound(db: &crate::db::Db, id: &str) -> bool {
    crate::db::devices::peer_device(db, "iroh", id)
        .ok()
        .flatten()
        .is_some()
}

fn relay_mode(choice: &RelayChoice) -> anyhow::Result<RelayMode> {
    Ok(match choice {
        RelayChoice::Default => RelayMode::Default,
        RelayChoice::Disabled => RelayMode::Disabled,
        RelayChoice::Custom(urls) => {
            let mut parsed = Vec::new();
            for url in urls {
                parsed.push(url.parse().map_err(|error| {
                    anyhow::anyhow!("VADGR_IROH_RELAYS carries {url:?}: {error}")
                })?);
            }
            RelayMode::custom(parsed)
        }
    })
}

/// Load the endpoint's secret key, or create it exactly once with the same
/// owner-only protection every credential file gets. An unreadable or
/// malformed file fails the transport loudly rather than minting a fresh
/// identity: a new key is a new machine to every paired phone.
fn load_or_create_key(path: &Path) -> anyhow::Result<SecretKey> {
    use crate::engine::provider::credentials::{
        create_secret_directory, create_secret_file, validate_secret_file,
    };
    if std::fs::symlink_metadata(path).is_ok() {
        validate_secret_file(path)?;
        let raw = std::fs::read_to_string(path)?;
        let bytes = decode_hex_key(raw.trim())
            .ok_or_else(|| anyhow::anyhow!("the secret key file is not 64 hex characters"))?;
        return Ok(SecretKey::from_bytes(&bytes));
    }
    if let Some(parent) = path.parent() {
        create_secret_directory(parent)?;
    }
    let key = SecretKey::generate();
    use std::io::Write;
    let mut file = create_secret_file(path)?;
    file.write_all(encode_hex_key(&key.to_bytes()).as_bytes())?;
    file.write_all(b"\n")?;
    Ok(key)
}

fn encode_hex_key(bytes: &[u8; 32]) -> String {
    bytes.iter().map(|b| format!("{b:02x}")).collect()
}

fn decode_hex_key(text: &str) -> Option<[u8; 32]> {
    if text.len() != 64 || !text.chars().all(|c| c.is_ascii_hexdigit()) {
        return None;
    }
    let mut bytes = [0u8; 32];
    for (i, chunk) in text.as_bytes().chunks(2).enumerate() {
        let pair = std::str::from_utf8(chunk).ok()?;
        bytes[i] = u8::from_str_radix(pair, 16).ok()?;
    }
    Some(bytes)
}

/// The direct addresses the pairing payload carries, capped at four: the QR
/// must stay scannable off a terminal, and the health block refreshes the
/// full set after pairing anyway. Prefer the LAN IPv4 and a global IPv6,
/// which are the two a phone on the same network or the open internet can
/// actually use.
pub(crate) fn select_direct(addrs: &[SocketAddr]) -> Vec<String> {
    let usable = |addr: &SocketAddr| !addr.ip().is_loopback() && !addr.ip().is_unspecified();
    let lan_v4 = |addr: &SocketAddr| match addr.ip() {
        std::net::IpAddr::V4(v4) => v4.is_private(),
        std::net::IpAddr::V6(_) => false,
    };
    let global_v6 = |addr: &SocketAddr| match addr.ip() {
        std::net::IpAddr::V4(_) => false,
        std::net::IpAddr::V6(v6) => {
            let first = v6.segments()[0];
            // Not link-local (fe80::/10) and not unique-local (fc00::/7).
            (first & 0xffc0) != 0xfe80 && (first & 0xfe00) != 0xfc00 && !v6.is_loopback()
        }
    };
    let mut picked: Vec<SocketAddr> = Vec::new();
    let mut push = |addr: &SocketAddr| {
        if picked.len() < 4 && !picked.contains(addr) {
            picked.push(*addr);
        }
    };
    if let Some(addr) = addrs.iter().filter(|a| usable(a)).find(|a| lan_v4(a)) {
        push(addr);
    }
    if let Some(addr) = addrs.iter().filter(|a| usable(a)).find(|a| global_v6(a)) {
        push(addr);
    }
    for addr in addrs.iter().filter(|a| usable(a)) {
        push(addr);
    }
    picked.iter().map(ToString::to_string).collect()
}

#[cfg(test)]
mod tests {
    use super::*;

    // ------------------------------------------------------- the admission

    fn window(id: WindowId) -> UnboundAdmission {
        UnboundAdmission::Window(id)
    }

    #[test]
    fn a_bound_id_is_admitted_regardless_of_window() {
        assert_eq!(admit(true, None, false, 0, 0, 0), Admit::Bound);
        assert_eq!(admit(true, Some(7), true, MAX_UNBOUND, 0, 0), Admit::Bound);
    }

    #[test]
    fn an_unbound_id_needs_a_live_window_on_a_machine_with_no_devices() {
        assert_eq!(
            admit(false, None, false, 0, 0, 0),
            Admit::RefuseOutsideWindow
        );
        assert_eq!(
            admit(false, Some(7), false, 0, 0, 0),
            Admit::Unbound(window(7))
        );
    }

    /// Transport adoption's clause: no window and no bound peer, but the machine has
    /// paired a device, so the handshake completes and the refusal of
    /// everything a token does not earn moves to the route. With zero
    /// devices the verdict is exactly what it always was.
    #[test]
    fn an_unbound_id_is_admitted_for_adoption_only_where_a_device_exists() {
        assert_eq!(
            admit(false, None, true, 0, 0, 0),
            Admit::Unbound(UnboundAdmission::Adoption)
        );
        assert_eq!(
            admit(false, None, false, 0, 0, 0),
            Admit::RefuseOutsideWindow
        );
    }

    /// The pre-handshake refusal fires only on the machine that could admit
    /// nobody: X1's fresh installation refuses with no device rows, and one
    /// paired device is enough to let the handshake complete.
    #[test]
    fn the_handshake_is_refused_only_on_a_machine_that_never_paired() {
        assert!(refuse_before_handshake(false, false, false));
        assert!(!refuse_before_handshake(false, false, true));
        assert!(!refuse_before_handshake(false, true, true));
        assert!(!refuse_before_handshake(true, false, false));
    }

    /// The anti-eviction assertion: the fifth concurrent unbound connection
    /// is refused, and nothing says an existing one is dropped, because the
    /// verdict is about the newcomer alone. "Oldest dropped" was the shape
    /// this rule first took and it is itself the attack.
    #[test]
    fn the_fifth_unbound_connection_is_refused_and_no_slot_is_freed() {
        assert_eq!(
            admit(false, Some(7), true, MAX_UNBOUND - 1, 0, 0),
            Admit::Unbound(window(7))
        );
        assert_eq!(
            admit(false, Some(7), true, MAX_UNBOUND, 0, 0),
            Admit::RefuseUnboundCap
        );
    }

    /// The adoption slots are their own partition, refused at their own cap:
    /// full adoption slots never refuse a pairing-window admission, which is
    /// B5's property, and full pairing slots never refuse an adoption.
    #[test]
    fn adopt_admissions_cannot_starve_the_pairing_window() {
        // The pairing window admits while every adoption slot is taken.
        assert_eq!(
            admit(false, Some(7), true, 0, MAX_ADOPTING, 0),
            Admit::Unbound(window(7))
        );
        // Adoption admits while every pairing slot is taken.
        assert_eq!(
            admit(false, None, true, MAX_UNBOUND, 0, 0),
            Admit::Unbound(UnboundAdmission::Adoption)
        );
        // And each refuses at its own cap, evicting nothing.
        assert_eq!(
            admit(false, None, true, 0, MAX_ADOPTING, 0),
            Admit::RefuseAdoptCap
        );
        assert_eq!(
            admit(false, Some(7), true, MAX_UNBOUND, 0, 0),
            Admit::RefuseUnboundCap
        );
    }

    /// A paired phone is never refused because a stranger is knocking: the
    /// caps are independent.
    #[test]
    fn a_bound_peer_is_admitted_while_the_unbound_cap_is_full() {
        assert_eq!(admit(true, Some(7), true, MAX_UNBOUND, 0, 0), Admit::Bound);
        assert_eq!(
            admit(true, None, true, 0, 0, MAX_BOUND),
            Admit::RefuseBoundCap
        );
    }

    // ------------------------------------------- the window and the streams

    #[test]
    fn an_unbound_connection_dies_with_the_window_that_admitted_it() {
        // Redeem, burn or expiry: the window is gone.
        assert!(!unbound_conn_lives(window(7), None, false));
        // A new mint is a fresh admission and does not rescue the old one.
        assert!(!unbound_conn_lives(window(7), Some(8), false));
        // The window that admitted it still stands.
        assert!(unbound_conn_lives(window(7), Some(7), false));
    }

    /// An adoption connection was never a window's, so no window transition
    /// closes it: its bound is the 60 second lifetime, and its promotion is
    /// the binding the route writes.
    #[test]
    fn an_adoption_connection_survives_window_transitions_unbound() {
        assert!(unbound_conn_lives(UnboundAdmission::Adoption, None, false));
        assert!(unbound_conn_lives(
            UnboundAdmission::Adoption,
            Some(8),
            false
        ));
        assert!(unbound_conn_lives(UnboundAdmission::Adoption, None, true));
    }

    /// The claimant is promoted, not closed: a connection whose identity is
    /// now bound belongs to the phone that just paired, and dropping it a
    /// millisecond after its 200 would be the release's first bug.
    #[test]
    fn a_promoted_connection_survives_every_window_transition() {
        assert!(unbound_conn_lives(window(7), None, true));
        assert!(unbound_conn_lives(window(7), Some(8), true));
    }

    /// Held-open connections cannot outrun the close: a stream accepted on a
    /// connection whose window has ended is not served even if the close
    /// raced.
    #[test]
    fn a_stream_on_an_ended_window_is_not_served() {
        assert!(!stream_may_serve(false, Some(window(7)), None));
        assert!(!stream_may_serve(false, Some(window(7)), Some(8)));
        assert!(stream_may_serve(false, Some(window(7)), Some(7)));
        assert!(stream_may_serve(true, Some(window(7)), None), "promoted");
    }

    /// An adoption connection's streams are served with no window at all:
    /// the adopt request itself arrives on one, and what it earns is the
    /// gate's question, not this one's.
    #[test]
    fn a_stream_on_an_adoption_connection_is_served_without_a_window() {
        assert!(stream_may_serve(
            false,
            Some(UnboundAdmission::Adoption),
            None
        ));
        assert!(stream_may_serve(
            false,
            Some(UnboundAdmission::Adoption),
            Some(7)
        ));
        assert!(
            stream_may_serve(true, Some(UnboundAdmission::Adoption), None),
            "promoted"
        );
    }

    /// A revoked device's connection stops being served per stream as well as
    /// being closed: the binding is re-read before every stream.
    #[test]
    fn a_bound_connection_whose_binding_is_gone_serves_nothing() {
        assert!(stream_may_serve(true, None, None));
        assert!(!stream_may_serve(false, None, Some(7)));
    }

    /// The request that revokes a device is itself an active stream on the
    /// connection being cut. Closing first loses its successful response and
    /// makes the phone claim the machine still lists it. Draining sends that
    /// response before the transport closes, while the binding check already
    /// refuses every new stream.
    #[tokio::test]
    async fn revocation_drains_the_active_response_before_connection_close() {
        let (response_sent, response_read) = tokio::sync::oneshot::channel();
        let mut active = JoinSet::new();
        active.spawn(async move {
            let _ = response_read.await;
        });

        let drain = tokio::spawn(async move {
            drain_active_streams(&mut active).await;
        });
        tokio::task::yield_now().await;
        assert!(
            !drain.is_finished(),
            "the connection must stay open while the revoke response is active"
        );

        response_sent.send(()).unwrap();
        tokio::time::timeout(Duration::from_secs(1), drain)
            .await
            .expect("the connection closes after its active response drains")
            .expect("the drain task completes");
    }

    // ------------------------------------------------------------- the key

    #[test]
    fn the_key_is_created_once_and_reused_forever() {
        let dir = std::env::temp_dir().join(format!("vadgr-iroh-key-{}", uuid::Uuid::new_v4()));
        let path = dir.join(SECRET_KEY_FILE);
        let first = load_or_create_key(&path).unwrap();
        let second = load_or_create_key(&path).unwrap();
        assert_eq!(first.to_bytes(), second.to_bytes());
        #[cfg(unix)]
        {
            use std::os::unix::fs::MetadataExt;
            let mode = std::fs::metadata(&path).unwrap().mode() & 0o777;
            assert_eq!(mode, 0o600, "the key is a credential file");
        }
        std::fs::remove_dir_all(&dir).ok();
    }

    /// A malformed key file fails loudly and is never regenerated: a new key
    /// is a new machine as far as every paired phone is concerned.
    #[test]
    fn a_malformed_key_file_is_refused_not_replaced() {
        let dir = std::env::temp_dir().join(format!("vadgr-iroh-key-{}", uuid::Uuid::new_v4()));
        let path = dir.join(SECRET_KEY_FILE);
        load_or_create_key(&path).unwrap();
        std::fs::write(&path, "not a key\n").unwrap();
        #[cfg(unix)]
        {
            use std::os::unix::fs::PermissionsExt;
            std::fs::set_permissions(&path, std::fs::Permissions::from_mode(0o600)).unwrap();
        }
        let refused = load_or_create_key(&path);
        assert!(refused.is_err());
        assert_eq!(
            std::fs::read_to_string(&path).unwrap(),
            "not a key\n",
            "the file is untouched"
        );
        std::fs::remove_dir_all(&dir).ok();
    }

    #[test]
    fn the_hex_round_trip_is_exact() {
        let bytes: [u8; 32] = std::array::from_fn(|i| i as u8 * 7);
        assert_eq!(decode_hex_key(&encode_hex_key(&bytes)), Some(bytes));
        assert_eq!(decode_hex_key("zz"), None);
        assert_eq!(decode_hex_key(&"a".repeat(63)), None);
    }

    // ------------------------------------------------------- the addresses

    #[test]
    fn direct_addresses_prefer_lan_v4_and_a_global_v6_and_cap_at_four() {
        let addrs: Vec<SocketAddr> = [
            "127.0.0.1:8000",
            "[::1]:8000",
            "[fe80::1]:8000",
            "203.0.113.9:8000",
            "198.51.100.4:8000",
            "192.0.2.10:8000",
            "[2001:db8::7]:8000",
            "192.168.1.20:8000",
        ]
        .iter()
        .map(|a| a.parse().unwrap())
        .collect();
        let picked = select_direct(&addrs);
        assert_eq!(picked.len(), 4);
        assert_eq!(picked[0], "192.168.1.20:8000", "the LAN IPv4 first");
        assert_eq!(picked[1], "[2001:db8::7]:8000", "then a global IPv6");
        assert!(!picked.contains(&"127.0.0.1:8000".to_string()));
    }

    /// The address form's keys are half of a registry rule: the deep link
    /// flattens every form into one query string, so no two transports may
    /// share a key. The tailscale suite pins `host` and `port`; this pins
    /// `node`, `relays` and `direct`.
    #[test]
    fn the_iroh_address_form_carries_exactly_its_own_keys() {
        let form = address_form("id".into(), vec![], vec![]);
        let keys: Vec<&String> = form.as_object().unwrap().keys().collect();
        assert_eq!(keys, ["direct", "node", "relays"]);
        for tailscale_key in ["host", "port"] {
            assert!(!form.as_object().unwrap().contains_key(tailscale_key));
        }
    }
}
