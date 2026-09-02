use eframe::egui::{self, Color32, CornerRadius, FontFamily, FontId, Stroke, Theme};
use std::sync::atomic::{AtomicBool, Ordering};

static DARK_MODE: AtomicBool = AtomicBool::new(true);

#[derive(Clone, Copy)]
struct Palette {
    bg: Color32,
    panel: Color32,
    panel_hover: Color32,
    text: Color32,
    muted: Color32,
    border: Color32,
    success: Color32,
    warning: Color32,
    danger: Color32,
}

const DARK: Palette = Palette {
    bg: Color32::from_rgb(18, 18, 17),
    panel: Color32::from_rgb(27, 27, 25),
    panel_hover: Color32::from_rgb(37, 36, 34),
    text: Color32::from_rgb(244, 242, 235),
    muted: Color32::from_rgb(181, 178, 168),
    border: Color32::from_rgb(47, 46, 42),
    success: Color32::from_rgb(139, 161, 102),
    warning: Color32::from_rgb(222, 186, 75),
    danger: Color32::from_rgb(206, 91, 82),
};

const LIGHT: Palette = Palette {
    bg: Color32::from_rgb(247, 246, 241),
    panel: Color32::from_rgb(255, 255, 253),
    panel_hover: Color32::from_rgb(235, 234, 229),
    text: Color32::from_rgb(24, 24, 22),
    muted: Color32::from_rgb(103, 99, 91),
    border: Color32::from_rgb(224, 221, 212),
    success: Color32::from_rgb(105, 128, 69),
    warning: Color32::from_rgb(167, 122, 25),
    danger: Color32::from_rgb(184, 60, 55),
};

pub fn install(ctx: &egui::Context) {
    ctx.set_theme(egui::ThemePreference::System);
    ctx.set_style_of(Theme::Dark, style(DARK, true));
    ctx.set_style_of(Theme::Light, style(LIGHT, false));
    refresh(ctx);
}

pub fn refresh(ctx: &egui::Context) {
    DARK_MODE.store(ctx.theme() == Theme::Dark, Ordering::Relaxed);
}

fn style(palette: Palette, dark_mode: bool) -> egui::Style {
    let mut style = egui::Style::default();
    style.visuals.dark_mode = dark_mode;
    style.visuals.panel_fill = palette.bg;
    style.visuals.window_fill = palette.panel;
    style.visuals.extreme_bg_color = palette.panel;
    style.visuals.faint_bg_color = palette.panel_hover;
    style.visuals.override_text_color = Some(palette.text);
    style.visuals.widgets.noninteractive.bg_fill = palette.panel;
    style.visuals.widgets.noninteractive.bg_stroke = Stroke::new(1.0, palette.border);
    style.visuals.widgets.inactive.bg_fill = palette.panel;
    style.visuals.widgets.inactive.bg_stroke = Stroke::new(1.0, palette.border);
    style.visuals.widgets.hovered.bg_fill = palette.panel_hover;
    style.visuals.widgets.hovered.bg_stroke = Stroke::new(1.0, palette.muted);
    style.visuals.widgets.active.bg_fill = palette.text;
    style.visuals.widgets.active.fg_stroke = Stroke::new(1.0, palette.bg);
    style.visuals.widgets.inactive.corner_radius = CornerRadius::same(10);
    style.visuals.widgets.hovered.corner_radius = CornerRadius::same(10);
    style.visuals.widgets.active.corner_radius = CornerRadius::same(10);
    style.spacing.button_padding = egui::vec2(14.0, 9.0);
    style.spacing.item_spacing = egui::vec2(10.0, 10.0);
    style.text_styles.insert(
        egui::TextStyle::Heading,
        FontId::new(25.0, FontFamily::Proportional),
    );
    style.text_styles.insert(
        egui::TextStyle::Body,
        FontId::new(14.0, FontFamily::Proportional),
    );
    style.text_styles.insert(
        egui::TextStyle::Monospace,
        FontId::new(12.0, FontFamily::Monospace),
    );
    style
}

fn palette() -> Palette {
    if DARK_MODE.load(Ordering::Relaxed) {
        DARK
    } else {
        LIGHT
    }
}

pub fn bg() -> Color32 {
    palette().bg
}
pub fn panel() -> Color32 {
    palette().panel
}
pub fn muted() -> Color32 {
    palette().muted
}
pub fn border() -> Color32 {
    palette().border
}
pub fn success() -> Color32 {
    palette().success
}
pub fn warning() -> Color32 {
    palette().warning
}
pub fn danger() -> Color32 {
    palette().danger
}

pub fn card() -> egui::Frame {
    egui::Frame::new()
        .fill(panel())
        .stroke(Stroke::new(1.0, border()))
        .corner_radius(15)
        .inner_margin(egui::Margin::same(16))
}
