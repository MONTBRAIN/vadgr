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

use super::{Gate1, Peer, Reach, Scope, Transport, public_diagnostics};
use axum::Router;
use futures_util::future::BoxFuture;
use serde_json::{Value, json};
use std::path::{Path, PathBuf};

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
    socket_path: PathBuf,
    #[cfg(windows)]
    pipe_path: PathBuf,
    /// macOS only: the LocalAPI reached over loopback TCP instead of a socket.
    ///
    /// The open-source `tailscaled` daemon listens on a unix socket, but the
    /// Tailscale macOS application does not create one at all. Both of its
    /// builds publish a loopback port and a shared secret instead, so a Mac
    /// running Tailscale the ordinary way has a healthy tailnet and no socket
    /// to find. Without this the daemon reports "tailscaled not running or
    /// logged out" while the tailnet is up, and pairing is unreachable.
    #[cfg(target_os = "macos")]
    tcp: Option<MacLocalApi>,
}

/// The loopback endpoint and shared secret the Tailscale macOS app publishes.
#[cfg(target_os = "macos")]
#[derive(Clone)]
pub struct MacLocalApi {
    port: u16,
    token: String,
}

impl TailscaledLocalApi {
    #[cfg(unix)]
    pub fn new(socket_path: impl Into<PathBuf>) -> Self {
        Self {
            socket_path: socket_path.into(),
            #[cfg(target_os = "macos")]
            tcp: mac_local_api(),
        }
    }

    #[cfg(windows)]
    pub fn new(pipe_path: impl Into<PathBuf>) -> Self {
        Self {
            pipe_path: pipe_path.into(),
        }
    }

    /// The native LocalAPI endpoint, with a platform-specific environment
    /// override. macOS and Linux use different standard socket paths.
    pub fn from_env() -> Self {
        #[cfg(unix)]
        {
            Self::new(
                std::env::var_os("VADGR_TAILSCALED_SOCKET")
                    .map(PathBuf::from)
                    .unwrap_or_else(|| default_local_api_endpoint(std::env::consts::OS)),
            )
        }
        #[cfg(windows)]
        {
            Self::new(
                std::env::var_os("VADGR_TAILSCALED_PIPE")
                    .map(PathBuf::from)
                    .unwrap_or_else(|| default_local_api_endpoint(std::env::consts::OS)),
            )
        }
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

            // The socket is the daemon install. When it is absent, macOS may
            // still have a healthy tailnet behind the application's loopback
            // endpoint, so that is tried rather than reporting "logged out".
            if let Ok(mut sock) = UnixStream::connect(&self.socket_path) {
                sock.set_read_timeout(Some(Duration::from_secs(2))).ok()?;
                sock.set_write_timeout(Some(Duration::from_secs(2))).ok()?;
                sock.write_all(req.as_bytes()).ok()?;
                let mut raw = Vec::new();
                sock.read_to_end(&mut raw).ok()?;
                return parse_local_api_response(&raw);
            }
            #[cfg(target_os = "macos")]
            {
                let mac = self.tcp.as_ref()?;
                mac.get(path)
            }
            #[cfg(not(target_os = "macos"))]
            {
                None
            }
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
            parse_local_api_response(&raw)
        }
    }
}

/// Split one LocalAPI HTTP/1.0 response into its JSON body.
///
/// Shared by every transport so the three of them cannot drift on what counts
/// as a successful answer.
fn parse_local_api_response(raw: &[u8]) -> Option<Value> {
    let sep = raw.windows(4).position(|w| w == b"\r\n\r\n")?;
    let (head, body) = raw.split_at(sep);
    let status_line = head.split(|b| *b == b'\r').next()?;
    if !status_line.windows(5).any(|w| w == b" 200 ") {
        return None;
    }
    serde_json::from_slice(&body[4..]).ok()
}

