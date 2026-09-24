use eframe::egui::{
    self, Color32, CornerRadius, FontData, FontDefinitions, FontFamily, FontId, Stroke, Theme,
};
use std::sync::Arc;
use std::sync::atomic::{AtomicBool, Ordering};

static DARK_MODE: AtomicBool = AtomicBool::new(true);

#[derive(Clone, Copy)]
struct Palette {
    bg: Color32,
    panel: Color32,
    tertiary: Color32,
    nav: Color32,
    input: Color32,
    panel_hover: Color32,
    text: Color32,
    muted: Color32,
    border: Color32,
    success: Color32,
    warning: Color32,
    info: Color32,
    danger: Color32,
    accent: Color32,
}

const DARK: Palette = Palette {
    bg: Color32::from_rgb(20, 20, 19),
    panel: Color32::from_rgb(30, 29, 27),
    tertiary: Color32::from_rgb(35, 34, 32),
    nav: Color32::from_rgb(24, 23, 22),
    input: Color32::from_rgb(37, 36, 34),
    panel_hover: Color32::from_rgb(53, 51, 48),
    text: Color32::from_rgb(244, 243, 238),
    muted: Color32::from_rgb(176, 174, 165),
    border: Color32::from_rgb(42, 40, 37),
    success: Color32::from_rgb(120, 140, 93),
    warning: Color32::from_rgb(201, 168, 76),
    info: Color32::from_rgb(106, 155, 204),
    danger: Color32::from_rgb(199, 93, 93),
    accent: Color32::from_rgb(212, 207, 199),
};

const LIGHT: Palette = Palette {
    bg: Color32::from_rgb(244, 243, 238),
    panel: Color32::from_rgb(255, 255, 255),
    tertiary: Color32::from_rgb(249, 248, 244),
    nav: Color32::from_rgb(250, 250, 246),
    input: Color32::from_rgb(240, 238, 230),
    panel_hover: Color32::from_rgb(236, 234, 223),
    text: Color32::from_rgb(20, 20, 19),
    muted: Color32::from_rgb(107, 105, 97),
    border: Color32::from_rgb(232, 230, 220),
    success: Color32::from_rgb(106, 125, 79),
    warning: Color32::from_rgb(168, 135, 46),
    info: Color32::from_rgb(90, 135, 181),
    danger: Color32::from_rgb(184, 76, 76),
    accent: Color32::from_rgb(92, 88, 80),
};

pub fn install(ctx: &egui::Context) {
    install_fonts(ctx);
    ctx.set_theme(egui::ThemePreference::System);
    ctx.set_style_of(Theme::Dark, style(DARK, true));
    ctx.set_style_of(Theme::Light, style(LIGHT, false));
    refresh(ctx);
}

fn install_fonts(ctx: &egui::Context) {
    let mut fonts = FontDefinitions::empty();
    add_font(
        &mut fonts,
        "dm-sans",
        include_bytes!("../../assets/fonts/DMSans-Bold.ttf"),
    );
    add_font(
        &mut fonts,
        "inter",
        include_bytes!("../../assets/fonts/Inter-Regular.ttf"),
    );
    add_font(
        &mut fonts,
        "inter-medium",
        include_bytes!("../../assets/fonts/Inter-Medium.ttf"),
    );
    add_font(
        &mut fonts,
        "jetbrains-mono",
        include_bytes!("../../assets/fonts/JetBrainsMono-Regular.ttf"),
    );
    fonts.families.insert(
        heading_family(),
        vec!["dm-sans".to_owned(), "inter".to_owned()],
    );
    fonts.families.insert(
        FontFamily::Proportional,
        vec!["inter".to_owned(), "dm-sans".to_owned()],
    );
    fonts.families.insert(
        medium_family(),
        vec!["inter-medium".to_owned(), "inter".to_owned()],
    );
    fonts
        .families
        .insert(FontFamily::Monospace, vec!["jetbrains-mono".to_owned()]);
    ctx.set_fonts(fonts);
}

fn add_font(fonts: &mut FontDefinitions, name: &str, bytes: &'static [u8]) {
    fonts
        .font_data
        .insert(name.to_owned(), Arc::new(FontData::from_static(bytes)));
}

