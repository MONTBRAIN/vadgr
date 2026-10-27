//! The installed local administration console.

mod app;
mod controller;
#[cfg(test)]
pub(crate) mod focus_tests;
pub(crate) mod native;
mod text_input;
pub(crate) mod theme;

pub use app::run;
pub use controller::{ConsoleController, HttpConsoleController};
