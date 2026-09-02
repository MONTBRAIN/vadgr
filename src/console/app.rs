use super::controller::{
    ConsoleController, DeviceSnapshot, HealthSnapshot, HttpConsoleController, MachineEdit,
    MachineSnapshot, PairingSession, ProviderSnapshot,
};
use super::theme;
use anyhow::{Result, anyhow};
use eframe::egui::{self, Align, Color32, Layout, RichText};
use std::sync::{Arc, mpsc};

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
enum View {
    Machine,
    Providers,
    Settings,
}

#[derive(Clone, Debug, Default)]
struct ConsoleData {
    install: crate::install::InstallStatus,
    health: Option<HealthSnapshot>,
    daemon_error: Option<String>,
    machine: MachineSnapshot,
    devices: Vec<DeviceSnapshot>,
    providers: Vec<ProviderSnapshot>,
}

enum OperationResult {
    Loaded(Box<ConsoleData>),
    Pairing(PairingSession),
    Changed,
    UpdateChecked(crate::install::UpdateCheck),
}

enum Dialog {
    Pairing {
        session: PairingSession,
        opened_at: std::time::Instant,
    },
    Revoke(DeviceSnapshot),
    EditMachine {
        edit: MachineEdit,
        skill_options: Vec<String>,
        server_options: Vec<String>,
    },
    ProviderAuth(ProviderSnapshot),
    ProviderPicker(Vec<ProviderSnapshot>),
    ProviderKey {
        provider: String,
        value: String,
    },
    Models {
        provider: ProviderSnapshot,
    },
    DisconnectProvider(ProviderSnapshot),
    Uninstall {
        purge: bool,
        confirmation: String,
    },
}

pub struct ConsoleApp {
    controller: Arc<dyn ConsoleController>,
    view: View,
    data: Option<ConsoleData>,
    pending: Option<mpsc::Receiver<Result<OperationResult>>>,
    dialog: Option<Dialog>,
    notice: Option<(bool, String)>,
    available_update: Option<String>,
}

impl ConsoleApp {
    fn new(controller: Arc<dyn ConsoleController>, ctx: &egui::Context) -> Self {
        theme::install(ctx);
        let mut app = Self {
            controller,
            view: View::Machine,
            data: None,
            pending: None,
            dialog: None,
            notice: None,
            available_update: None,
        };
        app.reload();
        app
    }

    fn start(
        &mut self,
        task: impl FnOnce(Arc<dyn ConsoleController>) -> Result<OperationResult> + Send + 'static,
    ) {
        if self.pending.is_some() {
            return;
        }
        let controller = self.controller.clone();
        let (send, receive) = mpsc::channel();
        std::thread::spawn(move || {
            let _ = send.send(task(controller));
        });
        self.pending = Some(receive);
        self.notice = None;
    }

    fn reload(&mut self) {
        self.start(|controller| {
            let install = controller.install_status()?;
            let daemon = (|| {
                Ok::<_, anyhow::Error>((
                    controller.health()?,
                    controller.machine()?,
                    controller.devices()?,
                    controller.providers()?,
                ))
            })();
            let (health, machine, devices, providers, daemon_error) = match daemon {
                Ok((health, machine, devices, providers)) => {
                    (Some(health), machine, devices, providers, None)
                }
                Err(error) => (
                    None,
                    MachineSnapshot::default(),
                    Vec::new(),
                    Vec::new(),
                    Some(format!("The daemon is unavailable: {error}")),
                ),
            };
            Ok(OperationResult::Loaded(Box::new(ConsoleData {
                install,
                health,
                daemon_error,
                machine,
                devices,
                providers,
            })))
        });
    }

    fn poll(&mut self, ctx: &egui::Context) {
        let Some(receiver) = self.pending.as_ref() else {
            return;
        };
        match receiver.try_recv() {
            Ok(Ok(OperationResult::Loaded(data))) => {
                self.data = Some(*data);
                self.pending = None;
            }
            Ok(Ok(OperationResult::Pairing(session))) => {
                self.dialog = Some(Dialog::Pairing {
                    session,
                    opened_at: std::time::Instant::now(),
                });
                self.pending = None;
            }
            Ok(Ok(OperationResult::Changed)) => {
                self.pending = None;
                self.notice = Some((true, "The change completed.".to_owned()));
                self.reload();
            }
            Ok(Ok(OperationResult::UpdateChecked(update))) => {
                self.pending = None;
                if update.update_available {
                    self.available_update = Some(update.available_version.clone());
                    self.notice = Some((
                        true,
                        format!("Vadgr {} is ready to install.", update.available_version),
                    ));
                } else {
                    self.available_update = None;
                    self.notice = Some((true, "Vadgr is up to date.".to_owned()));
                }
            }
            Ok(Err(error)) => {
                self.pending = None;
                self.notice = Some((false, error.to_string()));
            }
            Err(mpsc::TryRecvError::Disconnected) => {
                self.pending = None;
                self.notice = Some((false, "The operation ended without a result.".to_owned()));
            }
            Err(mpsc::TryRecvError::Empty) => {
                ctx.request_repaint_after(std::time::Duration::from_millis(50))
            }
        }
    }