/// Find the loopback LocalAPI the Tailscale macOS application publishes.
///
/// Two builds ship and they advertise themselves differently. The standalone
/// system-extension build writes `/Library/Tailscale/sameuserproof-<port>`
/// and puts the shared secret inside the file. The sandboxed App Store build
/// cannot write there, so it puts both halves in the name of a file in its
/// group container: `sameuserproof-<port>-<token>`. Neither creates a unix
/// socket, which is why looking only for one reports a running tailnet as
/// logged out.
#[cfg(target_os = "macos")]
fn mac_local_api() -> Option<MacLocalApi> {
    if let Some(found) = mac_local_api_from_dir(Path::new("/Library/Tailscale"), true) {
        return Some(found);
    }
    let home = std::env::var_os("HOME")?;
    let containers = Path::new(&home).join("Library").join("Group Containers");
    for entry in std::fs::read_dir(containers).ok()?.flatten() {
        let name = entry.file_name();
        let name = name.to_string_lossy();
        if !name.contains("io.tailscale.ipn.macos") {
            continue;
        }
        if let Some(found) = mac_local_api_from_dir(&entry.path(), false) {
            return Some(found);
        }
    }
    None
}

/// Read one directory's `sameuserproof-*` entry.
///
/// `secret_in_file` picks the build: the standalone one stores the secret as
/// the file's contents, the sandboxed one as the third field of its name.
#[cfg(target_os = "macos")]
fn mac_local_api_from_dir(dir: &Path, secret_in_file: bool) -> Option<MacLocalApi> {
    for entry in std::fs::read_dir(dir).ok()?.flatten() {
        let name = entry.file_name();
        let name = name.to_string_lossy().into_owned();
        let Some(rest) = name.strip_prefix("sameuserproof-") else {
            continue;
        };
        let (port, token) = if secret_in_file {
            let token = std::fs::read_to_string(entry.path()).ok()?;
            (rest.to_owned(), token.trim().to_owned())
        } else {
            let (port, token) = rest.split_once('-')?;
            (port.to_owned(), token.to_owned())
        };
        // A proof file with no secret is not usable, and neither is one whose
        // port does not parse. Skip rather than fail: another entry may serve.
        let Ok(port) = port.parse::<u16>() else {
            continue;
        };
        if token.is_empty() {
            continue;
        }
        return Some(MacLocalApi { port, token });
    }
    None
}

#[cfg(target_os = "macos")]
impl MacLocalApi {
    /// One LocalAPI request over loopback, authenticated with the shared secret.
    ///
    /// The secret goes in an HTTP Basic password with an empty user, which is
    /// the form tailscaled's own clients use.
    fn get(&self, path: &str) -> Option<Value> {
        use base64::Engine as _;
        use std::io::{Read, Write};
        use std::net::TcpStream;
        use std::time::Duration;

        let auth = base64::engine::general_purpose::STANDARD.encode(format!(":{}", self.token));
        let req = format!(
            "GET {path} HTTP/1.0\r\nHost: local-tailscaled.sock\r\n\
             Authorization: Basic {auth}\r\nConnection: close\r\n\r\n"
        );
        let addr = format!("127.0.0.1:{}", self.port);
        let mut sock = TcpStream::connect(&addr).ok()?;
        sock.set_read_timeout(Some(Duration::from_secs(2))).ok()?;
        sock.set_write_timeout(Some(Duration::from_secs(2))).ok()?;
        sock.write_all(req.as_bytes()).ok()?;
        let mut raw = Vec::new();
        sock.read_to_end(&mut raw).ok()?;
        parse_local_api_response(&raw)
    }
}

