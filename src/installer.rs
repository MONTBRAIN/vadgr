//! Native Linux graphical installer.

#[cfg(target_os = "linux")]
use anyhow::ensure;
use anyhow::{Result, anyhow};
#[cfg(target_os = "linux")]
use eframe::egui::{self, Align, Layout, RichText};
#[cfg(target_os = "linux")]
use std::path::Path;
use std::path::PathBuf;
#[cfg(target_os = "linux")]
use std::sync::mpsc;

#[cfg(target_os = "linux")]
enum State {
    Terms,
    Installing(String),
    Success(PathBuf),
    Failed(String),
}

#[cfg(not(target_os = "linux"))]
pub fn run(_vehicle: PathBuf) -> Result<()> {
    Err(anyhow!(
        "this graphical installer vehicle is only for native Linux"
    ))
}

#[cfg(target_os = "linux")]
pub fn run(vehicle: PathBuf) -> Result<()> {
    ensure!(
        vehicle.is_absolute(),
        "the installer vehicle path must be absolute"
    );
    // Open Vadgr and the installed daemon must not hold this vehicle's mount.
    crate::install::keep_inherited_descriptors_from_children()?;
    let preflight = Preflight::open(&vehicle)?;
    let options = crate::console::native::options(
        egui::ViewportBuilder::default()
            .with_title("Install Vadgr")
            .with_inner_size([760.0, 620.0])
            .with_min_inner_size([680.0, 540.0]),
    );
    eframe::run_native(
        "Install Vadgr",
        options,
        Box::new(move |cc| {
            crate::console::theme::install(&cc.egui_ctx);
            Ok(Box::new(InstallerApp::new(preflight)))
        }),
    )
    .map_err(|error| anyhow!(error.to_string()))
}

#[cfg(target_os = "linux")]
struct Preflight {
    vehicle: PathBuf,
    manifest: PathBuf,
    signature: PathBuf,
    bundle_root: PathBuf,
    terms_version: String,
    terms_sha256: String,
    version: String,
    terms_text: String,
    previously_accepted: bool,
}

#[cfg(target_os = "linux")]
impl Preflight {
    fn open(vehicle: &Path) -> Result<Self> {
        let parent = vehicle
            .parent()
            .ok_or_else(|| anyhow!("the installer vehicle has no parent"))?;
        let manifest = parent.join("release-manifest.json");
        let signature = parent.join("release-manifest.json.bundle.jsonl");
        let app_dir = std::env::var_os("APPDIR")
            .map(PathBuf::from)
            .filter(|path| path.is_absolute())
            .ok_or_else(|| anyhow!("the AppImage runtime did not provide APPDIR"))?;
        let verified =
            crate::install::VerifiedLinuxPackage::open(vehicle, &manifest, &signature, &app_dir)?;
        let terms_text = verified.terms_text(&app_dir)?;
        let terms_version = verified
            .terms_version()
            .ok_or_else(|| anyhow!("the package terms version is unavailable"))?
            .to_owned();
        let terms_sha256 = verified.terms_sha256().to_owned();
        let previously_accepted = matching_terms_acceptance(
            &terms_version,
            &terms_sha256,
            crate::install::terms_acceptance()?.as_ref(),
        )?;
        Ok(Self {
            vehicle: vehicle.to_owned(),
            manifest,
            signature,
            bundle_root: app_dir,
            terms_version,
            terms_sha256,
            version: verified.version().to_owned(),
            terms_text,
            previously_accepted,
        })
    }
}

#[cfg(target_os = "linux")]
fn matching_terms_acceptance(
    terms_version: &str,
    terms_sha256: &str,
    previous: Option<&crate::install::TermsAcceptance>,
) -> Result<bool> {
    let Some(previous) = previous.filter(|record| record.terms_version == terms_version) else {
        return Ok(false);
    };
    ensure!(
        previous.terms_sha256 == terms_sha256,
        "the accepted terms bytes changed without a new version"
    );
    Ok(true)
}

#[cfg(target_os = "linux")]
struct InstallerApp {
    preflight: Option<Preflight>,
    accepted: bool,
    state: State,
    receiver: Option<mpsc::Receiver<State>>,
}

#[cfg(target_os = "linux")]
impl InstallerApp {
    fn new(preflight: Preflight) -> Self {
        Self {
            preflight: Some(preflight),
            accepted: false,
            state: State::Terms,
            receiver: None,
        }
    }