    fn sidebar(&mut self, root: &mut egui::Ui) {
        egui::Panel::left("navigation")
            .exact_size(188.0)
            .frame(
                egui::Frame::new()
                    .fill(theme::bg())
                    .inner_margin(egui::Margin::symmetric(15, 24)),
            )
            .show(root, |ui| {
                ui.label(RichText::new("vadgr.").size(24.0).strong());
                ui.label(
                    RichText::new(format!("LOCAL  ·  {}", env!("CARGO_PKG_VERSION")))
                        .monospace()
                        .size(10.0)
                        .color(theme::muted()),
                );
                ui.add_space(40.0);
                nav(ui, &mut self.view, View::Machine, "▣", "Machine");
                nav(ui, &mut self.view, View::Providers, "▰", "Providers");
                nav(ui, &mut self.view, View::Settings, "◉", "Settings");
            });
    }

    fn heading(ui: &mut egui::Ui, title: &str, subtitle: &str) {
        ui.label(RichText::new(title).heading().strong());
        ui.label(RichText::new(subtitle).color(theme::muted()));
        ui.add_space(20.0);
    }

    fn machine_view(&mut self, ui: &mut egui::Ui) {
        let Some(data) = self.data.clone() else {
            loading(ui, "Reading this machine...");
            return;
        };
        ui.horizontal(|ui| {
            ui.vertical(|ui| {
                Self::heading(
                    ui,
                    if data.machine.name.is_empty() {
                        "This machine"
                    } else {
                        &data.machine.name
                    },
                    "This machine and its paired devices",
                )
            });
            ui.with_layout(Layout::right_to_left(Align::TOP), |ui| {
                if ui
                    .add_enabled(self.pending.is_none(), egui::Button::new("Restart Vadgr"))
                    .clicked()
                {
                    self.start(|controller| {
                        controller.restart_daemon()?;
                        Ok(OperationResult::Changed)
                    });
                }
            });
        });

        theme::card().show(ui, |ui| {
            ui.horizontal(|ui| {
                ui.label(RichText::new("▰").size(20.0));
                ui.vertical(|ui| {
                    let default = data
                        .machine
                        .default_provider
                        .as_deref()
                        .zip(data.machine.default_model.as_deref());
                    let provider_ready = default.is_some_and(|(provider, _)| {
                        data.providers
                            .iter()
                            .any(|row| row.id == provider && row.connected && row.available)
                    });
                    match (default, provider_ready) {
                        (Some((provider, model)), true) => {
                            ui.label(RichText::new(format!("{provider} · {model}")).strong());
                            ui.label(
                                RichText::new("Machine default · ready").color(theme::muted()),
                            );
                        }
                        (Some((provider, model)), false) => {
                            ui.label(RichText::new(format!("{provider} · {model}")).strong());
                            ui.label(
                                RichText::new("Default provider needs attention")
                                    .color(theme::warning()),
                            );
                        }
                        (None, _) => {
                            ui.label(RichText::new("No model provider").strong());
                            ui.label(
                                RichText::new("Connect a provider before pairing")
                                    .color(theme::warning()),
                            );
                        }
                    }
                });
                ui.with_layout(Layout::right_to_left(Align::Center), |ui| {
                    if ui.button("Manage providers").clicked() {
                        self.view = View::Providers;
                    }
                });
            });
        });
        ui.add_space(18.0);
        section_label(ui, "MACHINE");
        ui.with_layout(Layout::right_to_left(Align::Center), |ui| {
            if ui.button("Edit machine").clicked() {
                self.dialog = Some(Dialog::EditMachine {
                    skill_options: data.machine.granted_skills.clone(),
                    server_options: data.machine.granted_mcp_servers.clone(),
                    edit: MachineEdit {
                        name: data.machine.name.clone(),
                        role_prompt: data.machine.role_prompt.clone(),
                        autonomy: data.machine.autonomy.clone(),
                        workspace: data.machine.workspace.clone(),
                        granted_skills: data.machine.granted_skills.clone(),
                        granted_mcp_servers: data.machine.granted_mcp_servers.clone(),
                    },
                });
            }
        });
        theme::card().show(ui, |ui| {
            info_row(
                ui,
                "▣",
                if data.machine.name.is_empty() {
                    "This machine"
                } else {
                    &data.machine.name
                },
                &format!("{} · {}", data.machine.platform, data.machine.id),
                if data
                    .health
                    .as_ref()
                    .is_some_and(|health| health.status == "healthy")
                {
                    "Running"
                } else {
                    "Unavailable"
                },
            );
            ui.separator();
            info_row(
                ui,
                "◆",
                "Computer use",
                &format!("Included · version {}", crate::cua_payload::CUA_VERSION),
                if data
                    .health
                    .as_ref()
                    .and_then(|health| health.modules.get("computer_use"))
                    .and_then(serde_json::Value::as_bool)
                    .unwrap_or(false)
                {
                    "Available"
                } else {
                    "Unavailable"
                },
            );
            ui.separator();
            let (transport_detail, transport_status) = transport_summary(&data.machine.transport);
            info_row(ui, "◎", "Connection", &transport_detail, &transport_status);
        });
        ui.add_space(18.0);
        ui.horizontal(|ui| {
            section_label(ui, "PAIRED DEVICES");
            ui.with_layout(Layout::right_to_left(Align::Center), |ui| {
                let provider_ready = data
                    .machine
                    .default_provider
                    .as_deref()
                    .zip(data.machine.default_model.as_deref())
                    .is_some_and(|(provider, _)| {
                        data.providers
                            .iter()
                            .any(|row| row.id == provider && row.connected && row.available)
                    });
                if ui
                    .add_enabled(
                        self.pending.is_none() && provider_ready,
                        egui::Button::new("Pair device"),
                    )
                    .clicked()
                {
                    self.start(|controller| {
                        Ok(OperationResult::Pairing(controller.start_pairing()?))
                    });
                }
            });
        });
        if data.devices.is_empty() {
            theme::card().show(ui, |ui| {
                ui.vertical_centered(|ui| {
                    ui.label(RichText::new("No paired devices").strong());
                    ui.label(
                        RichText::new("Pair the vadgr mobile app to control this machine.")
                            .color(theme::muted()),
                    );
                });
            });
        }
        for device in data.devices {
            theme::card().show(ui, |ui| {
                ui.horizontal(|ui| {
                    ui.label(RichText::new("▯").size(20.0));
                    ui.vertical(|ui| {
                        ui.label(RichText::new(&device.name).strong());
                        if device.transports.is_empty() {
                            ui.label(RichText::new("Paired device").color(theme::muted()));
                        }
                        for transport in &device.transports {
                            let detail = transport
                                .detail
                                .as_deref()
                                .map(|value| format!(" · {value}"))
                                .unwrap_or_default();
                            ui.label(
                                RichText::new(format!(
                                    "{} · {}{}",
                                    transport.label, transport.status, detail
                                ))
                                .color(theme::muted()),
                            );
                        }
                    });
                    ui.with_layout(Layout::right_to_left(Align::Center), |ui| {
                        if ui.button("Unpair").clicked() {
                            self.dialog = Some(Dialog::Revoke(device.clone()));
                        }
                        let (status, color) = if device.connected {
                            ("● Connected", theme::success())
                        } else {
                            ("○ Paired", theme::muted())
                        };
                        ui.label(RichText::new(status).color(color));
                    });
                });
            });
        }
    }

