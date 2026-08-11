//! The phone stream's framing: internal broadcast events become published
//! `RunEvent` frames, and internal names never reach that wire.
//!
//! The two sockets share the fan-out and differ only here, which is why the
//! translation is a function a test can hold still.

use serde_json::json;
use vadgr_daemon::ws::run_ws::to_run_event;

#[test]
fn each_broadcast_type_maps_to_its_published_member() {
    let cases = [
        ("run_started", "started"),
        ("agent_started", "tool_call"),
        ("agent_log", "output"),
        ("agent_completed", "output"),
        ("awaiting", "paused"),
        ("agent_failed", "failed"),
        ("run_completed", "completed"),
        ("run_failed", "failed"),
    ];
    for (internal, published) in cases {
        let event = to_run_event(&json!({ "type": internal, "data": { "k": "v" } }))
            .unwrap_or_else(|| panic!("{internal} must map"));
        assert_eq!(event["type"], published, "for {internal}");
        assert_eq!(event["payload"], json!({ "k": "v" }));
    }
}

#[test]
fn awaiting_reaches_the_phone_as_paused() {
    // `awaiting` is how a gate says it is waiting for a human; an earlier map
    // dropped it, and an approval could never reach the device that has to
    // answer it. Pinned on its own for that history.
    let event = to_run_event(&json!({ "type": "awaiting", "data": {} })).unwrap();
    assert_eq!(event["type"], "paused");
}

#[test]
fn the_types_waiting_on_a_vocabulary_decision_are_dropped() {
    // Understood and deliberately not translatable yet: no member exists for
    // them, and inventing one here would name a published frame in the wrong
    // place.
    assert!(to_run_event(&json!({ "type": "todos", "data": [] })).is_none());
    assert!(to_run_event(&json!({ "type": "run_resumed" })).is_none());
}

#[test]
fn an_unknown_type_is_dropped_not_leaked() {
    assert!(to_run_event(&json!({ "type": "something_new" })).is_none());
    assert!(to_run_event(&json!({ "no_type": true })).is_none());
}

#[test]
fn the_broadcasts_timestamp_rides_along_and_a_bad_one_is_replaced() {
    let event = to_run_event(&json!({
        "type": "run_started",
        "timestamp": "2026-08-11T10:00:00.000000+00:00",
    }))
    .unwrap();
    assert_eq!(event["timestamp"], "2026-08-11T10:00:00.000000+00:00");

    let event = to_run_event(&json!({ "type": "run_started", "timestamp": "yesterday-ish" }))
        .unwrap();
    let stamped = event["timestamp"].as_str().unwrap();
    assert!(stamped.contains('T'), "a real timestamp stands in: {stamped}");
}

#[test]
fn a_missing_payload_is_an_empty_object_never_absent() {
    let event = to_run_event(&json!({ "type": "run_completed" })).unwrap();
    assert_eq!(event["payload"], json!({}));
    let keys: Vec<&str> = event.as_object().unwrap().keys().map(|s| s.as_str()).collect();
    assert_eq!(keys.len(), 3, "type, timestamp, payload and nothing else");
}
