//! The shared TCP listener loop, and the one place a socket address becomes a
//! `Peer` stamp.
//!
//! Both socket transports serve through this. Each passes its own name, so
//! the stamp on a request names the transport whose listener accepted it, and
//! after this layer the address fact travels one way: `Peer` is the only
//! thing the gate, the socket handlers and the OAuth routes read.

use super::{Peer, listener_address};
use axum::Router;
use axum::extract::{ConnectInfo, Request};
use axum::middleware::Next;
use axum::response::Response;
use std::net::SocketAddr;

/// Serve `app` on every host in `hosts` at `port`, stamping each request with
/// `Peer { transport: name, identity: <source ip> }`.
///
/// An empty host list is a transport with nothing to bind right now: it
/// serves nothing and never returns, so the other members keep serving and
/// the daemon stays up. A bind failure is an error the caller logs.
pub(crate) async fn serve_tcp(
    name: &'static str,
    app: Router,
    hosts: Vec<String>,
    port: u16,
) -> anyhow::Result<()> {
    if hosts.is_empty() {
        return std::future::pending().await;
    }
    let app = stamped(app, name);
    let mut listeners = Vec::new();
    for host in hosts {
        let addr = listener_address(&host, port)?;
        listeners.push(tokio::net::TcpListener::bind(addr).await?);
        tracing::info!(%addr, transport = name, "vadgr daemon listening");
    }
    futures_util::future::try_join_all(listeners.into_iter().map(|listener| {
        let app = app.clone();
        async move {
            axum::serve(
                listener,
                app.into_make_service_with_connect_info::<SocketAddr>(),
            )
            .await
        }
    }))
    .await?;
    Ok(())
}

/// `app`, stamping every request with `Peer { transport: name }` from its
/// `ConnectInfo`. Public so a test can serve a router exactly the way a
/// listening transport does.
pub fn stamped(app: Router, name: &'static str) -> Router {
    app.layer(axum::middleware::from_fn(
        move |req: Request, next: Next| stamp(name, req, next),
    ))
}

/// The stamp itself. It never synthesises an address: a request with no
/// `ConnectInfo` gets no `Peer`, and the gate refuses it rather than assuming
/// the owner's own terminal.
async fn stamp(name: &'static str, mut req: Request, next: Next) -> Response {
    if let Some(ConnectInfo(addr)) = req.extensions().get::<ConnectInfo<SocketAddr>>() {
        let identity = addr.ip().to_string();
        req.extensions_mut().insert(Peer {
            transport: name,
            identity,
        });
    }
    next.run(req).await
}