    fn providers_view(&mut self, ui: &mut egui::Ui) {
        let Some(data) = self.data.clone() else {
            loading(ui, "Reading providers...");
            return;
        };
        ui.horizontal(|ui| {
            ui.vertical(|ui| Self::heading(ui, "Providers", "Connections and default model"));
            ui.with_layout(Layout::right_to_left(Align::TOP), |ui| {
                let available = data
                    .providers
                    .iter()
                    .filter(|provider| !provider.connected)
                    .cloned()
                    .collect::<Vec<_>>();
                if ui
                    .add_enabled(!available.is_empty(), egui::Button::new("Connect provider"))
                    .clicked()
                {
                    self.dialog = Some(Dialog::ProviderPicker(available));
                }
            });
        });
        if data.providers.is_empty() {
            theme::card().show(ui, |ui| {
                ui.vertical_centered(|ui| {
                    ui.label(RichText::new("No providers are available").strong());
                    ui.label(
                        RichText::new("The daemon returned no provider descriptors.")
                            .color(theme::muted()),
                    );
                });
            });
        }
        for provider in data.providers {
            theme::card().show(ui, |ui| {
                ui.horizontal(|ui| {
                    ui.label(RichText::new("▰").size(20.0));
                    ui.vertical(|ui| {
                        ui.label(RichText::new(&provider.name).strong());
                        let detail = if provider.connected {
                            format!(
                                "{} · {} models",
                                provider.auth_method.as_deref().unwrap_or("Connected"),
                                provider.models.len()
                            )
                        } else {
                            "Not connected".to_owned()
                        };
                        ui.label(RichText::new(detail).color(theme::muted()));
                    });
                    ui.with_layout(Layout::right_to_left(Align::Center), |ui| {
                        if provider.connected && !provider.available {
                            ui.label(RichText::new("● Needs attention").color(theme::warning()));
                        } else if provider.connected {
                            if provider.catalog_stale {
                                ui.label(
                                    RichText::new("● Models need refresh").color(theme::warning()),
                                );
                            } else {
                                ui.label(RichText::new("● Connected").color(theme::success()));
                            }
                            if provider.default_model.is_some() {
                                ui.label(
                                    RichText::new("DEFAULT").monospace().color(theme::muted()),
                                );
                            }
                        } else if ui.button("Connect").clicked() {
                            self.open_provider_auth(provider.clone());
                        }
                    });
                });
                if provider.connected {
                    ui.separator();
                    ui.horizontal(|ui| {
                        if let Some(model) = &provider.default_model {
                            ui.label(RichText::new(model).monospace());
                            ui.label(RichText::new("Machine default").color(theme::muted()));
                        } else {
                            ui.label(
                                RichText::new("Not the machine default").color(theme::muted()),
                            );
                        }
                        ui.with_layout(Layout::right_to_left(Align::Center), |ui| {
                            if ui
                                .button(RichText::new("Disconnect").color(theme::danger()))
                                .clicked()
                            {
                                self.dialog = Some(Dialog::DisconnectProvider(provider.clone()));
                            }
                            if ui.button("Refresh models").clicked() {
                                let id = provider.id.clone();
                                self.start(move |c| {
                                    c.refresh_provider(&id)?;
                                    Ok(OperationResult::Changed)
                                });
                            }
                            if ui
                                .button(if provider.default_model.is_some() {
                                    "Change default"
                                } else {
                                    "Make default"
                                })
                                .clicked()
                            {
                                self.dialog = Some(Dialog::Models {
                                    provider: provider.clone(),
                                });
                            }
                        });
                    });
                }
            });
            ui.add_space(10.0);
        }
    }

