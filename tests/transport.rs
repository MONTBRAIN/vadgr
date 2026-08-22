//! The transport adapters and the registry, driven with no network.
//!
//! The tailscale adapter takes a fake LocalAPI client so every branch of
//! availability, addressing and peer authorization is asserted with no
//! tailscaled running. The registry tests are the rules a fourth transport is
//! held to: they fail the day somebody adds one carelessly rather than the
//! day a user finds it.

use serde_json::{Value, json};
use vadgr_daemon::auth::pairing::PairingStore;
use vadgr_daemon::config::{Config, Paths};
use vadgr_daemon::db::Db;
use vadgr_daemon::transport::{
    Gate1, LoopbackTransport, Peer, Reach, Scope, TailscaleTransport, Transport, Transports,
    listener_address,
};

/// A LocalAPI whose answers are the test's to script.
#[derive(Default)]
struct FakeApi {
    status: Option<Value>,
    whois: Option<Value>,
}

impl vadgr_daemon::transport::tailscale::LocalApi for FakeApi {
    fn status(&self) -> Option<Value> {
        self.status.clone()
    }
    fn whois(&self, _peer_ip: &str) -> Option<Value> {
        self.whois.clone()
    }
}

fn running(ips: &[&str], dns: &str) -> Option<Value> {
    Some(json!({
        "BackendState": "Running",
        "Self": { "TailscaleIPs": ips, "DNSName": dns },
    }))
}

fn transport(api: FakeApi) -> TailscaleTransport<FakeApi> {
    TailscaleTransport::new(api, 8000)
}

fn peer(transport: &'static str, identity: &str) -> Peer {
    Peer {
        transport,
        identity: identity.to_string(),
    }
}

/// A gate-1 context over an empty machine: no bindings, no window.
struct Ctx {
    db: Db,
    pairing: PairingStore,
}

impl Ctx {
    fn new() -> Self {
        Self {
            db: Db::open(":memory:").unwrap(),
            pairing: PairingStore::new(300),
        }
    }
    fn gate(&self) -> Gate1<'_> {
        Gate1 {
            db: &self.db,
            pairing: &self.pairing,
        }
    }
}

// ------------------------------------------------------------- availability

#[test]
fn no_daemon_means_unavailable() {
    let t = transport(FakeApi::default());
    assert!(matches!(t.reach(), Reach::Unavailable(_)));
    assert!(t.bind_hosts().is_empty());
}

#[test]
fn a_backend_that_is_not_running_is_unavailable() {
    let t = transport(FakeApi {
        status: Some(json!({
            "BackendState": "NeedsLogin",
            "Self": { "TailscaleIPs": ["100.64.0.1"] },
        })),
        ..Default::default()
    });
    assert!(matches!(t.reach(), Reach::Unavailable(_)));
}

#[test]
fn running_but_with_no_address_is_unavailable() {
    // Up and logged in is not enough: a transport with no address of its own
    // has nothing to bind and nothing to advertise.
    let t = transport(FakeApi {
        status: Some(json!({ "BackendState": "Running", "Self": { "TailscaleIPs": [] } })),
        ..Default::default()
    });
    assert!(matches!(t.reach(), Reach::Unavailable(_)));
}

#[test]
fn a_missing_backend_state_is_treated_as_running() {
    let t = transport(FakeApi {
        status: Some(json!({ "Self": { "TailscaleIPs": ["100.64.0.1"] } })),
        ..Default::default()
    });
    assert!(matches!(t.reach(), Reach::At(_)));
}

// --------------------------------------------------------------- addressing

#[test]
fn bind_hosts_is_the_nodes_own_address() {
    let t = transport(FakeApi {
        status: running(&["100.64.0.7"], "machine.tail.ts.net."),
        ..Default::default()
    });
    assert_eq!(t.bind_hosts(), vec!["100.64.0.7"]);
}

#[test]
fn a_down_transport_listens_on_nothing_rather_than_erroring() {
    // Binding an interface the transport did not name is the bug the F2 fix
    // removed. The port probe reads this list, so down is an empty answer
    // that leaves the other transports' addresses standing.
    let t = transport(FakeApi::default());
    assert!(t.bind_hosts().is_empty());
}

#[test]
fn the_v4_address_is_preferred_and_the_first_is_the_fallback() {
    let t = transport(FakeApi {
        status: running(&["fd7a::1234", "100.64.0.9"], ""),
        ..Default::default()
    });
    assert_eq!(t.bind_hosts(), vec!["100.64.0.9"]);

    // No v4 at all: the first address stands in, which is the shipped
    // adapter answers, rather than the transport reporting no address.
    let t = transport(FakeApi {
        status: running(&["fd7a::1234"], ""),
        ..Default::default()
    });
    assert_eq!(t.bind_hosts(), vec!["fd7a::1234"]);
}

#[test]
fn invalid_tailscale_addresses_are_ignored() {
    let t = transport(FakeApi {
        status: running(&["not-an-ip", "fd7a::1234"], ""),
        ..Default::default()
    });
    assert_eq!(t.bind_hosts(), vec!["fd7a::1234"]);

    let t = transport(FakeApi {
        status: running(&["not-an-ip"], ""),
        ..Default::default()
    });
    assert!(matches!(t.reach(), Reach::Unavailable(_)));
}

