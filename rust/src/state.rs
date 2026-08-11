//! What every handler is given.

use crate::auth::pairing::PairingStore;
use crate::config::Config;
use crate::db::Db;
use crate::transport::Transport;
use crate::ws::manager::ConnectionManager;
use std::sync::Arc;

#[derive(Clone)]
pub struct AppState {
    pub db: Db,
    pub config: Arc<Config>,
    pub transport: Arc<dyn Transport>,
    pub pairing: Arc<PairingStore>,
    pub ws: Arc<ConnectionManager>,
}