    fn open_provider_auth(&mut self, provider: ProviderSnapshot) {
        if provider.auth_methods.len() == 1 && provider.auth_methods[0] == "api_key" {
            self.dialog = Some(Dialog::ProviderKey {
                provider: provider.id,
                value: String::new(),
            });
        } else {
            self.dialog = Some(Dialog::ProviderAuth(provider));
        }
    }

    fn settings_view(&mut self, ui: &mut egui::Ui) {
        let Some(data) = self.data.clone() else {
            loading(ui, "Reading installation status...");
            return;
        };
        Self::heading(ui, "Settings", "Startup, updates, repair and uninstall");
        section_label(ui, "INSTALLATION");
        theme::card().show(ui, |ui| {
            if setting_row(
                ui,
                "▷",
                "Launch at login",
                "Start Vadgr when you sign in",
                if data.install.launch_at_login {
                    "Turn off"
                } else {
                    "Turn on"
                },
                data.install.installed,
            ) {
                let enabled = !data.install.launch_at_login;
                self.start(move |c| {
                    c.set_launch_at_login(enabled)?;
                    Ok(OperationResult::Changed)
                });
            }
            ui.separator();
            let update_label = if self.available_update.is_some() {
                "Install update"
            } else {
                "Check for updates"
            };
            if setting_row(
                ui,
                "◉",
                &format!("Version {}", data.install.version),
                &data.install.update_state,
                update_label,
                data.install.update_available,
            ) {
                if self.available_update.is_some() {
                    self.start(|c| {
                        c.apply_update()?;
                        Ok(OperationResult::Changed)
                    });
                } else {
                    self.start(|c| Ok(OperationResult::UpdateChecked(c.check_for_updates()?)));
                }
            }
            ui.separator();
            if setting_row(
                ui,
                "◇",
                "Legal and notices",
                "Terms, licenses and software notices",
                "Open",
                data.install.legal_available,
            ) {
                self.start(|c| {
                    c.open_legal_notices()?;
                    Ok(OperationResult::Changed)
                });
            }
            ui.separator();
            if setting_row(
                ui,
                "↶",
                "Roll back",
                "Return to the retained previous signed generation",
                "Roll back",
                data.install.rollback_available,
            ) {
                self.start(|c| {
                    c.rollback_installation()?;
                    Ok(OperationResult::Changed)
                });
            }
            ui.separator();
            if setting_row(
                ui,
                "◇",
                "Repair installation",
                "Check and restore the Vadgr installation",
                "Repair",
                data.install.lifecycle_available,
            ) {
                self.start(|c| {
                    c.repair_installation()?;
                    Ok(OperationResult::Changed)
                });
            }
            ui.separator();
            ui.horizontal(|ui| {
                ui.label(RichText::new("×").size(20.0));
                ui.vertical(|ui| {
                    ui.label(RichText::new("Uninstall Vadgr").strong());
                    ui.label(
                        RichText::new("Keeps your settings and data by default")
                            .color(theme::muted()),
                    );
                });
                ui.with_layout(Layout::right_to_left(Align::Center), |ui| {
                    if ui
                        .add_enabled(
                            data.install.lifecycle_available,
                            egui::Button::new(RichText::new("Uninstall...").color(theme::danger())),
                        )
                        .clicked()
                    {
                        self.dialog = Some(Dialog::Uninstall {
                            purge: false,
                            confirmation: String::new(),
                        });
                    }
                });
            });
        });
    }

