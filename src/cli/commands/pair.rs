//! `vadgr pair`: mint a one-time code and draw the QR a phone scans.
//!
//! The deep link is a cross-repo contract. `token` and `name` are required;
//! every other parameter is one key of one transport's own address form,
//! flattened by the builder with no knowledge of what those keys are, so the
//! shipped scanner's `host` and `port` come out of the tailscale entry
//! exactly as they always did, and a machine without a dialable tailscale
//! mints a QR with no `host` at all.

use qrcode_generator::qr::{Encoder, ErrorCorrection};
use serde_json::Value;

use crate::client::Client;
use crate::commands::provider;
use crate::error::CliError;
use crate::output;

/// The quiet zone, in modules.
///
/// The specification says four, the renderer shipped one, and the probe chose
/// two. At one, terminal text sitting directly against the symbol can
/// confuse a camera; two costs two columns and removes that (§2.1b.2).
const QUIET_ZONE: usize = 2;

/// The deep link the phone receives.
///
/// The value in `token` is the pairing code. The field is named `pairing_token`
/// on the wire and that name is the invariant; only the value it carries became
/// a short typeable code at `0.4.3`. `token` and `name` are the only required
/// halves: a transport with no address contributes nothing, and the ordinary
/// machine without a dialable tailscale must still mint a QR.
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
    let mut query = url::form_urlencoded::Serializer::new(String::new());
    query
        .append_pair("token", &field("pairing_token")?)
        .append_pair("name", &field("machine_name")?);
    // One query parameter per key of each transport's address form: a scalar
    // becomes one pair, an array a repeated pair. The builder knows nothing
    // about the keys, which is what keeps a new transport out of this file.
    if let Some(report) = pair.get("transports").and_then(Value::as_object) {
        for form in report.values() {
            let Some(form) = form.as_object() else {
                continue;
            };
            for (key, value) in form {
                match value {
                    Value::Array(items) => {
                        for item in items {
                            query.append_pair(key, &scalar(item));
                        }
                    }
                    other => {
                        query.append_pair(key, &scalar(other));
                    }
                }
            }
        }
    }
    Ok(format!("vadgr://pair?{}", query.finish()))
}

/// One address-form value as query text. Address forms carry strings and
/// numbers; anything else is serialised rather than dropped, so a defect is
/// visible in the link instead of silently absent.
fn scalar(value: &Value) -> String {
    match value {
        Value::String(s) => s.clone(),
        other => other.to_string(),
    }
}

/// One printed line per entry of the pairing report: the transport's
/// person-facing label, and a compact reading of its address form. The line
/// count follows the registry, not a list in this file.
fn transport_lines(
    report: &serde_json::Map<String, Value>,
    health: &Value,
) -> Vec<(String, String)> {
    let labels = label_map();
    report
        .iter()
        .map(|(name, form)| {
            let label = labels
                .iter()
                .find(|(n, _)| n == name)
                .map(|(_, l)| (*l).to_owned())
                .unwrap_or_else(|| name.clone());
            (label, address_summary(name, form, health))
        })
        .collect()
}

/// The person-facing labels, read from the registry every build carries
/// rather than from a list here. The probe registry serves nothing; it is
/// names and labels.
fn label_map() -> Vec<(String, &'static str)> {
    let Ok(config) = vadgr_daemon::config::Config::from_env() else {
        return Vec::new();
    };
    let registry = vadgr_daemon::transport::Transports::from_config(&config, config.port, None);
    registry
        .iter()
        .map(|t| (t.name().to_owned(), t.label()))
        .collect()
}

