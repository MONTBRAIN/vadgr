//! The waiting spinner, replacing `rich`'s `console.status`.
//!
//! `indicatif` is the one crate added purely for this. It is off when the stream
//! is not a terminal, so piping a command to a file does not fill it with frames.

use std::time::Duration;

use indicatif::{ProgressBar, ProgressStyle};

/// The tick pattern `rich` called `dots`, kept so the CLI looks unchanged.
const DOTS: &[&str] = &["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"];

/// A spinner that runs while something is awaited.
pub struct Spinner(ProgressBar);

impl Spinner {
    pub fn start(message: impl Into<String>) -> Self {
        let bar = ProgressBar::new_spinner();
        bar.set_style(
            ProgressStyle::with_template("{spinner} {msg}")
                .expect("the spinner template parses")
                .tick_strings(DOTS),
        );
        bar.set_message(message.into());
        bar.enable_steady_tick(Duration::from_millis(80));
        Self(bar)
    }

    pub fn update(&self, message: impl Into<String>) {
        self.0.set_message(message.into());
    }

    /// Stop and clear the line, so the next thing printed owns it.
    pub fn stop(self) {
        self.0.finish_and_clear();
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    /// The spinner must always be stoppable, because a spinner that never stops
    /// is what a user sees when a command fails on a path nobody tested.
    #[test]
    fn a_spinner_starts_updates_and_stops() {
        let s = Spinner::start("waiting");
        s.update("still waiting");
        s.stop();
    }
}