    fn draw_dialog(&mut self, ctx: &egui::Context) {
        let Some(mut dialog) = self.dialog.take() else {
            return;
        };
        let mut keep = true;
        egui::Window::new(dialog_title(&dialog))
            .collapsible(false)
            .resizable(false)
            .anchor(egui::Align2::CENTER_CENTER, [0.0, 0.0])
            .min_width(520.0)
            .show(ctx, |ui| match &mut dialog {
                Dialog::Pairing { session, opened_at } => {
                    let elapsed = opened_at.elapsed().as_secs();
                    let remaining = crate::auth::pairing::PAIRING_TTL_SECONDS
                        .saturating_sub(elapsed);
                    ui.label("Scan this code with the vadgr mobile app, or type the code.");
                    ui.add_space(12.0);
                    ui.vertical_centered(|ui| {
                        if let Err(error) = pairing_qr(ui, session) {
                            ui.label(RichText::new(error.to_string()).color(theme::danger()));
                        }
                        ui.label(RichText::new(&session.code).monospace().size(28.0).strong());
                        ui.label(RichText::new(format!("Machine: {}", session.machine_name)).color(theme::muted()));
                        if remaining == 0 {
                            ui.label(
                                RichText::new("This pairing code expired.")
                                    .color(theme::danger()),
                            );
                        } else {
                            ui.label(
                                RichText::new(format!(
                                    "Expires in {}:{:02}",
                                    remaining / 60,
                                    remaining % 60
                                ))
                                .color(theme::muted()),
                            );
                            ui.ctx().request_repaint_after(std::time::Duration::from_secs(1));
                        }
                    });
                    ui.add_space(14.0);
                    if ui
                        .button(if remaining == 0 {
                            "Close"
                        } else {
                            "Cancel pairing"
                        })
                        .clicked()
                    {
                        self.start(|c| { c.cancel_pairing()?; Ok(OperationResult::Changed) });
                        keep = false;
                    }
                }
                Dialog::Revoke(device) => {
                    ui.label(format!("Unpair {}?", device.name));
                    ui.label(RichText::new("This device will lose access now. You can pair it again later.").color(theme::muted()));
                    ui.horizontal(|ui| {
                        if ui.button("Keep paired").clicked() { keep = false; }
                        if ui.button(RichText::new("Unpair device").color(theme::danger())).clicked() {
                            let id = device.id.clone();
                            self.start(move |c| { c.revoke_device(&id)?; Ok(OperationResult::Changed) });
                            keep = false;
                        }
                    });
                }
                Dialog::EditMachine {
                    edit,
                    skill_options,
                    server_options,
                } => {
                    ui.label("Machine name");
                    ui.text_edit_singleline(&mut edit.name);
                    ui.label("Workspace");
                    let mut workspace = edit.workspace.clone().unwrap_or_default();
                    if ui.text_edit_singleline(&mut workspace).changed() { edit.workspace = (!workspace.trim().is_empty()).then_some(workspace); }
                    ui.label("Role prompt");
                    ui.add(egui::TextEdit::multiline(&mut edit.role_prompt).desired_rows(4));
                    ui.label("Autonomy mode");
                    let mode = edit
                        .autonomy
                        .get("mode")
                        .and_then(serde_json::Value::as_str)
                        .unwrap_or("default")
                        .to_owned();
                    let mut selected_mode = mode;
                    egui::ComboBox::from_id_salt("machine-autonomy")
                        .selected_text(&selected_mode)
                        .show_ui(ui, |ui| {
                            for candidate in ["default", "autonomous", "paranoid", "bypass"] {
                                ui.selectable_value(
                                    &mut selected_mode,
                                    candidate.to_owned(),
                                    candidate,
                                );
                            }
                        });
                    edit.autonomy = serde_json::json!({"mode": selected_mode});
                    if !skill_options.is_empty() {
                        ui.label("Skill grants");
                        for skill in skill_options.iter() {
                            grant_checkbox(ui, &mut edit.granted_skills, skill, false);
                        }
                    }
                    ui.label("MCP server grants");
                    for server in server_options.iter() {
                        let required = matches!(server.as_str(), "control-plane" | "vadgr-computer-use");
                        grant_checkbox(ui, &mut edit.granted_mcp_servers, server, required);
                    }
                    ui.horizontal(|ui| {
                        if ui.button("Cancel").clicked() { keep = false; }
                        if ui.button("Save changes").clicked() {
                            let value = edit.clone();
                            self.start(move |c| { c.update_machine(&value)?; Ok(OperationResult::Changed) });
                            keep = false;
                        }
                    });
                }
                Dialog::ProviderAuth(provider) => {
                    ui.label(format!("Choose how to connect {}.", provider.name));
                    ui.label(
                        RichText::new("Authentication is handled by the local Vadgr daemon.")
                            .color(theme::muted()),
                    );
                    ui.add_space(12.0);
                    if provider.auth_methods.iter().any(|method| method == "oauth")
                        && ui.button("Continue in browser").clicked()
                    {
                        let id = provider.id.clone();
                        self.start(move |c| {
                            c.connect_oauth(&id)?;
                            Ok(OperationResult::Changed)
                        });
                        keep = false;
                    }
                    if provider.auth_methods.iter().any(|method| method == "api_key")
                        && ui.button("Use an API key").clicked()
                    {
                        self.dialog = Some(Dialog::ProviderKey {
                            provider: provider.id.clone(),
                            value: String::new(),
                        });
                        keep = false;
                    }
                    if ui.button("Cancel").clicked() { keep = false; }
                }
                Dialog::ProviderPicker(providers) => {
                    ui.label("Choose a provider to connect.");
                    ui.add_space(12.0);
                    for provider in providers {
                        if ui.button(&provider.name).clicked() {
                            let provider = provider.clone();
                            self.open_provider_auth(provider);
                            keep = false;
                        }
                    }
                    if ui.button("Cancel").clicked() { keep = false; }
                }
                Dialog::ProviderKey { provider, value } => {
                    ui.label(format!("Enter the {provider} API key."));
                    ui.add(egui::TextEdit::singleline(value).password(true).hint_text("API key"));
                    ui.label(RichText::new("The key goes directly to the local daemon. Vadgr never displays it again.").color(theme::muted()));
                    ui.horizontal(|ui| {
                        if ui.button("Cancel").clicked() { value.clear(); keep = false; }
                        if ui.add_enabled(!value.trim().is_empty(), egui::Button::new("Connect")).clicked() {
                            let id = provider.clone();
                            let secret = std::mem::take(value);
                            self.start(move |c| { c.connect_api_key(&id, secret)?; Ok(OperationResult::Changed) });
                            keep = false;
                        }
                    });
                }
                Dialog::Models { provider } => {
                    ui.label(format!("Choose the machine default from {}.", provider.name));
                    for model in &provider.models {
                        let label = if model.name.is_empty() { &model.id } else { &model.name };
                        if ui.button(label).clicked() {
                            let provider_id = provider.id.clone();
                            let model_id = model.id.clone();
                            self.start(move |c| { c.set_default_model(&provider_id, &model_id)?; Ok(OperationResult::Changed) });
                            keep = false;
                        }
                    }
                    if ui.button("Cancel").clicked() { keep = false; }
                }
                Dialog::DisconnectProvider(provider) => {
                    ui.label(format!("Disconnect {}?", provider.name));
                    ui.label(
                        RichText::new(
                            "Vadgr keeps the connection if this provider still owns the machine default.",
                        )
                        .color(theme::muted()),
                    );
                    ui.horizontal(|ui| {
                        if ui.button("Keep connected").clicked() { keep = false; }
                        if ui.button(RichText::new("Disconnect").color(theme::danger())).clicked() {
                            let id = provider.id.clone();
                            self.start(move |c| {
                                c.disconnect_provider(&id)?;
                                Ok(OperationResult::Changed)
                            });
                            keep = false;
                        }
                    });
                }
                Dialog::Uninstall { purge, confirmation } => {
                    ui.checkbox(purge, "Also delete settings, credentials, pairings and journals");
                    if *purge {
                        ui.label("Type DELETE OWNER DATA to confirm the separate data deletion.");
                        ui.text_edit_singleline(confirmation);
                    }
                    ui.label(
                        RichText::new(
                            "Vadgr removes package files. Owner data stays unless you select and confirm its separate deletion.",
                        )
                        .color(theme::muted()),
                    );
                    let confirmed = !*purge || confirmation == "DELETE OWNER DATA";
                    ui.horizontal(|ui| {
                        if ui.button("Keep installed").clicked() { keep = false; }
                        if ui
                            .add_enabled(
                                confirmed,
                                egui::Button::new(
                                    RichText::new("Uninstall Vadgr").color(theme::danger()),
                                ),
                            )
                            .clicked()
                        {
                            let purge = *purge;
                            self.start(move |c| {
                                c.uninstall(purge)?;
                                Ok(OperationResult::Changed)
                            });
                            keep = false;
                        }
                    });
                }
            });
        if keep {
            self.dialog = Some(dialog);
        }
    }
}

