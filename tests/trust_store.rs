//! The machine owes the binary no trust store.
//!
//! A clean install has no `ca-certificates` package, and the CLI talks plain
//! HTTP to loopback, so nothing it does needs one. The product's client
//! construction (`vadgr_daemon::http`) therefore carries its own compiled-in
//! roots and must build wherever the binary runs. It once did not: the default
//! reqwest construction read the system store at build time and panicked on
//! exactly that machine.

use std::time::Duration;

#[test]
fn the_client_builds_where_the_machine_has_no_trust_store() {
    // The overrides rustls-native-certs honors, pointed at nothing: the
    // situation of a machine with no CA bundle. Safe here because this file is
    // its own process and every assertion below wants exactly this state.
    unsafe {
        std::env::set_var("SSL_CERT_FILE", "/nonexistent/certs.pem");
        std::env::set_var("SSL_CERT_DIR", "/nonexistent");
    }

    // The fixture check first, so this test can never rot into decoration: on
    // Linux the default construction (the one the CLI used to call) must
    // refuse this machine state, or the state is not simulating the clean
    // machine and a pass here would prove nothing. Linux only, because the
    // macOS and Windows verifiers read their platform stores, not these
    // variables.
    #[cfg(target_os = "linux")]
    assert!(
        reqwest::Client::builder().build().is_err(),
        "the default reqwest client built without a system trust store, so \
         this fixture no longer reproduces the clean machine"
    );

    // The product's construction carries its own roots and does not care.
    vadgr_daemon::http::client(Duration::from_secs(1))
        .expect("the product's HTTP client must build with no system trust store");
}
