//! The fan-out, and the 500-frame replay buffer.
//!
//! Released mobile `0.4.1` uses this replay to recover after a reconnect. The
//! compatibility adapter stays until the watch route is replaced at `0.6.0`.

use serde_json::Value;
use std::collections::HashMap;
use std::sync::Mutex;
use tokio::sync::broadcast;

/// The compatibility cap used by the released phone.
pub const MAX_BUFFER: usize = 500;

struct RunChannel {
    tx: broadcast::Sender<Value>,
    buffer: Vec<Value>,
}

#[derive(Default)]
pub struct ConnectionManager {
    channels: Mutex<HashMap<String, RunChannel>>,
    /// One revocation channel per device with live sockets. Every socket the
    /// device owns watches it, so revoking the device can drop them **now**:
    /// revocation that only applies to the next request leaves a live socket
    /// streaming to a phone the owner just unpaired.
    device_revocations: Mutex<HashMap<String, broadcast::Sender<()>>>,
}

impl ConnectionManager {
    pub fn new() -> Self {
        Self::default()
    }

    /// Subscribe, and take the replay with you.
    ///
    /// The buffered frames are returned rather than pushed so the caller sends
    /// them before its first live frame, in order. **The replay is the first
    /// thing a client sees and it is counted**, which is what makes a
    /// per-socket frame count a meaningful comparison at all.
    pub fn connect(&self, run_id: &str) -> (broadcast::Receiver<Value>, Vec<Value>) {
        let mut channels = self.channels.lock().expect("ws mutex poisoned");
        let entry = channels
            .entry(run_id.to_string())
            .or_insert_with(|| RunChannel {
                tx: broadcast::channel(1024).0,
                buffer: Vec::new(),
            });
        (entry.tx.subscribe(), entry.buffer.clone())
    }

    pub fn broadcast(&self, run_id: &str, event: Value) {
        let mut channels = self.channels.lock().expect("ws mutex poisoned");
        let entry = channels
            .entry(run_id.to_string())
            .or_insert_with(|| RunChannel {
                tx: broadcast::channel(1024).0,
                buffer: Vec::new(),
            });
        // Always buffer, so a late connector gets the history - capped, so a
        // long run cannot grow it without bound.
        if entry.buffer.len() < MAX_BUFFER {
            entry.buffer.push(event.clone());
        }
        let _ = entry.tx.send(event);
    }

    pub fn buffered_len(&self, run_id: &str) -> usize {
        self.channels
            .lock()
            .expect("ws mutex poisoned")
            .get(run_id)
            .map(|c| c.buffer.len())
            .unwrap_or(0)
    }

    /// The signal a socket owned by this device selects on. Fires when the
    /// device is revoked; the socket answers by closing itself.
    pub fn watch_device(&self, device_id: &str) -> broadcast::Receiver<()> {
        self.device_revocations
            .lock()
            .expect("ws mutex poisoned")
            .entry(device_id.to_string())
            .or_insert_with(|| broadcast::channel(1).0)
            .subscribe()
    }

    /// Drop every socket this device holds. Called by `DELETE /api/devices/{id}`.
    /// Idempotent: revoking a device with no sockets, or twice, is not an error.
    pub fn disconnect_device(&self, device_id: &str) {
        if let Some(tx) = self
            .device_revocations
            .lock()
            .expect("ws mutex poisoned")
            .remove(device_id)
        {
            let _ = tx.send(());
        }
    }

    /// Whether this device currently owns at least one live socket.
    pub fn device_connected(&self, device_id: &str) -> bool {
        self.device_revocations
            .lock()
            .expect("ws mutex poisoned")
            .get(device_id)
            .is_some_and(|sender| sender.receiver_count() > 0)
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn device_connection_status_follows_live_receivers() {
        let manager = ConnectionManager::new();
        assert!(!manager.device_connected("device-1"));
        let receiver = manager.watch_device("device-1");
        assert!(manager.device_connected("device-1"));
        drop(receiver);
        assert!(!manager.device_connected("device-1"));
    }
}
