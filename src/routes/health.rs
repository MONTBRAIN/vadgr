use crate::config::VERSION;
use crate::state::AppState;
use axum::Json;
use axum::extract::State;
use serde_json::{Value, json};

/// Unauthenticated: it is the phone's post-pair connectivity probe, so it has
/// to answer before a token exists.
/// Whether a module is **usable**, which is installed and switched on.
///
/// The published contract is that this field answers usability and never says
/// why: `false` covers a module that is absent and one the owner disabled. It
/// read `venv_ready` alone, so a machine whose owner had just run
/// `vadgr computer-use disable` still advertised the module as usable, and the
/// setting and the health block disagreed with each other on the same daemon.
fn module_usable(status: &Value) -> bool {
    let installed = status["venv_ready"].as_bool().unwrap_or(false);
    // Absent means not enabled: a status that predates the field should not
    // silently report a disabled module as usable.
    let enabled = status["enabled"].as_bool().unwrap_or(false);
    installed && enabled
}

pub async fn health(State(state): State<AppState>) -> Json<Value> {
    let computer_use_usable = module_usable(&state.computer_use_status.read().unwrap());
    Json(json!({
        "status": "healthy",
        "modules": { "computer_use": computer_use_usable },
        "platform": crate::platform::machine_platform(),
        "version": VERSION,
        "transport": state.transport.status(),
    }))
}

#[cfg(test)]
mod tests {
    use super::module_usable;
    use serde_json::json;

    /// A module the owner switched off is not usable, however installed it is.
    ///
    /// This field read `venv_ready` alone, so `vadgr computer-use disable` left
    /// the setting reading `false` while health still said the module was
    /// usable. The two answers came from the same daemon and disagreed.
    #[test]
    fn a_disabled_module_is_not_usable() {
        assert!(!module_usable(
            &json!({"venv_ready": true, "enabled": false})
        ));
    }

    #[test]
    fn an_absent_module_is_not_usable_even_when_enabled() {
        assert!(!module_usable(
            &json!({"venv_ready": false, "enabled": true})
        ));
    }

    #[test]
    fn installed_and_enabled_is_usable() {
        assert!(module_usable(&json!({"venv_ready": true, "enabled": true})));
    }

    /// A status that carries neither field reports not usable rather than
    /// defaulting to usable, so a missing field never advertises a module.
    #[test]
    fn an_unknown_status_is_not_usable() {
        assert!(!module_usable(&json!({})));
    }
}
