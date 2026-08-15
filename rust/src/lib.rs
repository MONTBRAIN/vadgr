//! The daemon as a library, so the suites can reach its parts.
//!
//! `main.rs` stays the binary and uses these modules from here; this exists so
//! an integration test can build a router without spawning a process, which is
//! what lets the gate's five outcomes be asserted rather than described.

pub mod auth;
pub mod computer_use_setup;
pub mod config;
pub mod db;
pub mod error;
pub mod platform;
pub mod routes;
pub mod state;
pub mod transport;
pub mod ws;
