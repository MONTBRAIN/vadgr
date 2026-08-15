//! What every handler is given.

use crate::auth::pairing::PairingStore;
use crate::computer_use_setup::SetupService;
use crate::config::Config;
use crate::db::Db;
use crate::transport::Transport;
use crate::ws::manager::ConnectionManager;
use serde_json::Value;
use std::sync::Arc;
use std::sync::RwLock;

#[derive(Clone)]
pub struct AppState {
    pub db: Db,
    pub config: Arc<Config>,
    pub transport: Arc<dyn Transport>,
    pub pairing: Arc<PairingStore>,
    pub ws: Arc<ConnectionManager>,
    pub providers: Arc<Vec<Value>>,
    pub computer_use_setup: Arc<SetupService>,
    pub computer_use_status: Arc<RwLock<Value>>,
}