#[test]
fn listener_addresses_support_both_ip_families() {
    assert_eq!(
        listener_address("127.0.0.1", 8100).unwrap().to_string(),
        "127.0.0.1:8100"
    );
    assert_eq!(
        listener_address("fd7a::1234", 8100).unwrap().to_string(),
        "[fd7a::1234]:8100"
    );
    assert!(listener_address("not-an-ip", 8100).is_err());
}

#[test]
fn reach_prefers_magic_dns_and_drops_the_trailing_dot() {
    let t = transport(FakeApi {
        status: running(&["100.64.0.7"], "machine.tail.ts.net."),
        ..Default::default()
    });
    let Reach::At(form) = t.reach() else {
        panic!("a running transport is dialable");
    };
    assert_eq!(form["host"], "machine.tail.ts.net");
    assert_eq!(form["port"], 8000);
}

#[test]
fn reach_falls_back_to_the_ip_when_dns_is_absent() {
    let t = transport(FakeApi {
        status: running(&["100.64.0.7"], ""),
        ..Default::default()
    });
    let Reach::At(form) = t.reach() else {
        panic!("a running transport is dialable");
    };
    assert_eq!(form["host"], "100.64.0.7");
}

/// The deep link flattens every address form into one query string, so the
/// tailscale form's keys are a shipped scanner's contract and no other
/// transport may claim them. The built-in transport's own unit test pins its
/// keys to `node`, `relays` and `direct`; this pins tailscale's half of the
/// disjointness.
#[test]
fn the_tailscale_address_form_carries_exactly_the_shipped_keys() {
    let t = transport(FakeApi {
        status: running(&["100.64.0.7"], "machine.tail.ts.net."),
        ..Default::default()
    });
    let Reach::At(form) = t.reach() else {
        panic!("a running transport is dialable");
    };
    let keys: Vec<&String> = form.as_object().unwrap().keys().collect();
    assert_eq!(keys, ["host", "port"]);
    for iroh_key in ["node", "relays", "direct"] {
        assert!(!form.as_object().unwrap().contains_key(iroh_key));
    }
}

// ------------------------------------------------------------------- gate 1

#[test]
fn a_whois_identity_authorizes_the_peer() {
    let ctx = Ctx::new();
    let t = transport(FakeApi {
        status: running(&["100.64.0.7"], ""),
        whois: Some(json!({ "UserProfile": { "LoginName": "owner@example.com" } })),
    });
    // WhoIs is authoritative even off the CGNAT range (subnet routes).
    assert!(t.authorizes(&peer("tailscale", "192.168.1.50"), ctx.gate()));
}

#[test]
fn without_whois_the_cgnat_range_is_the_fallback() {
    let ctx = Ctx::new();
    let t = transport(FakeApi {
        status: running(&["100.64.0.7"], ""),
        whois: None,
    });
    assert!(t.authorizes(&peer("tailscale", "100.64.0.9"), ctx.gate()));
    assert!(t.authorizes(&peer("tailscale", "100.127.255.254"), ctx.gate()));
    assert!(
        !t.authorizes(&peer("tailscale", "100.128.0.1"), ctx.gate()),
        "past the /10"
    );
    assert!(!t.authorizes(&peer("tailscale", "8.8.8.8"), ctx.gate()));
}

#[test]
fn a_string_that_is_not_an_address_is_refused() {
    let ctx = Ctx::new();
    let t = transport(FakeApi {
        status: running(&["100.64.0.7"], ""),
        whois: Some(json!({})),
    });
    assert!(!t.authorizes(&peer("tailscale", "not-an-ip"), ctx.gate()));
}

// ------------------------------------------------------------- diagnostics

#[test]
fn the_full_health_block_carries_the_four_fields_the_phone_reads() {
    let t = transport(FakeApi {
        status: running(&["100.64.0.7"], "machine.tail.ts.net."),
        ..Default::default()
    });
    let s = t.diagnostics(Scope::Full);
    assert_eq!(s["name"], "tailscale");
    assert_eq!(s["available"], true);
    assert_eq!(s["advertise_host"], "machine.tail.ts.net");
    assert_eq!(s["bind_host"], "100.64.0.7");
}

#[test]
fn the_unavailable_full_block_still_answers_and_carries_its_own_words() {
    let t = transport(FakeApi::default());
    let s = t.diagnostics(Scope::Full);
    assert_eq!(s["available"], false);
    assert!(s["advertise_host"].is_null());
    assert!(s["bind_host"].is_null());
    assert!(s["reason"].as_str().is_some());
}

/// A caller who has proved nothing learns that a transport exists and
/// whether it is up, and nothing about where it is: the machine's tailnet
/// name must not reach an unbound knocker inside a pairing window.
#[test]
fn the_public_block_names_no_address() {
    let t = transport(FakeApi {
        status: running(&["100.64.0.7"], "machine.tail.ts.net."),
        ..Default::default()
    });
    let s = t.diagnostics(Scope::Public);
    let keys: Vec<&String> = s.as_object().unwrap().keys().collect();
    assert_eq!(keys, ["available", "name"]);
}

