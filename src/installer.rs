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
            ui.checkbox(&mut self.accepted, "I have read and accept these terms");
        }
        ui.with_layout(Layout::right_to_left(Align::Center), |ui| {
            if ui
                .add_enabled(
                    self.accepted || previously_accepted,
                    egui::Button::new("Install Vadgr"),
                )
                .clicked()
            {
                self.install();
            }
            if ui
                .button(if previously_accepted {
                    "Cancel and close"
                } else {
                    "Decline and close"
                })
                .clicked()
            {
                ui.ctx().send_viewport_cmd(egui::ViewportCommand::Close);
            }
        });
    }
}

#[cfg(target_os = "linux")]
impl InstallerApp {
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
        egui::CentralPanel::default().show(root, |ui| {
            ui.add_space(24.0);
            ui.horizontal(|ui| {
                ui.heading("VADGR");
                ui.with_layout(Layout::right_to_left(Align::Center), |ui| { ui.label(format!("Version {}", self.preflight.as_ref().map_or("0.5.0", |value| &value.version))); });
            });
            ui.add_space(28.0);
            if cfg!(feature = "linux-unsigned-qualification") {
                ui.label(crate::build_policy::UNSIGNED_WARNING);
                ui.add_space(12.0);
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
                    if ui.button("Open Vadgr").clicked() {
                        let _ = std::process::Command::new(path.join("Vadgr.AppImage")).arg("--console").spawn();
                    }
                    if ui.button("Close").clicked() { ctx.send_viewport_cmd(egui::ViewportCommand::Close); }
                }
                State::Failed(message) => {
                    ui.heading("Vadgr was not installed");
                    ui.label(RichText::new(message).color(crate::console::theme::danger()));
                    ui.label("A previous working generation remains selected.");
                    if ui.button("Close").clicked() { ctx.send_viewport_cmd(egui::ViewportCommand::Close); }
                }
            }
        });
    }
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

        let ctx = egui::Context::default();
        ctx.enable_accesskit();
        crate::console::theme::install(&ctx);
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
                    screen_rect: Some(egui::Rect::from_min_size(
                        egui::Pos2::ZERO,
                        egui::vec2(760.0, 620.0),
                    )),
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
        assert!(last.bounds().unwrap().y0 > 620.0);
        let document_top = first.bounds().unwrap().y0;
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
                bounds.y0 >= document_top && bounds.y1 < document_top + 380.0,
                "focused terms block remains outside document viewport: {bounds:?}"
            );
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
