//! Native Linux graphical installer.

#[cfg(target_os = "linux")]
use anyhow::{Context, ensure};
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
    let options = eframe::NativeOptions {
        viewport: egui::ViewportBuilder::default()
            .with_title("Install Vadgr")
            .with_inner_size([760.0, 620.0])
            .with_min_inner_size([680.0, 540.0]),
        ..Default::default()
    };
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
    terms: PathBuf,
    terms_version: String,
    version: String,
    terms_text: String,
}

#[cfg(target_os = "linux")]
impl Preflight {
    fn open(vehicle: &Path) -> Result<Self> {
        let parent = vehicle
            .parent()
            .ok_or_else(|| anyhow!("the installer vehicle has no parent"))?;
        let manifest = parent.join("release-manifest.json");
        let signature = parent.join("release-manifest.json.minisig");
        let app_dir = std::env::var_os("APPDIR")
            .map(PathBuf::from)
            .filter(|path| path.is_absolute())
            .ok_or_else(|| anyhow!("the AppImage runtime did not provide APPDIR"))?;
        let terms = app_dir.join("legal/TERMS.txt");
        let verified = crate::install::VerifiedManifest::open(
            &manifest,
            &signature,
            crate::install::RELEASE_PUBLIC_KEY,
        )?;
        let artifact = verified.artifact_for_target(&crate::install::current_target()?)?;
        verified.verify_bytes_at(vehicle, &artifact)?;
        ensure!(
            crate::install::sha256_file(&terms)? == verified.manifest.terms_sha256,
            "the displayed terms do not match the signed manifest"
        );
        let terms_text =
            std::fs::read_to_string(&terms).context("reading the reviewed installer terms")?;
        Ok(Self {
            vehicle: vehicle.to_owned(),
            manifest,
            signature,
            bundle_root: app_dir,
            terms,
            terms_version: verified.manifest.terms_version.clone(),
            version: verified.manifest.version.clone(),
            terms_text,
        })
    }
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
        let Some(preflight) = self.preflight.take() else {
            return;
        };
        let (sender, receiver) = mpsc::channel();
        self.receiver = Some(receiver);
        self.state = State::Installing("Verifying the signed release".to_owned());
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
                        crate::install::InstallPhase::Verifying => "Verifying the signed release",
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
}

#[cfg(target_os = "linux")]
impl eframe::App for InstallerApp {
    fn update(&mut self, ctx: &egui::Context, _frame: &mut eframe::Frame) {
        crate::console::theme::refresh(ctx);
        if let Some(receiver) = &self.receiver {
            while let Ok(state) = receiver.try_recv() {
                self.state = state;
            }
            if matches!(self.state, State::Installing(_)) {
                ctx.request_repaint_after(std::time::Duration::from_millis(100));
            }
        }
        egui::CentralPanel::default().show(ctx, |ui| {
            ui.add_space(24.0);
            ui.horizontal(|ui| {
                ui.heading("VADGR");
                ui.with_layout(Layout::right_to_left(Align::Center), |ui| { ui.label(format!("Version {}", self.preflight.as_ref().map_or("0.5.0", |value| &value.version))); });
            });
            ui.add_space(28.0);
            match &self.state {
                State::Terms => {
                    ui.heading("Review the terms");
                    ui.label("Vadgr will not change this machine until you accept these terms and choose Install.");
                    ui.add_space(12.0);
                    egui::ScrollArea::vertical().max_height(380.0).show(ui, |ui| {
                        crate::console::theme::card().show(ui, |ui| { ui.label(&self.preflight.as_ref().expect("terms state keeps preflight").terms_text); });
                    });
                    ui.add_space(12.0);
                    ui.checkbox(&mut self.accepted, "I have read and accept these terms");
                    ui.with_layout(Layout::right_to_left(Align::Center), |ui| {
                        if ui.add_enabled(self.accepted, egui::Button::new("Install Vadgr")).clicked() { self.install(); }
                        if ui.button("Decline and close").clicked() { ctx.send_viewport_cmd(egui::ViewportCommand::Close); }
                    });
                }
                State::Installing(phase) => {
                    ui.heading("Installing Vadgr");
                    ui.add(egui::Spinner::new().size(28.0));
                    ui.label(phase);
                    ui.label(RichText::new("Do not close this window while the active generation is being committed.").color(crate::console::theme::muted()));
                }
                State::Success(path) => {
                    ui.heading("Vadgr is ready");
                    ui.label("The signed generation is installed and the daemon answered its health check.");
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
