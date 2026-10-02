use super::*;
use eframe::App;
use egui::accesskit::{Action, ActionData, ActionRequest, Node, NodeId, Role, TreeId};

struct RecordingController(mpsc::Sender<(String, String)>);

impl ConsoleController for RecordingController {
    fn install_status(&self) -> Result<crate::install::InstallStatus> {
        unreachable!()
    }
    fn health(&self) -> Result<HealthSnapshot> {
        unreachable!()
    }
    fn machine(&self) -> Result<MachineSnapshot> {
        unreachable!()
    }
    fn update_machine(&self, _: &MachineEdit) -> Result<MachineSnapshot> {
        unreachable!()
    }
    fn devices(&self) -> Result<Vec<DeviceSnapshot>> {
        unreachable!()
    }
    fn providers(&self) -> Result<Vec<ProviderSnapshot>> {
        unreachable!()
    }
    fn start_pairing(&self) -> Result<PairingSession> {
        unreachable!()
    }
    fn cancel_pairing(&self) -> Result<()> {
        unreachable!()
    }
    fn revoke_device(&self, _: &str) -> Result<()> {
        unreachable!()
    }
    fn refresh_provider(&self, _: &str) -> Result<()> {
        unreachable!()
    }
    fn connect_api_key(&self, _: &str, _: String) -> Result<()> {
        unreachable!()
    }
    fn connect_oauth(&self, _: &str) -> Result<()> {
        unreachable!()
    }
    fn set_default_model(&self, provider: &str, model: &str) -> Result<()> {
        self.0.send((provider.into(), model.into())).unwrap();
        Err(anyhow!("The selected model is unavailable"))
    }
    fn disconnect_provider(&self, _: &str) -> Result<()> {
        unreachable!()
    }
    fn restart_daemon(&self) -> Result<()> {
        unreachable!()
    }
    fn set_launch_at_login(&self, _: bool) -> Result<()> {
        unreachable!()
    }
    fn check_for_updates(&self) -> Result<crate::install::UpdateCheck> {
        unreachable!()
    }
    fn apply_update(&self) -> Result<crate::install::UpdateCheck> {
        unreachable!()
    }
    fn rollback_installation(&self) -> Result<()> {
        unreachable!()
    }
    fn repair_installation(&self) -> Result<()> {
        unreachable!()
    }
    fn open_legal_notices(&self) -> Result<()> {
        unreachable!()
    }
    fn uninstall(&self, _: bool) -> Result<()> {
        unreachable!()
    }
}

fn provider() -> ProviderSnapshot {
    ProviderSnapshot {
        id: "gemini".into(),
        name: "Gemini".into(),
        connected: true,
        available: true,
        auth_method: Some("API key".into()),
        models: (0..40)
            .map(|i| super::super::controller::ModelSnapshot {
                id: format!("gemini-long-model-identifier-{i:02}-with-a-version-suffix"),
                name: format!("Gemini model {i:02} with a long descriptive display name"),
            })
            .collect(),
        default_model: Some("gemini-long-model-identifier-00-with-a-version-suffix".into()),
        ..Default::default()
    }
}

fn app(theme: egui::Theme) -> (egui::Context, ConsoleApp) {
    let ctx = egui::Context::default();
    ctx.enable_accesskit();
    theme::install(&ctx);
    ctx.set_theme(theme);
    let app = ConsoleApp {
        controller: Arc::new(HttpConsoleController::new("http://127.0.0.1:1").unwrap()),
        view: View::Providers,
        data: Some(ConsoleData {
            providers: vec![provider()],
            machine: MachineSnapshot {
                default_provider: Some("gemini".into()),
                default_model: provider().default_model,
                ..Default::default()
            },
            ..Default::default()
        }),
        pending: None,
        dialog: None,
        notice: None,
        available_update: None,
        last_refresh: std::time::Instant::now(),
    };
    (ctx, app)
}

