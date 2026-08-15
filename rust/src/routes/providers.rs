use crate::state::AppState;
use axum::Json;
use axum::extract::State;
use serde_json::Value;

/// Providers with their availability and model lists.
///
/// Every per-provider failure is swallowed, exactly as the Python route does:
/// one provider whose availability probe throws must not take the list down,
/// because the list is what the phone's model picker reads.
pub async fn list_providers(State(state): State<AppState>) -> Json<Vec<Value>> {
    Json(state.providers.as_ref().clone())
}