    fn install(&mut self) {
        let Some(preflight) = self.preflight.as_ref() else {
            return;
        };
        // Recheck the validated record before starting any installation work.
        let assent = crate::install::terms_acceptance().and_then(|previous| {
            matching_terms_acceptance(
                &preflight.terms_version,
                &preflight.terms_sha256,
                previous.as_ref(),
            )
        });
        match assent {
            Ok(previously_accepted) if self.accepted || previously_accepted => {}
            Ok(_) if !preflight.previously_accepted => return,
            Ok(_) => {
                self.state = State::Failed(
                    "The previous terms acceptance is no longer available.".to_owned(),
                );
                return;
            }
            Err(error) => {
                self.state = State::Failed(format!("{error:#}"));
                return;
            }
        }
        let Some(preflight) = self.preflight.take() else {
            return;
        };
        let (sender, receiver) = mpsc::channel();
        self.receiver = Some(receiver);
        self.state = State::Installing(verification_label().to_owned());
        std::thread::spawn(move || {
            let phase_sender = sender.clone();
            let result = crate::install::install_appimage_with_progress(
                &preflight.vehicle,
                &preflight.manifest,
                &preflight.signature,
                &preflight.bundle_root,
                &preflight.terms_version,
                move |phase| {
                    let text = match phase {
                        crate::install::InstallPhase::Verifying => verification_label(),
                        crate::install::InstallPhase::Staging => "Staging the new generation",
                        crate::install::InstallPhase::Committing => "Committing the new generation",
                        crate::install::InstallPhase::RegisteringLaunch => {
                            "Registering application launch"
                        }
                        crate::install::InstallPhase::HealthCheck => "Checking daemon health",
                        crate::install::InstallPhase::Complete => "Installation complete",
                    };
                    let _ = phase_sender.send(State::Installing(text.to_owned()));
                },
            );
            let terminal = match result {
                Ok(path) => State::Success(path),
                Err(error) => State::Failed(format!("{error:#}")),
            };
            let _ = sender.send(terminal);
        });
    }

    fn terms_ui(&mut self, ui: &mut egui::Ui) {
        let preflight = self
            .preflight
            .as_ref()
            .expect("terms state keeps preflight");
        let previously_accepted = preflight.previously_accepted;
        if previously_accepted {
            ui.heading("Terms already accepted");
            ui.label(format!(
                "You previously accepted terms version {} with these exact contents. No new acceptance is needed.",
                preflight.terms_version
            ));
            ui.label("Vadgr will not change this machine until you choose Install.");
        } else {
            ui.heading("Review the terms");
            ui.label("Vadgr will not change this machine until you accept these terms and choose Install.");
        }
        ui.add_space(12.0);
        // Keep the document before assent in both the visual and accessibility
        // order, but reserve the themed controls before assigning its height.
        let spacing = ui.spacing();
        let button_height = spacing
            .interact_size
            .y
            .max(ui.text_style_height(&egui::TextStyle::Button) + 2.0 * spacing.button_padding.y);
        let checkbox_height = if previously_accepted {
            0.0
        } else {
            ui.text_style_height(&egui::TextStyle::Body)
                .max(spacing.icon_width)
                .max(spacing.interact_size.y)
                + spacing.item_spacing.y
        };
        let footer_height = 12.0 + spacing.item_spacing.y + checkbox_height + button_height;
        egui::ScrollArea::vertical()
            .max_height((ui.available_height() - footer_height).clamp(0.0, 380.0))
            .min_scrolled_height(0.0)
            .show(ui, |ui| {
                crate::console::theme::card().show(ui, |ui| {
                    show_terms(ui, &preflight.terms_text);
                });
            });
        ui.add_space(12.0);
        if !previously_accepted {
            crate::console::theme::checkbox(
                ui,
                &mut self.accepted,
                "I have read and accept these terms",
            );
        }
        installer_footer_space(ui);
        ui.with_layout(Layout::right_to_left(Align::Center), |ui| {
            if installer_button(
                ui,
                "Install Vadgr",
                true,
                self.accepted || previously_accepted,
            )
            .clicked()
            {
                self.install();
            }
            if installer_button(
                ui,
                if previously_accepted {
                    "Cancel and close"
                } else {
                    "Decline and close"
                },
                false,
                true,
            )
            .clicked()
            {
                ui.ctx().send_viewport_cmd(egui::ViewportCommand::Close);
            }
        });
    }
}

#[cfg(target_os = "linux")]
impl InstallerApp {
    fn progress_rail(&self, root: &mut egui::Ui) {
        use crate::console::theme;
        let width = (root.available_width() * 0.25).clamp(170.0, 285.0);
        let current = match self.state {
            State::Terms => 0,
            State::Success(_) => 2,
            State::Installing(_) | State::Failed(_) => 1,
        };
        egui::Panel::left("installer-progress")
            .exact_size(width)
            .resizable(false)
            .frame(
                egui::Frame::new()
                    .fill(theme::nav())
                    .inner_margin(egui::Margin::symmetric(18, 28)),
            )
            .show(root, |ui| {
                ui.label(
                    RichText::new("vadgr.")
                        .family(theme::heading_family())
                        .size(24.0),
                );
                ui.label(
                    RichText::new(format!(
                        "Version {}",
                        self.preflight
                            .as_ref()
                            .map_or("0.5.0", |value| &value.version)
                    ))
                    .monospace()
                    .size(10.0)
                    .color(theme::muted()),
                );
                ui.add_space(24.0);
                ui.label(
                    RichText::new("Your machine,\nready when you are.")
                        .family(theme::heading_family())
                        .size(24.0),
                );
                ui.add_space(8.0);
                ui.label(
                    RichText::new(
                        "Installs Vadgr and everything it needs to control this machine.",
                    )
                    .size(12.0)
                    .color(theme::muted()),
                );
                ui.add_space(28.0);
                for (index, label) in ["1. Terms", "2. Install", "3. Finish"].iter().enumerate() {
                    let response = ui.add(
                        egui::Label::new(
                            RichText::new(*label)
                                .family(theme::medium_family())
                                .size(14.0)
                                .color(if index == current {
                                    theme::text()
                                } else {
                                    theme::muted()
                                }),
                        )
                        .selectable(false)
                        .sense(egui::Sense::hover()),
                    );
                    ui.ctx().accesskit_node_builder(response.id, |node| {
                        node.set_description(if index == current {
                            "Current step"
                        } else if index < current {
                            "Completed step"
                        } else {
                            "Pending step"
                        });
                    });
                    ui.add_space(12.0);
                }
            });
    }

