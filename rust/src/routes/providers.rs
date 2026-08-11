use crate::state::AppState;
use axum::extract::State;
use axum::Json;
use serde_json::{json, Value};

/// Providers with their availability and model lists.
///
/// Every per-provider failure is swallowed, exactly as the Python route does:
/// one provider whose availability probe throws must not take the list down,
/// because the list is what the phone's model picker reads.
pub async fn list_providers(State(state): State<AppState>) -> Json<Vec<Value>> {
    let raw = crate::config::load_providers(&state.config.providers_path);
    let result = raw
        .into_iter()
        .map(|(key, cfg)| {
            let available = crate::config::provider_available(&cfg);
            json!({
                "id": key,
                "name": cfg.name.clone().unwrap_or_else(|| key.clone()),
                "available": available,
                // Published verbatim: the file's `{id, name}` maps, in the
                // file's order.
                "models": cfg.models,
            })
        })
        .collect();
    Json(result)
}
