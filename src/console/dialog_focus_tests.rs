//! Full application regressions for native modal entry and return focus.
use super::*;
use std::sync::Mutex;
use std::sync::atomic::{AtomicBool, AtomicU8, AtomicUsize, Ordering};

struct DialogController {
    data: Mutex<ConsoleData>,
    calls: Mutex<Vec<&'static str>>,
    outcome: AtomicU8,
    blocked: AtomicBool,
    reloads: AtomicUsize,
    uninstall_modes: Mutex<Vec<bool>>,
}

impl DialogController {
    fn action(&self, name: &'static str, change: impl FnOnce(&mut ConsoleData)) -> Result<()> {
        self.calls.lock().unwrap().push(name);
        let deadline = std::time::Instant::now() + std::time::Duration::from_secs(5);
        while self.blocked.load(Ordering::SeqCst) {
            assert!(
                std::time::Instant::now() < deadline,
                "fixture release timeout"
            );
            std::thread::sleep(std::time::Duration::from_millis(1));
        }
        match self.outcome.load(Ordering::SeqCst) {
            1 => return Err(anyhow!("fixture operation refused")),
            2 => panic!("fixture worker disconnect"),
            _ => {}
        }
        change(&mut self.data.lock().unwrap());
        Ok(())
    }
}

impl ConsoleController for DialogController {
    fn install_status(&self) -> Result<crate::install::InstallStatus> {
        self.reloads.fetch_add(1, Ordering::SeqCst);
        Ok(self.data.lock().unwrap().install.clone())
    }
    fn health(&self) -> Result<HealthSnapshot> {
        Ok(HealthSnapshot::default())
    }
    fn machine(&self) -> Result<MachineSnapshot> {
        Ok(self.data.lock().unwrap().machine.clone())
    }
    fn devices(&self) -> Result<Vec<DeviceSnapshot>> {
        Ok(self.data.lock().unwrap().devices.clone())
    }
    fn providers(&self) -> Result<Vec<ProviderSnapshot>> {
        Ok(self.data.lock().unwrap().providers.clone())
    }
    fn start_pairing(&self) -> Result<PairingSession> {
        self.action("pair", |_| {})?;
        Ok(PairingSession {
            code: "fixture-only".into(),
            ..Default::default()
        })
    }
    fn cancel_pairing(&self) -> Result<()> {
        self.action("cancel-pair", |_| {})
    }
    fn update_machine(&self, edit: &MachineEdit) -> Result<MachineSnapshot> {
        self.action("edit", |data| data.machine.name = edit.name.clone())?;
        self.machine()
    }
    fn revoke_device(&self, id: &str) -> Result<()> {
        self.action("revoke", |data| {
            data.devices.retain(|device| device.id != id)
        })
    }
    fn refresh_provider(&self, _: &str) -> Result<()> {
        self.action("refresh", |_| {})
    }
    fn connect_api_key(&self, _: &str, _: String) -> Result<()> {
        self.action("key", |data| {
            data.providers
                .iter_mut()
                .find(|provider| provider.id == "openai")
                .unwrap()
                .connected = true
        })
    }
    fn connect_oauth(&self, _: &str) -> Result<()> {
        self.action("oauth", |data| {
            data.providers
                .iter_mut()
                .find(|provider| provider.id == "openai")
                .unwrap()
                .connected = true
        })
    }
    fn set_default_model(&self, provider: &str, model: &str) -> Result<()> {
        self.action("model", |data| {
            data.machine.default_provider = Some(provider.to_owned());
            data.machine.default_model = Some(model.to_owned());
        })
    }
    fn disconnect_provider(&self, id: &str) -> Result<()> {
        self.action("disconnect", |data| {
            data.providers
                .iter_mut()
                .find(|provider| provider.id == id)
                .unwrap()
                .connected = false
        })
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
    fn uninstall(&self, purge: bool) -> Result<()> {
        self.uninstall_modes.lock().unwrap().push(purge);
        self.action("uninstall", |data| {
            data.install.installed = false;
            data.install.lifecycle_available = false;
        })
    }
}

#[derive(Clone, Copy, Debug)]
enum Family {
    Edit,
    Models,
    Picker,
    Auth,
    Key,
    Revoke,
    Disconnect,
    Uninstall,
    Pairing,
}

impl Family {
    fn opener(self) -> &'static str {
        match self {
            Self::Edit => "Edit machine",
            Self::Models => "Change default",
            Self::Picker => "Connect provider",
            Self::Auth | Self::Key => "Connect",
            Self::Revoke => "Unpair",
            Self::Disconnect => "Disconnect",
            Self::Uninstall => "Uninstall...",
            Self::Pairing => "Pair device",
        }
    }
    fn initial(self) -> &'static str {
        match self {
            Self::Edit => "Machine name",
            Self::Models => "Search models",
            Self::Picker => "OpenAI",
            Self::Auth => "Continue in browser",
            Self::Key => "Enter the openai API key.",
            Self::Revoke => "Keep paired",
            Self::Disconnect => "Keep connected",
            Self::Uninstall => "Keep installed",
            Self::Pairing => "Cancel pairing",
        }
    }
    fn cancel(self) -> &'static str {
        match self {
            Self::Revoke => "Keep paired",
            Self::Disconnect => "Keep connected",
            Self::Uninstall => "Keep installed",
            Self::Pairing => "Cancel pairing",
            _ => "Cancel",
        }
    }
}

