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
use std::time::{Duration, Instant};

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
    /// Hold the connection open for this long after the first request list,
    /// then send `after_hold` on the same connection. A cell that asks what
    /// happens to a connection admitted under one window and used after that
    /// window closed needs the connection to outlive the window, and a
    /// request list alone finishes far too fast to straddle it.
    #[serde(default)]
    hold_ms: u64,
    #[serde(default)]
    after_hold: Vec<ReqSpec>,
    /// Run sockets to open on this connection, after the request list. The
    /// deletion sweep re-run compares frame type counts per socket across
    /// transports, and `sockets.py` cannot speak QUIC, so this is the built-in
    /// transport's half of that comparison. The record it produces has the
    /// same shape as `sockets.py`'s so the two can be compared directly.
    #[serde(default)]
    sockets: Vec<SocketSpec>,
}

#[derive(Deserialize)]
struct SocketSpec {
    path: String,
    #[serde(default)]
    token: Option<String>,
    #[serde(default = "default_socket_seconds")]
    seconds: u64,
}

fn default_socket_seconds() -> u64 {
    25
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
    /// The dialer's own endpoint id. A cell that asks what a claim bound needs
    /// to name the identity that claimed, and only the dialer knows it.
    #[serde(rename = "self")]
    self_id: String,
    handshake: Handshake,
    #[serde(skip_serializing_if = "Option::is_none")]
    connect_ms: Option<u64>,
    #[serde(skip_serializing_if = "Option::is_none")]
    selected_path: Option<PathKind>,
    #[serde(skip_serializing_if = "Option::is_none")]
    error: Option<String>,
    responses: Vec<RespRecord>,
    /// Absent unless the job asked for a hold.
    #[serde(skip_serializing_if = "Option::is_none")]
    held_ms: Option<u64>,
    /// The peer's close reason observed at the end of the hold, or `null` if
    /// the connection was still open. This is the oracle's own reading of
    /// whether the daemon cut the connection, independent of whether the
    /// requests after the hold were answered.
    #[serde(skip_serializing_if = "Option::is_none")]
    closed_during_hold: Option<String>,
    #[serde(skip_serializing_if = "Vec::is_empty", default)]
    after_hold: Vec<RespRecord>,
    #[serde(skip_serializing_if = "Vec::is_empty", default)]
    sockets: Vec<SocketRecord>,
}

/// Deliberately the same field names `sockets.py` writes, so a comparison
/// between the transports is a comparison of records rather than a
/// translation between two formats.
#[derive(Serialize, Default)]
struct SocketRecord {
    path: String,
    token_supplied: bool,
    opened: bool,
    http_status: Option<u16>,
    status_line: Option<String>,
    frames: u32,
    frame_types: std::collections::BTreeMap<String, u32>,
    close_code: Option<u16>,
    close_reason: Option<String>,
    error: Option<String>,
}

#[derive(Serialize, PartialEq)]
enum Handshake {
    Completed,
    Refused,
    NotAttempted,
}

/// The selected route without its address, which is private test input.
#[derive(Debug, Serialize, PartialEq, Eq)]
#[serde(rename_all = "snake_case")]
enum PathKind {
    Direct,
    Relay,
    Unknown,
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

