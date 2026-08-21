//! The command implementations.
//!
//! **Boundary rule from the design:** a command never builds strings for the
//! terminal and never calls the HTTP layer directly. It calls `client` and hands
//! values to `output`. That is what makes the sweep's "whether output was
//! produced" assertion checkable per command.

pub mod info;
pub mod pair;
pub mod provider;
pub mod runs;
pub mod service;