fn fixture(family: Family, palette: egui::Theme) -> (egui::Context, ConsoleApp) {
    let (ctx, app, _) = controlled_fixture(family, palette);
    (ctx, app)
}

fn controlled_fixture(
    family: Family,
    palette: egui::Theme,
) -> (egui::Context, ConsoleApp, Arc<DialogController>) {
    let (ctx, mut app) = app(palette);
    app.view = match family {
        Family::Edit | Family::Revoke | Family::Pairing => View::Machine,
        Family::Uninstall => View::Settings,
        _ => View::Providers,
    };
    let data = app.data.as_mut().unwrap();
    data.install.installed = true;
    data.install.lifecycle_available = true;
    data.devices.push(DeviceSnapshot {
        id: "fixture-device".into(),
        ..Default::default()
    });
    data.providers.push(ProviderSnapshot {
        id: "openai".into(),
        name: "OpenAI".into(),
        available: true,
        auth_methods: if matches!(family, Family::Key) {
            vec!["api_key".into()]
        } else {
            vec!["oauth".into(), "api_key".into()]
        },
        ..Default::default()
    });
    let controller = Arc::new(DialogController {
        data: Mutex::new(data.clone()),
        calls: Mutex::new(Vec::new()),
        outcome: AtomicU8::new(0),
        blocked: AtomicBool::new(false),
        reloads: AtomicUsize::new(0),
        uninstall_modes: Mutex::new(Vec::new()),
    });
    app.controller = controller.clone();
    (ctx, app, controller)
}

fn node_text(nodes: &[(NodeId, Node)], node: &Node) -> String {
    node.label()
        .or(node.value())
        .map(str::to_owned)
        .unwrap_or_else(|| {
            node.children()
                .iter()
                .filter_map(|child| nodes.iter().find(|(id, _)| id == child))
                .map(|(_, child)| node_text(nodes, child))
                .collect()
        })
}

fn modal_has_waiting_reason(output: &egui::FullOutput) -> bool {
    let nodes = &output
        .platform_output
        .accesskit_update
        .as_ref()
        .unwrap()
        .nodes;
    fn contains(nodes: &[(NodeId, Node)], node: &Node) -> bool {
        (node.role() == Role::Label && node_text(nodes, node) == MODAL_WAIT_REASON)
            || node
                .children()
                .iter()
                .filter_map(|child| nodes.iter().find(|(id, _)| id == child))
                .any(|(_, child)| contains(nodes, child))
    }
    nodes.iter().any(|(_, node)| {
        node.role() == Role::Window && node.label().is_some() && contains(nodes, node)
    })
}

fn target(output: &egui::FullOutput, label: &str) -> NodeId {
    let nodes = &output
        .platform_output
        .accesskit_update
        .as_ref()
        .unwrap()
        .nodes;
    if let Some((id, _)) = nodes.iter().find(|(_, node)| {
        node.label() == Some(label) && node.supports_action(Action::Focus) && !node.is_disabled()
    }) {
        return *id;
    }
    let label_id = nodes
        .iter()
        .find(|(_, node)| node.role() == Role::Label && node_text(nodes, node) == label)
        .unwrap_or_else(|| panic!("missing label {label}"))
        .0;
    nodes
        .iter()
        .find(|(_, node)| {
            node.labelled_by().contains(&label_id)
                && node.supports_action(Action::Focus)
                && !node.is_disabled()
        })
        .unwrap_or_else(|| panic!("no focus target for {label}"))
        .0
}

fn focus(id: NodeId) -> egui::Event {
    egui::Event::AccessKitActionRequest(ActionRequest {
        action: Action::Focus,
        target_tree: TreeId::ROOT,
        target_node: id,
        data: None,
    })
}

fn settle(ctx: &egui::Context, app: &mut ConsoleApp, size: [f32; 2]) -> egui::FullOutput {
    for _ in 0..100 {
        draw(ctx, app, size, vec![]);
        if app.pending.is_none() {
            draw(ctx, app, size, vec![]);
            return draw(ctx, app, size, vec![]);
        }
        std::thread::sleep(std::time::Duration::from_millis(2));
    }
    panic!("isolated controller did not settle");
}

