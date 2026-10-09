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

/// The size a window asks for and the smallest size its layout supports.
#[derive(Clone, Copy, Debug, PartialEq)]
pub(crate) struct WindowSize {
    pub(crate) default: egui::Vec2,
    pub(crate) min: egui::Vec2,
}

impl WindowSize {
    pub(crate) fn viewport(self) -> egui::ViewportBuilder {
        egui::ViewportBuilder::default()
            .with_inner_size(self.default)
            .with_min_inner_size(self.min)
    }
}

/// Keeps a new window at a size its layout supports.
///
/// eframe limits a new window to the monitor size divided by the monitor's
/// scale factor. On Wayland that factor is the integer output scale, so with
/// GNOME fractional scaling (a 1920 by 1080 display at 125 or 150 percent,
/// for example) the window opens below its minimum and cuts off content. Such
/// a monitor is too small for the default size anyway, so maximize the window,
/// as GNOME does at map time for a window nearly as large as the screen.
/// Maximizing also keeps the window on screen, which a plain resize of an
/// already placed window does not.
///
/// The window learns its monitor only after GNOME shows it, and GNOME can
/// withhold the frame callbacks that drive later frames for seconds. The first
/// frame therefore estimates the monitor from eframe's own limit: the window
/// opened at the monitor size divided by the integer output scale, which GNOME
/// sets to the fractional scale rounded up.
pub(crate) struct InitialSize {
    default: egui::Vec2,
    min: egui::Vec2,
    done: bool,
    requested_at: Option<std::time::Instant>,
    attempts: u8,
}

/// Room for the desktop's top bar and the window's title bar. GNOME refuses
/// to maximize a window whose minimum does not fit beside them and then
/// grows it to the minimum where it stands, partly off the screen.
const DESKTOP_CHROME: egui::Vec2 = egui::vec2(0.0, 64.0);

/// GNOME can drop a maximize request that arrives while it is still placing a
/// new window, so an unanswered request is sent again a few times.
const RETRY_AFTER: std::time::Duration = std::time::Duration::from_millis(500);
const MAX_ATTEMPTS: u8 = 6;

impl InitialSize {
    pub(crate) fn new(size: WindowSize) -> Self {
        Self {
            default: size.default,
            min: size.min,
            done: false,
            requested_at: None,
            attempts: 0,
        }
    }

    pub(crate) fn check(&mut self, ctx: &egui::Context) {
        if self.done {
            return;
        }
        let (current, monitor, scale, maximized) = ctx.input(|input| {
            let viewport = input.viewport();
            (
                input.viewport_rect().size(),
                viewport.monitor_size,
                viewport.native_pixels_per_point,
                viewport.maximized,
            )
        });
        // Frames only run on input, so keep checking until this settles.
        ctx.request_repaint_after(RETRY_AFTER);
        let Some(monitor) =
            monitor.or_else(|| scale.map(|scale| estimated_monitor(current, self.default, scale)))
        else {
            return;
        };
        // Once the window fits, later sizes are the user's or the
        // compositor's and stay as they are.
        if !should_maximize(current, monitor, self.min) {
            self.done = true;
            return;
        }
        // Maximized but not yet resized: the compositor is applying it.
        if maximized == Some(true) {
            return;
        }
        if self
            .requested_at
            .is_some_and(|requested| requested.elapsed() < RETRY_AFTER)
        {
            return;
        }
        if self.attempts == MAX_ATTEMPTS {
            self.done = true;
            return;
        }
        self.attempts += 1;
        self.requested_at = Some(std::time::Instant::now());
        ctx.send_viewport_cmd(egui::ViewportCommand::Maximized(true));
    }
}

/// The monitor size in points, from the size eframe limited the window to.
/// A dimension eframe did not limit only bounds the monitor from below.
fn estimated_monitor(current: egui::Vec2, default: egui::Vec2, scale: f32) -> egui::Vec2 {
    let output_scale = scale.ceil().max(1.0);
    let limited = |current: f32, default: f32| {
        if current + 0.5 < default {
            current
        } else {
            default
        }
    };
    egui::vec2(limited(current.x, default.x), limited(current.y, default.y)) * output_scale / scale
}

fn should_maximize(current: egui::Vec2, monitor: egui::Vec2, min: egui::Vec2) -> bool {
    // Half a point absorbs rounding between physical pixels and points.
    let opened_below = current.x + 0.5 < min.x || current.y + 0.5 < min.y;
    let room = monitor - DESKTOP_CHROME;
    opened_below && room.x >= min.x && room.y >= min.y
}

#[cfg(test)]
mod tests {
    use super::*;