fn default_local_api_endpoint(os: &str) -> PathBuf {
    match os {
        "windows" => Path::new(r"\\.\pipe")
            .join("ProtectedPrefix")
            .join("Administrators")
            .join("Tailscale")
            .join("tailscaled"),
        "macos" => Path::new("/var").join("run").join("tailscaled.socket"),
        _ => Path::new("/var")
            .join("run")
            .join("tailscale")
            .join("tailscaled.sock"),
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
    /// The daemon's port, carried so the transport's own address form is a
    /// complete dial target: gate 1 here proves membership of a network, and
    /// the phone still needs a socket on it.
    port: u16,
}

impl<A: LocalApi> TailscaleTransport<A> {
    pub fn new(api: A, port: u16) -> Self {
        Self { api, port }
    }

    fn self_ip(&self) -> Option<String> {
        let s = self.api.status()?;
        let ips: Vec<std::net::IpAddr> = s
            .get("Self")?
            .get("TailscaleIPs")?
            .as_array()?
            .iter()
            .filter_map(|value| value.as_str()?.parse().ok())
            .collect();
        ips.iter()
            .find(|ip| ip.is_ipv4())
            .or_else(|| ips.first())
            .map(ToString::to_string)
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

impl<A: LocalApi> TailscaleTransport<A> {
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
        // is treated as running, which is the shipped behaviour.
        match s.get("BackendState") {
            None | Some(Value::Null) => {}
            Some(state) if state.as_str() == Some("Running") => {}
            Some(_) => return false,
        }
        self.self_ip().is_some()
    }
}

/// The words this transport gives out when it is down, in the `503`'s
/// message, `vadgr pair`'s print and the health block alike.
const DOWN: &str = "tailscaled is not running or logged out";

impl<A: LocalApi> Transport for TailscaleTransport<A> {
    fn name(&self) -> &'static str {
        "tailscale"
    }

    fn label(&self) -> &'static str {
        "Tailscale"
    }

    fn serve(
        &self,
        app: Router,
        port: u16,
        hosts: &[String],
    ) -> BoxFuture<'static, anyhow::Result<()>> {
        // The daemon's --host override wins where it names non-loopback
        // addresses, which are the ones this transport's own bind_hosts
        // produced for the port probe. **The F2 fix, kept**: the daemon binds
        // what the transport advertises, never a silent fall back to another
        // interface.
        let mut mine: Vec<String> = hosts
            .iter()
            .filter(|h| !super::loopback::is_loopback_identity(h))
            .cloned()
            .collect();
        if mine.is_empty() && hosts.is_empty() {
            mine = self.bind_hosts();
        }
        Box::pin(super::serve_tcp("tailscale", app, mine, port))
    }

    /// The 100.x address when tailscaled is up, and **empty** when it is not:
    /// a transport that is down listens on nothing rather than failing the
    /// port probe for every other transport.
    fn bind_hosts(&self) -> Vec<String> {
        self.self_ip().into_iter().collect()
    }

    fn reach(&self) -> Reach {
        match self.advertise_host() {
            Some(host) => Reach::At(json!({ "host": host, "port": self.port })),
            None => Reach::Unavailable(DOWN),
        }
    }

    fn grants_local_bypass(&self) -> bool {
        false
    }

    fn authorizes(&self, peer: &Peer, _ctx: Gate1<'_>) -> bool {
        // A string that is not an address is refused before anything is asked
        // about it: garbage never earns a WhoIs roundtrip.
        let Ok(ip) = peer.identity.parse::<std::net::IpAddr>() else {
            return false;
        };
        // Prefer an authoritative WhoIs identity check.
        if self.api.whois(&peer.identity).is_some() {
            return true;
        }
        // Fall back to the CGNAT range when WhoIs is unavailable.
        in_tailnet_cgnat(ip)
    }

    /// An IP is asserted by whoever sent the packet, and an unverified
    /// binding is worse than none: a tailnet claim binds nothing, exactly as
    /// it always has.
    fn bindable_identity(&self, _peer: &Peer) -> Option<String> {
        None
    }

    fn diagnostics(&self, scope: Scope) -> Value {
        let available = self.is_available();
        match scope {
            Scope::Public => public_diagnostics(self.name(), available),
            Scope::Full => {
                let mut block = json!({
                    "name": self.name(),
                    "available": available,
                    "advertise_host": if available { self.advertise_host() } else { None },
                    "bind_host": self.self_ip(),
                });
                if !available {
                    block["reason"] = json!(DOWN);
                }
                block
            }
        }
    }
}