#[test]
fn all_dialog_families_have_safe_initial_and_return_focus() {
    let mut failures = Vec::new();
    for palette in [egui::Theme::Light, egui::Theme::Dark] {
        for size in [[1200.0, 720.0], [900.0, 600.0]] {
            for family in [
                Family::Edit,
                Family::Models,
                Family::Picker,
                Family::Auth,
                Family::Key,
                Family::Revoke,
                Family::Disconnect,
                Family::Uninstall,
                Family::Pairing,
            ] {
                let (ctx, mut app) = fixture(family, palette);
                let before = settle(&ctx, &mut app, size);
                let opener = target(&before, family.opener());
                draw(&ctx, &mut app, size, vec![focus(opener)]);
                draw(&ctx, &mut app, size, vec![click(opener)]);
                let opened = settle(&ctx, &mut app, size);
                assert!(app.dialog.is_some(), "{family:?} did not open");
                let initial = target(&opened, family.initial());
                if opened
                    .platform_output
                    .accesskit_update
                    .as_ref()
                    .unwrap()
                    .focus
                    != initial
                {
                    failures.push(format!(
                        "{family:?} {palette:?} {size:?}: initial focus missing"
                    ));
                }
                let cancel = target(&opened, family.cancel());
                draw(&ctx, &mut app, size, vec![focus(cancel)]);
                draw(&ctx, &mut app, size, vec![click(cancel)]);
                let closed = settle(&ctx, &mut app, size);
                assert!(app.dialog.is_none(), "{family:?} did not close");
                let surviving = target(&closed, family.opener());
                if closed
                    .platform_output
                    .accesskit_update
                    .as_ref()
                    .unwrap()
                    .focus
                    != surviving
                {
                    failures.push(format!(
                        "{family:?} {palette:?} {size:?}: opener focus missing"
                    ));
                }
            }
        }
    }
    assert!(failures.is_empty(), "{}", failures.join("\n"));
}

const FAMILIES: [Family; 9] = [
    Family::Edit,
    Family::Models,
    Family::Picker,
    Family::Auth,
    Family::Key,
    Family::Revoke,
    Family::Disconnect,
    Family::Uninstall,
    Family::Pairing,
];

fn activate(ctx: &egui::Context, app: &mut ConsoleApp, size: [f32; 2], label: &str) {
    let current = settle(ctx, app, size);
    let id = target(&current, label);
    draw(ctx, app, size, vec![focus(id)]);
    draw(ctx, app, size, vec![click(id)]);
}

fn assert_focus(output: &egui::FullOutput, label: &str) {
    assert_eq!(
        output
            .platform_output
            .accesskit_update
            .as_ref()
            .unwrap()
            .focus,
        target(output, label),
        "expected enabled focus on {label}"
    );
}

fn escape() -> egui::Event {
    egui::Event::Key {
        key: egui::Key::Escape,
        physical_key: None,
        pressed: true,
        repeat: false,
        modifiers: Default::default(),
    }
}

#[test]
fn escape_and_scrim_restore_all_nine_openers() {
    for palette in [egui::Theme::Light, egui::Theme::Dark] {
        for size in [[1200.0, 720.0], [900.0, 600.0]] {
            for family in FAMILIES {
                for outside in [false, true] {
                    let (ctx, mut app) = fixture(family, palette);
                    activate(&ctx, &mut app, size, family.opener());
                    settle(&ctx, &mut app, size);
                    if outside {
                        let pos = egui::pos2(10.0, 10.0);
                        for pressed in [true, false] {
                            draw(
                                &ctx,
                                &mut app,
                                size,
                                vec![
                                    egui::Event::PointerMoved(pos),
                                    egui::Event::PointerButton {
                                        pos,
                                        button: egui::PointerButton::Primary,
                                        pressed,
                                        modifiers: Default::default(),
                                    },
                                ],
                            );
                        }
                    } else {
                        draw(&ctx, &mut app, size, vec![escape()]);
                    }
                    let closed = settle(&ctx, &mut app, size);
                    assert!(app.dialog.is_none(), "{family:?} outside={outside}");
                    assert_focus(&closed, family.opener());
                }
            }
        }
    }
}

#[test]
fn nested_provider_entry_is_once_per_stage_and_returns_to_outer_opener() {
    for palette in [egui::Theme::Light, egui::Theme::Dark] {
        for size in [[1200.0, 720.0], [900.0, 600.0]] {
            let (ctx, mut app) = fixture(Family::Picker, palette);
            activate(&ctx, &mut app, size, "Connect provider");
            assert_focus(&settle(&ctx, &mut app, size), "OpenAI");
            activate(&ctx, &mut app, size, "OpenAI");
            let auth = settle(&ctx, &mut app, size);
            assert_focus(&auth, "Continue in browser");
            let alternate = target(&auth, "Use an API key");
            draw(&ctx, &mut app, size, vec![focus(alternate)]);
            for _ in 0..4 {
                assert_focus(&draw(&ctx, &mut app, size, vec![]), "Use an API key");
            }
            draw(&ctx, &mut app, size, vec![click(alternate)]);
            assert_focus(&settle(&ctx, &mut app, size), "Enter the openai API key.");
            activate(&ctx, &mut app, size, "Cancel");
            assert_focus(&settle(&ctx, &mut app, size), "Connect provider");
        }
    }
}

