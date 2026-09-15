//! The installed local administration console.

mod app;
mod controller;
mod text_input;
pub(crate) mod theme;

pub use app::run;
pub use controller::{ConsoleController, HttpConsoleController};