    let connect_started = Instant::now();
    let connect = endpoint.connect(addr, ALPN);
    let mut record = Record {
        node: job.node.clone(),
        self_id: endpoint.id().to_string(),
        handshake: Handshake::NotAttempted,
        connect_ms: None,
        selected_path: None,
        error: None,
        held_ms: None,
        closed_during_hold: None,
        after_hold: Vec::new(),
        sockets: Vec::new(),
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
            record.connect_ms = Some(connect_started.elapsed().as_millis() as u64);
            if job.expect_handshake {
                for spec in &job.requests {
                    record.responses.push(one_request(&conn, spec).await);
                }
            }
            record.selected_path = selected_path(&conn);
            for spec in &job.sockets {
                record.sockets.push(one_socket(&conn, spec).await);
            }
            if job.hold_ms > 0 {
                record.held_ms = Some(job.hold_ms);
                tokio::time::sleep(Duration::from_millis(job.hold_ms)).await;
                record.closed_during_hold = conn.close_reason().map(|reason| reason.to_string());
                for spec in &job.after_hold {
                    record.after_hold.push(one_request(&conn, spec).await);
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

fn selected_path(conn: &iroh::endpoint::Connection) -> Option<PathKind> {
    conn.paths()
        .iter()
        .find(|path| path.is_selected())
        .map(|path| path_kind(path.is_ip(), path.is_relay()))
}

fn path_kind(is_ip: bool, is_relay: bool) -> PathKind {
    if is_ip {
        PathKind::Direct
    } else if is_relay {
        PathKind::Relay
    } else {
        PathKind::Unknown
    }
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
        .map(serde_json::to_vec)
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

/// Open one run socket over a QUIC stream and record what arrives.
///
/// The daemon serves HTTP/1.1 on a stream, so the WebSocket upgrade is the
/// same handshake it is over TCP: the only difference is what carries the
/// bytes. Server-to-client frames are never masked, which is what keeps the
/// reader this short.
async fn one_socket(conn: &iroh::endpoint::Connection, spec: &SocketSpec) -> SocketRecord {
    let mut record = SocketRecord {
        path: spec.path.clone(),
        token_supplied: spec.token.is_some(),
        ..Default::default()
    };
    if let Err(error) = drive_socket(conn, spec, &mut record).await {
        record.error = Some(format!("{error:#}"));
    }
    record
}

async fn drive_socket(
    conn: &iroh::endpoint::Connection,
    spec: &SocketSpec,
    record: &mut SocketRecord,
) -> Result<()> {
    let (mut send, mut recv) = conn.open_bi().await.context("opening a stream")?;
    let target = match &spec.token {
        Some(token) => format!("{}?token={token}", spec.path),
        None => spec.path.clone(),
    };
    // A fixed key: the server echoes an accept derived from it and this client
    // does not check the echo, so nothing here needs to be unpredictable.
    let head = format!(
        "GET {target} HTTP/1.1\r\nHost: vadgr\r\nUpgrade: websocket\r\n\
         Connection: Upgrade\r\nSec-WebSocket-Key: dGhlIHNhbXBsZSBub25jZQ==\r\n\
         Sec-WebSocket-Version: 13\r\n\r\n"
    );
    send.write_all(head.as_bytes()).await?;

    let deadline = tokio::time::Instant::now() + Duration::from_secs(spec.seconds);
    let mut buffer: Vec<u8> = Vec::new();
    let mut chunk = [0u8; 8192];

    // The response head, up to and including the blank line.
    let head_end = loop {
        if let Some(at) = find(&buffer, b"\r\n\r\n") {
            break at + 4;
        }
        if !pull(&mut recv, &mut chunk, &mut buffer, deadline).await? {
            anyhow::bail!("the connection ended before the upgrade response");
        }
    };
    let line = String::from_utf8_lossy(&buffer[..head_end])
        .lines()
        .next()
        .unwrap_or_default()
        .to_string();
    record.http_status = line.split_whitespace().nth(1).and_then(|s| s.parse().ok());
    record.status_line = Some(line);
    if record.http_status != Some(101) {
        return Ok(());
    }
    record.opened = true;
    buffer.drain(..head_end);

    loop {
        // One frame: the two byte header, then the length, then the payload.
        while buffer.len() < 2 {
            if !pull(&mut recv, &mut chunk, &mut buffer, deadline).await? {
                return Ok(());
            }
        }
        let opcode = buffer[0] & 0x0f;
        let masked = buffer[1] & 0x80 != 0;
        let short = (buffer[1] & 0x7f) as usize;
        let (mut at, mut length) = (2usize, short);
        if short == 126 {
            while buffer.len() < 4 {
                if !pull(&mut recv, &mut chunk, &mut buffer, deadline).await? {
                    return Ok(());
                }
            }
            length = u16::from_be_bytes([buffer[2], buffer[3]]) as usize;
            at = 4;
        } else if short == 127 {
            while buffer.len() < 10 {
                if !pull(&mut recv, &mut chunk, &mut buffer, deadline).await? {
                    return Ok(());
                }
            }
            let mut wide = [0u8; 8];
            wide.copy_from_slice(&buffer[2..10]);
            length = u64::from_be_bytes(wide) as usize;
            at = 10;
        }
        let mask_at = at;
        if masked {
            at += 4;
        }
        while buffer.len() < at + length {
            if !pull(&mut recv, &mut chunk, &mut buffer, deadline).await? {
                return Ok(());
            }
        }
        let mut payload = buffer[at..at + length].to_vec();
        if masked {
            let mask: Vec<u8> = buffer[mask_at..mask_at + 4].to_vec();
            for (i, byte) in payload.iter_mut().enumerate() {
                *byte ^= mask[i % 4];
            }
        }
        buffer.drain(..at + length);

        match opcode {
            0x8 => {
                if payload.len() >= 2 {
                    record.close_code = Some(u16::from_be_bytes([payload[0], payload[1]]));
                    record.close_reason = Some(String::from_utf8_lossy(&payload[2..]).into_owned());
                }
                return Ok(());
            }
            0x9 => *record.frame_types.entry("ping".into()).or_insert(0) += 1,
            0xa => *record.frame_types.entry("pong".into()).or_insert(0) += 1,
            0x2 => {
                record.frames += 1;
                *record.frame_types.entry("binary".into()).or_insert(0) += 1;
            }
            _ => {
                record.frames += 1;
                let text = String::from_utf8_lossy(&payload).into_owned();
                let name = match serde_json::from_str::<serde_json::Value>(&text) {
                    Ok(value) => value
                        .get("type")
                        .or_else(|| value.get("phase"))
                        .and_then(|v| v.as_str())
                        .map(|s| s.to_string())
                        .unwrap_or_else(|| "text/untyped".into()),
                    Err(_) => "text/not-json".into(),
                };
                *record.frame_types.entry(name).or_insert(0) += 1;
            }
        }
    }
}

fn find(haystack: &[u8], needle: &[u8]) -> Option<usize> {
    haystack.windows(needle.len()).position(|w| w == needle)
}

/// Read more bytes, or report that nothing more is coming. `false` means the
/// stream ended or the socket's own deadline passed, both of which end a
/// reading cell rather than failing it.
async fn pull(
    recv: &mut iroh::endpoint::RecvStream,
    chunk: &mut [u8; 8192],
    buffer: &mut Vec<u8>,
    deadline: tokio::time::Instant,
) -> Result<bool> {
    match tokio::time::timeout_at(deadline, recv.read(chunk)).await {
        Err(_) => Ok(false),
        Ok(read) => match read.context("reading the socket")? {
            None | Some(0) => Ok(false),
            Some(n) => {
                buffer.extend_from_slice(&chunk[..n]);
                Ok(true)
            }
        },
    }
}

#[cfg(test)]
mod tests {
    use super::{PathKind, path_kind};

    #[test]
    fn classifies_the_selected_path_without_recording_its_address() {
        assert_eq!(path_kind(true, false), PathKind::Direct);
        assert_eq!(path_kind(false, true), PathKind::Relay);
        assert_eq!(path_kind(false, false), PathKind::Unknown);
    }
}