#[test]
fn async_submit_success_error_and_disconnection_have_safe_return_destinations() {
    for palette in [egui::Theme::Light, egui::Theme::Dark] {
        for size in [[1200.0, 720.0], [900.0, 600.0]] {
            for family in [
                Family::Edit,
                Family::Models,
                Family::Auth,
                Family::Key,
                Family::Revoke,
                Family::Disconnect,
                Family::Uninstall,
            ] {
                for outcome in 0..3 {
                    let (ctx, mut app, controller) = controlled_fixture(family, palette);
                    activate(&ctx, &mut app, size, family.opener());
                    let opened = settle(&ctx, &mut app, size);
                    let submit = match family {
                        Family::Edit => "Save changes",
                        Family::Models => {
                            let id = opened
                                .platform_output
                                .accesskit_update
                                .as_ref()
                                .unwrap()
                                .nodes
                                .iter()
                                .find(|(_, node)| {
                                    node.label()
                                        .is_some_and(|label| label.starts_with("Gemini model 01"))
                                })
                                .unwrap()
                                .0;
                            draw(&ctx, &mut app, size, vec![click(id)]);
                            "Use as default"
                        }
                        Family::Auth => "Continue in browser",
                        Family::Key => {
                            let id = target(&opened, "Enter the openai API key.");
                            draw(
                                &ctx,
                                &mut app,
                                size,
                                vec![egui::Event::AccessKitActionRequest(ActionRequest {
                                    action: Action::SetValue,
                                    target_tree: TreeId::ROOT,
                                    target_node: id,
                                    data: Some(ActionData::Value("nonsecret-fixture".into())),
                                })],
                            );
                            "Connect"
                        }
                        Family::Revoke => "Unpair device",
                        Family::Disconnect => "Disconnect",
                        Family::Uninstall => "Uninstall Vadgr",
                        _ => unreachable!(),
                    };
                    controller.outcome.store(outcome, Ordering::SeqCst);
                    activate(&ctx, &mut app, size, submit);
                    let closed = settle(&ctx, &mut app, size);
                    assert!(app.dialog.is_none());
                    assert_eq!(
                        controller.calls.lock().unwrap().len(),
                        1,
                        "one submitted operation"
                    );
                    if matches!(family, Family::Uninstall) && outcome == 0 {
                        assert!(requests_close(&closed));
                        assert_eq!(controller.reloads.load(Ordering::SeqCst), 0);
                        continue;
                    }
                    let expected = if outcome == 0 {
                        match family {
                            Family::Auth | Family::Key | Family::Disconnect => "Providers",
                            Family::Revoke => "Machine",
                            _ => family.opener(),
                        }
                    } else {
                        family.opener()
                    };
                    assert_focus(&closed, expected);
                    if outcome != 0 {
                        assert_eq!(app.notice.as_ref().map(|notice| notice.0), Some(false));
                    }
                }
            }
        }
    }
}

#[test]
fn pairing_completion_and_expiry_keep_safe_focus_and_cancel_backend() {
    for palette in [egui::Theme::Light, egui::Theme::Dark] {
        for size in [[1200.0, 720.0], [900.0, 600.0]] {
            let (ctx, mut app, controller) = controlled_fixture(Family::Pairing, palette);
            activate(&ctx, &mut app, size, "Pair device");
            let before = settle(&ctx, &mut app, size);
            let cancel = target(&before, "Cancel pairing");
            if let Some(Dialog::Pairing { opened_at, .. }) = app.dialog.as_mut() {
                *opened_at = std::time::Instant::now()
                    - std::time::Duration::from_secs(crate::auth::pairing::PAIRING_TTL_SECONDS + 1);
            } else {
                panic!("pairing did not open");
            }
            let expired = settle(&ctx, &mut app, size);
            assert_eq!(
                target(&expired, "Close"),
                cancel,
                "expiry must not replace safe control identity"
            );
            assert_focus(&expired, "Close");
            activate(&ctx, &mut app, size, "Close");
            assert_focus(&settle(&ctx, &mut app, size), "Pair device");
            assert!(controller.calls.lock().unwrap().contains(&"cancel-pair"));
            activate(&ctx, &mut app, size, "Pair device");
            settle(&ctx, &mut app, size);
            controller
                .data
                .lock()
                .unwrap()
                .devices
                .push(DeviceSnapshot {
                    id: "claimed-fixture".into(),
                    ..Default::default()
                });
            app.reload();
            let paired = settle(&ctx, &mut app, size);
            assert!(app.dialog.is_none());
            assert_focus(&paired, "Pair device");
        }
    }
}

fn wait_call(controller: &DialogController, name: &str) {
    for _ in 0..1000 {
        if controller.calls.lock().unwrap().contains(&name) {
            return;
        }
        std::thread::sleep(std::time::Duration::from_millis(1));
    }
    panic!("worker did not start {name}");
}

