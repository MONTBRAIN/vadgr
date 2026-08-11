//! The transport adapter. 374 lines in Python, and the part that looks hard is
//! not: it speaks HTTP/1.0 over an `AF_UNIX` socket to tailscaled, and over a
//! named pipe on Windows. A socket, a hand-written request line, a parse.

pub mod tailscale;

use serde_json::Value;

pub trait Transport: Send + Sync {
    fn name(&self) -> &'static str;
    /// The host a QR may advertise, or `None` when nothing reachable exists.
    /// `None` is what makes `POST /api/auth/pair` refuse with
    /// `TRANSPORT_UNREACHABLE` rather than hand out a localhost QR no phone
    /// could use.
    fn advertise_host(&self) -> Option<String>;
    fn bind_host(&self) -> String;
    fn is_authorized_source(&self, host: &str) -> bool;
    fn status(&self) -> Value;
}
