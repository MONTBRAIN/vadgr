//! Everything the CLI puts on a terminal.
//!
//! Ported from `cli/output.py`, which already centralised status colouring,
//! key-value printing and duration formatting. §6a warns against reimplementing
//! logic the original had factored, so each of those keeps one home here rather
//! than one per command.
//!
//! `rich` has no Rust equivalent worth depending on, so tables come from
//! `comfy-table` and colour from `anstyle`. `anstyle` is declared in the
//! manifest because Rust needs a direct dependency to import it, but it adds
//! nothing to the compiled tree: `clap` already brings it.

use anstyle::{AnsiColor, Color, Style};
use comfy_table::{ContentArrangement, Table, presets::UTF8_FULL};

pub mod status;

/// The status palette, one place, as `_STATUS_STYLES` was in Python.
fn status_style(status: &str) -> Style {
    let colour = match status {
        "ready" | "completed" => AnsiColor::Green,
        "running" => AnsiColor::BrightBlue,
        "creating" | "queued" | "awaiting_approval" => AnsiColor::Yellow,
        "failed" | "cancelled" => AnsiColor::Red,
        _ => return Style::new(),
    };
    Style::new().fg_color(Some(Color::Ansi(colour)))
}

/// A status, coloured when colour is on and plain when it is not.
///
/// The decision is made once, by `anstream`, from whether the stream is a
/// terminal and whether `NO_COLOR` is set. No command asks that question.
pub fn format_status(status: &str) -> String {
    let s = status_style(status);
    format!("{s}{status}{s:#}")
}

/// A table with the shape the CLI has always drawn.
pub fn render_table(headers: &[&str], rows: &[Vec<String>]) -> String {
    let mut table = Table::new();
    table
        .load_style(UTF8_FULL)
        .set_content_arrangement(ContentArrangement::Dynamic)
        .set_header(headers.iter().map(|h| h.to_string()));
    for row in rows {
        table.add_row(row.clone());
    }
    table.to_string()
}

/// Key and value, at the fixed label width the Python version used.
pub fn render_kv(pairs: &[(String, String)]) -> String {
    const LABEL_WIDTH: usize = 12;
    pairs
        .iter()
        .map(|(k, v)| format!("{k:<LABEL_WIDTH$} {v}"))
        .collect::<Vec<_>>()
        .join("\n")
}

/// A duration, in the CLI's own shorthand.
pub fn format_duration(seconds: f64) -> String {
    if seconds < 1.0 {
        return format!("{:.0}ms", seconds * 1000.0);
    }
    if seconds < 60.0 {
        return format!("{seconds:.0}s");
    }
    let minutes = (seconds / 60.0).floor();
    let rest = seconds - minutes * 60.0;
    if minutes < 60.0 {
        return format!("{minutes:.0}m {rest:.0}s");
    }
    let hours = (minutes / 60.0).floor();
    format!("{hours:.0}h {:.0}m", minutes - hours * 60.0)
}

fn styled(prefix: &str, colour: AnsiColor, message: &str) -> String {
    let s = Style::new().fg_color(Some(Color::Ansi(colour)));
    format!("{s}{prefix}{s:#} {message}")
}

pub fn success(message: &str) -> String {
    styled("[vadgr]", AnsiColor::Green, message)
}

pub fn info(message: &str) -> String {
    styled("[vadgr]", AnsiColor::Blue, message)
}

pub fn warning(message: &str) -> String {
    styled("[vadgr]", AnsiColor::Yellow, message)
}

pub fn error(message: &str) -> String {
    styled("Error:", AnsiColor::Red, message)
}

#[cfg(test)]
mod tests {
    use super::*;

    /// Assert the rendering as text rather than by eye, which is why colour is
    /// forced off for these.
    fn plain(s: &str) -> String {
        // Strip SGR sequences so the shape is asserted, not the escapes.
        let mut out = String::new();
        let mut chars = s.chars();
        while let Some(c) = chars.next() {
            if c == '\u{1b}' {
                for c in chars.by_ref() {
                    if c == 'm' {
                        break;
                    }
                }
            } else {
                out.push(c);
            }
        }
        out
    }

    #[test]
    fn a_table_carries_its_headers_and_every_row() {
        let out = render_table(
            &["Run ID", "Status"],
            &[
                vec!["run-abcd".into(), "completed".into()],
                vec!["run-efgh".into(), "failed".into()],
            ],
        );
        assert!(out.contains("Run ID"));
        assert!(out.contains("run-abcd"));
        assert!(out.contains("run-efgh"));
        assert_eq!(out.matches("run-").count(), 2, "no row is dropped");
    }

    #[test]
    fn a_key_value_block_pads_to_the_label_width() {
        let out = render_kv(&[("Status".into(), "running".into())]);
        assert_eq!(out, "Status       running");
    }

    #[test]
    fn a_status_reads_the_same_with_colour_stripped() {
        assert_eq!(plain(&format_status("completed")), "completed");
        assert_eq!(plain(&format_status("failed")), "failed");
        // An unknown status still renders, uncoloured rather than dropped.
        assert_eq!(plain(&format_status("surprising")), "surprising");
    }

    #[test]
    fn durations_read_the_way_the_cli_has_always_written_them() {
        assert_eq!(format_duration(0.25), "250ms");
        assert_eq!(format_duration(9.0), "9s");
        assert_eq!(format_duration(75.0), "1m 15s");
        assert_eq!(format_duration(3720.0), "1h 2m");
    }

    #[test]
    fn the_four_levels_carry_their_prefix() {
        assert!(plain(&success("done")).starts_with("[vadgr] done"));
        assert!(plain(&info("checking")).starts_with("[vadgr] checking"));
        assert!(plain(&warning("careful")).starts_with("[vadgr] careful"));
        assert!(plain(&error("no")).starts_with("Error: no"));
    }
}