#[test]
fn pending_pairing_cannot_override_navigation_or_new_focus_and_is_cancelled() {
    for palette in [egui::Theme::Light, egui::Theme::Dark] {
        for ready in [false, true] {
            for interaction in 0..3 {
                let navigate = interaction == 1;
                let size = [900.0, 600.0];
                let (ctx, mut app, controller) = controlled_fixture(Family::Pairing, palette);
                let before = settle(&ctx, &mut app, size);
                let destination = if navigate {
                    "Providers"
                } else {
                    "Edit machine"
                };
                let target = target(&before, destination);
                controller.blocked.store(true, Ordering::SeqCst);
                activate(&ctx, &mut app, size, "Pair device");
                wait_call(&controller, "pair");
                if ready {
                    controller.blocked.store(false, Ordering::SeqCst);
                    // Retain the real start() worker result, then deterministically stage
                    // that exact result for poll in the queued native-action frame.
                    let result = app
                        .pending
                        .as_ref()
                        .unwrap()
                        .recv_timeout(std::time::Duration::from_secs(1))
                        .unwrap();
                    let (send, receive) = mpsc::channel();
                    send.send(result).unwrap();
                    app.pending = Some(receive);
                }
                let events = if interaction != 0 {
                    vec![focus(target), click(target)]
                } else {
                    vec![focus(target)]
                };
                draw(&ctx, &mut app, size, events);
                controller.blocked.store(false, Ordering::SeqCst);
                let after = settle(&ctx, &mut app, size);
                if interaction == 2 {
                    assert!(matches!(app.dialog, Some(Dialog::EditMachine { .. })));
                } else {
                    assert!(app.dialog.is_none());
                }
                assert_eq!(
                    app.view,
                    if navigate {
                        View::Providers
                    } else {
                        View::Machine
                    }
                );
                assert_focus(
                    &after,
                    if interaction == 2 {
                        "Machine name"
                    } else {
                        destination
                    },
                );
                assert_eq!(
                    controller
                        .calls
                        .lock()
                        .unwrap()
                        .iter()
                        .filter(|&&call| call == "cancel-pair")
                        .count(),
                    1
                );
            }
        }
    }
}

#[test]
fn submitted_operation_never_steals_later_focus_or_submits_twice() {
    for palette in [egui::Theme::Light, egui::Theme::Dark] {
        for navigate in [false, true] {
            let size = [1200.0, 720.0];
            let (ctx, mut app, controller) = controlled_fixture(Family::Edit, palette);
            activate(&ctx, &mut app, size, "Edit machine");
            let opened = settle(&ctx, &mut app, size);
            let submit = target(&opened, "Save changes");
            controller.blocked.store(true, Ordering::SeqCst);
            draw(
                &ctx,
                &mut app,
                size,
                vec![focus(submit), click(submit), click(submit)],
            );
            wait_call(&controller, "edit");
            let background = draw(&ctx, &mut app, size, vec![]);
            let navigation = target(&background, "Providers");
            draw(
                &ctx,
                &mut app,
                size,
                if navigate {
                    vec![focus(navigation), click(navigation)]
                } else {
                    vec![focus(navigation)]
                },
            );
            controller.blocked.store(false, Ordering::SeqCst);
            let after = settle(&ctx, &mut app, size);
            assert_focus(&after, "Providers");
            assert_eq!(
                controller
                    .calls
                    .lock()
                    .unwrap()
                    .iter()
                    .filter(|&&call| call == "edit")
                    .count(),
                1
            );
        }
    }
}

#[test]
fn semantic_opener_survives_reordered_provider_rows() {
    for palette in [egui::Theme::Light, egui::Theme::Dark] {
        let size = [1200.0, 720.0];
        let (ctx, mut app) = fixture(Family::Models, palette);
        let before = settle(&ctx, &mut app, size);
        let id = target(&before, "Change default");
        activate(&ctx, &mut app, size, "Change default");
        app.data.as_mut().unwrap().providers.reverse();
        activate(&ctx, &mut app, size, "Cancel");
        let after = settle(&ctx, &mut app, size);
        assert_eq!(target(&after, "Change default"), id);
        assert_focus(&after, "Change default");
    }
}

#[test]
fn no_choice_auth_has_safe_cancel_and_modal_background_is_disabled() {
    for palette in [egui::Theme::Light, egui::Theme::Dark] {
        let size = [900.0, 600.0];
        let (ctx, mut app) = fixture(Family::Auth, palette);
        app.data
            .as_mut()
            .unwrap()
            .providers
            .last_mut()
            .unwrap()
            .auth_methods
            .clear();
        activate(&ctx, &mut app, size, "Connect");
        let dialog = settle(&ctx, &mut app, size);
        assert_focus(&dialog, "Cancel");
        for label in ["Machine", "Providers", "Settings", "Connect provider"] {
            assert!(
                named(&dialog, label).1.is_disabled(),
                "modal background {label} must be disabled"
            );
        }
        activate(&ctx, &mut app, size, "Cancel");
        assert_focus(&settle(&ctx, &mut app, size), "Connect");
        app.data
            .as_mut()
            .unwrap()
            .providers
            .iter_mut()
            .for_each(|provider| provider.connected = true);
        let empty = settle(&ctx, &mut app, size);
        let disabled = named(&empty, "Connect provider");
        assert!(disabled.1.is_disabled());
        draw(&ctx, &mut app, size, vec![click(disabled.0)]);
        assert!(
            app.dialog.is_none(),
            "an empty picker is not a reachable modal"
        );
    }
}

