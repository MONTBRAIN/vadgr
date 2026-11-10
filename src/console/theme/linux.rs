//! Linux appearance comes from the desktop portal, not winit's absent theme.

use eframe::egui;
use std::sync::Once;
use std::sync::atomic::{AtomicU32, Ordering};
use std::time::Duration;

const REFRESH: Duration = Duration::from_secs(1);
const CALL_TIMEOUT: Duration = Duration::from_secs(2);
static START: Once = Once::new();
static SCHEME: AtomicU32 = AtomicU32::new(0);

pub(super) fn start() {
    // One process-wide worker retains no window or egui Context. Portal calls
    // never run on the UI thread, including connection setup and recovery.
    START.call_once(|| {
        let _ = std::thread::Builder::new()
            .name("desktop-appearance".into())
            .spawn(|| {
                loop {
                    SCHEME.store(read_scheme().unwrap_or(0), Ordering::Relaxed);
                    std::thread::sleep(REFRESH);
                }
            });
    });
}

fn read_scheme() -> Option<u32> {
    let connection = zbus::blocking::connection::Builder::session()
        .ok()?
        .method_timeout(CALL_TIMEOUT)
        .build()
        .ok()?;
    let proxy = zbus::blocking::Proxy::new(
        &connection,
        "org.freedesktop.portal.Desktop",
        "/org/freedesktop/portal/desktop",
        "org.freedesktop.portal.Settings",
    )
    .ok()?;
    let value: zbus::zvariant::OwnedValue = proxy
        .call("Read", &("org.freedesktop.appearance", "color-scheme"))
        .ok()?;
    decode(&value)
}

fn decode(mut value: &zbus::zvariant::Value<'_>) -> Option<u32> {
    // Read can wrap a setting in a second variant on older portal backends.
    // Bound the compatibility unwrapping and reject every non-u32 value.
    for _ in 0..=4 {
        match value {
            zbus::zvariant::Value::U32(scheme) => return Some(*scheme),
            zbus::zvariant::Value::Value(inner) => value = inner,
            _ => return None,
        }
    }
    None
}

pub(super) fn refresh(ctx: &egui::Context) {
    apply(ctx, SCHEME.load(Ordering::Relaxed));
    // A covered or idle window still observes changes without a busy loop.
    ctx.request_repaint_after(REFRESH);
}

fn apply(ctx: &egui::Context, scheme: u32) {
    ctx.set_theme(match scheme {
        1 => egui::ThemePreference::Dark,
        2 => egui::ThemePreference::Light,
        _ => egui::ThemePreference::System,
    });
}

#[cfg(test)]
mod tests {
    use super::*;
    use egui::Theme;

    #[test]
    fn portal_decoder_accepts_plain_and_nested_values_but_bounds_unwrapping() {
        use zbus::zvariant::Value;
        let mut value = Value::U32(2);
        for _ in 0..=4 {
            assert_eq!(decode(&value), Some(2));
            value = Value::Value(Box::new(value));
        }
        assert_eq!(decode(&value), None);
        assert_eq!(decode(&Value::Bool(true)), None);
        assert_eq!(decode(&Value::I32(2)), None);
    }

    #[test]
    #[ignore = "read-only diagnostic requires a running native desktop portal"]
    fn native_portal_read_only_diagnostic() {
        let scheme = read_scheme();
        println!("Native portal color-scheme: {scheme:?}");
        assert!(matches!(scheme, Some(0..=2)));
    }

    #[test]
    fn portal_changes_select_the_registered_palettes() {
        let ctx = egui::Context::default();
        super::super::install(&ctx);
        for (scheme, expected) in [(2, Theme::Light), (1, Theme::Dark), (2, Theme::Light)] {
            apply(&ctx, scheme);
            assert_eq!(ctx.theme(), expected);
            assert_eq!(
                ctx.global_style().visuals.dark_mode,
                expected == Theme::Dark
            );
        }
    }

    #[test]
    fn absent_unknown_and_failed_reads_return_to_the_normal_fallback() {
        let ctx = egui::Context::default();
        ctx.set_theme(egui::ThemePreference::System);
        let fallback = ctx.theme();
        for scheme in [Some(0), Some(3), Some(u32::MAX), None] {
            apply(&ctx, 2);
            apply(&ctx, scheme.unwrap_or(0));
            assert_eq!(ctx.system_theme(), None);
            assert_eq!(ctx.theme(), fallback);
            assert_eq!(
                ctx.options(|o| o.theme_preference),
                egui::ThemePreference::System
            );
        }
        apply(&ctx, 2);
        assert_eq!(ctx.theme(), Theme::Light);
    }

    #[test]
    fn ui_refresh_uses_only_cached_state_and_a_bounded_repaint() {
        // Keep the worker entry compiled, but unit tests never connect to the
        // host's bus. Refresh does not invoke it or perform any bus operation.
        let _worker_entry: fn() = start;
        let ctx = egui::Context::default();
        let mut output = ctx.run_ui(egui::RawInput::default(), |ui| refresh(ui.ctx()));
        output.textures_delta.clear();
        assert!(output.viewport_output[&egui::ViewportId::ROOT].repaint_delay <= REFRESH);
        assert_eq!(CALL_TIMEOUT, Duration::from_secs(2));
    }
}