/// A compact reading of one address form: `host:port` where the form carries
/// both, the first relay for a rendezvous form, the transport's own words
/// from the health block when it is down, and the first value otherwise.
fn address_summary(name: &str, form: &Value, health: &Value) -> String {
    if let Some(form) = form.as_object() {
        if let (Some(host), Some(port)) = (form.get("host"), form.get("port")) {
            return format!("{}:{}", scalar(host), scalar(port));
        }
        if let Some(relay) = form
            .get("relays")
            .and_then(Value::as_array)
            .and_then(|r| r.first())
        {
            let relay = scalar(relay);
            let via = relay
                .trim_start_matches("https://")
                .trim_end_matches('/')
                .trim_end_matches('.');
            return format!("via {via}");
        }
        if let Some(first) = form.values().next() {
            return scalar(first);
        }
    }
    // A transport that is down is present with `null`, and its own words are
    // in the health block's entry for it.
    let reason = health
        .get("transport")
        .and_then(|t| t.get(name))
        .and_then(|entry| entry.get("reason"))
        .and_then(Value::as_str)
        .unwrap_or("this transport cannot be dialed right now");
    format!("not available ({reason})")
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
    let empty = serde_json::Map::new();
    let report = data
        .get("transports")
        .and_then(Value::as_object)
        .unwrap_or(&empty);
    // A down transport's own words live in the health block, so it is read
    // once when any entry is down; the pair response carries addresses only.
    let health = if report.values().any(Value::is_null) {
        client.get("/api/health").await.unwrap_or(Value::Null)
    } else {
        Value::Null
    };
    let mut rows = vec![("Machine".to_owned(), text("machine_name"))];
    for (label, summary) in transport_lines(report, &health) {
        rows.push((label, summary));
    }
    rows.push(("Pairing code".to_owned(), text("pairing_token")));
    anstream::println!("{}", output::render_kv(&rows));
    anstream::println!();
    // The typed fallback needs a typeable address, which is a host and port.
    let typeable = report.values().any(|form| {
        form.as_object()
            .is_some_and(|f| f.contains_key("host") && f.contains_key("port"))
    });
    if typeable {
        anstream::println!(
            "{}",
            output::success(
                "Scan with the Vadgr mobile app, or type the code. One-time, valid for 5 minutes."
            )
        );
    } else {
        anstream::println!(
            "{}",
            output::success(
                "Scan with the Vadgr mobile app. One-time, valid for 5 minutes. This machine                  pairs by QR only; typing an address needs Tailscale running here."
            )
        );
    }
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
            "transports": {
                "iroh": {
                    "node": "ee5c4b2f",
                    "relays": ["https://use1-1.relay.n0.iroh.link./"],
                    "direct": ["192.168.1.20:8000", "[fd12::7]:8000"],
                },
                "tailscale": {
                    "host": "santiago-wsl.tail4b2c.ts.net",
                    "port": 8000,
                },
            },
        })
    }

    /// The scanner's `host`, `port`, `token` and `name` still come out, and
    /// each transport's own keys beside them: the builder flattens the report
    /// with no knowledge of what the keys are.
    #[test]
    fn the_deep_link_carries_the_shipped_names_and_every_transport_key() {
        let uri = build_pair_uri(&payload()).unwrap();
        assert!(uri.starts_with("vadgr://pair?"));
        for key in [
            "host=", "port=", "token=", "name=", "node=", "relays=", "direct=",
        ] {
            assert!(uri.contains(key), "{uri} is missing {key}");
        }
        assert!(uri.contains("token=K7M2-9QRT"));
        // An array is a repeated parameter, one per member.
        assert_eq!(uri.matches("direct=").count(), 2);
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

    /// **The regression that would have broken `vadgr pair` on the ordinary
    /// machine**: no Tailscale means no `host` and no `port` anywhere, and
    /// the URI must still build, because the built-in transport's keys are
    /// what the phone dials.
    #[test]
    fn the_uri_builds_with_no_host_and_no_port_at_all() {
        let payload = json!({
            "pairing_token": "K7M2-9QRT",
            "machine_name": "santiago-wsl",
            "transports": {
                "iroh": { "node": "ee5c4b2f", "relays": ["https://r.example"], "direct": [] },
                "tailscale": null,
            },
        });
        let uri = build_pair_uri(&payload).unwrap();
        assert!(!uri.contains("host="), "{uri}");
        assert!(uri.contains("node=ee5c4b2f"), "{uri}");
    }

    /// The builder knows nothing about transport names: a fabricated two-key
    /// form produces two parameters, and a null member produces nothing.
    #[test]
    fn the_flattening_is_shape_driven_not_name_driven() {
        let payload = json!({
            "pairing_token": "K7M2-9QRT",
            "machine_name": "m",
            "transports": {
                "carrier-nobody-built": { "alpha": "1", "beta": ["x", "y"] },
                "down-one": null,
            },
        });
        let uri = build_pair_uri(&payload).unwrap();
        assert!(uri.contains("alpha=1"), "{uri}");
        assert_eq!(uri.matches("beta=").count(), 2, "{uri}");
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