#[test]
fn escape_closes_child_combo_before_machine_dialog() {
    for palette in [egui::Theme::Light, egui::Theme::Dark] {
        let size = [1200.0, 720.0];
        let (ctx, mut app) = fixture(Family::Edit, palette);
        activate(&ctx, &mut app, size, "Edit machine");
        activate(&ctx, &mut app, size, "Autonomy mode");
        assert!(egui::Popup::is_any_open(&ctx));
        draw(&ctx, &mut app, size, vec![escape()]);
        settle(&ctx, &mut app, size);
        assert!(!egui::Popup::is_any_open(&ctx));
        assert!(matches!(app.dialog, Some(Dialog::EditMachine { .. })));
        draw(&ctx, &mut app, size, vec![escape()]);
        assert_focus(&settle(&ctx, &mut app, size), "Edit machine");
    }
}

#[test]
fn disappearing_purge_field_returns_focus_to_its_toggle() {
    let label = "Also delete settings, credentials, pairings and journals";
    let confirmation = "Type DELETE OWNER DATA to confirm the separate data deletion.";
    for palette in [egui::Theme::Light, egui::Theme::Dark] {
        let size = [1200.0, 720.0];
        let (ctx, mut app) = fixture(Family::Uninstall, palette);
        activate(&ctx, &mut app, size, "Uninstall...");
        let original = settle(&ctx, &mut app, size);
        assert_focus(&original, "Keep installed");
        let safe = target(&original, "Keep installed");
        draw(&ctx, &mut app, size, vec![click(target(&original, label))]);
        let opened = settle(&ctx, &mut app, size);
        assert_eq!(
            target(&opened, "Keep installed"),
            safe,
            "conditional field cannot replace footer identity"
        );
        assert_focus(&opened, "Keep installed");
        let field = target(&opened, confirmation);
        let toggle = target(&opened, label);
        draw(&ctx, &mut app, size, vec![focus(field)]);
        draw(&ctx, &mut app, size, vec![click(toggle)]);
        let closed = settle(&ctx, &mut app, size);
        assert_focus(&closed, label);
        assert!(matches!(
            app.dialog,
            Some(Dialog::Uninstall { purge: false, .. })
        ));
        activate(&ctx, &mut app, size, "Keep installed");
        assert_focus(&settle(&ctx, &mut app, size), "Uninstall...");
    }
}

#[test]
fn nested_key_completion_uses_outer_opener_or_enabled_fallback() {
    for palette in [egui::Theme::Light, egui::Theme::Dark] {
        for size in [[1200.0, 720.0], [900.0, 600.0]] {
            for outcome in 0..2 {
                let (ctx, mut app, controller) = controlled_fixture(Family::Picker, palette);
                activate(&ctx, &mut app, size, "Connect provider");
                activate(&ctx, &mut app, size, "OpenAI");
                activate(&ctx, &mut app, size, "Use an API key");
                let opened = settle(&ctx, &mut app, size);
                let field = target(&opened, "Enter the openai API key.");
                draw(
                    &ctx,
                    &mut app,
                    size,
                    vec![egui::Event::AccessKitActionRequest(ActionRequest {
                        action: Action::SetValue,
                        target_tree: TreeId::ROOT,
                        target_node: field,
                        data: Some(ActionData::Value("nonsecret-fixture".into())),
                    })],
                );
                controller.outcome.store(outcome, Ordering::SeqCst);
                activate(&ctx, &mut app, size, "Connect");
                let closed = settle(&ctx, &mut app, size);
                assert!(app.dialog.is_none());
                assert_focus(
                    &closed,
                    if outcome == 0 {
                        "Providers"
                    } else {
                        "Connect provider"
                    },
                );
                assert_eq!(*controller.calls.lock().unwrap(), ["key"]);
            }
        }
    }
}

#[test]
fn pairing_start_failure_or_disconnected_worker_returns_without_modal() {
    for palette in [egui::Theme::Light, egui::Theme::Dark] {
        for outcome in 1..3 {
            let size = [900.0, 600.0];
            let (ctx, mut app, controller) = controlled_fixture(Family::Pairing, palette);
            controller.outcome.store(outcome, Ordering::SeqCst);
            activate(&ctx, &mut app, size, "Pair device");
            let failed = settle(&ctx, &mut app, size);
            assert!(app.dialog.is_none());
            assert_focus(&failed, "Pair device");
            assert_eq!(app.notice.as_ref().map(|notice| notice.0), Some(false));
            assert_eq!(*controller.calls.lock().unwrap(), ["pair"]);
        }
    }
}

struct ReleaseWorker(Arc<DialogController>);
impl Drop for ReleaseWorker {
    fn drop(&mut self) {
        self.0.blocked.store(false, Ordering::SeqCst);
    }
}

fn requests_close(output: &egui::FullOutput) -> bool {
    output.viewport_output.values().any(|viewport| {
        viewport
            .commands
            .iter()
            .any(|command| matches!(command, egui::ViewportCommand::Close))
    })
}

