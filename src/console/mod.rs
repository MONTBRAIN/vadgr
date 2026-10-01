//! The installed local administration console.

mod app;
mod controller;
pub(crate) mod native;
mod text_input;
pub(crate) mod theme;

pub use app::run;
pub use controller::{ConsoleController, HttpConsoleController};
