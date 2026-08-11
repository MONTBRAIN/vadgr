//! The fan-out, and the 500-frame replay buffer.
//!
//! **The published architecture describes this as a lossy live view, and the code
//! is not that.** The divergence is dispositioned in the plan against this
//! release: `0.4.5` **reproduces** the buffer and does not fix it, because the
//! frame counts per socket are what judge this release and a replay buffer is
//! directly observable in them. "Fixed" and "wrong" would be the same
//! measurement. The fix belongs to `0.6.0`, which reshapes the stream.

use serde_json::Value;
use std::collections::HashMap;
use std::sync::Mutex;
use tokio::sync::broadcast;

/// `api/websocket/manager.py:11`, verbatim.
pub const MAX_BUFFER: usize = 500;

struct RunChannel {
    tx: broadcast::Sender<Value>,
    buffer: Vec<Value>,
}

#[derive(Default)]
pub struct ConnectionManager {
    channels: Mutex<HashMap<String, RunChannel>>,
    /// Sockets a device holds, so revoking that device can drop them now.
    /// Revocation that only applies to the next request leaves a live socket
    /// streaming to a phone the owner just unpaired.
    device_sockets: Mutex<HashMap<String, Vec<broadcast::Sender<Value>>>>,
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
        let entry = channels.entry(run_id.to_string()).or_insert_with(|| RunChannel {
            tx: broadcast::channel(1024).0,
            buffer: Vec::new(),
        });
        (entry.tx.subscribe(), entry.buffer.clone())
    }

    pub fn broadcast(&self, run_id: &str, event: Value) {
        let mut channels = self.channels.lock().expect("ws mutex poisoned");
        let entry = channels.entry(run_id.to_string()).or_insert_with(|| RunChannel {
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

    pub fn register_device_socket(&self, device_id: &str, tx: broadcast::Sender<Value>) {
        self.device_sockets
            .lock()
            .expect("ws mutex poisoned")
            .entry(device_id.to_string())
            .or_default()
            .push(tx);
    }

    /// Drop every socket this device holds. Called by `DELETE /api/devices/{id}`.
    pub fn disconnect_device(&self, device_id: &str) {
        self.device_sockets
            .lock()
            .expect("ws mutex poisoned")
            .remove(device_id);
    }
}