    const CONSOLE: WindowSize = WindowSize {
        default: egui::vec2(1200.0, 720.0),
        min: egui::vec2(900.0, 600.0),
    };

    const INSTALLER: WindowSize = WindowSize {
        default: egui::vec2(760.0, 620.0),
        min: egui::vec2(680.0, 540.0),
    };

    fn frame(
        ctx: &egui::Context,
        size: &mut InitialSize,
        current: egui::Vec2,
        monitor: Option<egui::Vec2>,
    ) -> Vec<egui::ViewportCommand> {
        frame_maximized(ctx, size, current, monitor, None)
    }

    fn first_frame(
        ctx: &egui::Context,
        size: &mut InitialSize,
        current: egui::Vec2,
        scale: f32,
    ) -> Vec<egui::ViewportCommand> {
        let mut input = egui::RawInput {
            screen_rect: Some(egui::Rect::from_min_size(egui::Pos2::ZERO, current)),
            ..Default::default()
        };
        input
            .viewports
            .entry(egui::ViewportId::ROOT)
            .or_default()
            .native_pixels_per_point = Some(scale);
        let mut output = ctx.run_ui(input, |ui| size.check(ui.ctx()));
        output.textures_delta.clear();
        output
            .viewport_output
            .get(&egui::ViewportId::ROOT)
            .map(|viewport| viewport.commands.clone())
            .unwrap_or_default()
            .into_iter()
            .filter(|command| matches!(command, egui::ViewportCommand::Maximized(_)))
            .collect()
    }

    fn frame_maximized(
        ctx: &egui::Context,
        size: &mut InitialSize,
        current: egui::Vec2,
        monitor: Option<egui::Vec2>,
        maximized: Option<bool>,
    ) -> Vec<egui::ViewportCommand> {
        let mut input = egui::RawInput {
            screen_rect: Some(egui::Rect::from_min_size(egui::Pos2::ZERO, current)),
            ..Default::default()
        };
        let viewport = input.viewports.entry(egui::ViewportId::ROOT).or_default();
        viewport.monitor_size = monitor;
        viewport.maximized = maximized;
        let mut output = ctx.run_ui(input, |ui| size.check(ui.ctx()));
        output.textures_delta.clear();
        output
            .viewport_output
            .get(&egui::ViewportId::ROOT)
            .map(|viewport| viewport.commands.clone())
            .unwrap_or_default()
            .into_iter()
            // egui sets the theme on its first frame; only sizing matters here.
            .filter(|command| {
                matches!(
                    command,
                    egui::ViewportCommand::InnerSize(_) | egui::ViewportCommand::Maximized(_)
                )
            })
            .collect()
    }

    #[test]
    fn a_window_opened_below_its_minimum_is_maximized_once_its_monitor_is_known() {
        // GNOME at 150 percent on a 1920x1080 display: eframe opened the
        // console at 960x540 points on a 1280x720 point monitor.
        let ctx = egui::Context::default();
        let mut size = InitialSize::new(CONSOLE);
        let small = egui::vec2(960.0, 540.0);
        assert!(frame(&ctx, &mut size, small, None).is_empty());
        assert_eq!(
            frame(&ctx, &mut size, small, Some(egui::vec2(1280.0, 720.0))),
            vec![egui::ViewportCommand::Maximized(true)]
        );
        assert!(frame(&ctx, &mut size, small, Some(egui::vec2(1280.0, 720.0))).is_empty());
    }

    #[test]
    fn the_first_frame_estimates_the_monitor_from_the_limited_size() {
        // 1920x1080 at 125 percent: GNOME reports output scale 2, so eframe
        // limited the console to 960x540; the monitor is 1536x864 points.
        assert_eq!(
            estimated_monitor(egui::vec2(960.0, 540.0), CONSOLE.default, 1.25),
            egui::vec2(1536.0, 864.0)
        );
        // An unlimited dimension stays at the default and bounds from below.
        assert_eq!(
            estimated_monitor(egui::vec2(1200.0, 720.0), CONSOLE.default, 1.0),
            egui::vec2(1200.0, 720.0)
        );
    }

    #[test]
    fn an_undersized_window_is_maximized_before_its_monitor_is_reported() {
        let ctx = egui::Context::default();
        let mut size = InitialSize::new(CONSOLE);
        assert_eq!(
            first_frame(&ctx, &mut size, egui::vec2(960.0, 540.0), 1.5),
            vec![egui::ViewportCommand::Maximized(true)]
        );
        // 1280x800 at 125 percent has no room for the console's minimum.
        let mut size = InitialSize::new(CONSOLE);
        assert!(first_frame(&ctx, &mut size, egui::vec2(640.0, 400.0), 1.25).is_empty());
        // The installer's smaller minimum fits the same monitor.
        let mut size = InitialSize::new(INSTALLER);
        assert_eq!(
            first_frame(&ctx, &mut size, egui::vec2(640.0, 400.0), 1.25),
            vec![egui::ViewportCommand::Maximized(true)]
        );
    }