    fn render(&mut self, root: &mut egui::Ui) {
        let ctx = root.ctx().clone();
        crate::console::theme::refresh(&ctx);
        if let Some(receiver) = &self.receiver {
            while let Ok(state) = receiver.try_recv() {
                self.state = state;
            }
            if matches!(self.state, State::Installing(_)) {
                ctx.request_repaint_after(std::time::Duration::from_millis(100));
            }
        }
        let inset = if root.available_width() >= 1000.0 {
            48
        } else {
            24
        };
        self.progress_rail(root);
        egui::CentralPanel::default()
            .frame(egui::Frame::new().fill(crate::console::theme::bg()).inner_margin(egui::Margin::same(inset)))
            .show(root, |ui| {
            ui.label(RichText::new(match self.state {
                State::Terms => "BEFORE INSTALLATION",
                State::Installing(_) => "INSTALLING",
                State::Success(_) => "INSTALLATION COMPLETE",
                State::Failed(_) => "INSTALLATION STOPPED",
            }).monospace().size(10.0).color(crate::console::theme::muted()));
            if cfg!(feature = "linux-unsigned-qualification") {
                ui.label(crate::build_policy::UNSIGNED_WARNING);
                ui.add_space(8.0);
            }
            match &self.state {
                State::Terms => {
                    self.terms_ui(ui);
                }
                State::Installing(phase) => {
                    ui.heading("Installing Vadgr");
                    ui.add(egui::Spinner::new().size(28.0));
                    ui.label(phase);
                    ui.label(RichText::new("Do not close this window while the active generation is being committed.").color(crate::console::theme::muted()));
                }
                State::Success(path) => {
                    ui.heading("Vadgr is ready");
                    ui.label(if cfg!(feature = "linux-unsigned-qualification") {
                        "The unsigned development generation is installed and the daemon answered its health check."
                    } else {
                        "The signed generation is installed and the daemon answered its health check."
                    });
                    ui.label(RichText::new(path.display().to_string()).monospace().color(crate::console::theme::muted()));
                    installer_footer_space(ui);
                    ui.with_layout(Layout::right_to_left(Align::Center), |ui| {
                        if installer_button(ui, "Open Vadgr", true, true).clicked() {
                            let _ = std::process::Command::new(path.join("Vadgr.AppImage")).arg("--console").spawn();
                        }
                        if installer_button(ui, "Close", false, true).clicked() { ctx.send_viewport_cmd(egui::ViewportCommand::Close); }
                    });
                }
                State::Failed(message) => {
                    ui.heading("Vadgr was not installed");
                    ui.label(RichText::new(message).color(crate::console::theme::danger()));
                    installer_footer_space(ui);
                    ui.with_layout(Layout::right_to_left(Align::Center), |ui| {
                        if installer_button(ui, "Close", false, true).clicked() { ctx.send_viewport_cmd(egui::ViewportCommand::Close); }
                    });
                }
            }
        });
    }
}

#[cfg(target_os = "linux")]
fn installer_footer_space(ui: &mut egui::Ui) {
    let height =
        ui.spacing().interact_size.y.max(
            ui.text_style_height(&egui::TextStyle::Button) + 2.0 * ui.spacing().button_padding.y,
        );
    ui.add_space((ui.available_height() - height).max(0.0));
}

#[cfg(target_os = "linux")]
fn installer_button(
    ui: &mut egui::Ui,
    label: &str,
    primary: bool,
    enabled: bool,
) -> egui::Response {
    use crate::console::theme;
    let (foreground, background) = if primary {
        (theme::accent_text(), theme::accent())
    } else {
        (theme::text(), theme::panel())
    };
    let response = ui.add_enabled(
        enabled,
        egui::Button::new(RichText::new(label).color(foreground))
            .fill(background)
            .stroke(egui::Stroke::new(1.0, theme::border()))
            .corner_radius(10),
    );
    theme::focus_outline(ui, &response, foreground);
    response
}

#[cfg(target_os = "linux")]
impl eframe::App for InstallerApp {
    fn ui(&mut self, root: &mut egui::Ui, _frame: &mut eframe::Frame) {
        self.render(root);
    }
}

