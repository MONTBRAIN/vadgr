//! The one way this product builds an HTTPS client.
//!
//! The trust roots are compiled in (`webpki-roots`, Mozilla's list) rather
//! than read from the machine. The judgement, stated so a reader can disagree
//! with it: this binary must run on a normal user's machine, and such a
//! machine owes it no trust store, so the binary carries its own. reqwest's
//! default rustls verifier refuses to construct where the system has no CA
//! bundle, and `vadgr health` once died on exactly that machine with a panic,
//! while talking plain HTTP to loopback and needing no trust at all. Bundled
//! roots also close a split: the WebSocket path already carried webpki roots
//! (`tokio-tungstenite` with `rustls-tls-webpki-roots`), so two halves of one
//! product trusted different authorities.
//!
//! The cost: a corporate TLS-inspecting proxy whose root lives only in the
//! operating system store fails against the providers, where a native-roots
//! build would succeed. Such a user is expected to have the proxy exempt the
//! provider hosts (`api.openai.com`, `generativelanguage.googleapis.com`,
//! `api.anthropic.com`) from interception. An override that loads extra roots
//! is a separate decision nobody has made.

use std::time::Duration;

/// Build a client that verifies TLS against the compiled-in roots.
///
/// Fallible, and every caller turns the error into its own kind: a failure to
/// construct a client must never surface as a panic and a backtrace note.
pub fn client(timeout: Duration) -> Result<reqwest::Client, reqwest::Error> {
    let roots = rustls::RootCertStore::from_iter(webpki_roots::TLS_SERVER_ROOTS.iter().cloned());
    let tls = rustls::ClientConfig::builder()
        .with_root_certificates(roots)
        .with_no_client_auth();
    reqwest::Client::builder()
        .tls_backend_preconfigured(tls)
        .timeout(timeout)
        .build()
}
