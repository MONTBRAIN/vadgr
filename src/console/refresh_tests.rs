use super::*;
use eframe::App;
use egui::accesskit::{Action, ActionRequest, Role, TreeId};

struct Controller(
    mpsc::Sender<&'static str>,
    Option<std::sync::Mutex<mpsc::Receiver<()>>>,
);

impl ConsoleController for Controller {
    fn install_status(&self) -> Result<crate::install::InstallStatus> {
        self.0.send("refresh").unwrap();
        // A gated refresh stays pending until its test drops the gate.
        if let Some(gate) = &self.1 {
            let _ = gate.lock().unwrap().recv();
        }
        Err(anyhow!("synthetic refresh result"))
    }
    fn restart_daemon(&self) -> Result<()> {
        self.0.send("restart").unwrap();
        Ok(())
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
    fn set_default_model(&self, _: &str, _: &str) -> Result<()> {
        unreachable!()
    }
    fn disconnect_provider(&self, _: &str) -> Result<()> {
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

fn draw(ctx: &egui::Context, app: &mut ConsoleApp, events: Vec<egui::Event>) -> egui::FullOutput {
    let mut frame = eframe::Frame::_new_kittest();
    let mut output = ctx.run_ui(
        egui::RawInput {
            screen_rect: Some(egui::Rect::from_min_size(
                egui::Pos2::ZERO,
                egui::vec2(1200.0, 720.0),
            )),
            events,
            ..Default::default()
        },
        |root| app.ui(root, &mut frame),
    );
    output.textures_delta.clear();
    output
}

fn ready_app() -> (egui::Context, ConsoleApp, mpsc::Receiver<&'static str>) {
    ready_app_with_refresh_gate(None)
}

fn ready_app_with_refresh_gate(
    gate: Option<mpsc::Receiver<()>>,
) -> (egui::Context, ConsoleApp, mpsc::Receiver<&'static str>) {
    let ctx = egui::Context::default();
    ctx.enable_accesskit();
    theme::install(&ctx);
    let (send, calls) = mpsc::channel();
    let app = ConsoleApp {
        controller: Arc::new(Controller(send, gate.map(std::sync::Mutex::new))),
        view: View::Machine,
        data: Some(ConsoleData::default()),
        pending: None,
        pending_announced: false,
        uninstalled: false,
        dialog: None,
        dialog_focus: DialogFocus::default(),
        notice: None,
        available_update: None,
        last_refresh: std::time::Instant::now(),
    };
    (ctx, app, calls)
}

fn assert_live_status(success: Option<bool>, expected: &str, live: egui::accesskit::Live) {
    let (ctx, mut app, calls) = ready_app();
    app.view = View::Settings;
    let first = draw(&ctx, &mut app, vec![]);
    let settings = first
        .platform_output
        .accesskit_update
        .as_ref()
        .unwrap()
        .nodes
        .iter()
        .find(|(_, node)| node.label() == Some("Settings"))
        .unwrap()
        .0;
    draw(
        &ctx,
        &mut app,
        vec![egui::Event::AccessKitActionRequest(ActionRequest {
            action: Action::Focus,
            target_tree: TreeId::ROOT,
            target_node: settings,
            data: None,
        })],
    );
    let (_send, receive) = mpsc::channel();
    if let Some(success) = success {
        app.notice = Some((success, expected.to_owned()));
    } else {
        // A user-started operation; background refresh progress is covered separately.
        app.pending = Some(receive);
        app.pending_announced = true;
    }
    let mut status_id = None;
    for _ in 0..2 {
        let output = draw(&ctx, &mut app, vec![]);
        let tree = output.platform_output.accesskit_update.as_ref().unwrap();
        let (id, node) = tree
            .nodes
            .iter()
            .find(|(_, node)| node.value() == Some(expected) || node.label() == Some(expected))
            .expect("the visible status text is exposed");
        assert_eq!(
            node.live(),
            Some(live),
            "status must be available without moving focus"
        );
        assert_eq!(tree.focus, settings, "status must not take keyboard focus");
        if let Some(previous) = status_id {
            assert_eq!(
                *id, previous,
                "unchanged status keeps its accessible identity"
            );
        }
        status_id = Some(*id);
    }
    assert!(calls.try_recv().is_err());
}

#[test]
fn dynamic_status_success_is_polite_without_taking_focus() {
    assert_live_status(
        Some(true),
        "The change completed.",
        egui::accesskit::Live::Polite,
    );
}

#[test]
fn dynamic_status_failure_is_assertive_without_taking_focus() {
    assert_live_status(
        Some(false),
        "The action failed.",
        egui::accesskit::Live::Assertive,
    );
}

#[test]
fn dynamic_status_pending_is_polite_without_taking_focus() {
    assert_live_status(
        None,
        "Vadgr is completing this action...",
        egui::accesskit::Live::Polite,
    );
}

#[test]
fn automatic_refresh_progress_is_not_announced() {
    let progress = "Vadgr is completing this action...";
    let (gate, wait) = mpsc::channel::<()>();
    let (ctx, mut app, calls) = ready_app_with_refresh_gate(Some(wait));
    app.last_refresh = std::time::Instant::now() - std::time::Duration::from_secs(30);
    // An idle frame starts the automatic refresh, which the gate holds pending.
    draw(&ctx, &mut app, vec![]);
    assert_eq!(
        calls.recv_timeout(std::time::Duration::from_secs(5)),
        Ok("refresh")
    );
    for _ in 0..2 {
        let output = draw(&ctx, &mut app, vec![]);
        let tree = output.platform_output.accesskit_update.as_ref().unwrap();
        let (_, node) = tree
            .nodes
            .iter()
            .find(|(_, node)| node.value() == Some(progress) || node.label() == Some(progress))
            .expect("the background progress stays visible");
        assert!(
            matches!(node.live(), None | Some(egui::accesskit::Live::Off)),
            "an automatic refresh the user did not start must not be announced"
        );
    }
    drop(gate);
}

fn draw_sidebar(
    ctx: &egui::Context,
    app: &mut ConsoleApp,
    size: egui::Vec2,
    events: Vec<egui::Event>,
) -> egui::FullOutput {
    let mut output = ctx.run_ui(
        egui::RawInput {
            screen_rect: Some(egui::Rect::from_min_size(egui::Pos2::ZERO, size)),
            events,
            ..Default::default()
        },
        |root| {
            app.sidebar(root);
            egui::CentralPanel::default().show(root, |ui| {
                let _ = ui.button("Page action");
            });
        },
    );
    output.textures_delta.clear();
    output
}

#[test]
fn sidebar_exposes_only_named_navigation_focus_targets() {
    for (size, palette) in [egui::vec2(900.0, 600.0), egui::vec2(1200.0, 720.0)]
        .into_iter()
        .flat_map(|size| [egui::Theme::Dark, egui::Theme::Light].map(|palette| (size, palette)))
    {
        let (ctx, mut app, calls) = ready_app();
        ctx.set_theme(palette);
        theme::refresh(&ctx);
        let output = draw_sidebar(&ctx, &mut app, size, vec![]);
        let tree = output.platform_output.accesskit_update.as_ref().unwrap();
        let mut labels: Vec<_> = tree
            .nodes
            .iter()
            .filter(|(_, node)| node.supports_action(Action::Focus) && !node.is_disabled())
            .map(|(_, node)| node.label())
            .collect();
        labels.sort_unstable();
        assert_eq!(
            labels,
            vec![
                Some("Machine"),
                Some("Page action"),
                Some("Providers"),
                Some("Settings"),
            ],
            "fixed navigation must not expose an anonymous resize handle"
        );
        assert!(calls.try_recv().is_err());
    }
}

#[test]
fn sidebar_tab_moves_from_settings_directly_to_page_action() {
    for (size, palette) in [egui::vec2(900.0, 600.0), egui::vec2(1200.0, 720.0)]
        .into_iter()
        .flat_map(|size| [egui::Theme::Dark, egui::Theme::Light].map(|palette| (size, palette)))
    {
        let (ctx, mut app, calls) = ready_app();
        ctx.set_theme(palette);
        theme::refresh(&ctx);
        let output = draw_sidebar(&ctx, &mut app, size, vec![]);
        let tree = output.platform_output.accesskit_update.as_ref().unwrap();
        let named = |label| {
            tree.nodes
                .iter()
                .find(|(_, node)| node.label() == Some(label))
                .unwrap()
                .0
        };
        let settings = named("Settings");
        let next = named("Page action");
        draw_sidebar(
            &ctx,
            &mut app,
            size,
            vec![egui::Event::AccessKitActionRequest(ActionRequest {
                action: Action::Focus,
                target_tree: TreeId::ROOT,
                target_node: settings,
                data: None,
            })],
        );
        let output = draw_sidebar(
            &ctx,
            &mut app,
            size,
            vec![egui::Event::Key {
                key: egui::Key::Tab,
                physical_key: None,
                pressed: true,
                repeat: false,
                modifiers: egui::Modifiers::NONE,
            }],
        );
        assert_eq!(
            output
                .platform_output
                .accesskit_update
                .as_ref()
                .unwrap()
                .focus,
            next,
            "Tab must skip the noninteractive sidebar edge"
        );
        assert!(calls.try_recv().is_err());
    }
}

#[test]
fn enabled_native_restart_wins_over_a_due_background_refresh() {
    let (ctx, mut app, calls) = ready_app();
    let output = draw(&ctx, &mut app, vec![]);
    let (id, node) = output
        .platform_output
        .accesskit_update
        .as_ref()
        .unwrap()
        .nodes
        .iter()
        .find(|(_, node)| node.role() == Role::Button && node.label() == Some("Restart Vadgr"))
        .expect("restart is exposed");
    assert!(!node.is_disabled());
    assert!(calls.try_recv().is_err());
    app.last_refresh = std::time::Instant::now() - std::time::Duration::from_secs(9);
    draw(
        &ctx,
        &mut app,
        vec![egui::Event::AccessKitActionRequest(ActionRequest {
            action: Action::Click,
            target_tree: TreeId::ROOT,
            target_node: *id,
            data: None,
        })],
    );
    let operation = calls
        .recv_timeout(std::time::Duration::from_secs(2))
        .unwrap();
    assert_eq!(
        operation, "restart",
        "the enabled action must precede automatic refresh"
    );
}

#[test]
fn background_refresh_still_starts_on_an_idle_frame() {
    let (ctx, mut app, calls) = ready_app();
    draw(&ctx, &mut app, vec![]);
    app.last_refresh = std::time::Instant::now() - std::time::Duration::from_secs(9);
    draw(&ctx, &mut app, vec![]);
    assert_eq!(
        calls
            .recv_timeout(std::time::Duration::from_secs(2))
            .unwrap(),
        "refresh"
    );
}

#[test]
fn an_already_pending_operation_keeps_restart_disabled() {
    let (ctx, mut app, calls) = ready_app();
    let (hold_pending, pending) = mpsc::channel();
    app.pending = Some(pending);
    let output = draw(&ctx, &mut app, vec![]);
    let (id, node) = output
        .platform_output
        .accesskit_update
        .as_ref()
        .unwrap()
        .nodes
        .iter()
        .find(|(_, node)| node.role() == Role::Button && node.label() == Some("Restart Vadgr"))
        .unwrap();
    assert!(node.is_disabled());
    app.last_refresh = std::time::Instant::now() - std::time::Duration::from_secs(9);
    draw(
        &ctx,
        &mut app,
        vec![egui::Event::AccessKitActionRequest(ActionRequest {
            action: Action::Click,
            target_tree: TreeId::ROOT,
            target_node: *id,
            data: None,
        })],
    );
    assert!(calls.try_recv().is_err());
    assert!(app.pending.is_some());
    drop(hold_pending);
}

#[test]
fn background_refresh_does_not_interrupt_a_pointer_press() {
    let (ctx, mut app, calls) = ready_app();
    let output = draw(&ctx, &mut app, vec![]);
    let node = &output
        .platform_output
        .accesskit_update
        .as_ref()
        .unwrap()
        .nodes
        .iter()
        .find(|(_, node)| node.role() == Role::Button && node.label() == Some("Restart Vadgr"))
        .unwrap()
        .1;
    let bounds = node.bounds().unwrap();
    let pos = egui::pos2(
        ((bounds.x0 + bounds.x1) / 2.0) as f32,
        ((bounds.y0 + bounds.y1) / 2.0) as f32,
    );
    draw(&ctx, &mut app, vec![egui::Event::PointerMoved(pos)]);
    app.last_refresh = std::time::Instant::now() - std::time::Duration::from_secs(9);
    draw(
        &ctx,
        &mut app,
        vec![egui::Event::PointerButton {
            pos,
            button: egui::PointerButton::Primary,
            pressed: true,
            modifiers: egui::Modifiers::NONE,
        }],
    );
    draw(&ctx, &mut app, vec![]);
    assert!(
        app.pending.is_none(),
        "a held pointer must not start an automatic refresh"
    );
    assert!(calls.try_recv().is_err());
    draw(
        &ctx,
        &mut app,
        vec![egui::Event::PointerButton {
            pos,
            button: egui::PointerButton::Primary,
            pressed: false,
            modifiers: egui::Modifiers::NONE,
        }],
    );
    assert_eq!(
        calls
            .recv_timeout(std::time::Duration::from_secs(2))
            .unwrap(),
        "restart"
    );
}