#[cfg(target_os = "linux")]
fn terms_label(ui: &mut egui::Ui, text: impl Into<egui::WidgetText>) {
    // Native focus must reveal the document block without pointer scrolling
    // or relying on a screen reader changing egui's separate focus option.
    let response = ui.add(egui::Label::new(text).sense(egui::Sense::focusable_noninteractive()));
    if response.gained_focus() {
        response.scroll_to_me_animation(
            Some(egui::Align::Center),
            egui::style::ScrollAnimation::none(),
        );
    }
}

#[cfg(target_os = "linux")]
fn show_terms(ui: &mut egui::Ui, terms: &str) {
    // The reviewed text uses headings, strong spans and unordered lists. Render
    // those without changing the bytes verified and recorded by the installer.
    for block in terms.split("\n\n").filter(|block| !block.trim().is_empty()) {
        let block = block.trim();
        if let Some(heading) = block.strip_prefix("### ") {
            terms_label(ui, RichText::new(heading).heading());
        } else if let Some(heading) = block.strip_prefix("#### ") {
            ui.add_space(6.0);
            terms_label(
                ui,
                RichText::new(heading)
                    .family(crate::console::theme::medium_family())
                    .size(15.0),
            );
        } else if block.lines().all(|line| line.starts_with("- ")) {
            for line in block.lines() {
                terms_label(ui, terms_inline(ui, &format!("• {}", &line[2..])));
            }
        } else {
            let paragraph = block.lines().map(str::trim).collect::<Vec<_>>().join(" ");
            terms_label(ui, terms_inline(ui, &paragraph));
        }
    }
}

#[cfg(target_os = "linux")]
fn terms_inline(ui: &egui::Ui, mut text: &str) -> egui::text::LayoutJob {
    let mut job = egui::text::LayoutJob::default();
    let regular = egui::TextFormat {
        font_id: egui::TextStyle::Body.resolve(ui.style()),
        color: ui.visuals().text_color(),
        ..Default::default()
    };
    let strong = egui::TextFormat {
        font_id: egui::FontId::new(regular.font_id.size, crate::console::theme::medium_family()),
        ..regular.clone()
    };
    while let Some(start) = text.find("**") {
        let after = &text[start + 2..];
        let Some(end) = after.find("**") else {
            break;
        };
        job.append(&text[..start], 0.0, regular.clone());
        job.append(&after[..end], 0.0, strong.clone());
        text = &after[end + 2..];
    }
    job.append(text, 0.0, regular);
    job
}

#[cfg(target_os = "linux")]
fn verification_label() -> &'static str {
    if cfg!(feature = "linux-unsigned-qualification") {
        "Checking development package integrity"
    } else {
        "Verifying the signed release"
    }
}

#[cfg(all(test, target_os = "linux"))]
mod tests {
    use super::*;

    #[test]
    fn native_button_focus_is_visible() {
        let mut failures = Vec::new();
        for primary in [false, true] {
            failures.extend(crate::console::focus_tests::audit(
                "Installer action",
                |ui| {
                    assert!(!installer_button(ui, "Installer action", primary, true).clicked());
                },
            ));
        }
        assert!(failures.is_empty(), "{}", failures.join("\n"));
    }

    fn acceptance() -> crate::install::TermsAcceptance {
        crate::install::TermsAcceptance {
            schema: 1,
            terms_version: "1.0".to_owned(),
            terms_sha256: "a".repeat(64),
            accepted_at: "2026-09-30T00:00:00Z".to_owned(),
            installer_version: "0.5.0".to_owned(),
            installer_artifact_sha256: "b".repeat(64),
            install_scope: "user".to_owned(),
            installation_id: "synthetic-installer-test".to_owned(),
            assent_method: "unchecked_checkbox_then_install".to_owned(),
        }
    }

    fn terms_app(
        version: &str,
        previous: Option<&crate::install::TermsAcceptance>,
    ) -> Result<InstallerApp> {
        let digest = "a".repeat(64);
        Ok(InstallerApp::new(Preflight {
            vehicle: PathBuf::from("/unused-installer-test/Vadgr.AppImage"),
            manifest: PathBuf::from("/unused-installer-test/release-manifest.json"),
            signature: PathBuf::from("/unused-installer-test/release-manifest.json.bundle.jsonl"),
            bundle_root: PathBuf::from("/unused-installer-test"),
            terms_version: version.to_owned(),
            previously_accepted: matching_terms_acceptance(version, &digest, previous)?,
            terms_sha256: digest,
            version: "0.5.0".to_owned(),
            terms_text: "### Distribution terms\n\nThe complete reviewed text.".to_owned(),
        }))
    }

