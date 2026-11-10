//! Token primitives: pure crypto, no I/O.
//!
//! Ported from `api/auth/tokens.py`, including the alphabet and the confusion
//! map, because a code minted by one daemon must be typeable into the other
//! during the migration.

use rand::RngExt;
use sha2::{Digest, Sha256};

/// Crockford base32: digits plus the alphabet minus I, L, O and U. The
/// exclusions are the whole point - a person reads this off a terminal and
/// types it on a phone, and 0/O and 1/I/L are where that goes wrong.
pub const CROCKFORD_ALPHABET: &[u8] = b"0123456789ABCDEFGHJKMNPQRSTVWXYZ";

const TOKEN_ENTROPY_BYTES: usize = 32;

pub fn generate_token() -> String {
    let mut rng = rand::rng();
    let bytes: Vec<u8> = (0..TOKEN_ENTROPY_BYTES)
        .map(|_| rng.random::<u8>())
        .collect();
    // URL-safe, unpadded: the same shape `secrets.token_urlsafe` produces.
    base64_url_nopad(&bytes)
}

fn base64_url_nopad(bytes: &[u8]) -> String {
    const T: &[u8] = b"ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_";
    let mut out = String::new();
    for chunk in bytes.chunks(3) {
        let b = [
            chunk[0],
            *chunk.get(1).unwrap_or(&0),
            *chunk.get(2).unwrap_or(&0),
        ];
        let n = ((b[0] as u32) << 16) | ((b[1] as u32) << 8) | b[2] as u32;
        let idx = [(n >> 18) & 63, (n >> 12) & 63, (n >> 6) & 63, n & 63];
        for (i, ix) in idx.iter().enumerate() {
            if i <= chunk.len() {
                out.push(T[*ix as usize] as char);
            }
        }
    }
    out
}

/// Eight symbols chosen uniformly from the 32-symbol alphabet: 40 bits by
/// construction, with no modulo bias to reason about. Returned in the grouped
/// `XXXX-XXXX` form the route puts on the wire.
pub fn generate_pairing_code() -> String {
    let mut rng = rand::rng();
    let raw: String = (0..8)
        .map(|_| CROCKFORD_ALPHABET[rng.random_range(0..CROCKFORD_ALPHABET.len())] as char)
        .collect();
    format!("{}-{}", &raw[..4], &raw[4..])
}

/// The ungrouped 8-character form of whatever a person typed, or `None`.
///
/// Normalising server-side rather than in each client is what makes the
/// forgiveness identical everywhere: the CLI, the QR and a phone keyboard all
/// get the same answer for the same intent. Malformed and unknown deliberately
/// share one verdict downstream, so a guesser learns nothing from the split.
pub fn normalize_pairing_code(raw: &str) -> Option<String> {
    let candidate: String = raw
        .to_uppercase()
        .chars()
        .filter(|c| *c != '-' && *c != ' ')
        .map(|c| match c {
            'O' => '0',
            'I' | 'L' => '1',
            other => other,
        })
        .collect();
    if candidate.len() != 8 {
        return None;
    }
    if !candidate.bytes().all(|b| CROCKFORD_ALPHABET.contains(&b)) {
        return None;
    }
    Some(candidate)
}

pub fn hash_token(token: &str) -> String {
    let mut h = Sha256::new();
    h.update(token.as_bytes());
    // sha2 0.11 returns an array that does not implement LowerHex, so the hex
    // digest is written here. It must stay lowercase and unpadded: the phone's stored digest
    // daemon stores the same digest, and both daemons compare against one
    // devices table during the migration.
    h.finalize().iter().map(|b| format!("{b:02x}")).collect()
}

/// Constant-time comparison of two hex digests.
pub fn constant_time_eq(a: &str, b: &str) -> bool {
    if a.len() != b.len() {
        return false;
    }
    let mut diff = 0u8;
    for (x, y) in a.bytes().zip(b.bytes()) {
        diff |= x ^ y;
    }
    diff == 0
}