#[test]
fn successful_uninstall_closes_only_after_completion_without_reloading() {
    for palette in [egui::Theme::Light, egui::Theme::Dark] {
        for purge in [false, true] {
            let size = [900.0, 600.0];
            let (ctx, mut app, controller) = controlled_fixture(Family::Uninstall, palette);
            activate(&ctx, &mut app, size, "Uninstall...");
            if let Some(Dialog::Uninstall {
                purge: selected,
                confirmation,
            }) = &mut app.dialog
            {
                *selected = purge;
                *confirmation = if purge {
                    "DELETE OWNER DATA".into()
                } else {
                    String::new()
                };
            } else {
                panic!("missing uninstall confirmation");
            }
            controller.blocked.store(true, Ordering::SeqCst);
            let _release = ReleaseWorker(controller.clone());
            activate(&ctx, &mut app, size, "Uninstall Vadgr");
            wait_call(&controller, "uninstall");
            for _ in 0..3 {
                assert!(
                    !requests_close(&draw(&ctx, &mut app, size, vec![])),
                    "pending uninstall must keep the window open"
                );
            }
            assert!(controller.data.lock().unwrap().install.installed);
            assert_eq!(controller.reloads.load(Ordering::SeqCst), 0);
            controller.blocked.store(false, Ordering::SeqCst);
            let completed = settle(&ctx, &mut app, size);
            assert!(
                requests_close(&completed),
                "successful uninstall must close the native viewport"
            );
            assert!(!controller.data.lock().unwrap().install.installed);
            assert_eq!(*controller.uninstall_modes.lock().unwrap(), [purge]);
            // Even another frame beyond the normal refresh deadline must not
            // contact the removed daemon or draw a stale installation again.
            app.last_refresh = std::time::Instant::now() - std::time::Duration::from_secs(30);
            assert!(requests_close(&draw(&ctx, &mut app, size, vec![])));
            assert!(app.pending.is_none());
            assert!(app.notice.is_none());
            assert_eq!(controller.reloads.load(Ordering::SeqCst), 0);
        }
    }
}

#[test]
fn cancelled_or_failed_uninstall_keeps_the_console_open() {
    for palette in [egui::Theme::Light, egui::Theme::Dark] {
        let size = [900.0, 600.0];
        let (ctx, mut app, controller) = controlled_fixture(Family::Uninstall, palette);
        activate(&ctx, &mut app, size, "Uninstall...");
        activate(&ctx, &mut app, size, "Keep installed");
        assert!(!requests_close(&settle(&ctx, &mut app, size)));
        assert!(controller.calls.lock().unwrap().is_empty());
        for outcome in [1, 2] {
            controller.outcome.store(outcome, Ordering::SeqCst);
            activate(&ctx, &mut app, size, "Uninstall...");
            activate(&ctx, &mut app, size, "Uninstall Vadgr");
            let failed = settle(&ctx, &mut app, size);
            assert!(!requests_close(&failed));
            assert_focus(&failed, "Uninstall...");
            assert!(controller.data.lock().unwrap().install.installed);
            let expected = if outcome == 1 {
                "fixture operation refused"
            } else {
                "The operation ended without a result."
            };
            assert_eq!(app.notice, Some((false, expected.into())));
            assert_eq!(controller.reloads.load(Ordering::SeqCst), 0);
        }
    }
}

#[test]
fn pending_pairing_keeps_machine_draft_and_truthfully_disables_save() {
    for palette in [egui::Theme::Light, egui::Theme::Dark] {
        let size = [900.0, 600.0];
        let (ctx, mut app, controller) = controlled_fixture(Family::Pairing, palette);
        let before = settle(&ctx, &mut app, size);
        let edit = target(&before, "Edit machine");
        controller.blocked.store(true, Ordering::SeqCst);
        let _release = ReleaseWorker(controller.clone());
        activate(&ctx, &mut app, size, "Pair device");
        wait_call(&controller, "pair");
        draw(&ctx, &mut app, size, vec![focus(edit), click(edit)]);
        let opened = draw(&ctx, &mut app, size, vec![]);
        let field = target(&opened, "Machine name");
        draw(
            &ctx,
            &mut app,
            size,
            vec![egui::Event::AccessKitActionRequest(ActionRequest {
                action: Action::SetValue,
                target_tree: TreeId::ROOT,
                target_node: field,
                data: Some(ActionData::Value("retained-fixture-draft".into())),
            })],
        );
        let busy = draw(&ctx, &mut app, size, vec![]);
        let save = named(&busy, "Save changes");
        let disabled = save.1.is_disabled();
        draw(&ctx, &mut app, size, vec![click(save.0)]);
        assert!(
            disabled && app.dialog.is_some(),
            "busy submit: disabled={disabled}, editor_retained={}, controller_calls={:?}",
            app.dialog.is_some(),
            controller.calls.lock().unwrap()
        );
        assert!(
            matches!(&app.dialog, Some(Dialog::EditMachine { edit, .. }) if edit.name == "retained-fixture-draft")
        );
        assert_eq!(*controller.calls.lock().unwrap(), ["pair"]);
        controller.blocked.store(false, Ordering::SeqCst);
        settle(&ctx, &mut app, size);
        assert!(
            matches!(&app.dialog, Some(Dialog::EditMachine { edit, .. }) if edit.name == "retained-fixture-draft")
        );
        activate(&ctx, &mut app, size, "Save changes");
        let saved = settle(&ctx, &mut app, size);
        assert_focus(&saved, "Edit machine");
        assert_eq!(
            controller.data.lock().unwrap().machine.name,
            "retained-fixture-draft"
        );
        assert_eq!(
            *controller.calls.lock().unwrap(),
            ["pair", "cancel-pair", "edit"]
        );
    }
}

