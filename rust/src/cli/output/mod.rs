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
use unicode_width::UnicodeWidthStr;

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

/// The visible width of a cell, with any styling discounted.
///
/// **Measuring the raw string is the bug this exists to stop.** A styled cell
/// carries escape bytes that occupy no columns, so a table laid out from the raw
/// length pads the coloured column by the length of its escapes and every other
/// row in that column lands short. It was caught on the first `vadgr status` of
/// the `0.4.8` pass, where `Status` was drawn eighteen columns wide for a seven
/// character word.
fn display_width(cell: &str) -> usize {
    plain(cell).width()
}

/// A copy of the text with SGR sequences removed.
fn plain(text: &str) -> String {
    let mut out = String::with_capacity(text.len());
    let mut chars = text.chars();
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

/// A table with the shape the CLI has always drawn: **no box.**
///
/// The Python CLI built `rich.Table(show_edge=False, pad_edge=False, box=None)`,
/// which prints columns padded to their widest cell and separated by two spaces.
/// A boxed table is a different surface, and the port draws the shipped one.
///
/// Widths come from `unicode-width` on the unstyled text, so a wide character
/// and a coloured status both land in the right column.
pub fn render_table(headers: &[&str], rows: &[Vec<String>]) -> String {
    let columns = headers.len();
    let mut widths: Vec<usize> = headers.iter().map(|h| h.width()).collect();
    for row in rows {
        for (index, cell) in row.iter().enumerate().take(columns) {
            widths[index] = widths[index].max(display_width(cell));
        }
    }

    let mut out = String::new();
    let pad = |out: &mut String, cell: &str, width: usize| {
        out.push_str(cell);
        for _ in display_width(cell)..width {
            out.push(' ');
        }
    };

    for (index, header) in headers.iter().enumerate() {
        if index > 0 {
            out.push_str("  ");
        }
        pad(&mut out, header, widths[index]);
    }
    out.push('\n');

    for row in rows {
        for (index, width) in widths.iter().enumerate().take(columns) {
            if index > 0 {
                out.push_str("  ");
            }
            let cell = row.get(index).map(String::as_str).unwrap_or("");
            pad(&mut out, cell, *width);
        }
        out.push('\n');
    }
    out.trim_end_matches('\n').to_owned()
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

    /// The shipped table has no box. The Python CLI drew `box=None`, and a boxed
    /// table is a different surface rather than a nicer one.
    #[test]
    fn the_table_is_padded_columns_and_not_a_box() {
        let out = render_table(&["Service", "PID"], &[vec!["api".into(), "28138".into()]]);
        assert_eq!(out, "Service  PID  \napi      28138");
        for glyph in ['\u{250c}', '\u{2502}', '\u{2500}', '\u{2554}', '\u{2551}'] {
            assert!(!out.contains(glyph), "{out:?} drew a box");
        }
    }

    /// **The defect this test exists for.** A coloured cell carries escape bytes
    /// that occupy no columns. Laying the table out from the raw length pads the
    /// coloured column by the length of its escapes, and every other row in it
    /// lands short. Caught on the first `vadgr status` of the `0.4.8` pass.
    #[test]
    fn a_coloured_cell_does_not_widen_its_column() {
        let coloured = render_table(
            &["Service", "PID", "Status"],
            &[
                vec!["api".into(), "28138".into(), format_status("running")],
                vec!["daemon".into(), "-".into(), format_status("failed")],
            ],
        );
        let uncoloured = render_table(
            &["Service", "PID", "Status"],
            &[
                vec!["api".into(), "28138".into(), "running".into()],
                vec!["daemon".into(), "-".into(), "failed".into()],
            ],
        );
        assert_eq!(
            plain(&coloured),
            uncoloured,
            "styling changed the layout, so the columns no longer line up"
        );
        // And every rendered line is the same visible width.
        let widths: Vec<usize> = plain(&coloured).lines().map(|l| l.width()).collect();
        assert!(
            widths.windows(2).all(|w| w[0] == w[1]),
            "ragged lines: {widths:?}"
        );
    }

    /// A task sentence is prose, so a wide character must occupy the columns it
    /// actually occupies.
    #[test]
    fn a_wide_character_is_measured_by_its_width() {
        let out = render_table(
            &["Task", "Status"],
            &[
                vec!["\u{6f22}\u{5b57}".into(), "ok".into()],
                vec!["abcd".into(), "ok".into()],
            ],
        );
        let widths: Vec<usize> = out.lines().map(|l| l.width()).collect();
        assert!(
            widths.windows(2).all(|w| w[0] == w[1]),
            "ragged: {widths:?}"
        );
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