    fn terms_output(app: &mut InstallerApp) -> egui::FullOutput {
        let ctx = egui::Context::default();
        ctx.enable_accesskit();
        crate::console::theme::install(&ctx);
        let mut output = ctx.run_ui(
            egui::RawInput {
                screen_rect: Some(egui::Rect::from_min_size(
                    egui::Pos2::ZERO,
                    egui::vec2(760.0, 620.0),
                )),
                ..Default::default()
            },
            |ui| app.terms_ui(ui),
        );
        output.textures_delta.clear();
        assert!(!app.accepted, "viewing terms must never create new assent");
        assert!(
            app.receiver.is_none(),
            "viewing terms must not start installation"
        );
        assert!(app.preflight.is_some());
        output
    }

    #[test]
    fn installer_enabled_actions_have_readable_rendered_contrast_in_both_themes() {
        fn luminance(color: egui::Color32) -> f64 {
            let linear = |channel: u8| {
                let value = f64::from(channel) / 255.0;
                if value <= 0.04045 {
                    value / 12.92
                } else {
                    ((value + 0.055) / 1.055).powf(2.4)
                }
            };
            0.2126 * linear(color.r()) + 0.7152 * linear(color.g()) + 0.0722 * linear(color.b())
        }
        for theme in [egui::Theme::Light, egui::Theme::Dark] {
            let previous = acceptance();
            let mut app = terms_app("1.0", Some(&previous)).unwrap();
            let ctx = egui::Context::default();
            ctx.enable_accesskit();
            crate::console::theme::install(&ctx);
            ctx.set_theme(theme);
            let mut output = ctx.run_ui(
                egui::RawInput {
                    screen_rect: Some(egui::Rect::from_min_size(
                        egui::Pos2::ZERO,
                        egui::vec2(760.0, 620.0),
                    )),
                    ..Default::default()
                },
                |ui| app.render(ui),
            );
            output.textures_delta.clear();
            for label in ["Cancel and close", "Install Vadgr"] {
                let node = &output
                    .platform_output
                    .accesskit_update
                    .as_ref()
                    .unwrap()
                    .nodes
                    .iter()
                    .find(|(_, node)| node.label() == Some(label))
                    .unwrap()
                    .1;
                assert!(!node.is_disabled());
                let bounds = node.bounds().unwrap();
                let text = output
                    .shapes
                    .iter()
                    .find_map(|shape| match &shape.shape {
                        egui::Shape::Text(text) if text.galley.job.text == label => Some(text),
                        _ => None,
                    })
                    .expect("enabled action text is painted");
                let specified = text.galley.job.sections[0].format.color;
                let foreground = text.override_text_color.unwrap_or(
                    if specified == egui::Color32::PLACEHOLDER {
                        text.fallback_color
                    } else {
                        specified
                    },
                );
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
                    .expect("enabled action background is painted");
                let (a, b) = (luminance(foreground), luminance(background));
                let contrast = (a.max(b) + 0.05) / (a.min(b) + 0.05);
                assert!(
                    contrast >= 4.5,
                    "{label} in {theme:?}: contrast {contrast}, {foreground:?} on {background:?}"
                );
            }
        }
    }

    #[test]
    fn failed_install_does_not_claim_an_unverified_previous_generation() {
        let ctx = egui::Context::default();
        ctx.enable_accesskit();
        crate::console::theme::install(&ctx);
        let mut app = terms_app("1.0", None).unwrap();
        app.state = State::Failed("The installed daemon did not become ready.".to_owned());
        let mut output = ctx.run_ui(
            egui::RawInput {
                screen_rect: Some(egui::Rect::from_min_size(
                    egui::Pos2::ZERO,
                    egui::vec2(760.0, 620.0),
                )),
                ..Default::default()
            },
            |ui| app.render(ui),
        );
        output.textures_delta.clear();
        let tree = output.platform_output.accesskit_update.unwrap();
        assert!(
            tree.nodes.iter().any(|(_, node)| {
                node.value().or(node.label()) == Some("Vadgr was not installed")
            })
        );
        assert!(!tree.nodes.iter().any(|(_, node)| {
            node.value().or(node.label()) == Some("A previous working generation remains selected.")
        }));
    }

