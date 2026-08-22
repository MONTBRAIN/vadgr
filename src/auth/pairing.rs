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
    /// Which admission window this code opened. Changes on every transition
    /// of the slot, so a connection admitted under one window can be told
    /// apart from one admitted under the next.
    window: WindowId,
}

/// One admission window: the life of one outstanding pairing code. The id
/// changes on **every** transition of the one slot - mint, redeem, burn on
/// the fifth failure, and expiry - so it is a fact a transport can hold and
/// compare, not a boolean it has to poll.
pub type WindowId = u64;

pub struct PairingStore {
    ttl: Duration,
    slot: Mutex<Option<Slot>>,
    /// Counts transitions. The value itself is the current window id when a
    /// live code is outstanding.
    transitions: Mutex<WindowId>,
    /// Wakes the built-in transport's reaper on every transition, so a
    /// connection admitted under an ended window is closed rather than aged
    /// out.
    notify: tokio::sync::watch::Sender<WindowId>,
}

impl PairingStore {
    pub fn new(ttl_seconds: u64) -> Self {
        let (notify, _) = tokio::sync::watch::channel(0);
        Self {
            ttl: Duration::from_secs(ttl_seconds),
            slot: Mutex::new(None),
            transitions: Mutex::new(0),
            notify,
        }
    }

    fn next_window(&self) -> WindowId {
        let mut guard = self.transitions.lock().expect("pairing mutex poisoned");
        *guard += 1;
        *guard
    }

    fn transition(&self, id: WindowId) {
        let _ = self.notify.send(id);
    }

    /// The live admission window and its deadline, or `None` when no
    /// unexpired code is outstanding. Expiry is evaluated here, lazily, which
    /// is why the reaper also arms a timer at the deadline: an expiring
    /// window must close connections at the expiry, not at the next claim.
    pub fn window(&self) -> Option<(WindowId, Instant)> {
        let guard = self.slot.lock().expect("pairing mutex poisoned");
        guard.as_ref().and_then(|slot| {
            (Instant::now() < slot.expires_at).then_some((slot.window, slot.expires_at))
        })
    }

    /// Told on every transition of the slot, rather than polling for one.
    pub fn subscribe(&self) -> tokio::sync::watch::Receiver<WindowId> {
        self.notify.subscribe()
    }

    /// Mint a code, replacing any outstanding one, live or expired.
    pub fn mint(&self) -> String {
        let display = generate_pairing_code();
        let normalized = normalize_pairing_code(&display).expect("minted code normalises");
        let window = self.next_window();
        {
            let mut guard = self.slot.lock().expect("pairing mutex poisoned");
            *guard = Some(Slot {
                code: normalized,
                expires_at: Instant::now() + self.ttl,
                failures: 0,
                window,
            });
        }
        self.transition(window);
        display
    }

    pub fn redeem(&self, presented: &str) -> ClaimResult {
        let result = self.redeem_locked(presented);
        if matches!(
            result,
            ClaimResult::Ok | ClaimResult::Expired | ClaimResult::RateLimited
        ) {
            // The slot transitioned, so every reaper watching the window is
            // told. Outside the slot lock, because a watch send can wake a
            // task that immediately reads the window back.
            let id = self.next_window();
            self.transition(id);
        }
        result
    }

    fn redeem_locked(&self, presented: &str) -> ClaimResult {
        let now = Instant::now();
        let candidate = normalize_pairing_code(presented);
        let mut guard = self.slot.lock().expect("pairing mutex poisoned");
        let Some(slot) = guard.as_mut() else {
            return ClaimResult::Invalid;
        };
        let Some(candidate) = candidate else {
            // Malformed input never reaches the counter, so garbage cannot
            // burn a code: only eight well-formed wrong characters can. The
            // cap defends the code against guessing, and a guess that could
            // never match any code is not a guess at this one.
            return ClaimResult::Invalid;
        };
        let matches = super::tokens::constant_time_eq(&candidate, &slot.code);
        if now >= slot.expires_at {
            // The slot is held until it is minted over, so the RIGHT code
            // typed late still answers Expired - "ask for a new one" -
            // instead of decaying into unknown.
            if matches {
                *guard = None;
                return ClaimResult::Expired;
            }
            // A wrong guess at a dead code counts for nothing.
            return ClaimResult::Invalid;
        }
        if matches {
            *guard = None; // single-use, even on the fifth try
            return ClaimResult::Ok;
        }
        slot.failures += 1;
        if slot.failures >= PAIRING_MAX_FAILURES {
            *guard = None; // burned; the true code is now dead too
            return ClaimResult::RateLimited;
        }
        ClaimResult::Invalid
    }
}