// ----------------------------------------------------------------- loopback

#[test]
fn loopback_authorizes_only_the_loopback_net() {
    let ctx = Ctx::new();
    let t = LoopbackTransport;
    assert!(t.authorizes(&peer("loopback", "127.0.0.1"), ctx.gate()));
    assert!(t.authorizes(&peer("loopback", "127.0.0.53"), ctx.gate()));
    assert!(t.authorizes(&peer("loopback", "::1"), ctx.gate()));
    assert!(!t.authorizes(&peer("loopback", "100.64.0.9"), ctx.gate()));
    assert!(!t.authorizes(&peer("loopback", "not-an-ip"), ctx.gate()));
}

// ------------------------------------------------------------- the registry
//
// These are the rules a fourth transport is held to. Each is one assertion
// over the registry a real config builds, so it fails the day somebody adds
// a transport carelessly.

fn supported() -> Transports {
    let root = std::env::temp_dir().join(format!("vadgr-transport-test-{}", uuid::Uuid::new_v4()));
    let paths = Paths {
        db: root.join("vadgr.db"),
        runs: root.join("runs"),
        credentials: root.join("credentials"),
        root,
    };
    let config = Config::for_paths(&paths);
    Transports::from_config(&config, 8000, None)
}

fn local_only() -> Transports {
    let root = std::env::temp_dir().join(format!("vadgr-transport-test-{}", uuid::Uuid::new_v4()));
    let paths = Paths {
        db: root.join("vadgr.db"),
        runs: root.join("runs"),
        credentials: root.join("credentials"),
        root,
    };
    let config = Config::from_values(None, Some("loopback".into()), None, &paths).unwrap();
    Transports::from_config(&config, 8000, None)
}

#[test]
fn the_supported_list_is_loopback_iroh_and_tailscale() {
    let names: Vec<&str> = supported().iter().map(|t| t.name()).collect();
    assert_eq!(names, ["loopback", "iroh", "tailscale"]);
}

#[test]
fn the_local_only_override_leaves_the_loopback_transport_alone() {
    let names: Vec<&str> = local_only().iter().map(|t| t.name()).collect();
    assert_eq!(names, ["loopback"]);
}

#[test]
fn exactly_one_registered_transport_grants_the_local_bypass() {
    let bypassing: Vec<&str> = supported()
        .iter()
        .filter(|t| t.grants_local_bypass())
        .map(|t| t.name())
        .collect();
    assert_eq!(bypassing, ["loopback"]);
}

#[test]
fn no_two_transports_share_a_name_or_a_label() {
    let registry = supported();
    let names: Vec<&str> = registry.iter().map(|t| t.name()).collect();
    let labels: Vec<&str> = registry.iter().map(|t| t.label()).collect();
    for list in [&names, &labels] {
        let mut seen = list.clone();
        seen.sort_unstable();
        seen.dedup();
        assert_eq!(seen.len(), list.len(), "{list:?}");
    }
}

#[test]
fn every_registered_transport_is_in_the_health_block() {
    let registry = supported();
    let block = registry.diagnostics(Scope::Public);
    for t in registry.iter() {
        assert!(block.contains_key(t.name()), "{} missing", t.name());
    }
}

/// The report holds only the transports that can carry a phone, and holds
/// every one of them: "supported and not working now" is a `null` member,
/// never an absent key, because the phone acts differently on each.
#[test]
fn the_report_keys_are_the_supported_list_minus_local() {
    let registry = supported();
    let report = registry.report();
    let keys: Vec<&String> = report.keys().collect();
    assert_eq!(keys, ["iroh", "tailscale"]);
    // No endpoint was started in this process, so the built-in transport is
    // supported and not dialable: present, null. The tailscale member's value
    // follows the machine the suite runs on, so only its presence is
    // asserted, one line up.
    assert!(report["iroh"].is_null());
}

#[test]
fn the_local_only_report_is_empty_and_nothing_is_reachable() {
    let registry = local_only();
    assert!(registry.report().is_empty());
    assert!(!registry.any_reachable());
}

#[test]
fn the_probe_bind_hosts_always_include_loopback() {
    assert!(supported().bind_hosts().contains(&"127.0.0.1".to_string()));
    assert_eq!(local_only().bind_hosts(), vec!["127.0.0.1"]);
}

/// The gate refuses a stamp naming a transport this build does not have: the
/// absent case is a wiring defect, and the only safe reading of "I do not
/// know who this is" is a refusal.
#[test]
fn an_unknown_stamp_passes_no_gate() {
    let ctx = Ctx::new();
    let registry = supported();
    let stranger = peer("carrier-nobody-built", "127.0.0.1");
    assert!(registry.of(&stranger).is_none());
    assert!(!registry.grants_local_bypass(&stranger));
    assert!(!registry.authorizes(&stranger, ctx.gate()));
}
