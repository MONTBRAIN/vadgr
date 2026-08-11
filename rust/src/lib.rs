//! The daemon as a library, so the suites can reach its parts.
//!
//! `main.rs` stays the binary and declares the same modules; this exists so an
//! integration test can build a router without spawning a process, which is
//! what lets the gate's five outcomes be asserted rather than described.

pub mod auth;
pub mod config;
pub mod db;
pub mod error;
pub mod routes;
pub mod state;
pub mod transport;
pub mod ws;