#[test]
fn every_mutating_dialog_disables_submit_but_keeps_cancel_while_busy() {
    for palette in [egui::Theme::Light, egui::Theme::Dark] {
        for size in [[1200.0, 720.0], [900.0, 600.0]] {
            for family in [
                Family::Edit,
                Family::Models,
                Family::Auth,
                Family::Key,
                Family::Revoke,
                Family::Disconnect,
                Family::Uninstall,
            ] {
                let (ctx, mut app, controller) = controlled_fixture(family, palette);
                activate(&ctx, &mut app, size, family.opener());
                let opened = settle(&ctx, &mut app, size);
                let label = match family {
                    Family::Models => {
                        let id = opened
                            .platform_output
                            .accesskit_update
                            .as_ref()
                            .unwrap()
                            .nodes
                            .iter()
                            .find(|(_, node)| {
                                node.label()
                                    .is_some_and(|label| label.starts_with("Gemini model 01"))
                            })
                            .unwrap()
                            .0;
                        draw(&ctx, &mut app, size, vec![click(id)]);
                        "Use as default"
                    }
                    Family::Key => {
                        draw(
                            &ctx,
                            &mut app,
                            size,
                            vec![egui::Event::AccessKitActionRequest(ActionRequest {
                                action: Action::SetValue,
                                target_tree: TreeId::ROOT,
                                target_node: target(&opened, "Enter the openai API key."),
                                data: Some(ActionData::Value("nonsecret-fixture".into())),
                            })],
                        );
                        "Connect"
                    }
                    Family::Edit => "Save changes",
                    Family::Auth => "Continue in browser",
                    Family::Revoke => "Unpair device",
                    Family::Disconnect => "Disconnect",
                    Family::Uninstall => "Uninstall Vadgr",
                    _ => unreachable!(),
                };
                let enabled = settle(&ctx, &mut app, size);
                let submit = target(&enabled, label);
                let prior_focus = enabled
                    .platform_output
                    .accesskit_update
                    .as_ref()
                    .unwrap()
                    .focus;
                controller.blocked.store(true, Ordering::SeqCst);
                let _release = ReleaseWorker(controller.clone());
                app.start(|controller| {
                    controller.refresh_provider("gemini")?;
                    Ok(OperationResult::Changed)
                });
                wait_call(&controller, "refresh");
                for _ in 0..2 {
                    draw(&ctx, &mut app, size, vec![]);
                }
                let busy = draw(&ctx, &mut app, size, vec![]);
                assert!(modal_has_waiting_reason(&busy));
                let busy_tree = busy.platform_output.accesskit_update.as_ref().unwrap();
                let focus_still_enabled = busy_tree.nodes.iter().any(|(id, node)| {
                    *id == prior_focus && !node.is_disabled() && node.supports_action(Action::Focus)
                });
                if focus_still_enabled {
                    assert_eq!(
                        busy_tree.focus, prior_focus,
                        "waiting reason changed a live control identity/focus"
                    );
                }
                let submit_node = busy
                    .platform_output
                    .accesskit_update
                    .as_ref()
                    .unwrap()
                    .nodes
                    .iter()
                    .find(|(id, _)| *id == submit)
                    .unwrap()
                    .1
                    .clone();
                assert!(
                    submit_node.is_disabled(),
                    "{family:?} must not offer a dropped mutation"
                );
                // target() requires an enabled focusable control, even while busy.
                let cancel = target(&busy, family.cancel());
                let cancel_bounds = busy_tree
                    .nodes
                    .iter()
                    .find(|(id, _)| *id == cancel)
                    .unwrap()
                    .1
                    .bounds()
                    .unwrap();
                assert!(
                    cancel_bounds.y0 >= 0.0 && cancel_bounds.y1 <= f64::from(size[1]),
                    "{family:?} waiting reason pushed the safe footer outside the viewport: {cancel_bounds:?}"
                );
                let reason = busy_tree
                    .nodes
                    .iter()
                    .find(|(_, node)| {
                        node.role() == Role::Label
                            && node_text(&busy_tree.nodes, node) == MODAL_WAIT_REASON
                    })
                    .unwrap()
                    .1
                    .bounds()
                    .unwrap();
                assert!(reason.y0 >= 0.0 && reason.y1 <= f64::from(size[1]));
                draw(&ctx, &mut app, size, vec![click(submit)]);
                assert!(app.dialog.is_some());
                assert_eq!(*controller.calls.lock().unwrap(), ["refresh"]);
                controller.blocked.store(false, Ordering::SeqCst);
                let ready = settle(&ctx, &mut app, size);
                assert!(!modal_has_waiting_reason(&ready));
                if focus_still_enabled {
                    assert_eq!(
                        ready
                            .platform_output
                            .accesskit_update
                            .as_ref()
                            .unwrap()
                            .focus,
                        prior_focus
                    );
                }
                assert_eq!(target(&ready, label), submit);
                activate(&ctx, &mut app, size, family.cancel());
                assert_focus(&settle(&ctx, &mut app, size), family.opener());
            }
        }
    }
}