fn draw(
    ctx: &egui::Context,
    app: &mut ConsoleApp,
    size: [f32; 2],
    events: Vec<egui::Event>,
) -> egui::FullOutput {
    let mut frame = eframe::Frame::_new_kittest();
    let mut output = ctx.run_ui(
        egui::RawInput {
            screen_rect: Some(egui::Rect::from_min_size(egui::Pos2::ZERO, size.into())),
            events,
            ..Default::default()
        },
        |root| app.ui(root, &mut frame),
    );
    output.textures_delta.clear();
    output
}

fn named<'a>(output: &'a egui::FullOutput, label: &str) -> (NodeId, &'a Node) {
    output
        .platform_output
        .accesskit_update
        .as_ref()
        .unwrap()
        .nodes
        .iter()
        .find(|(_, node)| node.label() == Some(label))
        .map(|(id, node)| (*id, node))
        .unwrap_or_else(|| panic!("missing {label}"))
}

fn click(id: NodeId) -> egui::Event {
    egui::Event::AccessKitActionRequest(ActionRequest {
        action: Action::Click,
        target_tree: TreeId::ROOT,
        target_node: id,
        data: None,
    })
}

fn value(output: &egui::FullOutput, text: &str) -> egui::Event {
    let id = output
        .platform_output
        .accesskit_update
        .as_ref()
        .unwrap()
        .nodes
        .iter()
        .find(|(_, node)| node.role() == Role::TextInput)
        .unwrap()
        .0;
    egui::Event::AccessKitActionRequest(ActionRequest {
        action: Action::SetValue,
        target_tree: TreeId::ROOT,
        target_node: id,
        data: Some(ActionData::Value(text.into())),
    })
}

fn model_label(index: usize) -> String {
    let p = provider();
    let model = &p.models[index];
    format!("{} ({})", model.name, model.id)
}

#[test]
fn native_search_and_draft_selection_do_not_mutate_until_confirmation() {
    let (ctx, mut app) = app(egui::Theme::Light);
    let (send, calls) = mpsc::channel();
    app.controller = Arc::new(RecordingController(send));
    let size = [900.0, 600.0];
    let output = open_models(&ctx, &mut app, size);
    assert!(named(&output, "Use as default").1.is_disabled());
    let output = draw(&ctx, &mut app, size, vec![value(&output, "MODEL 39")]);
    let label = model_label(39);
    let id = named(&output, &label).0;
    let output = draw(&ctx, &mut app, size, vec![click(id)]);
    assert!(!named(&output, "Use as default").1.is_disabled());
    assert!(app.pending.is_none() && calls.try_recv().is_err());
    let cancel = named(&output, "Cancel").0;
    draw(&ctx, &mut app, size, vec![click(cancel)]);
    assert!(app.dialog.is_none() && app.pending.is_none() && calls.try_recv().is_err());
    assert_eq!(
        app.data.as_ref().unwrap().machine.default_model,
        provider().default_model
    );

    let output = open_models(&ctx, &mut app, size);
    let output = draw(&ctx, &mut app, size, vec![value(&output, "identifier-39")]);
    let output = draw(&ctx, &mut app, size, vec![click(named(&output, &label).0)]);
    draw(
        &ctx,
        &mut app,
        size,
        vec![click(named(&output, "Use as default").0)],
    );
    let call = calls
        .recv_timeout(std::time::Duration::from_secs(2))
        .unwrap();
    assert_eq!(call, ("gemini".into(), provider().models[39].id.clone()));
    assert!(calls.try_recv().is_err());
    for _ in 0..100 {
        app.poll(&ctx);
        if app.pending.is_none() {
            break;
        }
        std::thread::yield_now();
    }
    assert_eq!(
        app.notice,
        Some((false, "The selected model is unavailable".into()))
    );
    assert_eq!(
        app.data.as_ref().unwrap().machine.default_model,
        provider().default_model
    );
}

