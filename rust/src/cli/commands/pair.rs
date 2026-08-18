//! `vadgr pair`: mint a one-time code and draw the QR a phone scans.
//!
//! Ported from `cli/commands/pair_cmd.py`. The deep link is a cross-repo
//! contract: `vadgr-mobile`'s `pair_payload.dart` requires `host`, `port`,
//! `token` and `name`, each with its own error message, so the four parameter
//! names are fixed by a shipped scanner rather than by taste.

use qrcode_generator::qr::{Encoder, ErrorCorrection};
use serde_json::Value;

use crate::client::Client;
use crate::commands::provider;
use crate::error::CliError;
use crate::output;

/// The quiet zone, in modules.
///
/// The specification says four, the Python renderer ships one, and the probe
/// chose two. At one, terminal text sitting directly against the symbol can
/// confuse a camera; two costs two columns and removes that (§2.1b.2).
const QUIET_ZONE: usize = 2;

/// The deep link the phone receives.
///
/// The value in `token` is the pairing code. The field is named `pairing_token`
/// on the wire and that name is the invariant; only the value it carries became
/// a short typeable code at `0.4.3`.
pub fn build_pair_uri(pair: &Value) -> Result<String, CliError> {
    let field = |key: &str| -> Result<String, CliError> {
        match pair.get(key) {
            Some(Value::String(s)) => Ok(s.clone()),
            Some(Value::Number(n)) => Ok(n.to_string()),
            _ => Err(CliError::Failed(
                "Pairing failed: unexpected response from the API.".to_owned(),
            )),
        }
    };
    let query = url::form_urlencoded::Serializer::new(String::new())
        .append_pair("host", &field("host")?)
        .append_pair("port", &field("port")?)
        .append_pair("token", &field("pairing_token")?)
        .append_pair("name", &field("machine_name")?)
        .finish();
    Ok(format!("vadgr://pair?{query}"))
}

/// The symbol, drawn with half blocks: two module rows per printed line.
///
/// `dark` says which way round to draw it. **A QR drawn dark on light does not
/// scan on a dark terminal**, and a terminal's background colour cannot be read
/// reliably, so the command picks the case a terminal usually is and the
/// function keeps both testable.
///
/// Error correction is `Low`, which the probe chose: error correction exists for
/// physical damage, and a symbol on a screen for thirty seconds has none of it.
/// Dropping `Medium` to `Low` buys a whole symbol version (§2.1b.2).
pub fn render_qr(data: &str, dark: bool) -> Result<String, CliError> {
    let symbol = Encoder::new(ErrorCorrection::Low)
        .encode_text(data)
        .map_err(|e| CliError::Failed(format!("The pairing QR could not be encoded: {e}")))?;
    let matrix = symbol.to_matrix();
    let size = matrix.len();
    let side = size + QUIET_ZONE * 2;

    let module = |x: usize, y: usize| -> bool {
        x >= QUIET_ZONE
            && y >= QUIET_ZONE
            && x < QUIET_ZONE + size
            && y < QUIET_ZONE + size
            && matrix[y - QUIET_ZONE][x - QUIET_ZONE]
    };

    let mut out = String::new();
    let mut y = 0;
    while y < side {
        for x in 0..side {
            let top = module(x, y);
            let bottom = y + 1 < side && module(x, y + 1);
            // On a dark terminal the light modules are what must be painted, so
            // the pair is inverted rather than the glyphs being swapped.
            let (top, bottom) = if dark { (!top, !bottom) } else { (top, bottom) };
            out.push(match (top, bottom) {
                (true, true) => '\u{2588}',
                (true, false) => '\u{2580}',
                (false, true) => '\u{2584}',
                (false, false) => ' ',
            });
        }
        out.push('\n');
        y += 2;
    }
    Ok(out)
}