pub fn heading_family() -> FontFamily {
    FontFamily::Name(Arc::from("DM Sans"))
}

pub fn medium_family() -> FontFamily {
    FontFamily::Name(Arc::from("Inter Medium"))
}

pub fn refresh(ctx: &egui::Context) {
    DARK_MODE.store(ctx.theme() == Theme::Dark, Ordering::Relaxed);
}

fn style(palette: Palette, dark_mode: bool) -> egui::Style {
    let mut style = egui::Style::default();
    style.visuals.dark_mode = dark_mode;
    style.visuals.panel_fill = palette.bg;
    style.visuals.window_fill = palette.panel;
    style.visuals.extreme_bg_color = palette.input;
    style.visuals.faint_bg_color = palette.tertiary;
    style.visuals.override_text_color = Some(palette.text);
    style.visuals.weak_text_color = Some(palette.muted);
    style.visuals.hyperlink_color = palette.info;
    style.visuals.warn_fg_color = palette.warning;
    style.visuals.error_fg_color = palette.danger;
    style.visuals.selection.bg_fill = palette.tertiary;
    style.visuals.selection.stroke = Stroke::new(1.0, palette.text);
    style.visuals.widgets.noninteractive.bg_fill = palette.panel;
    style.visuals.widgets.noninteractive.bg_stroke = Stroke::new(1.0, palette.border);
    style.visuals.widgets.noninteractive.fg_stroke = Stroke::new(1.0, palette.text);
    style.visuals.widgets.inactive.bg_fill = Color32::TRANSPARENT;
    style.visuals.widgets.inactive.bg_stroke = Stroke::new(1.0, palette.border);
    style.visuals.widgets.inactive.fg_stroke = Stroke::new(1.0, palette.text);
    style.visuals.widgets.hovered.bg_fill = palette.tertiary;
    style.visuals.widgets.hovered.bg_stroke = Stroke::new(1.0, palette.panel_hover);
    style.visuals.widgets.hovered.fg_stroke = Stroke::new(1.0, palette.text);
    style.visuals.widgets.active.bg_fill = palette.tertiary;
    // Strong text uses this foreground. Primary controls supply their own contrast.
    style.visuals.widgets.active.fg_stroke = Stroke::new(1.0, palette.text);
    style.visuals.widgets.open.bg_fill = palette.tertiary;
    style.visuals.widgets.open.bg_stroke = Stroke::new(1.0, palette.panel_hover);
    style.visuals.widgets.open.fg_stroke = Stroke::new(1.0, palette.text);
    for visual in [
        &mut style.visuals.widgets.inactive,
        &mut style.visuals.widgets.hovered,
        &mut style.visuals.widgets.active,
        &mut style.visuals.widgets.open,
    ] {
        visual.corner_radius = CornerRadius::same(10);
    }
    style.spacing.button_padding = egui::vec2(13.0, 8.0);
    style.spacing.item_spacing = egui::vec2(10.0, 8.0);
    style.text_styles.insert(
        egui::TextStyle::Heading,
        FontId::new(25.0, heading_family()),
    );
    style.text_styles.insert(
        egui::TextStyle::Body,
        FontId::new(13.0, FontFamily::Proportional),
    );
    style
        .text_styles
        .insert(egui::TextStyle::Button, FontId::new(12.0, medium_family()));
    style.text_styles.insert(
        egui::TextStyle::Monospace,
        FontId::new(11.0, FontFamily::Monospace),
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
pub fn nav() -> Color32 {
    palette().nav
}
pub fn text() -> Color32 {
    palette().text
}
pub fn panel() -> Color32 {
    palette().panel
}
pub fn tertiary() -> Color32 {
    palette().tertiary
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
pub fn accent() -> Color32 {
    palette().accent
}
pub fn accent_text() -> Color32 {
    palette().bg
}

pub fn card() -> egui::Frame {
    egui::Frame::new()
        .fill(panel())
        .stroke(Stroke::new(1.0, border()))
        .corner_radius(15)
        .inner_margin(egui::Margin::same(16))
}