    #[test]
    fn installer_preserves_brand_and_step_rail_in_every_state_and_supported_window() {
        for size in [[760.0, 620.0], [680.0, 540.0]] {
            for theme in [egui::Theme::Dark, egui::Theme::Light] {
                for state_index in 0..4 {
                    let ctx = egui::Context::default();
                    ctx.enable_accesskit();
                    crate::console::theme::install(&ctx);
                    ctx.set_theme(theme);
                    let mut app = terms_app("1.0", None).unwrap();
                    app.state = match state_index {
                        0 => State::Terms,
                        1 => State::Installing("Preparing files".to_owned()),
                        2 => State::Success(PathBuf::from("/synthetic-installed-generation")),
                        _ => State::Failed("The new generation could not start.".to_owned()),
                    };
                    for _ in 0..3 {
                        let mut output = ctx.run_ui(
                            egui::RawInput {
                                screen_rect: Some(egui::Rect::from_min_size(
                                    egui::Pos2::ZERO,
                                    size.into(),
                                )),
                                ..Default::default()
                            },
                            |ui| app.render(ui),
                        );
                        output.textures_delta.clear();
                        let tree = output.platform_output.accesskit_update.as_ref().unwrap();
                        let find = |text: &str| {
                            tree.nodes
                                .iter()
                                .find(|(_, node)| node.value().or(node.label()) == Some(text))
                                .map(|(_, node)| node)
                                .unwrap_or_else(|| {
                                    panic!("missing installer hierarchy label: {text}")
                                })
                        };
                        let brand = find("vadgr.").bounds().unwrap();
                        let heading = find(match state_index {
                            0 => "Review the terms",
                            1 => "Installing Vadgr",
                            2 => "Vadgr is ready",
                            _ => "Vadgr was not installed",
                        })
                        .bounds()
                        .unwrap();
                        assert!(
                            brand.x1 < heading.x0,
                            "brand must stay in a separate left rail"
                        );
                        let mut previous_bottom = brand.y1;
                        for (index, name) in
                            ["1. Terms", "2. Install", "3. Finish"].iter().enumerate()
                        {
                            let node = find(name);
                            assert_eq!(node.role(), egui::accesskit::Role::Label);
                            let bounds = node.bounds().unwrap();
                            assert!(bounds.x1 < heading.x0 && bounds.y0 > previous_bottom);
                            assert!(bounds.y1 < f64::from(size[1]));
                            let current = match state_index {
                                0 => 0,
                                2 => 2,
                                _ => 1,
                            };
                            assert_eq!(
                                node.description(),
                                Some(if index == current {
                                    "Current step"
                                } else if index < current {
                                    "Completed step"
                                } else {
                                    "Pending step"
                                })
                            );
                            assert!(!node.supports_action(egui::accesskit::Action::Click));
                            previous_bottom = bounds.y1;
                        }
                        let actions: &[&str] = match state_index {
                            0 => &["Install Vadgr", "Decline and close"],
                            2 => &["Open Vadgr", "Close"],
                            3 => &["Close"],
                            _ => &[],
                        };
                        for name in actions {
                            let bounds = find(name).bounds().unwrap();
                            assert!(bounds.x0 >= heading.x0 && bounds.x1 <= f64::from(size[0]));
                            assert!(bounds.y0 > previous_bottom && bounds.y1 <= f64::from(size[1]));
                        }
                        assert!(!app.accepted);
                        assert!(app.receiver.is_none());
                    }
                }
            }
        }
    }

    #[test]
    fn complete_installer_keeps_terms_actions_inside_supported_windows() {
        let previous = acceptance();
        for (size, theme) in [
            ([760.0, 620.0], egui::Theme::Dark),
            ([680.0, 540.0], egui::Theme::Dark),
            ([760.0, 620.0], egui::Theme::Light),
            ([680.0, 540.0], egui::Theme::Light),
        ] {
            for retained in [false, true] {
                let mut app = terms_app("1.0", retained.then_some(&previous)).unwrap();
                app.preflight.as_mut().unwrap().terms_text =
                    include_str!("../packaging/legal/TERMS.txt").to_owned();
                let ctx = egui::Context::default();
                ctx.enable_accesskit();
                crate::console::theme::install(&ctx);
                ctx.set_theme(theme);
                let viewport = egui::Rect::from_min_size(egui::Pos2::ZERO, size.into());
                for _ in 0..3 {
                    let mut output = ctx.run_ui(
                        egui::RawInput {
                            screen_rect: Some(viewport),
                            ..Default::default()
                        },
                        |ui| app.render(ui),
                    );
                    output.textures_delta.clear();
                    let tree = output.platform_output.accesskit_update.as_ref().unwrap();
                    let mut pending = vec![tree.tree.as_ref().unwrap().root];
                    let mut reading_order = Vec::new();
                    while let Some(id) = pending.pop() {
                        let node = &tree.nodes.iter().find(|(key, _)| *key == id).unwrap().1;
                        reading_order.extend(node.label().or(node.value()));
                        pending.extend(node.children().iter().rev());
                    }
                    let heading = if retained {
                        "Terms already accepted"
                    } else {
                        "Review the terms"
                    };
                    let position = |text| {
                        reading_order
                            .iter()
                            .position(|value| *value == text)
                            .unwrap()
                    };
                    assert!(position(heading) < position("Install Vadgr"));
                    if !retained {
                        assert!(position(heading) < position("I have read and accept these terms"));
                        assert!(
                            position("I have read and accept these terms")
                                < position("Install Vadgr")
                        );
                    }
                    for label in [
                        "Install Vadgr",
                        if retained {
                            "Cancel and close"
                        } else {
                            "Decline and close"
                        },
                    ]
                    .into_iter()
                    .chain((!retained).then_some("I have read and accept these terms"))
                    {
                        let node = &tree
                            .nodes
                            .iter()
                            .find(|(_, node)| node.label() == Some(label))
                            .expect("installer action remains exposed")
                            .1;
                        let bounds = node.bounds().expect("installer action has bounds");
                        assert!(
                            bounds.x0 >= 0.0
                                && bounds.y0 >= 0.0
                                && bounds.x1 <= f64::from(size[0])
                                && bounds.y1 <= f64::from(size[1]),
                            "{label}: {bounds:?}, viewport {size:?}, retained {retained}"
                        );
                        if label == "Install Vadgr" {
                            assert_eq!(node.is_disabled(), !retained);
                        }
                    }
                    assert!(
                        tree.nodes
                            .iter()
                            .any(|(_, node)| { node.role() == egui::accesskit::Role::ScrollBar }),
                        "complete terms retain their scrolling control"
                    );
                    assert!(!app.accepted);
                    assert!(app.receiver.is_none());
                }
            }
        }
    }