fn pairing_uri(session: &PairingSession) -> String {
    let mut query = url::form_urlencoded::Serializer::new(String::new());
    query
        .append_pair("token", &session.code)
        .append_pair("name", &session.machine_name);
    if let Some(transports) = session.transports.as_object() {
        for address in transports.values().filter_map(serde_json::Value::as_object) {
            for (key, value) in address {
                match value {
                    serde_json::Value::Array(values) => {
                        for value in values {
                            query.append_pair(key, &pairing_scalar(value));
                        }
                    }
                    value => {
                        query.append_pair(key, &pairing_scalar(value));
                    }
                }
            }
        }
    }
    format!("vadgr://pair?{}", query.finish())
}

fn pairing_scalar(value: &serde_json::Value) -> String {
    value
        .as_str()
        .map(str::to_owned)
        .unwrap_or_else(|| value.to_string())
}

fn transport_summary(value: &serde_json::Value) -> (String, String) {
    let Some(transports) = value.as_object() else {
        return ("No transport details".to_owned(), "Unavailable".to_owned());
    };
    let labels = transports
        .iter()
        .map(|(id, detail)| {
            let label = match id.as_str() {
                "iroh" | "built_in" => "Built-in",
                "tailscale" => "Tailscale",
                "loopback" => "Local",
                other => other,
            };
            let available = detail
                .get("available")
                .and_then(serde_json::Value::as_bool)
                .unwrap_or(false);
            format!(
                "{label} {}",
                if available { "ready" } else { "unavailable" }
            )
        })
        .collect::<Vec<_>>();
    let ready = transports.values().any(|detail| {
        detail
            .get("available")
            .and_then(serde_json::Value::as_bool)
            .unwrap_or(false)
    });
    (
        if labels.is_empty() {
            "No transports are configured".to_owned()
        } else {
            labels.join(" · ")
        },
        if ready { "Ready" } else { "Unavailable" }.to_owned(),
    )
}