#[cfg(test)]
mod tests {
    use super::default_local_api_endpoint;
    #[cfg(target_os = "macos")]
    use super::mac_local_api_from_dir;
    use super::parse_local_api_response;
    use std::path::Path;

    #[test]
    fn local_api_defaults_match_each_native_tailscale_endpoint() {
        assert_eq!(
            default_local_api_endpoint("linux"),
            Path::new("/var")
                .join("run")
                .join("tailscale")
                .join("tailscaled.sock")
        );
        assert_eq!(
            default_local_api_endpoint("macos"),
            Path::new("/var").join("run").join("tailscaled.socket")
        );
        assert_eq!(
            default_local_api_endpoint("windows"),
            Path::new(r"\\.\pipe")
                .join("ProtectedPrefix")
                .join("Administrators")
                .join("Tailscale")
                .join("tailscaled")
        );
    }

    /// The Tailscale macOS application publishes no unix socket. The standalone
    /// build writes the port in the file name and the secret inside the file.
    #[cfg(target_os = "macos")]
    #[test]
    fn the_standalone_mac_app_is_found_by_its_proof_file() {
        let dir = std::env::temp_dir().join(format!("vadgr-ts-standalone-{}", std::process::id()));
        std::fs::create_dir_all(&dir).unwrap();
        std::fs::write(dir.join("sameuserproof-49161"), "s3cr3t-token\n").unwrap();

        let found = mac_local_api_from_dir(&dir, true).expect("the proof file names an endpoint");

        assert_eq!(found.port, 49161);
        assert_eq!(
            found.token, "s3cr3t-token",
            "the trailing newline is not part of it"
        );
        std::fs::remove_dir_all(&dir).ok();
    }

    /// The sandboxed App Store build cannot write outside its container, so it
    /// carries both halves in the file name instead.
    #[cfg(target_os = "macos")]
    #[test]
    fn the_sandboxed_mac_app_carries_its_secret_in_the_name() {
        let dir = std::env::temp_dir().join(format!("vadgr-ts-sandboxed-{}", std::process::id()));
        std::fs::create_dir_all(&dir).unwrap();
        std::fs::write(dir.join("sameuserproof-52525-abc123"), "").unwrap();

        let found = mac_local_api_from_dir(&dir, false).expect("the name carries the endpoint");

        assert_eq!(found.port, 52525);
        assert_eq!(found.token, "abc123");
        std::fs::remove_dir_all(&dir).ok();
    }

    /// A directory with nothing usable must answer "no endpoint" rather than
    /// panicking or returning a half-built one.
    #[cfg(target_os = "macos")]
    #[test]
    fn an_unusable_proof_is_skipped_rather_than_trusted() {
        let dir = std::env::temp_dir().join(format!("vadgr-ts-unusable-{}", std::process::id()));
        std::fs::create_dir_all(&dir).unwrap();
        std::fs::write(dir.join("sameuserproof-not-a-port"), "tok").unwrap();
        std::fs::write(dir.join("unrelated-file"), "tok").unwrap();
        assert!(mac_local_api_from_dir(&dir, true).is_none());

        // A parseable port with an empty secret is not usable either.
        std::fs::write(dir.join("sameuserproof-51000"), "   \n").unwrap();
        assert!(mac_local_api_from_dir(&dir, true).is_none());
        std::fs::remove_dir_all(&dir).ok();
    }

    /// The response parser is shared by all three transports, so it is asserted
    /// once here rather than three times by hand.
    #[test]
    fn only_a_200_response_yields_a_body() {
        let ok = b"HTTP/1.0 200 OK\r\nContent-Type: application/json\r\n\r\n{\"BackendState\":\"Running\"}";
        assert_eq!(
            parse_local_api_response(ok).unwrap()["BackendState"],
            "Running"
        );
        let denied = b"HTTP/1.0 403 Forbidden\r\n\r\n{\"BackendState\":\"Running\"}";
        assert!(parse_local_api_response(denied).is_none());
    }
}
