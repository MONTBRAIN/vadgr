//! The pairing code: mint, redeem, the five-attempt cap, and the split verdicts.
//!
//! Every case here is carried from the Python behaviour before the Rust
//! implementation, not read back off it. A test written from the code it tests
//! asserts that the code does what it does.

use vadgr_daemon::auth::pairing::{ClaimResult, PAIRING_MAX_FAILURES, PairingStore};
use vadgr_daemon::auth::tokens::{CROCKFORD_ALPHABET, hash_token, normalize_pairing_code};

#[test]
fn a_minted_code_is_grouped_and_normalises_to_eight_symbols() {
    let store = PairingStore::new(300);
    let code = store.mint();
    assert_eq!(code.len(), 9, "XXXX-XXXX");
    assert_eq!(code.as_bytes()[4], b'-');
    let normalized = normalize_pairing_code(&code).expect("a minted code normalises");
    assert_eq!(normalized.len(), 8);
    assert!(normalized.bytes().all(|b| CROCKFORD_ALPHABET.contains(&b)));
}

#[test]
fn the_alphabet_excludes_the_confusable_letters() {
    // The exclusions are the whole point: a person reads this off a terminal
    // and types it on a phone, and 0/O and 1/I/L are where that goes wrong.
    for ch in *b"ILOU" {
        assert!(
            !CROCKFORD_ALPHABET.contains(&ch),
            "{} must not be in the alphabet",
            ch as char
        );
    }
}

#[test]
fn typing_is_forgiven_the_way_the_server_decides_not_each_client() {
    let store = PairingStore::new(300);
    let code = store.mint();
    let mangled = code.to_lowercase().replace('-', " ");
    assert_eq!(store.redeem(&mangled), ClaimResult::Ok);
}

#[test]
fn a_code_is_claimable_exactly_once() {
    let store = PairingStore::new(300);
    let code = store.mint();
    assert_eq!(store.redeem(&code), ClaimResult::Ok);
    assert_eq!(
        store.redeem(&code),
        ClaimResult::Invalid,
        "a used code is not claimable"
    );
}

#[test]
fn minting_supersedes_whatever_was_outstanding() {
    // One slot, not a map. It is what makes "five attempts against this code"
    // well defined at all.
    let store = PairingStore::new(300);
    let first = store.mint();
    let second = store.mint();
    assert_eq!(store.redeem(&first), ClaimResult::Invalid);
    assert_eq!(store.redeem(&second), ClaimResult::Ok);
}

#[test]
fn the_fifth_failure_burns_the_code_and_says_so_once() {
    let store = PairingStore::new(300);
    let _code = store.mint();
    for attempt in 1..PAIRING_MAX_FAILURES {
        assert_eq!(
            store.redeem("00000000"),
            ClaimResult::Invalid,
            "attempt {attempt} is not yet the cap"
        );
    }
    // Fired exactly once, at the moment the cap acts: the one moment "too many
    // attempts" is a fact distinct from "not claimable".
    assert_eq!(store.redeem("00000000"), ClaimResult::RateLimited);
    // and afterwards the code is simply gone, not rate-limited for ever
    assert_eq!(store.redeem("00000000"), ClaimResult::Invalid);
}

#[test]
fn malformed_input_never_reaches_the_counter() {
    // Garbage cannot burn a code: only eight well-formed wrong characters
    // can. The cap defends the code against guessing, and anyone able to
    // reach the endpoint could otherwise kill a live pairing with noise.
    let store = PairingStore::new(300);
    let code = store.mint();
    for _ in 0..(PAIRING_MAX_FAILURES * 2) {
        assert_eq!(store.redeem("nope"), ClaimResult::Invalid);
    }
    assert_eq!(
        store.redeem(&code),
        ClaimResult::Ok,
        "the code survived the noise"
    );
}

#[test]
fn an_expired_code_is_expired_and_not_merely_invalid() {
    // 410 rather than 401 downstream, and the split is the point: the phone
    // tells the owner to ask for a new code instead of that they mistyped.
    let store = PairingStore::new(0);
    let code = store.mint();
    std::thread::sleep(std::time::Duration::from_millis(5));
    assert_eq!(store.redeem(&code), ClaimResult::Expired);
}

#[test]
fn only_the_right_code_typed_late_answers_expired() {
    // A wrong guess at a dead code counts for nothing and learns nothing:
    // answering Expired to any guess would tell a guesser a code existed. The
    // slot is held until it is minted over, so the RIGHT code typed late
    // still answers Expired afterwards.
    let store = PairingStore::new(0);
    let code = store.mint();
    std::thread::sleep(std::time::Duration::from_millis(5));
    assert_eq!(store.redeem("00000000"), ClaimResult::Invalid);
    assert_eq!(store.redeem("junk"), ClaimResult::Invalid);
    assert_eq!(store.redeem(&code), ClaimResult::Expired);
    // and consuming the expiry verdict clears the slot
    assert_eq!(store.redeem(&code), ClaimResult::Invalid);
}

#[test]
fn redeeming_with_nothing_outstanding_is_invalid() {
    let store = PairingStore::new(300);
    assert_eq!(store.redeem("ABCD1234"), ClaimResult::Invalid);
}

#[test]
fn a_device_token_has_the_shape_token_urlsafe_produces() {
    // 32 bytes of entropy, url-safe base64, no padding: 43 characters. The
    // phone stores whatever it is handed, so the shape only has to stay
    // consistent between the two daemons - and it does, by construction.
    let token = vadgr_daemon::auth::tokens::generate_token();
    assert_eq!(token.len(), 43);
    assert!(
        token
            .bytes()
            .all(|b| b.is_ascii_alphanumeric() || b == b'-' || b == b'_')
    );
}

#[test]
fn only_the_hash_is_ever_storable_and_it_is_stable() {
    // Same digest the Python side stores, so a device paired against one daemon
    // authenticates against the other during the migration.
    assert_eq!(
        hash_token("hello"),
        "2cf24dba5fb0a30e26e83b2ac5b9e29e1b161e5c1fa7425e73043362938b9824"
    );
}
