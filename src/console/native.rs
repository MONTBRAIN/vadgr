//! Native window options shared by the console and installer.

use eframe::egui;

pub(crate) fn options(viewport: egui::ViewportBuilder) -> eframe::NativeOptions {
    let mut options = eframe::NativeOptions {
        viewport,
        ..Default::default()
    };
    if cfg!(target_os = "linux") {
        // Wayland can withhold frame callbacks while a window is covered.
        // Waiting for vsync on the UI thread would stall native actions,
        // including Close, until the window is uncovered.
        options.glow_options.vsync = false;
    }
    options
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn native_options_preserve_the_requested_viewport() {
        let viewport = egui::ViewportBuilder::default()
            .with_title("Window options test")
            .with_inner_size([760.0, 620.0])
            .with_min_inner_size([680.0, 540.0]);
        assert_eq!(options(viewport.clone()).viewport, viewport);
    }

    #[test]
    fn native_options_keep_linux_actions_independent_of_swap_callbacks() {
        let options = options(egui::ViewportBuilder::default());
        if cfg!(target_os = "linux") {
            assert!(!options.glow_options.vsync);
        } else {
            assert_eq!(
                options.glow_options.vsync,
                eframe::NativeOptions::default().glow_options.vsync
            );
        }
    }
}
