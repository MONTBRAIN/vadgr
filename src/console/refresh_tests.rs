use super::*;
use eframe::App;
use egui::accesskit::{Action, ActionRequest, Role, TreeId};

struct Controller(mpsc::Sender<&'static str>);

impl ConsoleController for Controller {
    fn install_status(&self) -> Result<crate::install::InstallStatus> {
        self.0.send("refresh").unwrap();
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
    let ctx = egui::Context::default();
    ctx.enable_accesskit();
    theme::install(&ctx);
    let (send, calls) = mpsc::channel();
    let app = ConsoleApp {
        controller: Arc::new(Controller(send)),
        view: View::Machine,
        data: Some(ConsoleData::default()),
        pending: None,
        dialog: None,
        dialog_focus: DialogFocus::default(),
        notice: None,
        available_update: None,
        last_refresh: std::time::Instant::now(),
    };
    (ctx, app, calls)
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