fn pairing_qr(ui: &mut egui::Ui, session: &PairingSession) -> Result<()> {
    use qrcode_generator::qr::{Encoder, ErrorCorrection};

    let symbol = Encoder::new(ErrorCorrection::Low)
        .encode_text(pairing_uri(session))
        .map_err(|error| anyhow!("The pairing QR could not be encoded: {error}"))?;
    let matrix = symbol.to_matrix();
    let quiet_zone = 4usize;
    let modules = matrix.len() + quiet_zone * 2;
    let side = 236.0;
    let (response, painter) = ui.allocate_painter(egui::vec2(side, side), egui::Sense::hover());
    painter.rect_filled(response.rect, 5.0, Color32::WHITE);
    let module = side / modules as f32;
    for (y, row) in matrix.iter().enumerate() {
        for (x, dark) in row.iter().enumerate() {
            if *dark {
                let min = response.rect.min
                    + egui::vec2(
                        (x + quiet_zone) as f32 * module,
                        (y + quiet_zone) as f32 * module,
                    );
                let max = response.rect.min
                    + egui::vec2(
                        (x + quiet_zone + 1) as f32 * module,
                        (y + quiet_zone + 1) as f32 * module,
                    );
                painter.rect_filled(egui::Rect::from_min_max(min, max), 0.0, Color32::BLACK);
            }
        }
    }
    Ok(())
}

impl eframe::App for ConsoleApp {
    fn ui(&mut self, root: &mut egui::Ui, _frame: &mut eframe::Frame) {
        let ctx = root.ctx().clone();
        theme::refresh(&ctx);
        self.poll(&ctx);
        self.sidebar(root);
        egui::CentralPanel::default()
            .frame(
                egui::Frame::new()
                    .fill(theme::bg())
                    .inner_margin(egui::Margin::symmetric(35, 22)),
            )
            .show(root, |ui| {
                if let Some((success, message)) = &self.notice {
                    let color = if *success {
                        theme::success()
                    } else {
                        theme::danger()
                    };
                    theme::card().show(ui, |ui| {
                        ui.label(RichText::new(message).color(color));
                    });
                    ui.add_space(12.0);
                }
                if let Some(message) = self
                    .data
                    .as_ref()
                    .and_then(|data| data.daemon_error.as_ref())
                {
                    theme::card().show(ui, |ui| {
                        ui.label(RichText::new(message).color(theme::danger()));
                        ui.label(
                            RichText::new("Restart Vadgr to try the local daemon again.")
                                .color(theme::muted()),
                        );
                    });
                    ui.add_space(12.0);
                }
                match self.view {
                    View::Machine => self.machine_view(ui),
                    View::Providers => self.providers_view(ui),
                    View::Settings => self.settings_view(ui),
                }
                if self.pending.is_some() {
                    ui.with_layout(Layout::bottom_up(Align::RIGHT), |ui| {
                        ui.spinner();
                    });
                }
            });
        self.draw_dialog(&ctx);
    }
}

