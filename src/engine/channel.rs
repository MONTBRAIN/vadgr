use tokio_util::sync::CancellationToken;

#[derive(Clone)]
pub struct PendingChannel {
    cancelled: CancellationToken,
}

impl PendingChannel {
    pub fn new(cancelled: CancellationToken) -> Self {
        Self { cancelled }
    }

    pub async fn park(&self) -> Result<(), String> {
        self.cancelled.cancelled().await;
        Err("run was cancelled while awaiting owner input".to_owned())
    }
}