#[test]
fn current_default_remains_accessible_after_draft_selection_moves() {
    for theme in [egui::Theme::Dark, egui::Theme::Light] {
        let (ctx, mut app) = app(theme);
        let size = [900.0, 600.0];
        let output = open_models(&ctx, &mut app, size);
        let next = named(&output, &model_label(1)).0;
        draw(&ctx, &mut app, size, vec![click(next)]);
        let output = draw(&ctx, &mut app, size, vec![]);
        let current = named(&output, &model_label(0)).1;
        let selected = named(&output, &model_label(1)).1;
        assert_eq!(current.description(), Some("Current default"));
        assert_eq!(current.toggled(), Some(egui::accesskit::Toggled::False));
        assert_eq!(selected.description(), None);
        assert_eq!(selected.toggled(), Some(egui::accesskit::Toggled::True));
        assert!(app.pending.is_none());
        assert_eq!(
            app.data.as_ref().unwrap().machine.default_model,
            provider().default_model
        );
    }
}

#[test]
fn another_providers_retained_model_can_become_the_machine_default() {
    let (ctx, mut app) = app(egui::Theme::Dark);
    let machine = &mut app.data.as_mut().unwrap().machine;
    machine.default_provider = Some("another-provider".into());
    machine.default_model = Some("another-model".into());
    let mut output = draw(&ctx, &mut app, [900.0, 600.0], vec![]);
    for _ in 0..2 {
        output = draw(&ctx, &mut app, [900.0, 600.0], vec![]);
    }
    assert!(
        output
            .platform_output
            .accesskit_update
            .as_ref()
            .unwrap()
            .nodes
            .iter()
            .any(|(_, node)| node.value() == Some("Not the machine default"))
    );
    let id = named(&output, "Make default").0;
    draw(&ctx, &mut app, [900.0, 600.0], vec![click(id)]);
    let output = draw(&ctx, &mut app, [900.0, 600.0], vec![]);
    assert!(!named(&output, "Use as default").1.is_disabled());
    assert!(
        output
            .platform_output
            .accesskit_update
            .as_ref()
            .unwrap()
            .nodes
            .iter()
            .all(|(_, node)| !node
                .value()
                .is_some_and(|text| text.contains("Current default")))
    );
    assert!(app.pending.is_none());
}

#[test]
fn native_focus_reveals_last_model_and_empty_search_keeps_cancel_visible() {
    for theme in [egui::Theme::Dark, egui::Theme::Light] {
        let (ctx, mut app) = app(theme);
        let size = [900.0, 600.0];
        let output = open_models(&ctx, &mut app, size);
        let id = named(&output, &model_label(39)).0;
        draw(
            &ctx,
            &mut app,
            size,
            vec![egui::Event::AccessKitActionRequest(ActionRequest {
                action: Action::Focus,
                target_tree: TreeId::ROOT,
                target_node: id,
                data: None,
            })],
        );
        let mut output = draw(&ctx, &mut app, size, vec![]);
        for _ in 0..5 {
            output = draw(&ctx, &mut app, size, vec![]);
        }
        let row = named(&output, &model_label(39)).1.bounds().unwrap();
        let list = output
            .platform_output
            .accesskit_update
            .as_ref()
            .unwrap()
            .nodes
            .iter()
            .filter(|(_, node)| node.role() == Role::ScrollBar && !node.is_disabled())
            .filter_map(|(_, node)| node.bounds())
            .find(|bounds| bounds.x0 > 600.0 && bounds.y0 > 100.0)
            .expect("model list viewport");
        assert!(
            row.y0 >= list.y0
                && row.y1 <= list.y1
                && row.y1 < named(&output, "Cancel").1.bounds().unwrap().y0,
            "last model not revealed: {row:?}"
        );
        let output = draw(&ctx, &mut app, size, vec![value(&output, "no-such-model")]);
        assert!(
            output
                .platform_output
                .accesskit_update
                .as_ref()
                .unwrap()
                .nodes
                .iter()
                .any(|(_, node)| node
                    .value()
                    .is_some_and(|text| text.starts_with("No matching models.")))
        );
        assert!(named(&output, "Cancel").1.bounds().unwrap().y1 <= 600.0);
        assert!(app.pending.is_none());
    }
}

