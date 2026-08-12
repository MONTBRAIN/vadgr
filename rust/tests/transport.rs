//! The tailscale adapter, driven through a fake LocalAPI client.
//!
//! The client is injected for exactly this: every branch of availability,
//! addressing and peer authorization asserted with no tailscaled running.
//! Each case is carried from the Python adapter's behaviour, not read back
//! off the Rust implementation.

use serde_json::{Value, json};
use vadgr_daemon::transport::tailscale::{LocalApi, TailscaleTransport};
use vadgr_daemon::transport::{LoopbackTransport, Transport, bind_hosts};

/// A LocalAPI whose answers are the test's to script.
#[derive(Default)]
struct FakeApi {
    status: Option<Value>,
    whois: Option<Value>,
}

impl LocalApi for FakeApi {
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
    TailscaleTransport::new(api)
}

// ------------------------------------------------------------- availability

#[test]
fn no_daemon_means_unavailable() {
    let t = transport(FakeApi::default());
    assert!(!t.is_available());
    assert_eq!(t.advertise_host(), None);
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
    assert!(!t.is_available());
}

#[test]
fn running_but_with_no_address_is_unavailable() {
    // Up and logged in is not enough: a transport with no address of its own
    // has nothing to bind and nothing to advertise.
    let t = transport(FakeApi {
        status: Some(json!({ "BackendState": "Running", "Self": { "TailscaleIPs": [] } })),
        ..Default::default()
    });
    assert!(!t.is_available());
}

#[test]
fn a_missing_backend_state_is_treated_as_running() {
    let t = transport(FakeApi {
        status: Some(json!({ "Self": { "TailscaleIPs": ["100.64.0.1"] } })),
        ..Default::default()
    });
    assert!(t.is_available());
}

// --------------------------------------------------------------- addressing

#[test]
fn bind_host_is_the_nodes_own_address() {
    let t = transport(FakeApi {
        status: running(&["100.64.0.7"], "machine.tail.ts.net."),
        ..Default::default()
    });
    assert_eq!(t.bind_host().unwrap(), "100.64.0.7");
}

#[test]
fn bind_host_refuses_rather_than_falling_back_to_loopback() {
    // Binding an interface the transport did not name is the bug the F2 fix
    // removed; unavailable must be an error the boot hears, not a quiet
    // 127.0.0.1.
    let t = transport(FakeApi::default());
    assert!(t.bind_host().is_err());
}

#[test]
fn the_launcher_adds_loopback_beside_the_transport_address() {
    let t = transport(FakeApi {
        status: running(&["100.64.0.7"], "machine.tail.ts.net."),
        ..Default::default()
    });
    assert_eq!(bind_hosts(&t), vec!["100.64.0.7", "127.0.0.1"]);
}

#[test]
fn an_unavailable_transport_keeps_the_local_cli_address_open() {
    let t = transport(FakeApi::default());
    assert_eq!(bind_hosts(&t), vec!["127.0.0.1"]);
}

#[test]
fn the_v4_address_is_preferred_and_the_first_is_the_fallback() {
    let t = transport(FakeApi {
        status: running(&["fd7a::1234", "100.64.0.9"], ""),
        ..Default::default()
    });
    assert_eq!(t.bind_host().unwrap(), "100.64.0.9");

    // No v4 at all: the first address stands in, exactly as the Python
    // adapter answers, rather than the transport reporting no address.
    let t = transport(FakeApi {
        status: running(&["fd7a::1234"], ""),
        ..Default::default()
    });
    assert_eq!(t.bind_host().unwrap(), "fd7a::1234");
}

#[test]
fn advertising_prefers_magic_dns_and_drops_the_trailing_dot() {
    let t = transport(FakeApi {
        status: running(&["100.64.0.7"], "machine.tail.ts.net."),
        ..Default::default()
    });
    assert_eq!(t.advertise_host().unwrap(), "machine.tail.ts.net");
}

#[test]
fn advertising_falls_back_to_the_ip_when_dns_is_absent() {
    let t = transport(FakeApi {
        status: running(&["100.64.0.7"], ""),
        ..Default::default()
    });
    assert_eq!(t.advertise_host().unwrap(), "100.64.0.7");
}

// ------------------------------------------------------------------- gate 1

#[test]
fn a_whois_identity_authorizes_the_peer() {
    let t = transport(FakeApi {
        status: running(&["100.64.0.7"], ""),
        whois: Some(json!({ "UserProfile": { "LoginName": "owner@example.com" } })),
    });
    // WhoIs is authoritative even off the CGNAT range (subnet routes).
    assert!(t.is_authorized_source("192.168.1.50"));
}

#[test]
fn without_whois_the_cgnat_range_is_the_fallback() {
    let t = transport(FakeApi {
        status: running(&["100.64.0.7"], ""),
        whois: None,
    });
    assert!(t.is_authorized_source("100.64.0.9"));
    assert!(t.is_authorized_source("100.127.255.254"));
    assert!(!t.is_authorized_source("100.128.0.1"), "past the /10");
    assert!(!t.is_authorized_source("8.8.8.8"));
}

#[test]
fn a_string_that_is_not_an_address_is_refused() {
    let t = transport(FakeApi {
        status: running(&["100.64.0.7"], ""),
        whois: Some(json!({})),
    });
    assert!(!t.is_authorized_source("not-an-ip"));
}

// ------------------------------------------------------------------- status

#[test]
fn the_health_block_carries_the_four_fields_the_phone_reads() {
    let t = transport(FakeApi {
        status: running(&["100.64.0.7"], "machine.tail.ts.net."),
        ..Default::default()
    });
    let s = t.status();
    assert_eq!(s["name"], "tailscale");
    assert_eq!(s["available"], true);
    assert_eq!(s["advertise_host"], "machine.tail.ts.net");
    assert_eq!(s["bind_host"], "100.64.0.7");
}

#[test]
fn the_unavailable_status_block_still_answers() {
    let t = transport(FakeApi::default());
    let s = t.status();
    assert_eq!(s["available"], false);
    assert!(s["advertise_host"].is_null());
    assert!(s["bind_host"].is_null());
}

// ----------------------------------------------------------------- loopback

#[test]
fn loopback_authorizes_only_the_loopback_net() {
    let t = LoopbackTransport;
    assert!(t.is_authorized_source("127.0.0.1"));
    assert!(t.is_authorized_source("127.0.0.53"));
    assert!(!t.is_authorized_source("100.64.0.9"));
    assert!(!t.is_authorized_source("not-an-ip"));
}
