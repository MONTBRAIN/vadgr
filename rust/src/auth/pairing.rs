//! The one outstanding pairing code: the pair -> claim handshake.
//!
//! **One slot, not a map.** Minting replaces whatever code was outstanding, so
//! at most one exists at a time - which is also what makes "five attempts
//! against this code" well defined. A failed guess matches no key, so with
//! several concurrent codes there would be nothing to charge it against; with
//! exactly one, a failed claim is unambiguously an attempt on it.

use super::tokens::{generate_pairing_code, normalize_pairing_code};
use std::sync::Mutex;
use std::time::{Duration, Instant};

pub const PAIRING_TTL_SECONDS: u64 = 300;
pub const PAIRING_MAX_FAILURES: u32 = 5;

/// Why a redemption succeeded or failed.
///
/// `Invalid` covers wrong, malformed, unknown, already-used, superseded and
/// burned. All of them are "that code is not claimable", and telling them apart
/// would tell a guesser which codes exist.
#[derive(Debug, PartialEq, Eq, Clone, Copy)]
pub enum ClaimResult {
    Ok,
    Invalid,
    Expired,
    /// This attempt hit the cap and burned the code. Fired exactly once, at the
    /// moment the cap acts - the one moment "too many attempts" is a fact
    /// distinct from "not claimable".
    RateLimited,
}

struct Slot {
    code: String,
    expires_at: Instant,
    failures: u32,
}

pub struct PairingStore {
    ttl: Duration,
    slot: Mutex<Option<Slot>>,
}

impl PairingStore {
    pub fn new(ttl_seconds: u64) -> Self {
        Self { ttl: Duration::from_secs(ttl_seconds), slot: Mutex::new(None) }
    }

    /// Mint a code, replacing any outstanding one, live or expired.
    pub fn mint(&self) -> String {
        let display = generate_pairing_code();
        let normalized = normalize_pairing_code(&display).expect("minted code normalises");
        let mut guard = self.slot.lock().expect("pairing mutex poisoned");
        *guard = Some(Slot {
            code: normalized,
            expires_at: Instant::now() + self.ttl,
            failures: 0,
        });
        display
    }

    pub fn redeem(&self, presented: &str) -> ClaimResult {
        let mut guard = self.slot.lock().expect("pairing mutex poisoned");
        let slot = match guard.as_mut() {
            Some(s) => s,
            None => return ClaimResult::Invalid,
        };

        if Instant::now() >= slot.expires_at {
            *guard = None;
            return ClaimResult::Expired;
        }

        let candidate = match normalize_pairing_code(presented) {
            Some(c) => c,
            None => {
                // A malformed code is still an attempt on the outstanding one.
                // Not charging it would make the cap trivially bypassable by
                // sending nine characters.
                return Self::charge(guard);
            }
        };

        if super::tokens::constant_time_eq(&candidate, &slot.code) {
            *guard = None;
            return ClaimResult::Ok;
        }
        Self::charge(guard)
    }

    fn charge(mut guard: std::sync::MutexGuard<'_, Option<Slot>>) -> ClaimResult {
        let burned = {
            let slot = guard.as_mut().expect("charged against a live slot");
            slot.failures += 1;
            slot.failures >= PAIRING_MAX_FAILURES
        };
        if burned {
            *guard = None;
            ClaimResult::RateLimited
        } else {
            ClaimResult::Invalid
        }
    }
}