    #[test]
    fn retained_exact_terms_enable_install_without_new_assent() {
        let previous = acceptance();
        let mut app = terms_app("1.0", Some(&previous)).unwrap();
        let output = terms_output(&mut app);
        let tree = output.platform_output.accesskit_update.as_ref().unwrap();
        assert!(label_text(&output).contains(&"Terms already accepted"));
        assert!(
            tree.nodes
                .iter()
                .all(|(_, node)| node.role() != egui::accesskit::Role::CheckBox)
        );
        let install = tree
            .nodes
            .iter()
            .find(|(_, node)| node.label() == Some("Install Vadgr"))
            .unwrap();
        assert!(!install.1.is_disabled());
        assert!(
            tree.nodes
                .iter()
                .any(|(_, node)| node.label() == Some("Cancel and close"))
        );
    }

    #[test]
    fn first_or_new_terms_keep_assent_unchecked_and_install_disabled() {
        let previous = acceptance();
        for (version, receipt) in [("1.0", None), ("2.0", Some(&previous))] {
            let mut app = terms_app(version, receipt).unwrap();
            let output = terms_output(&mut app);
            let tree = output.platform_output.accesskit_update.as_ref().unwrap();
            assert!(label_text(&output).contains(&"Review the terms"));
            let checkbox = tree
                .nodes
                .iter()
                .find(|(_, node)| node.role() == egui::accesskit::Role::CheckBox)
                .unwrap();
            assert_eq!(checkbox.1.toggled(), Some(egui::accesskit::Toggled::False));
            let install = tree
                .nodes
                .iter()
                .find(|(_, node)| node.label() == Some("Install Vadgr"))
                .unwrap();
            assert!(install.1.is_disabled());
            assert!(
                tree.nodes
                    .iter()
                    .any(|(_, node)| node.label() == Some("Decline and close"))
            );
        }
    }

    #[test]
    fn retained_same_version_changed_bytes_fail_before_installation() {
        let mut previous = acceptance();
        previous.terms_sha256 = "c".repeat(64);
        let error = terms_app("1.0", Some(&previous))
            .err()
            .expect("changed terms must fail before the installer is created");
        assert!(error.to_string().contains("changed without a new version"));
    }

