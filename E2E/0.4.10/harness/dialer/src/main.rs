//! The built-in-transport dialer: an independent QUIC client of the daemon's
//! iroh endpoint, for the cells sockets.py cannot reach.
//!
//! It reads a JSON job on argv (or stdin), dials the endpoint id over the
//! relays and direct addresses the pairing report gave, opens one
//! bidirectional stream per HTTP request, writes an HTTP/1.1 request over it,
//! and records the status line and body. It records; it never asserts. A cell
//! reads the record and decides.
//!
//! It is not the product: the product's client is the phone. This is the
//! runbook's oracle, an implementation of the wire independent of the server.
//!
//! Usage:
//!   vadgr-iroh-dialer '<job-json>' > record.json
//!   echo '<job-json>' | vadgr-iroh-dialer > record.json
//!
//! Job shape:
//!   {
//!     "node": "<endpoint id hex>",
//!     "relays": ["https://..."],       // optional
//!     "direct": ["192.168.1.20:8000"], // optional
//!     "requests": [                     // one stream each, in order
//!       {"method": "GET", "path": "/api/health"},
//!       {"method": "POST", "path": "/api/auth/claim",
//!        "body": {"pairing_token": "AAAA-AAAA", "device_name": "probe"}}
//!     ],
//!     "connect_timeout_ms": 15000,      // optional
//!     "expect_handshake": true          // optional; false records the
//!                                        //   handshake refusal without a request
//!   }

use anyhow::{Context, Result};
use iroh::endpoint::presets;
use iroh::{Endpoint, EndpointAddr, EndpointId, RelayMode, SecretKey};
use serde::{Deserialize, Serialize};
use std::str::FromStr;
use std::time::Duration;

const ALPN: &[u8] = b"vadgr/http/1";

#[derive(Deserialize)]
struct Job {
    node: String,
    #[serde(default)]
    relays: Vec<String>,
    #[serde(default)]
    direct: Vec<String>,
    #[serde(default)]
    requests: Vec<ReqSpec>,
    #[serde(default = "default_timeout")]
    connect_timeout_ms: u64,
    #[serde(default = "yes")]
    expect_handshake: bool,
    /// A 64-hex-character secret key, so the dialer keeps one identity across
    /// invocations: the phone that claims and the phone that dials afterward
    /// must be the same endpoint id. Omitted means a fresh identity, which is
    /// what the unbound-knocker cells want.
    #[serde(default)]
    secret_key: Option<String>,
}

fn default_timeout() -> u64 {
    15000
}
fn yes() -> bool {
    true
}

#[derive(Deserialize)]
struct ReqSpec {
    method: String,
    path: String,
    #[serde(default)]
    body: Option<serde_json::Value>,
    #[serde(default)]
    token: Option<String>,
}

#[derive(Serialize)]
struct Record {
    node: String,
    handshake: Handshake,
    #[serde(skip_serializing_if = "Option::is_none")]
    error: Option<String>,
    responses: Vec<RespRecord>,
}

#[derive(Serialize, PartialEq)]
enum Handshake {
    Completed,
    Refused,
    NotAttempted,
}

#[derive(Serialize)]
struct RespRecord {
    method: String,
    path: String,
    #[serde(skip_serializing_if = "Option::is_none")]
    status: Option<u16>,
    #[serde(skip_serializing_if = "Option::is_none")]
    error_code: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    body: Option<serde_json::Value>,
    #[serde(skip_serializing_if = "Option::is_none")]
    stream_error: Option<String>,
}

#[tokio::main]
async fn main() -> Result<()> {
    let raw = std::env::args().nth(1).map(Ok).unwrap_or_else(|| {
        use std::io::Read;
        let mut buf = String::new();
        std::io::stdin().read_to_string(&mut buf).map(|_| buf)
    })?;
    let job: Job = serde_json::from_str(raw.trim()).context("parsing the dialer job")?;

    let id = EndpointId::from_str(job.node.trim()).context("the node is not an endpoint id")?;
    let mut addr = EndpointAddr::new(id);
    for relay in &job.relays {
        addr = addr.with_relay_url(relay.parse().context("a relay is not a URL")?);
    }
    for direct in &job.direct {
        addr = addr.with_ip_addr(
            direct
                .parse()
                .context("a direct address is not host:port")?,
        );
    }

    // The dialer names no relays of its own unless the job did: if the report
    // carried a relay we use exactly it, and if it carried only direct
    // addresses we dial relay-free, which is what the same-network cell wants.
    let relay_mode = if job.relays.is_empty() {
        RelayMode::Disabled
    } else {
        RelayMode::Default
    };
    let mut builder = Endpoint::builder(presets::N0)
        .alpns(vec![ALPN.to_vec()])
        .relay_mode(relay_mode);
    if let Some(hex) = &job.secret_key {
        builder = builder.secret_key(parse_secret_key(hex.trim())?);
    }
    let endpoint = builder
        .bind()
        .await
        .context("binding the dialer endpoint")?;

    let connect = endpoint.connect(addr, ALPN);
    let mut record = Record {
        node: job.node.clone(),
        handshake: Handshake::NotAttempted,
        error: None,
        responses: Vec::new(),
    };

    match tokio::time::timeout(Duration::from_millis(job.connect_timeout_ms), connect).await {
        Err(_) => {
            record.handshake = Handshake::Refused;
            record.error = Some("connect timed out: the handshake did not complete".into());
        }
        Ok(Err(error)) => {
            record.handshake = Handshake::Refused;
            record.error = Some(format!("connect refused: {error}"));
        }
        Ok(Ok(conn)) => {
            record.handshake = Handshake::Completed;
            if job.expect_handshake {
                for spec in &job.requests {
                    record.responses.push(one_request(&conn, spec).await);
                }
            }
            conn.close(0u32.into(), b"done");
        }
    }

    // The out-of-the-box cell asks for a refusal and gets one; recording a
    // completed handshake it did not expect is still the honest record.
    println!("{}", serde_json::to_string_pretty(&record)?);
    endpoint.close().await;
    Ok(())
}