#[test]
fn provider_actions_do_not_overlap_long_default_identifiers_at_minimum_width() {
    for theme in [egui::Theme::Light, egui::Theme::Dark] {
        let (ctx, mut app) = app(theme);
        let mut output = draw(&ctx, &mut app, [900.0, 600.0], vec![]);
        for _ in 0..2 {
            output = draw(&ctx, &mut app, [900.0, 600.0], vec![]);
        }
        let tree = output.platform_output.accesskit_update.as_ref().unwrap();
        let model = provider().default_model.unwrap();
        let label = tree
            .nodes
            .iter()
            .find(|(_, node)| node.value() == Some(model.as_str()))
            .unwrap()
            .1
            .bounds()
            .unwrap();
        let mut previous = None;
        for name in ["Change default", "Refresh models", "Disconnect"] {
            let bounds = named(&output, name).1.bounds().unwrap();
            assert!(bounds.y0 > label.y1 && bounds.x0 >= 180.0 && bounds.x1 <= 900.0);
            if let Some(right) = previous {
                assert!(bounds.x0 >= right, "actions overlap");
            }
            previous = Some(bounds.x1);
        }
    }
}

fn open_models(ctx: &egui::Context, app: &mut ConsoleApp, size: [f32; 2]) -> egui::FullOutput {
    let mut output = draw(ctx, app, size, vec![]);
    for _ in 0..2 {
        output = draw(ctx, app, size, vec![]);
    }
    let id = named(&output, "Change default").0;
    draw(ctx, app, size, vec![click(id)]);
    let mut output = draw(ctx, app, size, vec![]);
    for _ in 0..2 {
        output = draw(ctx, app, size, vec![]);
    }
    output
}

#[test]
fn model_picker_has_search_and_a_visible_reserved_footer_at_supported_sizes() {
    for theme in [egui::Theme::Light, egui::Theme::Dark] {
        for size in [[900.0, 600.0], [1200.0, 720.0]] {
            let (ctx, mut app) = app(theme);
            let output = open_models(&ctx, &mut app, size);
            assert!(
                output
                    .platform_output
                    .accesskit_update
                    .as_ref()
                    .unwrap()
                    .nodes
                    .iter()
                    .any(|(_, node)| node.role() == Role::TextInput),
                "search field is required"
            );
            for label in ["Cancel", "Use as default"] {
                let bounds = named(&output, label).1.bounds().unwrap();
                assert!(
                    bounds.y0 >= 0.0 && bounds.y1 <= f64::from(size[1]),
                    "{label} clipped: {bounds:?}"
                );
            }
            let nodes = &output
                .platform_output
                .accesskit_update
                .as_ref()
                .unwrap()
                .nodes;
            for (_, node) in nodes.iter().filter(|(_, node)| {
                node.role() == Role::TextInput
                    || node.value() == Some("Choose the default model")
                    || node.value() == Some("Search models")
            }) {
                let bounds = node.bounds().unwrap();
                assert!(
                    bounds.y0 >= 0.0 && bounds.y1 <= f64::from(size[1]),
                    "header/search clipped"
                );
            }
            assert!(app.pending.is_none());
        }
    }
}

