use super::controller::{
    ConsoleController, DeviceSnapshot, HealthSnapshot, HttpConsoleController, MachineEdit,
    MachineSnapshot, PairingSession, ProviderSnapshot,
};
use super::theme;
use anyhow::{Result, anyhow};
use eframe::egui::{self, Align, Color32, Layout, RichText, Sense, Stroke, StrokeKind, Vec2};
use std::sync::{Arc, mpsc};

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
enum View {
    Machine,
    Providers,
    Settings,
}

#[derive(Clone, Copy)]
enum Icon {
    Machine,
    Key,
    Gear,
    Plug,
    Globe,
    Phone,
    Play,
    Info,
    Shield,
    Undo,
    Close,
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
    last_refresh: std::time::Instant,
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
            last_refresh: std::time::Instant::now(),
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
                let paired = matches!(
                    &self.dialog,
                    Some(Dialog::Pairing {
                        session: _,
                        opened_at: _
                    })
                ) && self
                    .data
                    .as_ref()
                    .is_some_and(|previous| data.devices.len() > previous.devices.len());
                self.data = Some(*data);
                self.pending = None;
                self.last_refresh = std::time::Instant::now();
                if paired {
                    self.dialog = None;
                    self.notice = Some((true, "The device is paired.".to_owned()));
                }
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
                self.reload();
                self.notice = Some((true, "The change completed.".to_owned()));
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
                    .fill(theme::nav())
                    .inner_margin(egui::Margin::symmetric(15, 24)),
            )
            .show(root, |ui| {
                if self.dialog.is_some() {
                    ui.disable();
                }
                ui.label(
                    RichText::new("vadgr.")
                        .family(theme::heading_family())
                        .size(24.0),
                );
                ui.label(
                    RichText::new(format!("LOCAL  ·  {}", env!("CARGO_PKG_VERSION")))
                        .monospace()
                        .size(10.0)
                        .color(theme::muted()),
                );
                ui.add_space(40.0);
                nav(ui, &mut self.view, View::Machine, Icon::Machine, "Machine");
                nav(ui, &mut self.view, View::Providers, Icon::Key, "Providers");
                nav(ui, &mut self.view, View::Settings, Icon::Gear, "Settings");
            });
    }

    fn heading(ui: &mut egui::Ui, title: &str, subtitle: &str) {
        ui.label(
            RichText::new(title)
                .heading()
                .family(theme::heading_family()),
        );
        ui.label(RichText::new(subtitle).color(theme::muted()));
    }

    fn machine_view(&mut self, ui: &mut egui::Ui) {
        let Some(data) = self.data.clone() else {
            loading(ui, "Reading this machine...");
            return;
        };
        let header_width = visible_width(ui);
        fixed_ui(
            ui,
            Vec2::new(header_width, 62.0),
            Layout::right_to_left(Align::TOP),
            |ui| {
                if ui
                    .add_enabled(self.pending.is_none(), egui::Button::new("Restart Vadgr"))
                    .clicked()
                {
                    self.start(|controller| {
                        controller.restart_daemon()?;
                        Ok(OperationResult::Changed)
                    });
                }
                ui.with_layout(Layout::top_down(Align::Min), |ui| {
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
            },
        );
        ui.separator();
        ui.add_space(22.0);
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
        theme::card().show(ui, |ui| {
            let row_width = visible_width(ui);
            fixed_ui(
                ui,
                Vec2::new(row_width, 46.0),
                Layout::right_to_left(Align::Center),
                |ui| {
                    let manage = if provider_ready {
                        ui.button("Manage providers").clicked()
                    } else {
                        primary_button(ui, "Manage providers", true)
                    };
                    if manage {
                        self.view = View::Providers;
                    }
                    ui.with_layout(Layout::left_to_right(Align::Center), |ui| {
                        paint_icon(ui, Icon::Key, 20.0, theme::muted(), "Model provider");
                        ui.vertical(|ui| match (default, provider_ready) {
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
                        });
                    });
                },
            );
        });
        ui.add_space(18.0);
        let section_width = visible_width(ui);
        fixed_ui(
            ui,
            Vec2::new(section_width, 35.0),
            Layout::right_to_left(Align::Center),
            |ui| {
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
                ui.with_layout(Layout::left_to_right(Align::Center), |ui| {
                    section_label(ui, "MACHINE")
                });
            },
        );
        theme::card().show(ui, |ui| {
            info_row(
                ui,
                Icon::Machine,
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
                Icon::Plug,
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
            info_row(
                ui,
                Icon::Globe,
                "Connection",
                &transport_detail,
                &transport_status,
            );
        });
        ui.add_space(18.0);
        let devices_width = visible_width(ui);
        fixed_ui(
            ui,
            Vec2::new(devices_width, 38.0),
            Layout::right_to_left(Align::Center),
            |ui| {
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
                if primary_button(ui, "Pair device", self.pending.is_none() && provider_ready) {
                    self.start(|controller| {
                        Ok(OperationResult::Pairing(controller.start_pairing()?))
                    });
                }
                ui.with_layout(Layout::left_to_right(Align::Center), |ui| {
                    section_label(ui, "PAIRED DEVICES")
                });
            },
        );
        ui.separator();
        ui.add_space(22.0);
        if data.devices.is_empty() {
            let compact = ui.clip_rect().bottom() - ui.cursor().top() < 190.0;
            theme::card().show(ui, |ui| {
                ui.set_min_width(ui.available_width());
                if compact {
                    ui.set_min_height(58.0);
                    ui.horizontal_centered(|ui| {
                        paint_icon(ui, Icon::Phone, 24.0, theme::muted(), "Phone");
                        ui.add_space(8.0);
                        ui.vertical(|ui| {
                            ui.label(
                                RichText::new("No paired devices")
                                    .family(theme::heading_family())
                                    .size(16.0),
                            );
                            ui.label(
                                RichText::new(
                                    "Pair a phone to reach this machine away from your desk.",
                                )
                                .color(theme::muted()),
                            );
                        });
                    });
                } else {
                    ui.set_min_height(168.0);
                    ui.vertical_centered(|ui| {
                        ui.add_space(16.0);
                        icon_tile(ui, Icon::Phone, "Phone");
                        ui.add_space(4.0);
                        ui.label(
                            RichText::new("No paired devices")
                                .family(theme::heading_family())
                                .size(16.0),
                        );
                        ui.label(
                            RichText::new(
                                "Pair a phone to reach this machine away from your desk.",
                            )
                            .color(theme::muted()),
                        );
                    });
                }
            });
        }
        for device in data.devices {
            theme::card().show(ui, |ui| {
                let row_width = visible_width(ui);
                ui.horizontal(|ui| {
                    paint_icon(ui, Icon::Phone, 20.0, theme::muted(), "Phone");
                    fixed_ui(
                        ui,
                        Vec2::new((row_width - 280.0).max(200.0), 58.0),
                        Layout::top_down(Align::Min),
                        |ui| {
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
                        },
                    );
                    fixed_ui(
                        ui,
                        Vec2::new(240.0, 58.0),
                        Layout::right_to_left(Align::Center),
                        |ui| {
                            if ui.button("Unpair").clicked() {
                                self.dialog = Some(Dialog::Revoke(device.clone()));
                            }
                            let (status, color) = if device.connected {
                                ("● Connected", theme::success())
                            } else {
                                ("○ Paired", theme::muted())
                            };
                            ui.label(RichText::new(status).color(color));
                        },
                    );
                });
            });
        }
    }

    fn providers_view(&mut self, ui: &mut egui::Ui) {
        let Some(data) = self.data.clone() else {
            loading(ui, "Reading providers...");
            return;
        };
        let header_width = visible_width(ui);
        fixed_ui(
            ui,
            Vec2::new(header_width, 62.0),
            Layout::right_to_left(Align::TOP),
            |ui| {
                let available = data
                    .providers
                    .iter()
                    .filter(|provider| !provider.connected)
                    .cloned()
                    .collect::<Vec<_>>();
                if primary_button(ui, "Connect provider", !available.is_empty()) {
                    self.dialog = Some(Dialog::ProviderPicker(available));
                }
                ui.with_layout(Layout::top_down(Align::Min), |ui| {
                    Self::heading(ui, "Providers", "Connections and default model")
                });
            },
        );
        if !data.providers.iter().any(|provider| provider.connected) {
            theme::card().show(ui, |ui| {
                ui.set_min_height(188.0);
                ui.vertical_centered(|ui| {
                    ui.add_space(20.0);
                    icon_tile(ui, Icon::Key, "Provider");
                    ui.add_space(4.0);
                    ui.label(
                        RichText::new("No providers connected")
                            .family(theme::heading_family())
                            .size(16.0),
                    );
                    ui.label(
                        RichText::new(
                            "Connect one provider and Vadgr will verify a starter model before saving it.",
                        )
                            .color(theme::muted()),
                    );
                });
            });
            return;
        }
        for provider in data.providers {
            theme::card().show(ui, |ui| {
                let row_width = visible_width(ui);
                fixed_ui(
                    ui,
                    Vec2::new(row_width, 46.0),
                    Layout::right_to_left(Align::Center),
                    |ui| {
                        if provider.connected && !provider.available {
                            ui.label(RichText::new("● Needs attention").color(theme::warning()));
                        } else if provider.connected {
                            let status = if provider.catalog_stale {
                                RichText::new("● Models need refresh").color(theme::warning())
                            } else {
                                RichText::new("● Connected").color(theme::success())
                            };
                            ui.label(status);
                            if provider.default_model.is_some() {
                                ui.label(
                                    RichText::new("DEFAULT").monospace().color(theme::muted()),
                                );
                            }
                        } else if ui.button("Connect").clicked() {
                            self.open_provider_auth(provider.clone());
                        }
                        ui.with_layout(Layout::left_to_right(Align::Center), |ui| {
                            paint_icon(ui, Icon::Key, 20.0, theme::muted(), "Provider");
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
                        });
                    },
                );
                if provider.connected {
                    ui.separator();
                    let footer_width = visible_width(ui);
                    fixed_ui(
                        ui,
                        Vec2::new(footer_width, 38.0),
                        Layout::right_to_left(Align::Center),
                        |ui| {
                            if danger_button(ui, "Disconnect", true) {
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
                            ui.with_layout(Layout::left_to_right(Align::Center), |ui| {
                                if let Some(model) = &provider.default_model {
                                    ui.label(RichText::new(model).monospace());
                                    ui.label(
                                        RichText::new("Machine default").color(theme::muted()),
                                    );
                                } else {
                                    ui.label(
                                        RichText::new("Not the machine default")
                                            .color(theme::muted()),
                                    );
                                }
                            });
                        },
                    );
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
        ui.separator();
        ui.add_space(22.0);
        section_label(ui, "INSTALLATION");
        theme::card().show(ui, |ui| {
            if setting_row(
                ui,
                Icon::Play,
                "Launch at login",
                if data.install.installed {
                    "Start Vadgr when you sign in"
                } else {
                    INSTALLED_ONLY_DETAIL
                },
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
                Icon::Info,
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
                Icon::Shield,
                "Legal and notices",
                legal_detail(&data.install),
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
                Icon::Undo,
                "Roll back",
                rollback_detail(&data.install),
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
                Icon::Shield,
                "Repair installation",
                if data.install.lifecycle_available {
                    "Check and restore the Vadgr installation"
                } else {
                    INSTALLED_ONLY_DETAIL
                },
                "Repair",
                data.install.lifecycle_available,
            ) {
                self.start(|c| {
                    c.repair_installation()?;
                    Ok(OperationResult::Changed)
                });
            }
            ui.separator();
            let uninstall_width = visible_width(ui);
            fixed_ui(
                ui,
                Vec2::new(uninstall_width, 46.0),
                Layout::right_to_left(Align::Center),
                |ui| {
                    if danger_button(ui, "Uninstall...", data.install.lifecycle_available) {
                        self.dialog = Some(Dialog::Uninstall {
                            purge: false,
                            confirmation: String::new(),
                        });
                    }
                    ui.with_layout(Layout::left_to_right(Align::Center), |ui| {
                        paint_icon(ui, Icon::Close, 20.0, theme::muted(), "Uninstall");
                        ui.vertical(|ui| {
                            ui.label(RichText::new("Uninstall Vadgr").strong());
                            ui.label(
                                RichText::new(if data.install.lifecycle_available {
                                    "Keeps your settings and data by default"
                                } else {
                                    INSTALLED_ONLY_DETAIL
                                })
                                .color(theme::muted()),
                            );
                        });
                    });
                },
            );
        });
    }

    fn draw_dialog(&mut self, ctx: &egui::Context) {
        let Some(mut dialog) = self.dialog.take() else {
            return;
        };
        let pairing_dialog = matches!(&dialog, Dialog::Pairing { .. });
        let mut keep = true;
        let screen = ctx.content_rect();
        let compact_dialog = screen.height() < 650.0 || screen.width() < 1000.0;
        let dialog_width = if pairing_dialog {
            if compact_dialog { 560.0 } else { 620.0 }
        } else {
            570.0
        };
        egui::Area::new("console-modal-scrim".into())
            .order(egui::Order::Foreground)
            .fixed_pos(screen.min)
            .show(ctx, |ui| {
                let (rect, _) = ui.allocate_exact_size(screen.size(), Sense::click_and_drag());
                ui.painter()
                    .rect_filled(rect, 0.0, Color32::from_black_alpha(176));
            });
        egui::Window::new(dialog_title(&dialog))
            .title_bar(false)
            .collapsible(false)
            .resizable(false)
            .order(egui::Order::Foreground)
            .anchor(egui::Align2::CENTER_CENTER, [0.0, 0.0])
            .min_width(dialog_width)
            .max_width(dialog_width)
            .frame(
                egui::Frame::new()
                    .fill(theme::panel())
                    .stroke(Stroke::new(1.0, theme::border()))
                    .corner_radius(20)
                    .inner_margin(26),
            )
            .show(ctx, |ui| {
                ui.vertical_centered(|ui| {
                    let (bar, _) =
                        ui.allocate_exact_size(Vec2::new(36.0, 4.0), Sense::hover());
                    ui.painter().rect_filled(bar, 2.0, theme::border());
                });
                ui.add_space(10.0);
                let title = RichText::new(dialog_title(&dialog))
                    .family(theme::heading_family())
                    .size(if pairing_dialog { 22.0 } else { 19.0 });
                if pairing_dialog {
                    ui.vertical_centered(|ui| {
                        ui.label(title);
                    });
                } else {
                    ui.label(title);
                }
                ui.add_space(5.0);
                match &mut dialog {
                Dialog::Pairing { session, opened_at } => {
                    let elapsed = opened_at.elapsed().as_secs();
                    let remaining = crate::auth::pairing::PAIRING_TTL_SECONDS
                        .saturating_sub(elapsed);
                    ui.vertical_centered(|ui| {
                        ui.label(
                            RichText::new(format!(
                                "Scan or enter the same one-time code. Both expire in {}:{:02}.",
                                remaining / 60,
                                remaining % 60
                            ))
                            .color(theme::muted()),
                        );
                        ui.add_space(18.0);
                        let qr_side = if compact_dialog { 190.0 } else { 230.0 };
                        if let Err(error) = pairing_qr(ui, session, qr_side) {
                            ui.label(RichText::new(error.to_string()).color(theme::danger()));
                        }
                        ui.add_space(14.0);
                        ui.label(
                            RichText::new("Open Vadgr on your phone and choose Pair machine.")
                                .color(theme::muted()),
                        );
                        ui.add_space(5.0);
                        ui.label(
                            RichText::new(&session.code)
                                .monospace()
                                .size(23.0)
                                .strong(),
                        );
                        ui.label(
                            RichText::new("Typing the code pairs the same way as scanning it.")
                                .color(theme::muted()),
                        );
                        if remaining == 0 {
                            ui.label(
                                RichText::new("This pairing code expired.")
                                    .color(theme::danger()),
                            );
                        } else {
                            ui.ctx()
                                .request_repaint_after(std::time::Duration::from_secs(1));
                        }
                        ui.add_space(18.0);
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
                    });
                }
                Dialog::Revoke(device) => {
                    ui.label(RichText::new("This device will lose access now. You can pair it again later.").color(theme::muted()));
                    ui.horizontal(|ui| {
                        if ui.button("Keep paired").clicked() { keep = false; }
                        if danger_button(ui, "Unpair device", true) {
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
                    let machine_name_label = ui.label("Machine name");
                    ui.text_edit_singleline(&mut edit.name)
                        .labelled_by(machine_name_label.id);
                    let workspace_label = ui.label("Workspace");
                    let mut workspace = edit.workspace.clone().unwrap_or_default();
                    if ui
                        .text_edit_singleline(&mut workspace)
                        .labelled_by(workspace_label.id)
                        .changed()
                    {
                        edit.workspace = (!workspace.trim().is_empty()).then_some(workspace);
                    }
                    let role_prompt_label = ui.label("Role prompt");
                    ui.add(egui::TextEdit::multiline(&mut edit.role_prompt).desired_rows(4))
                        .labelled_by(role_prompt_label.id);
                    let autonomy_label = ui.label("Autonomy mode");
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
                        })
                        .response
                        .labelled_by(autonomy_label.id);
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
                    let key_label = ui.label(format!("Enter the {provider} API key."));
                    ui.add(egui::TextEdit::singleline(value).password(true).hint_text("API key"))
                        .labelled_by(key_label.id);
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
                    ui.label(
                        RichText::new(
                            "Vadgr keeps the connection if this provider still owns the machine default.",
                        )
                        .color(theme::muted()),
                    );
                    ui.horizontal(|ui| {
                        if ui.button("Keep connected").clicked() { keep = false; }
                        if danger_button(ui, "Disconnect", true) {
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
                        let confirmation_label = ui.label(
                            "Type DELETE OWNER DATA to confirm the separate data deletion.",
                        );
                        ui.text_edit_singleline(confirmation)
                            .labelled_by(confirmation_label.id);
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
                        if danger_button(ui, "Uninstall Vadgr", confirmed) {
                            let purge = *purge;
                            self.start(move |c| {
                                c.uninstall(purge)?;
                                Ok(OperationResult::Changed)
                            });
                            keep = false;
                        }
                    });
                }
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

fn pairing_qr(ui: &mut egui::Ui, session: &PairingSession, side: f32) -> Result<()> {
    use qrcode_generator::qr::{Encoder, ErrorCorrection};

    let symbol = Encoder::new(ErrorCorrection::Low)
        .encode_text(pairing_uri(session))
        .map_err(|error| anyhow!("The pairing QR could not be encoded: {error}"))?;
    let matrix = symbol.to_matrix();
    let quiet_zone = 4usize;
    let modules = matrix.len() + quiet_zone * 2;
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
        let refresh_after = if matches!(self.dialog, Some(Dialog::Pairing { .. })) {
            std::time::Duration::from_secs(2)
        } else {
            std::time::Duration::from_secs(8)
        };
        if self.pending.is_none()
            && (self.dialog.is_none() || matches!(self.dialog, Some(Dialog::Pairing { .. })))
            && self.last_refresh.elapsed() >= refresh_after
        {
            self.reload();
        }
        ctx.request_repaint_after(refresh_after);
        self.sidebar(root);
        egui::CentralPanel::default()
            .frame(
                egui::Frame::new()
                    .fill(theme::bg())
                    .inner_margin(egui::Margin::symmetric(35, 22)),
            )
            .show(root, |ui| {
                // A modal sheet owns interaction and focus while it is open.
                // The scrim is visual; this state is what makes the underlying
                // AccessKit tree unavailable to keyboard and automation users.
                if self.dialog.is_some() {
                    ui.disable();
                }
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
                egui::ScrollArea::vertical()
                    .auto_shrink([false, false])
                    .show(ui, |ui| {
                        match self.view {
                            View::Machine => self.machine_view(ui),
                            View::Providers => self.providers_view(ui),
                            View::Settings => self.settings_view(ui),
                        }
                        if self.pending.is_some() {
                            ui.add_space(12.0);
                            theme::card().show(ui, |ui| {
                                ui.horizontal(|ui| {
                                    ui.spinner();
                                    ui.label(
                                        RichText::new("Vadgr is completing this action...")
                                            .color(theme::muted()),
                                    );
                                });
                            });
                        }
                    });
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

fn nav(ui: &mut egui::Ui, current: &mut View, target: View, icon: Icon, label: &str) {
    let selected = *current == target;
    let (rect, response) = ui.allocate_exact_size(Vec2::new(158.0, 42.0), Sense::click());
    response.widget_info(|| {
        egui::WidgetInfo::selected(egui::WidgetType::Button, true, selected, label)
    });
    let fill = if selected || response.hovered() {
        theme::tertiary()
    } else {
        Color32::TRANSPARENT
    };
    ui.painter().rect_filled(rect, 10.0, fill);
    if response.has_focus() {
        ui.painter().rect_stroke(
            rect,
            10.0,
            Stroke::new(1.0, theme::text()),
            StrokeKind::Inside,
        );
    }
    let icon_rect = egui::Rect::from_center_size(
        egui::pos2(rect.left() + 20.0, rect.center().y),
        Vec2::splat(18.0),
    );
    paint_icon_at(ui.painter(), icon_rect, icon, theme::muted());
    ui.painter().text(
        egui::pos2(rect.left() + 40.0, rect.center().y),
        egui::Align2::LEFT_CENTER,
        label,
        egui::FontId::new(13.0, theme::medium_family()),
        if selected {
            theme::text()
        } else {
            theme::muted()
        },
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

fn fixed_ui<R>(
    ui: &mut egui::Ui,
    size: Vec2,
    layout: Layout,
    add_contents: impl FnOnce(&mut egui::Ui) -> R,
) -> R {
    let (rect, _) = ui.allocate_exact_size(size, Sense::hover());
    ui.scope_builder(
        egui::UiBuilder::new().max_rect(rect).layout(layout),
        add_contents,
    )
    .inner
}

fn visible_width(ui: &egui::Ui) -> f32 {
    (ui.max_rect().right() - ui.cursor().left()).max(0.0)
}

fn info_row(ui: &mut egui::Ui, icon: Icon, title: &str, detail: &str, status: &str) {
    let row_width = visible_width(ui);
    fixed_ui(
        ui,
        Vec2::new(row_width, 46.0),
        Layout::right_to_left(Align::Center),
        |ui| {
            ui.label(RichText::new(status).color(theme::muted()));
            ui.with_layout(Layout::left_to_right(Align::Center), |ui| {
                paint_icon(ui, icon, 19.0, theme::muted(), title);
                ui.vertical(|ui| {
                    ui.label(RichText::new(title).strong());
                    ui.label(RichText::new(detail).color(theme::muted()));
                });
            });
        },
    );
}

fn setting_row(
    ui: &mut egui::Ui,
    icon: Icon,
    title: &str,
    detail: &str,
    action: &str,
    enabled: bool,
) -> bool {
    let mut clicked = false;
    let row_width = visible_width(ui);
    fixed_ui(
        ui,
        Vec2::new(row_width, 46.0),
        Layout::right_to_left(Align::Center),
        |ui| {
            clicked = if title == "Launch at login" {
                toggle_switch(ui, action == "Turn off", enabled, title)
            } else {
                ui.add_enabled(enabled, egui::Button::new(action)).clicked()
            };
            ui.with_layout(Layout::left_to_right(Align::Center), |ui| {
                paint_icon(ui, icon, 19.0, theme::muted(), title);
                ui.vertical(|ui| {
                    ui.label(RichText::new(title).strong());
                    ui.label(RichText::new(detail).color(theme::muted()));
                });
            });
        },
    );
    clicked
}

const INSTALLED_ONLY_DETAIL: &str = "Available after Vadgr is installed";

fn legal_detail(install: &crate::install::InstallStatus) -> &'static str {
    if install.legal_available {
        "Terms, licenses and software notices"
    } else if install.installed {
        "Installed legal bundle is missing"
    } else {
        INSTALLED_ONLY_DETAIL
    }
}

fn rollback_detail(install: &crate::install::InstallStatus) -> &'static str {
    if install.rollback_available {
        "Return to the retained previous signed generation"
    } else if install.installed {
        "No verified previous generation is retained"
    } else {
        INSTALLED_ONLY_DETAIL
    }
}

fn paint_icon(ui: &mut egui::Ui, icon: Icon, size: f32, color: Color32, label: &str) {
    let (rect, response) = ui.allocate_exact_size(Vec2::splat(size), Sense::hover());
    response.widget_info(|| egui::WidgetInfo::labeled(egui::WidgetType::Image, true, label));
    paint_icon_at(ui.painter(), rect, icon, color);
}

fn icon_tile(ui: &mut egui::Ui, icon: Icon, label: &str) {
    let (rect, response) = ui.allocate_exact_size(Vec2::splat(64.0), Sense::hover());
    response.widget_info(|| egui::WidgetInfo::labeled(egui::WidgetType::Image, true, label));
    ui.painter().rect_filled(rect, 21.0, theme::tertiary());
    ui.painter().rect_stroke(
        rect,
        21.0,
        Stroke::new(1.0, theme::border()),
        StrokeKind::Inside,
    );
    paint_icon_at(
        ui.painter(),
        egui::Rect::from_center_size(rect.center(), Vec2::splat(28.0)),
        icon,
        theme::muted(),
    );
}

fn primary_button(ui: &mut egui::Ui, label: &str, enabled: bool) -> bool {
    ui.add_enabled(
        enabled,
        egui::Button::new(
            RichText::new(label)
                .family(theme::medium_family())
                .color(theme::accent_text()),
        )
        .fill(theme::accent())
        .stroke(Stroke::new(1.0, theme::accent())),
    )
    .clicked()
}

fn danger_button(ui: &mut egui::Ui, label: &str, enabled: bool) -> bool {
    ui.add_enabled(
        enabled,
        egui::Button::new(
            RichText::new(label)
                .family(theme::medium_family())
                .color(theme::danger()),
        )
        .fill(theme::danger().gamma_multiply(0.14))
        .stroke(Stroke::new(1.0, theme::danger().gamma_multiply(0.5))),
    )
    .clicked()
}

fn toggle_switch(ui: &mut egui::Ui, selected: bool, enabled: bool, label: &str) -> bool {
    let response = ui.add_enabled_ui(enabled, |ui| {
        let (rect, response) = ui.allocate_exact_size(Vec2::new(38.0, 22.0), Sense::click());
        response.widget_info(|| {
            egui::WidgetInfo::selected(egui::WidgetType::Checkbox, enabled, selected, label)
        });
        let rail = if selected {
            theme::accent()
        } else {
            theme::border()
        };
        ui.painter().rect_filled(rect, 11.0, rail);
        let knob_x = if selected {
            rect.right() - 11.0
        } else {
            rect.left() + 11.0
        };
        ui.painter().circle_filled(
            egui::pos2(knob_x, rect.center().y),
            8.0,
            if selected {
                theme::accent_text()
            } else {
                theme::text()
            },
        );
        response.clicked()
    });
    response.inner
}

fn paint_icon_at(painter: &egui::Painter, rect: egui::Rect, icon: Icon, color: Color32) {
    let stroke = Stroke::new((rect.width() / 12.0).max(1.25), color);
    let c = rect.center();
    let r = rect.width() * 0.38;
    match icon {
        Icon::Machine => {
            let body = egui::Rect::from_center_size(c, Vec2::new(r * 1.05, r * 1.75));
            painter.rect_stroke(body, 1.5, stroke, StrokeKind::Inside);
            painter.line_segment(
                [
                    egui::pos2(body.left() + r * 0.22, body.top() + r * 0.42),
                    egui::pos2(body.right() - r * 0.22, body.top() + r * 0.42),
                ],
                stroke,
            );
            painter.circle_filled(
                egui::pos2(c.x, body.bottom() - r * 0.25),
                stroke.width * 0.65,
                color,
            );
        }
        Icon::Key => {
            painter.circle_stroke(egui::pos2(c.x - r * 0.55, c.y), r * 0.43, stroke);
            painter.line_segment(
                [egui::pos2(c.x - r * 0.12, c.y), egui::pos2(c.x + r, c.y)],
                stroke,
            );
            painter.line_segment(
                [
                    egui::pos2(c.x + r * 0.52, c.y),
                    egui::pos2(c.x + r * 0.52, c.y + r * 0.4),
                ],
                stroke,
            );
            painter.line_segment(
                [
                    egui::pos2(c.x + r * 0.82, c.y),
                    egui::pos2(c.x + r * 0.82, c.y + r * 0.28),
                ],
                stroke,
            );
        }
        Icon::Gear => {
            painter.circle_stroke(c, r * 0.55, stroke);
            painter.circle_stroke(c, r * 0.18, stroke);
            for (x, y) in [(0.0, -1.0), (1.0, 0.0), (0.0, 1.0), (-1.0, 0.0)] {
                painter.line_segment(
                    [c + Vec2::new(x, y) * r * 0.63, c + Vec2::new(x, y) * r],
                    stroke,
                );
            }
        }
        Icon::Plug => {
            painter.line_segment(
                [egui::pos2(c.x - r, c.y), egui::pos2(c.x + r * 0.6, c.y)],
                stroke,
            );
            painter.line_segment(
                [
                    egui::pos2(c.x - r * 0.55, c.y - r * 0.45),
                    egui::pos2(c.x - r * 0.55, c.y + r * 0.45),
                ],
                stroke,
            );
            painter.line_segment(
                [
                    egui::pos2(c.x + r * 0.1, c.y - r * 0.45),
                    egui::pos2(c.x + r * 0.1, c.y + r * 0.45),
                ],
                stroke,
            );
            painter.line_segment(
                [
                    egui::pos2(c.x + r * 0.6, c.y),
                    egui::pos2(c.x + r, c.y + r * 0.45),
                ],
                stroke,
            );
        }
        Icon::Globe => {
            painter.circle_stroke(c, r, stroke);
            painter.line_segment([egui::pos2(c.x - r, c.y), egui::pos2(c.x + r, c.y)], stroke);
            painter.line_segment([egui::pos2(c.x, c.y - r), egui::pos2(c.x, c.y + r)], stroke);
        }
        Icon::Phone => {
            let body = egui::Rect::from_center_size(c, Vec2::new(r * 1.05, r * 1.8));
            painter.rect_stroke(body, 2.0, stroke, StrokeKind::Inside);
            painter.circle_filled(
                egui::pos2(c.x, body.bottom() - r * 0.2),
                stroke.width * 0.55,
                color,
            );
        }
        Icon::Play => {
            painter.add(egui::Shape::convex_polygon(
                vec![
                    egui::pos2(c.x - r * 0.55, c.y - r),
                    egui::pos2(c.x + r, c.y),
                    egui::pos2(c.x - r * 0.55, c.y + r),
                ],
                color,
                Stroke::NONE,
            ));
        }
        Icon::Info => {
            painter.circle_stroke(c, r, stroke);
            painter.circle_filled(egui::pos2(c.x, c.y - r * 0.45), stroke.width, color);
            painter.line_segment(
                [
                    egui::pos2(c.x, c.y - r * 0.05),
                    egui::pos2(c.x, c.y + r * 0.55),
                ],
                stroke,
            );
        }
        Icon::Shield => {
            painter.add(egui::Shape::closed_line(
                vec![
                    egui::pos2(c.x, c.y - r),
                    egui::pos2(c.x + r * 0.82, c.y - r * 0.6),
                    egui::pos2(c.x + r * 0.65, c.y + r * 0.4),
                    egui::pos2(c.x, c.y + r),
                    egui::pos2(c.x - r * 0.65, c.y + r * 0.4),
                    egui::pos2(c.x - r * 0.82, c.y - r * 0.6),
                ],
                stroke,
            ));
        }
        Icon::Undo => {
            painter.line_segment(
                [
                    egui::pos2(c.x - r, c.y),
                    egui::pos2(c.x - r * 0.3, c.y - r * 0.62),
                ],
                stroke,
            );
            painter.line_segment(
                [
                    egui::pos2(c.x - r, c.y),
                    egui::pos2(c.x - r * 0.3, c.y + r * 0.62),
                ],
                stroke,
            );
            painter.line_segment(
                [egui::pos2(c.x - r, c.y), egui::pos2(c.x + r * 0.45, c.y)],
                stroke,
            );
            painter.circle_stroke(egui::pos2(c.x + r * 0.25, c.y), r * 0.72, stroke);
        }
        Icon::Close => {
            painter.line_segment(
                [egui::pos2(c.x - r, c.y - r), egui::pos2(c.x + r, c.y + r)],
                stroke,
            );
            painter.line_segment(
                [egui::pos2(c.x + r, c.y - r), egui::pos2(c.x - r, c.y + r)],
                stroke,
            );
        }
    }
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

fn dialog_title(dialog: &Dialog) -> String {
    match dialog {
        Dialog::Pairing { .. } => "Pair a device".to_owned(),
        Dialog::Revoke(device) => format!("Unpair {}?", device.name),
        Dialog::EditMachine { .. } => "Machine settings".to_owned(),
        Dialog::ProviderAuth(provider) => format!("Connect {}", provider.name),
        Dialog::ProviderPicker(_) => "Connect provider".to_owned(),
        Dialog::ProviderKey { provider, .. } => format!("Connect {}", provider_name(provider)),
        Dialog::Models { .. } => "Choose the default model".to_owned(),
        Dialog::DisconnectProvider(provider) => format!("Disconnect {}?", provider.name),
        Dialog::Uninstall { .. } => "Uninstall Vadgr?".to_owned(),
    }
}

fn provider_name(id: &str) -> &str {
    match id {
        "openai" => "OpenAI",
        "gemini" => "Gemini",
        "anthropic" => "Anthropic",
        other => other,
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn unavailable_installation_controls_name_the_current_state() {
        let development = crate::install::InstallStatus::default();
        assert_eq!(legal_detail(&development), INSTALLED_ONLY_DETAIL);
        assert_eq!(rollback_detail(&development), INSTALLED_ONLY_DETAIL);

        let installed_without_optional_assets = crate::install::InstallStatus {
            installed: true,
            ..Default::default()
        };
        assert_eq!(
            legal_detail(&installed_without_optional_assets),
            "Installed legal bundle is missing"
        );
        assert_eq!(
            rollback_detail(&installed_without_optional_assets),
            "No verified previous generation is retained"
        );
    }

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