async fn one_request(conn: &iroh::endpoint::Connection, spec: &ReqSpec) -> RespRecord {
    let mut rec = RespRecord {
        method: spec.method.clone(),
        path: spec.path.clone(),
        status: None,
        error_code: None,
        body: None,
        stream_error: None,
    };
    match request_over_stream(conn, spec).await {
        Ok((status, body)) => {
            rec.status = Some(status);
            if let Ok(value) = serde_json::from_slice::<serde_json::Value>(&body) {
                rec.error_code = value
                    .get("error")
                    .and_then(|e| e.get("code"))
                    .and_then(|c| c.as_str())
                    .map(str::to_owned);
                rec.body = Some(value);
            }
        }
        Err(error) => rec.stream_error = Some(error.to_string()),
    }
    rec
}

async fn request_over_stream(
    conn: &iroh::endpoint::Connection,
    spec: &ReqSpec,
) -> Result<(u16, Vec<u8>)> {
    let (mut send, mut recv) = conn.open_bi().await.context("opening a stream")?;
    let body = spec
        .body
        .as_ref()
        .map(|b| serde_json::to_vec(b))
        .transpose()?
        .unwrap_or_default();
    let mut head = format!(
        "{} {} HTTP/1.1\r\nHost: vadgr\r\nConnection: close\r\n",
        spec.method, spec.path
    );
    if let Some(token) = &spec.token {
        head.push_str(&format!("Authorization: Bearer {token}\r\n"));
    }
    if spec.body.is_some() {
        head.push_str("Content-Type: application/json\r\n");
        head.push_str(&format!("Content-Length: {}\r\n", body.len()));
    }
    head.push_str("\r\n");
    send.write_all(head.as_bytes()).await?;
    if !body.is_empty() {
        send.write_all(&body).await?;
    }
    // Do not finish the send half here: the daemon knows the request is
    // complete from its method and Content-Length, and finishing races the
    // response on some QUIC stacks. The stream is finished when it drops,
    // after the response is read.

    // Read the response as it arrives rather than waiting for the stream to
    // finish: the daemon serves one HTTP/1.1 message and may hold the stream
    // open, so a header terminator plus the Content-Length body is the end of
    // the response, not the end of the stream. A read budget bounds a peer
    // that never answers.
    let mut raw = Vec::new();
    let mut chunk = [0u8; 8192];
    loop {
        let read = tokio::time::timeout(Duration::from_secs(20), recv.read(&mut chunk))
            .await
            .context("the response read timed out")?;
        match read.context("reading the response")? {
            None | Some(0) => break,
            Some(n) => raw.extend_from_slice(&chunk[..n]),
        }
        if let Some(sep) = raw.windows(4).position(|w| w == b"\r\n\r\n") {
            let want = content_length(&raw[..sep]);
            if raw.len() >= sep + 4 + want {
                raw.truncate(sep + 4 + want);
                break;
            }
        }
    }
    let sep = raw
        .windows(4)
        .position(|w| w == b"\r\n\r\n")
        .with_context(|| {
            format!(
                "no header terminator in the {} response bytes: {:?}",
                raw.len(),
                String::from_utf8_lossy(&raw[..raw.len().min(200)])
            )
        })?;
    let head = &raw[..sep];
    let status_line = head
        .split(|b| *b == b'\r')
        .next()
        .context("no status line")?;
    let status = std::str::from_utf8(status_line)?
        .split_whitespace()
        .nth(1)
        .and_then(|s| s.parse::<u16>().ok())
        .context("no status code")?;
    Ok((status, raw[sep + 4..].to_vec()))
}

/// A 64-hex secret key into an iroh `SecretKey`, so the dialer can keep one
/// identity across invocations.
fn parse_secret_key(hex: &str) -> Result<SecretKey> {
    anyhow::ensure!(
        hex.len() == 64 && hex.chars().all(|c| c.is_ascii_hexdigit()),
        "the secret key must be 64 hex characters"
    );
    let mut bytes = [0u8; 32];
    for (i, chunk) in hex.as_bytes().chunks(2).enumerate() {
        bytes[i] = u8::from_str_radix(std::str::from_utf8(chunk)?, 16)?;
    }
    Ok(SecretKey::from_bytes(&bytes))
}

/// The `Content-Length` of a response, from its header block. Zero when
/// absent, which covers the daemon's empty-body responses.
fn content_length(head: &[u8]) -> usize {
    let text = String::from_utf8_lossy(head);
    for line in text.split("\r\n") {
        if let Some(rest) = line.to_ascii_lowercase().strip_prefix("content-length:") {
            return rest.trim().parse().unwrap_or(0);
        }
    }
    0
}
