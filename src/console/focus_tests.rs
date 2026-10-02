//! Native focus must produce a visible, contrasting indicator, not just a tree state.
use super::theme;
use eframe::egui::{self, Color32};
use egui::accesskit::{Action, ActionRequest, TreeId};

pub(crate) fn audit(label: &str, mut draw: impl FnMut(&mut egui::Ui)) -> Vec<String> {
    fn luminance(c: Color32) -> f64 {
        let linear = |v: u8| {
            let v = f64::from(v) / 255.0;
            if v <= 0.04045 {
                v / 12.92
            } else {
                ((v + 0.055) / 1.055).powf(2.4)
            }
        };
        0.2126 * linear(c.r()) + 0.7152 * linear(c.g()) + 0.0722 * linear(c.b())
    }
    let mut failures = Vec::new();
    for (palette, panel) in [egui::Theme::Light, egui::Theme::Dark]
        .into_iter()
        .flat_map(|palette| [false, true].map(|panel| (palette, panel)))
    {
        let ctx = egui::Context::default();
        ctx.enable_accesskit();
        theme::install(&ctx);
        ctx.set_theme(palette);
        theme::refresh(&ctx);
        let surface = if panel { theme::panel() } else { theme::bg() };
        let mut render = |events| {
            let mut output = ctx.run_ui(
                egui::RawInput {
                    events,
                    ..Default::default()
                },
                |ui| {
                    theme::refresh(&ctx);
                    ui.painter().rect_filled(ui.max_rect(), 0.0, surface);
                    draw(ui);
                },
            );
            output.textures_delta.clear();
            output
        };
        let mut before = render(vec![]);
        for _ in 0..2 {
            before = render(vec![]);
        }
        let tree = before.platform_output.accesskit_update.as_ref().unwrap();
        let (id, node) = tree
            .nodes
            .iter()
            .find(|(_, node)| node.label() == Some(label))
            .unwrap();
        let (id, bounds) = (*id, node.bounds().unwrap());
        assert!(!node.is_disabled() && node.supports_action(Action::Focus));
        render(vec![egui::Event::AccessKitActionRequest(ActionRequest {
            action: Action::Focus,
            target_tree: TreeId::ROOT,
            target_node: id,
            data: None,
        })]);
        let after = render(vec![]);
        let focused_node = after
            .platform_output
            .accesskit_update
            .as_ref()
            .unwrap()
            .nodes
            .iter()
            .find(|(node_id, _)| *node_id == id)
            .unwrap()
            .1
            .clone();
        assert_eq!(
            focused_node.bounds(),
            Some(bounds),
            "focus must not resize the control"
        );
        assert_eq!(
            after
                .platform_output
                .accesskit_update
                .as_ref()
                .unwrap()
                .focus,
            id
        );
        let frames = |output: &egui::FullOutput| {
            output
                .shapes
                .iter()
                .filter_map(|shape| match &shape.shape {
                    egui::Shape::Rect(rect)
                        if (f64::from(rect.rect.left()) - bounds.x0).abs() <= 4.0
                            && (f64::from(rect.rect.right()) - bounds.x1).abs() <= 4.0
                            && (f64::from(rect.rect.top()) - bounds.y0).abs() <= 4.0
                            && (f64::from(rect.rect.bottom()) - bounds.y1).abs() <= 4.0 =>
                    {
                        Some(rect.clone())
                    }
                    _ => None,
                })
                .collect::<Vec<_>>()
        };
        let old = frames(&before);
        let new = frames(&after);
        let fill = new.first().map_or(surface, |rect| surface.blend(rect.fill));
        let contrasting_new_outline = new.iter().any(|rect| {
            let changed = !old
                .iter()
                .any(|prior| prior.rect == rect.rect && prior.stroke == rect.stroke);
            let color = fill.blend(rect.stroke.color);
            let (a, b) = (luminance(color), luminance(fill));
            changed && rect.stroke.width >= 1.0 && (a.max(b) + 0.05) / (a.min(b) + 0.05) >= 3.0
        });
        if !contrasting_new_outline {
            failures.push(format!("{label} {palette:?} panel={panel}: native focus has no new contrasting outline; old={old:?}, new={new:?}"));
        }
    }
    failures
}
