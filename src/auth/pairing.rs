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

    /// Close the current pairing window. Returns false when no live window exists.
    pub fn cancel(&self) -> bool {
        let cancelled = {
            let mut guard = self.slot.lock().expect("pairing mutex poisoned");
            if guard
                .as_ref()
                .is_some_and(|slot| Instant::now() < slot.expires_at)
            {
                *guard = None;
                true
            } else {
                false
            }
        };
        if cancelled {
            let id = self.next_window();
            self.transition(id);
        }
        cancelled
    }

    /// Redeem a code. **The transition is not announced here**: the caller
    /// announces it with [`settled`] once the claim's own work is done.
    ///
    /// It used to be announced here, and that cost a release. A reaper woken
    /// by the transition asks the database whether the peer is bound, and on
    /// a successful claim the binding is written by the caller *after* this
    /// returns. So the reaper saw an unbound peer on a window that had just
    /// ended, and closed the very connection the claim was answering on. The
    /// daemon paired the device, wrote the row, returned `200`, and the phone
    /// never received it, because the connection carrying it was gone
    /// fourteen milliseconds earlier. Found on a handheld away-case pass, and
    /// predicted word for word by the reaper's own doc comment.
    pub fn redeem(&self, presented: &str) -> ClaimResult {
        self.redeem_locked(presented)
    }

    /// Announce the transition this claim caused, after the caller has
    /// finished everything the claim implies: the device row, and the binding
    /// that decides whether the connection survives the window it arrived on.
    ///
    /// Safe to call for any outcome. Only the three that move the slot
    /// announce anything, so a wrong guess costs nothing and a forgotten call
    /// is the bug this exists to stop.
    pub fn settled(&self, result: ClaimResult) {
        if matches!(
            result,
            ClaimResult::Ok | ClaimResult::Expired | ClaimResult::RateLimited
        ) {
            // Outside the slot lock, because a watch send can wake a task
            // that immediately reads the window back.
            let id = self.next_window();
            self.transition(id);
        }
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

#[cfg(test)]
mod transition_tests {
    use super::{ClaimResult, PairingStore};

    /// Redeeming must not wake a reaper on its own.
    ///
    /// The reaper's job is to close connections whose window ended, keeping
    /// the ones whose peer is now bound. On a successful claim the binding is
    /// written by the caller *after* redeem returns, so a transition
    /// announced inside redeem reaches the reaper while the peer still looks
    /// unbound, and it closes the connection the claim is answering on. That
    /// is not hypothetical: a handheld pass paired a device, wrote its row,
    /// returned 200, and the phone never saw the response, because the
    /// connection carrying it was closed fourteen milliseconds earlier.
    #[test]
    fn redeeming_does_not_announce_the_transition_by_itself() {
        let store = PairingStore::new(300);
        let code = store.mint();
        let watcher = store.subscribe();

        assert_eq!(store.redeem(&code), ClaimResult::Ok);

        assert!(
            !watcher.has_changed().expect("the channel is open"),
            "redeem announced the transition before the caller could bind \
             the peer, which is what closes the claim's own connection",
        );
    }

    /// And the announcement still happens, once the caller says so. A fix
    /// that simply stopped announcing would leave every unbound connection
    /// alive until its own timer, which is the opposite defect.
    #[test]
    fn settling_announces_it() {
        let store = PairingStore::new(300);
        let code = store.mint();
        let watcher = store.subscribe();

        let outcome = store.redeem(&code);
        store.settled(outcome);

        assert!(
            watcher.has_changed().expect("the channel is open"),
            "nothing woke the reaper, so a connection on the ended window \
             would live until its own lifetime ran out",
        );
    }

    /// An outcome that moved the slot without binding anything still
    /// announces: the window ended, and connections admitted under it must go.
    #[test]
    fn an_expired_code_also_announces_when_settled() {
        let store = PairingStore::new(0);
        let code = store.mint();
        let watcher = store.subscribe();

        let outcome = store.redeem(&code);
        assert_eq!(outcome, ClaimResult::Expired);
        store.settled(outcome);

        assert!(watcher.has_changed().expect("the channel is open"));
    }

    /// A wrong code moves nothing, so it announces nothing: waking every
    /// reaper on each mistyped character is work for no reason.
    #[test]
    fn a_wrong_code_announces_nothing() {
        let store = PairingStore::new(300);
        let _ = store.mint();
        let watcher = store.subscribe();

        let outcome = store.redeem("ZZZZ-ZZZZ");
        assert_eq!(outcome, ClaimResult::Invalid);
        store.settled(outcome);

        assert!(!watcher.has_changed().expect("the channel is open"));
    }

    #[test]
    fn cancelling_closes_and_announces_the_live_window() {
        let store = PairingStore::new(300);
        let _ = store.mint();
        let watcher = store.subscribe();

        assert!(store.cancel());
        assert!(store.window().is_none());
        assert!(watcher.has_changed().expect("the channel is open"));
        assert!(!store.cancel());
    }
}
