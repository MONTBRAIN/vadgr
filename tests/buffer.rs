//! The replay buffer used by released mobile `0.4.1` after a reconnect.
//!
//! The compatibility adapter holds 500 frames and replays them on connect. It
//! leaves with the quarantined watch route at `0.6.0`.

use serde_json::json;
use vadgr_daemon::ws::manager::{ConnectionManager, MAX_BUFFER};

#[test]
fn a_late_connector_gets_the_history_before_any_live_frame() {
    let m = ConnectionManager::new();
    for i in 0..3 {
        m.broadcast("r1", json!({ "type": "output", "seq": i }));
    }
    let (_rx, replay) = m.connect("r1");
    assert_eq!(replay.len(), 3);
    assert_eq!(replay[0]["seq"], 0, "in order");
    assert_eq!(replay[2]["seq"], 2);
}

#[test]
fn the_buffer_is_capped_at_five_hundred() {
    let m = ConnectionManager::new();
    for i in 0..(MAX_BUFFER + 50) {
        m.broadcast("r1", json!({ "seq": i }));
    }
    assert_eq!(m.buffered_len("r1"), MAX_BUFFER);
    let (_rx, replay) = m.connect("r1");
    assert_eq!(replay.len(), MAX_BUFFER);
    // The cap drops the newest, not the oldest, which is what the Python does:
    // it appends only while under the cap. Recorded because it is surprising
    // and because the frame counts would show it either way.
    assert_eq!(replay[MAX_BUFFER - 1]["seq"], (MAX_BUFFER - 1) as i64);
}

#[test]
fn buffers_do_not_leak_across_runs() {
    let m = ConnectionManager::new();
    m.broadcast("r1", json!({ "seq": 0 }));
    let (_rx, replay) = m.connect("r2");
    assert!(replay.is_empty());
}

#[tokio::test]
async fn a_subscriber_receives_what_is_broadcast_after_it_connects() {
    let m = ConnectionManager::new();
    let (mut rx, replay) = m.connect("r1");
    assert!(replay.is_empty());
    m.broadcast("r1", json!({ "type": "status", "status": "running" }));
    let got = rx.recv().await.unwrap();
    assert_eq!(got["status"], "running");
}

#[test]
fn revoking_a_device_signals_every_socket_watching_it() {
    // Revocation that only applied to the next request would leave a socket
    // streaming to a phone the owner just unpaired. The watch channel is how
    // the signal actually reaches a live socket's select loop.
    let m = ConnectionManager::new();
    let mut first = m.watch_device("d1");
    let mut second = m.watch_device("d1");
    let mut other = m.watch_device("d2");
    m.disconnect_device("d1");
    assert!(
        first.try_recv().is_ok(),
        "the first socket hears the revocation"
    );
    assert!(second.try_recv().is_ok(), "so does the second");
    assert!(
        other.try_recv().is_err(),
        "another device's socket does not"
    );
    // Idempotent: revoking twice is not an error, because the phone may retry.
    m.disconnect_device("d1");
}