#[test]
fn provider_choices_are_full_width_grouped_rows_not_a_tiny_button_stack() {
    let (ctx, mut app) = app(egui::Theme::Light);
    app.dialog = Some(Dialog::ProviderPicker(vec![provider()]));
    let mut output = draw(&ctx, &mut app, [900.0, 600.0], vec![]);
    for _ in 0..3 {
        output = draw(&ctx, &mut app, [900.0, 600.0], vec![]);
    }
    let bounds = named(&output, "Gemini").1.bounds().unwrap();
    assert!(
        bounds.width() >= 400.0 && bounds.height() >= 44.0,
        "choice is cramped: {bounds:?}"
    );
    let footer = named(&output, "Cancel").1.bounds().unwrap();
    assert!(
        footer.y0 - bounds.y1 >= 12.0,
        "footer is not separated from choices"
    );
}

#[test]
fn console_standard_buttons_have_readable_painted_contrast_in_both_themes() {
    fn luminance(color: Color32) -> f64 {
        let linear = |c: u8| {
            let v = f64::from(c) / 255.0;
            if v <= 0.04045 {
                v / 12.92
            } else {
                ((v + 0.055) / 1.055).powf(2.4)
            }
        };
        0.2126 * linear(color.r()) + 0.7152 * linear(color.g()) + 0.0722 * linear(color.b())
    }
    for theme in [egui::Theme::Light, egui::Theme::Dark] {
        let (ctx, mut app) = app(theme);
        let mut output = draw(&ctx, &mut app, [1200.0, 720.0], vec![]);
        for _ in 0..2 {
            output = draw(&ctx, &mut app, [1200.0, 720.0], vec![]);
        }
        for label in ["Change default", "Refresh models"] {
            let bounds = named(&output, label).1.bounds().unwrap();
            let text = output
                .shapes
                .iter()
                .find_map(|shape| match &shape.shape {
                    egui::Shape::Text(text) if text.galley.job.text == label => Some(text),
                    _ => None,
                })
                .expect("action text is painted");
            let specified = text.galley.job.sections[0].format.color;
            let foreground =
                text.override_text_color
                    .unwrap_or(if specified == Color32::PLACEHOLDER {
                        text.fallback_color
                    } else {
                        specified
                    });
            let background = output
                .shapes
                .iter()
                .find_map(|shape| match &shape.shape {
                    egui::Shape::Rect(rect)
                        if (f64::from(rect.rect.min.x) - bounds.x0).abs() < 1.0
                            && (f64::from(rect.rect.min.y) - bounds.y0).abs() < 1.0
                            && (f64::from(rect.rect.max.x) - bounds.x1).abs() < 1.0
                            && (f64::from(rect.rect.max.y) - bounds.y1).abs() < 1.0 =>
                    {
                        Some(rect.fill)
                    }
                    _ => None,
                })
                .expect("action background is painted");
            let background =
                Color32::from(egui::Rgba::from(theme::panel()).blend(egui::Rgba::from(background)));
            let foreground = Color32::from(egui::Rgba::from(background).blend(egui::Rgba::from(
                foreground.gamma_multiply(text.opacity_factor),
            )));
            let (a, b) = (luminance(foreground), luminance(background));
            let contrast = (a.max(b) + 0.05) / (a.min(b) + 0.05);
            assert!(
                contrast >= 4.5,
                "{label} {theme:?} contrast {contrast}: {foreground:?} on {background:?}"
            );
        }
    }
}