pub async fn pair(client: &Client) -> Result<(), CliError> {
    // Pairing without a model provider gives a phone a machine that cannot run
    // anything, so the provider flow comes first rather than failing later.
    let providers = client.get("/api/providers").await?;
    let has_default = providers.as_array().is_some_and(|rows| {
        rows.iter()
            .any(|r| r.get("is_default").and_then(|v| v.as_bool()) == Some(true))
    });
    if !has_default {
        anstream::println!("Before this machine can pair, connect a model provider.\n");
        provider::connect(client, None, None, None).await?;
    }

    let data = client.post("/api/auth/pair", None).await?;
    if data.get("pairing_token").and_then(|v| v.as_str()).is_none() {
        anstream::println!(
            "{}",
            output::error("Pairing failed: unexpected response from the API.")
        );
        return Err(CliError::Failed(String::new()));
    }

    let uri = build_pair_uri(&data)?;
    anstream::println!();
    anstream::print!("{}", render_qr(&uri, true)?);
    anstream::println!();

    let text = |key: &str| {
        data.get(key)
            .and_then(|v| v.as_str())
            .unwrap_or("-")
            .to_owned()
    };
    let port = data
        .get("port")
        .map(|v| v.to_string().trim_matches('"').to_owned())
        .unwrap_or_else(|| "-".to_owned());
    anstream::println!(
        "{}",
        output::render_kv(&[
            ("Machine".to_owned(), text("machine_name")),
            ("Address".to_owned(), format!("{}:{port}", text("host"))),
            ("Pairing code".to_owned(), text("pairing_token")),
        ])
    );
    anstream::println!();
    anstream::println!(
        "{}",
        output::success(
            "Scan with the Vadgr mobile app, or type the code. One-time, valid for 5 minutes."
        )
    );
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;

    fn payload() -> Value {
        json!({
            "host": "santiago-wsl.tail4b2c.ts.net",
            "port": 8000,
            "pairing_token": "K7M2-9QRT",
            "machine_name": "santiago-wsl",
        })
    }

    /// The four names are a shipped scanner's contract, not a preference.
    #[test]
    fn the_deep_link_carries_the_four_names_the_phone_reads() {
        let uri = build_pair_uri(&payload()).unwrap();
        assert!(uri.starts_with("vadgr://pair?"));
        for key in ["host=", "port=", "token=", "name="] {
            assert!(uri.contains(key), "{uri} is missing {key}");
        }
        assert!(uri.contains("token=K7M2-9QRT"));
    }

    /// A numeric port arrives as a number and must not reach the phone as `8000.0`
    /// or quoted.
    #[test]
    fn a_numeric_port_reaches_the_link_as_digits() {
        let uri = build_pair_uri(&payload()).unwrap();
        assert!(uri.contains("port=8000"), "{uri}");
    }

    #[test]
    fn a_response_missing_a_field_is_a_named_failure_rather_than_a_broken_link() {
        let mut broken = payload();
        broken.as_object_mut().unwrap().remove("machine_name");
        assert!(build_pair_uri(&broken).is_err());
    }

    /// A machine name with a space must survive the round trip, because a person
    /// names their own machine.
    #[test]
    fn a_machine_name_with_a_space_is_encoded() {
        let mut named = payload();
        named["machine_name"] = json!("Santiago Desktop");
        let uri = build_pair_uri(&named).unwrap();
        assert!(!uri.contains("Santiago Desktop"), "{uri} is not encoded");
        let parsed = url::Url::parse(&uri).unwrap();
        let name = parsed
            .query_pairs()
            .find(|(k, _)| k == "name")
            .map(|(_, v)| v.to_string());
        assert_eq!(name.as_deref(), Some("Santiago Desktop"));
    }

    /// The size the owner scanned: quiet zone 2 on each side, two module rows
    /// per printed line.
    #[test]
    fn the_symbol_is_drawn_at_the_size_the_probe_chose() {
        let uri = build_pair_uri(&payload()).unwrap();
        let drawn = render_qr(&uri, true).unwrap();
        let lines: Vec<&str> = drawn.lines().collect();
        let width = lines[0].chars().count();
        assert!(
            lines.iter().all(|l| l.chars().count() == width),
            "every line is the same width"
        );
        // A symbol of `n` modules draws `n + 4` columns and half as many rows.
        assert_eq!(lines.len(), width.div_ceil(2));
        assert!(width >= 25, "a version 1 symbol plus the quiet zone");
    }

    /// **The regression this test exists for**: a QR drawn dark on light does not
    /// scan on a dark terminal, and no other assertion notices.
    #[test]
    fn the_two_forms_are_inverses_of_each_other() {
        let uri = build_pair_uri(&payload()).unwrap();
        let dark = render_qr(&uri, true).unwrap();
        let light = render_qr(&uri, false).unwrap();
        assert_ne!(dark, light);
        let flip = |c: char| match c {
            '\u{2588}' => ' ',
            ' ' => '\u{2588}',
            '\u{2580}' => '\u{2584}',
            '\u{2584}' => '\u{2580}',
            other => other,
        };
        assert_eq!(dark.chars().map(flip).collect::<String>(), light);
    }

    /// The quiet zone is what a scanner finds the edge with, so it is asserted
    /// rather than assumed: the first two printed lines carry no module.
    #[test]
    fn the_quiet_zone_is_present_on_every_side() {
        let uri = build_pair_uri(&payload()).unwrap();
        let light = render_qr(&uri, false).unwrap();
        let lines: Vec<&str> = light.lines().collect();
        assert!(
            lines[0].chars().all(|c| c == ' '),
            "the top quiet zone is blank"
        );
        assert!(
            lines.last().unwrap().chars().all(|c| c == ' '),
            "the bottom quiet zone is blank"
        );
        for line in &lines {
            let chars: Vec<char> = line.chars().collect();
            assert_eq!(chars[0], ' ', "the left quiet zone is blank");
            assert_eq!(chars[1], ' ', "two modules of it");
            assert_eq!(chars[chars.len() - 1], ' ', "the right quiet zone is blank");
        }
    }
}