pub fn run(base_url: String) -> Result<()> {
    let controller = Arc::new(HttpConsoleController::new(base_url)?);
    let options = eframe::NativeOptions {
        viewport: egui::ViewportBuilder::default()
            .with_inner_size([1200.0, 720.0])
            .with_min_inner_size([900.0, 600.0]),
        ..Default::default()
    };
    eframe::run_native(
        "Vadgr",
        options,
        Box::new(move |creation| Ok(Box::new(ConsoleApp::new(controller, &creation.egui_ctx)))),
    )
    .map_err(|error| anyhow!(error.to_string()))
}

fn nav(ui: &mut egui::Ui, current: &mut View, target: View, icon: &str, label: &str) {
    let selected = *current == target;
    let response = ui.add_sized(
        [158.0, 44.0],
        egui::Button::selectable(selected, format!("{icon}    {label}")),
    );
    if response.clicked() {
        *current = target;
    }
    ui.add_space(4.0);
}

fn section_label(ui: &mut egui::Ui, text: &str) {
    ui.label(
        RichText::new(text)
            .monospace()
            .size(11.0)
            .color(theme::muted()),
    );
}

fn info_row(ui: &mut egui::Ui, icon: &str, title: &str, detail: &str, status: &str) {
    ui.horizontal(|ui| {
        ui.label(RichText::new(icon).size(19.0));
        ui.vertical(|ui| {
            ui.label(RichText::new(title).strong());
            ui.label(RichText::new(detail).color(theme::muted()));
        });
        ui.with_layout(Layout::right_to_left(Align::Center), |ui| {
            ui.label(RichText::new(status).color(theme::muted()));
        });
    });
}

fn setting_row(
    ui: &mut egui::Ui,
    icon: &str,
    title: &str,
    detail: &str,
    action: &str,
    enabled: bool,
) -> bool {
    let mut clicked = false;
    ui.horizontal(|ui| {
        ui.label(RichText::new(icon).size(19.0));
        ui.vertical(|ui| {
            ui.label(RichText::new(title).strong());
            ui.label(RichText::new(detail).color(theme::muted()));
        });
        ui.with_layout(Layout::right_to_left(Align::Center), |ui| {
            clicked = ui.add_enabled(enabled, egui::Button::new(action)).clicked();
        });
    });
    clicked
}

fn loading(ui: &mut egui::Ui, message: &str) {
    ui.vertical_centered(|ui| {
        ui.add_space(180.0);
        ui.spinner();
        ui.label(RichText::new(message).color(theme::muted()));
    });
}

fn grant_checkbox(ui: &mut egui::Ui, selected: &mut Vec<String>, value: &str, required: bool) {
    let mut enabled = selected.iter().any(|entry| entry == value);
    let response = ui.add_enabled(
        !required,
        egui::Checkbox::new(
            &mut enabled,
            if required {
                format!("{value} (required)")
            } else {
                value.to_owned()
            },
        ),
    );
    if response.changed() {
        if enabled {
            if !selected.iter().any(|entry| entry == value) {
                selected.push(value.to_owned());
                selected.sort();
            }
        } else {
            selected.retain(|entry| entry != value);
        }
    }
}

fn dialog_title(dialog: &Dialog) -> &'static str {
    match dialog {
        Dialog::Pairing { .. } => "Pair a device",
        Dialog::Revoke(_) => "Unpair device",
        Dialog::EditMachine { .. } => "Edit machine",
        Dialog::ProviderAuth(_) => "Connect provider",
        Dialog::ProviderPicker(_) => "Connect provider",
        Dialog::ProviderKey { .. } => "Connect provider",
        Dialog::Models { .. } => "Change default",
        Dialog::DisconnectProvider(_) => "Disconnect provider",
        Dialog::Uninstall { .. } => "Uninstall Vadgr",
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn pairing_qr_keeps_the_mobile_deep_link_shape() {
        let uri = pairing_uri(&PairingSession {
            code: "ABCD-1234".to_owned(),
            machine_name: "Studio PC".to_owned(),
            transports: serde_json::json!({
                "tailscale": {"host": "100.64.0.2", "port": 8000},
                "built_in": {"relays": ["https://relay.example"]}
            }),
        });
        let parsed = url::Url::parse(&uri).unwrap();
        let query: std::collections::HashMap<_, _> = parsed.query_pairs().collect();
        assert_eq!(parsed.scheme(), "vadgr");
        assert_eq!(parsed.host_str(), Some("pair"));
        assert_eq!(
            query.get("token").map(|value| value.as_ref()),
            Some("ABCD-1234")
        );
        assert_eq!(
            query.get("name").map(|value| value.as_ref()),
            Some("Studio PC")
        );
        assert_eq!(
            query.get("host").map(|value| value.as_ref()),
            Some("100.64.0.2")
        );
        assert_eq!(query.get("port").map(|value| value.as_ref()), Some("8000"));
    }
}