#[test]
fn console_action_states_keep_readable_colors_and_truthful_disabled_semantics() {
    fn render(ctx: &egui::Context, state: &str, events: Vec<egui::Event>) -> egui::FullOutput {
        let mut output = ctx.run_ui(
            egui::RawInput {
                events,
                ..Default::default()
            },
            |ui| {
                theme::refresh(ctx);
                let response = ui.add_enabled(
                    state != "disabled",
                    egui::Button::new("Test action").selected(state == "selected"),
                );
                let actual = (
                    response.hovered(),
                    response.has_focus(),
                    response.is_pointer_button_down_on(),
                );
                ctx.data_mut(|data| data.insert_temp(egui::Id::new("actual-action-state"), actual));
            },
        );
        output.textures_delta.clear();
        output
    }
    fn luminance(color: Color32) -> f64 {
        let linear = |c: u8| {
            let v = f64::from(c) / 255.0;
            if v <= 0.04045 {
                v / 12.92
            } else {
                ((v + 0.055) / 1.055).powf(2.4)
            }
        };
        0.2126 * linear(color.r()) + 0.7152 * linear(color.g()) + 0.0722 * linear(color.b())
    }
    for theme in [egui::Theme::Light, egui::Theme::Dark] {
        let mut enabled_normal = None;
        for state in [
            "normal", "hover", "focused", "pressed", "selected", "disabled",
        ] {
            let ctx = egui::Context::default();
            ctx.enable_accesskit();
            theme::install(&ctx);
            ctx.set_theme(theme);
            let mut output = render(&ctx, state, vec![]);
            for _ in 0..2 {
                output = render(&ctx, state, vec![]);
            }
            let (id, node) = named(&output, "Test action");
            let bounds = node.bounds().unwrap();
            let pos = egui::pos2(
                ((bounds.x0 + bounds.x1) / 2.0) as f32,
                ((bounds.y0 + bounds.y1) / 2.0) as f32,
            );
            if matches!(state, "hover" | "pressed") {
                render(&ctx, state, vec![egui::Event::PointerMoved(pos)]);
            }
            if state == "pressed" {
                render(
                    &ctx,
                    state,
                    vec![egui::Event::PointerButton {
                        pos,
                        button: egui::PointerButton::Primary,
                        pressed: true,
                        modifiers: egui::Modifiers::NONE,
                    }],
                );
            }
            if state == "focused" {
                output = render(
                    &ctx,
                    state,
                    vec![egui::Event::AccessKitActionRequest(ActionRequest {
                        action: Action::Focus,
                        target_tree: TreeId::ROOT,
                        target_node: id,
                        data: None,
                    })],
                );
                assert_eq!(
                    output
                        .platform_output
                        .accesskit_update
                        .as_ref()
                        .unwrap()
                        .focus,
                    id
                );
            }
            output = render(&ctx, state, vec![]);
            let actual = ctx
                .data(|data| {
                    data.get_temp::<(bool, bool, bool)>(egui::Id::new("actual-action-state"))
                })
                .unwrap();
            if state == "hover" {
                assert!(actual.0 && !actual.2);
            }
            if state == "focused" {
                assert!(actual.1);
            }
            if state == "pressed" {
                assert!(actual.2);
            }
            let node = named(&output, "Test action").1;
            assert_eq!(node.is_disabled(), state == "disabled");
            if state == "selected" {
                assert_eq!(node.toggled(), Some(egui::accesskit::Toggled::True));
            }
            let text = output
                .shapes
                .iter()
                .find_map(|shape| match &shape.shape {
                    egui::Shape::Text(text) if text.galley.job.text == "Test action" => Some(text),
                    _ => None,
                })
                .unwrap();
            let specified = text.galley.job.sections[0].format.color;
            let foreground =
                text.override_text_color
                    .unwrap_or(if specified == Color32::PLACEHOLDER {
                        text.fallback_color
                    } else {
                        specified
                    });
            let background = output
                .shapes
                .iter()
                .find_map(|shape| match &shape.shape {
                    egui::Shape::Rect(rect)
                        if (f64::from(rect.rect.min.x) - bounds.x0).abs() < 1.0
                            && (f64::from(rect.rect.min.y) - bounds.y0).abs() < 1.0
                            && (f64::from(rect.rect.max.x) - bounds.x1).abs() < 1.0
                            && (f64::from(rect.rect.max.y) - bounds.y1).abs() < 1.0 =>
                    {
                        Some(rect.fill)
                    }
                    _ => None,
                })
                .unwrap();
            let background =
                Color32::from(egui::Rgba::from(theme::bg()).blend(egui::Rgba::from(background)));
            let foreground = Color32::from(egui::Rgba::from(background).blend(egui::Rgba::from(
                foreground.gamma_multiply(text.opacity_factor),
            )));
            if state == "normal" {
                enabled_normal = Some((foreground, background));
            }
            if state == "disabled" {
                assert_ne!(foreground, background, "disabled text must remain visible");
                assert_ne!(
                    Some((foreground, background)),
                    enabled_normal,
                    "disabled state must be visually distinct"
                );
            } else {
                let (a, b) = (luminance(foreground), luminance(background));
                let contrast = (a.max(b) + 0.05) / (a.min(b) + 0.05);
                assert!(
                    contrast >= 4.5,
                    "{theme:?} {state}: contrast {contrast}, {foreground:?} on {background:?}"
                );
            }
        }
    }
}