    #[test]
    fn a_maximize_the_compositor_dropped_is_sent_again() {
        // GNOME at 125 percent on 1280x800 left the installer at 640x400 in
        // one of five launches after a single request.
        let ctx = egui::Context::default();
        let mut size = InitialSize::new(INSTALLER);
        let small = egui::vec2(640.0, 400.0);
        let monitor = Some(egui::vec2(1024.0, 640.0));
        assert_eq!(
            frame(&ctx, &mut size, small, monitor),
            vec![egui::ViewportCommand::Maximized(true)]
        );
        size.requested_at = Some(std::time::Instant::now() - RETRY_AFTER);
        assert_eq!(
            frame_maximized(&ctx, &mut size, small, monitor, Some(false)),
            vec![egui::ViewportCommand::Maximized(true)]
        );
    }

    #[test]
    fn a_maximize_in_progress_is_not_repeated() {
        let ctx = egui::Context::default();
        let mut size = InitialSize::new(INSTALLER);
        let small = egui::vec2(640.0, 400.0);
        let monitor = Some(egui::vec2(1024.0, 640.0));
        assert_eq!(frame(&ctx, &mut size, small, monitor).len(), 1);
        size.requested_at = Some(std::time::Instant::now() - RETRY_AFTER);
        assert!(frame_maximized(&ctx, &mut size, small, monitor, Some(true)).is_empty());
    }

    #[test]
    fn retries_stop_after_the_limit_or_once_the_window_fits() {
        let ctx = egui::Context::default();
        let small = egui::vec2(640.0, 400.0);
        let monitor = Some(egui::vec2(1024.0, 640.0));
        let mut size = InitialSize::new(INSTALLER);
        let mut sent = 0;
        for _ in 0..20 {
            sent += frame(&ctx, &mut size, small, monitor).len();
            size.requested_at = Some(std::time::Instant::now() - RETRY_AFTER);
        }
        assert_eq!(sent, usize::from(MAX_ATTEMPTS));

        let mut size = InitialSize::new(INSTALLER);
        assert_eq!(frame(&ctx, &mut size, small, monitor).len(), 1);
        assert!(frame(&ctx, &mut size, egui::vec2(957.0, 576.0), monitor).is_empty());
        size.requested_at = Some(std::time::Instant::now() - RETRY_AFTER);
        assert!(frame(&ctx, &mut size, small, monitor).is_empty());
    }

    #[test]
    fn a_window_below_its_minimum_in_one_dimension_is_maximized() {
        let monitor = egui::vec2(1536.0, 864.0);
        assert!(should_maximize(
            egui::vec2(960.0, 540.0),
            monitor,
            CONSOLE.min
        ));
        assert!(should_maximize(
            egui::vec2(899.0, 720.0),
            monitor,
            CONSOLE.min
        ));
    }

    #[test]
    fn a_window_at_or_above_its_minimum_is_left_alone() {
        let monitor = egui::vec2(1536.0, 960.0);
        for current in [
            egui::vec2(1200.0, 720.0),
            egui::vec2(960.0, 600.0),
            egui::vec2(900.0, 600.0),
            egui::vec2(899.6, 600.0),
        ] {
            assert!(
                !should_maximize(current, monitor, CONSOLE.min),
                "{current:?}"
            );
        }
    }

    #[test]
    fn a_monitor_without_room_for_the_minimum_keeps_the_window_on_screen() {
        // 125 percent on a 1280x800 display leaves 1024x640 points: GNOME
        // cannot maximize a 900x600 minimum beside its bars.
        assert!(!should_maximize(
            egui::vec2(640.0, 400.0),
            egui::vec2(1024.0, 640.0),
            CONSOLE.min
        ));
        // The installer's smaller minimum fits the same monitor.
        assert!(should_maximize(
            egui::vec2(640.0, 400.0),
            egui::vec2(1024.0, 640.0),
            egui::vec2(680.0, 540.0)
        ));
    }

    #[test]
    fn a_correctly_sized_window_is_never_resized_later() {
        let ctx = egui::Context::default();
        let mut size = InitialSize::new(CONSOLE);
        let monitor = Some(egui::vec2(1280.0, 800.0));
        assert!(frame(&ctx, &mut size, egui::vec2(1200.0, 720.0), monitor).is_empty());
        assert!(frame(&ctx, &mut size, egui::vec2(640.0, 400.0), monitor).is_empty());
    }

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