    fn label_text(output: &egui::FullOutput) -> Vec<&str> {
        let tree = output.platform_output.accesskit_update.as_ref().unwrap();
        fn visit<'a>(
            tree: &'a egui::accesskit::TreeUpdate,
            id: egui::accesskit::NodeId,
            text: &mut Vec<&'a str>,
        ) {
            let node = &tree.nodes.iter().find(|(key, _)| *key == id).unwrap().1;
            if node.role() == egui::accesskit::Role::Label {
                text.extend(node.value());
            }
            for child in node.children() {
                visit(tree, *child, text);
            }
        }
        let mut text = Vec::new();
        visit(tree, tree.tree.as_ref().unwrap().root, &mut text);
        text
    }

    #[test]
    fn complete_reviewed_terms_remain_readable_without_source_markup() {
        let terms = include_str!("../packaging/legal/TERMS.txt");
        let ctx = egui::Context::default();
        ctx.enable_accesskit();
        crate::console::theme::install(&ctx);
        let mut output = ctx.run_ui(egui::RawInput::default(), |ui| show_terms(ui, terms));
        output.textures_delta.clear();
        let paragraphs = label_text(&output);
        assert_eq!(
            paragraphs.first(),
            Some(&"Vadgr packaged distribution terms")
        );
        assert!(paragraphs.contains(&"Version 1.0"));
        assert!(paragraphs.contains(&"12. General terms"));
        assert!(
            paragraphs
                .last()
                .unwrap()
                .ends_with("applies where you live.")
        );
        assert!(
            paragraphs
                .iter()
                .all(|text| !text.contains("**") && !text.starts_with('#'))
        );
        // Every word of the approved text survives presentation, including
        // paragraph continuations and all twelve sections.
        let expected: Vec<_> = terms
            .split_whitespace()
            .filter(|word| !matches!(*word, "###" | "####" | "-"))
            .map(|word| word.replace("**", ""))
            .collect();
        let actual: Vec<_> = paragraphs
            .iter()
            .flat_map(|text| text.split_whitespace())
            .filter(|word| *word != "•")
            .collect();
        assert_eq!(actual, expected);
    }

    #[test]
    fn terms_accessibility_focus_reveals_last_and_first_blocks_without_assent() {
        use egui::accesskit::{Action, ActionRequest, TreeId};

        for (size, theme) in [
            ([760.0, 620.0], egui::Theme::Dark),
            ([680.0, 540.0], egui::Theme::Dark),
            ([760.0, 620.0], egui::Theme::Light),
            ([680.0, 540.0], egui::Theme::Light),
        ] {
            let ctx = egui::Context::default();
            ctx.enable_accesskit();
            crate::console::theme::install(&ctx);
            ctx.set_theme(theme);
            let mut app = terms_app("1.0", None).unwrap();
            app.preflight.as_mut().unwrap().terms_text = format!(
                "### First heading\n\n{}\n\nLast terms paragraph.",
                (0..50)
                    .map(|n| format!("Paragraph {n} with readable terms."))
                    .collect::<Vec<_>>()
                    .join("\n\n")
            );
            let mut draw = |events| {
                let mut output = ctx.run_ui(
                    egui::RawInput {
                        screen_rect: Some(egui::Rect::from_min_size(egui::Pos2::ZERO, size.into())),
                        events,
                        ..Default::default()
                    },
                    |ui| app.render(ui),
                );
                output.textures_delta.clear();
                assert!(!app.accepted);
                assert!(app.receiver.is_none());
                output
            };
            let locate = |output: &egui::FullOutput, text: &str| {
                output
                    .platform_output
                    .accesskit_update
                    .as_ref()
                    .unwrap()
                    .nodes
                    .iter()
                    .find(|(_, node)| {
                        node.role() == egui::accesskit::Role::Label && node.value() == Some(text)
                    })
                    .map(|(id, node)| (*id, node.clone()))
                    .unwrap()
            };
            let initial = draw(vec![]);
            let (first_id, first) = locate(&initial, "First heading");
            let (last_id, last) = locate(&initial, "Last terms paragraph.");
            assert!(first.supports_action(Action::Focus));
            assert!(last.supports_action(Action::Focus));
            assert!(last.bounds().unwrap().y0 > f64::from(size[1]));
            for (id, label) in [
                (last_id, "Last terms paragraph."),
                (first_id, "First heading"),
            ] {
                draw(vec![egui::Event::AccessKitActionRequest(ActionRequest {
                    action: Action::Focus,
                    target_tree: TreeId::ROOT,
                    target_node: id,
                    data: None,
                })]);
                let _ = draw(vec![]);
                let settled = draw(vec![]);
                let (_, node) = locate(&settled, label);
                let bounds = node.bounds().unwrap();
                let scroll_bounds = settled
                    .platform_output
                    .accesskit_update
                    .as_ref()
                    .unwrap()
                    .nodes
                    .iter()
                    .find(|(_, node)| node.role() == egui::accesskit::Role::ScrollBar)
                    .expect("the long terms document retains its scrollbar")
                    .1
                    .bounds()
                    .unwrap();
                assert_eq!(
                    settled
                        .platform_output
                        .accesskit_update
                        .as_ref()
                        .unwrap()
                        .focus,
                    id
                );
                assert!(
                    bounds.y0 >= scroll_bounds.y0
                        && bounds.y1 <= scroll_bounds.y1
                        && bounds.x0 >= 0.0
                        && bounds.x1 <= scroll_bounds.x0,
                    "focused terms block {bounds:?} exceeds actual scroll viewport {scroll_bounds:?}; window {size:?}, theme {theme:?}"
                );
            }
        }
    }

    #[test]
    fn terms_render_as_readable_text_with_heading_and_emphasis() {
        let terms = "### Distribution terms\n\n**Version 1.0**\n\n#### 1. Scope\n\nThese terms name **the\nPublisher** and preserve every word.\n\n- First item\n- Second item";
        let ctx = egui::Context::default();
        ctx.enable_accesskit();
        crate::console::theme::install(&ctx);
        let mut output = ctx.run_ui(egui::RawInput::default(), |ui| show_terms(ui, terms));
        output.textures_delta.clear();
        let text = label_text(&output);
        assert_eq!(
            text,
            [
                "Distribution terms",
                "Version 1.0",
                "1. Scope",
                "These terms name the Publisher and preserve every word.",
                "• First item",
                "• Second item",
            ]
        );
        let jobs: Vec<_> = output
            .shapes
            .iter()
            .filter_map(|shape| match &shape.shape {
                egui::Shape::Text(text) => Some(&text.galley.job),
                _ => None,
            })
            .collect();
        let paragraph = jobs
            .iter()
            .find(|job| job.text.starts_with("These terms"))
            .unwrap();
        let publisher = paragraph
            .sections
            .iter()
            .find(|section| {
                &paragraph.text[section.byte_range.start.0..section.byte_range.end.0]
                    == "the Publisher"
            })
            .unwrap();
        assert_eq!(
            publisher.format.font_id.family,
            crate::console::theme::medium_family()
        );
        let heading = jobs
            .iter()
            .find(|job| job.text == "Distribution terms")
            .unwrap();
        assert!(
            heading.sections[0].format.font_id.size > paragraph.sections[0].format.font_id.size
        );
    }
}