#[test]
fn selected_model_text_and_enabled_confirmation_have_composited_contrast() {
    fn luminance(color: Color32) -> f64 {
        let linear = |c: u8| {
            let v = f64::from(c) / 255.0;
            if v <= 0.04045 {
                v / 12.92
            } else {
                ((v + 0.055) / 1.055).powf(2.4)
            }
        };
        0.2126 * linear(color.r()) + 0.7152 * linear(color.g()) + 0.0722 * linear(color.b())
    }
    for theme in [egui::Theme::Light, egui::Theme::Dark] {
        let (ctx, mut app) = app(theme);
        let size = [900.0, 600.0];
        let output = open_models(&ctx, &mut app, size);
        let output = draw(&ctx, &mut app, size, vec![value(&output, "model 01")]);
        let label = model_label(1);
        draw(&ctx, &mut app, size, vec![click(named(&output, &label).0)]);
        let mut output = draw(&ctx, &mut app, size, vec![]);
        for _ in 0..12 {
            output = draw(&ctx, &mut app, size, vec![]);
        }
        assert_eq!(
            named(&output, &label).1.toggled(),
            Some(egui::accesskit::Toggled::True)
        );
        assert!(!named(&output, "Use as default").1.is_disabled());
        for (node_label, text_prefix) in [
            (label.as_str(), "Gemini model 01"),
            ("Use as default", "Use as default"),
        ] {
            let bounds = named(&output, node_label).1.bounds().unwrap();
            let fill = output
                .shapes
                .iter()
                .find_map(|shape| match &shape.shape {
                    egui::Shape::Rect(rect)
                        if (f64::from(rect.rect.min.x) - bounds.x0).abs() < 1.0
                            && (f64::from(rect.rect.min.y) - bounds.y0).abs() < 1.0
                            && (f64::from(rect.rect.max.x) - bounds.x1).abs() < 1.0
                            && (f64::from(rect.rect.max.y) - bounds.y1).abs() < 1.0 =>
                    {
                        Some(rect.fill)
                    }
                    _ => None,
                })
                .expect("real action background");
            let background =
                Color32::from(egui::Rgba::from(theme::panel()).blend(egui::Rgba::from(fill)));
            let text = output
                .shapes
                .iter()
                .find_map(|shape| match &shape.shape {
                    egui::Shape::Text(text) if text.galley.job.text.starts_with(text_prefix) => {
                        Some(text)
                    }
                    _ => None,
                })
                .expect("real selected model or confirmation text");
            for section in &text.galley.job.sections {
                let specified = section.format.color;
                let foreground =
                    text.override_text_color
                        .unwrap_or(if specified == Color32::PLACEHOLDER {
                            text.fallback_color
                        } else {
                            specified
                        });
                let foreground = Color32::from(egui::Rgba::from(background).blend(
                    egui::Rgba::from(foreground.gamma_multiply(text.opacity_factor)),
                ));
                let (a, b) = (luminance(foreground), luminance(background));
                let contrast = (a.max(b) + 0.05) / (a.min(b) + 0.05);
                assert!(
                    contrast >= 4.5,
                    "{theme:?} {node_label} contrast {contrast}: {foreground:?} on {background:?}"
                );
            }
        }
    }
}
