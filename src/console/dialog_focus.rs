//! Modal focus is an interaction lifecycle, not a per-frame focus request.
use super::{Dialog, View};
use eframe::egui;

pub(super) fn initial_control(
    target: &mut Option<egui::Id>,
    response: egui::Response,
) -> egui::Response {
    if target.is_none() && response.enabled() {
        *target = Some(response.id);
    }
    response
}

#[derive(Default)]
pub(super) struct DialogFocus {
    origin: Option<(View, egui::Id)>,
    stage: Option<std::mem::Discriminant<Dialog>>,
    returning_from: Option<Option<egui::Id>>,
    pub(super) awaiting_pairing: bool,
    controls: Vec<egui::Response>,
    fallback: Option<egui::Response>,
}

impl DialogFocus {
    pub(super) fn begin_frame(&mut self, ctx: &egui::Context, view: View) {
        // Read navigation intent before poll can open a ready asynchronous modal
        // and disable the very control the user is trying to reach.
        if (self.awaiting_pairing || self.returning_from.is_some())
            && self.origin.is_some_and(|(_, origin)| {
                let bounds = self
                    .controls
                    .iter()
                    .find(|response| response.id == origin)
                    .map(|response| response.rect);
                ctx.input(|input| {
                    input.events.iter().any(|event| match event {
                        egui::Event::AccessKitActionRequest(request) => {
                            matches!(
                                request.action,
                                egui::accesskit::Action::Focus | egui::accesskit::Action::Click
                            ) && request.target_node != origin.accesskit_id()
                        }
                        egui::Event::Key {
                            key: egui::Key::Escape,
                            pressed: true,
                            ..
                        } => true,
                        egui::Event::Key {
                            key: egui::Key::Tab,
                            pressed: true,
                            modifiers,
                            ..
                        } => !modifiers.any() || modifiers.shift_only(),
                        egui::Event::Key {
                            key:
                                egui::Key::ArrowUp
                                | egui::Key::ArrowDown
                                | egui::Key::ArrowLeft
                                | egui::Key::ArrowRight,
                            pressed: true,
                            modifiers,
                            ..
                        } => !modifiers.any(),
                        egui::Event::PointerButton {
                            pos, pressed: true, ..
                        } => bounds.is_none_or(|rect| !rect.contains(*pos)),
                        _ => false,
                    })
                })
            })
        {
            self.origin = None;
            self.returning_from = None;
            self.awaiting_pairing = false;
        }
        self.controls.clear();
        self.fallback = None;
        self.check_view(view);
    }

    fn check_view(&mut self, view: View) {
        if self.origin.is_some_and(|(origin, _)| origin != view) {
            self.origin = None;
            self.returning_from = None;
            self.stage = None;
            self.awaiting_pairing = false;
        }
    }

    pub(super) fn opener(&mut self, view: View, response: egui::Response) -> bool {
        let clicked = response.clicked();
        if clicked {
            self.origin = Some((view, response.id));
            self.stage = None;
            self.returning_from = None;
            self.awaiting_pairing = false;
        }
        self.controls.push(response);
        clicked
    }

    pub(super) fn fallback(&mut self, response: egui::Response) {
        self.fallback = Some(response);
    }

    pub(super) fn enter(&mut self, ctx: &egui::Context, dialog: &Dialog, target: Option<egui::Id>) {
        let stage = std::mem::discriminant(dialog);
        if self.stage != Some(stage)
            && let Some(target) = target
        {
            ctx.memory_mut(|memory| memory.request_focus(target));
            self.stage = Some(stage);
        }
    }

    pub(super) fn closed(&mut self, ctx: &egui::Context) {
        self.stage = None;
        self.awaiting_pairing = false;
        self.returning_from = Some(ctx.memory(|memory| memory.focused()));
    }

    pub(super) fn finish_frame(
        &mut self,
        ctx: &egui::Context,
        view: View,
        busy: bool,
        modal: bool,
    ) {
        self.check_view(view);
        let Some(previous_focus) = self.returning_from else {
            return;
        };
        if modal {
            return;
        }
        let focused = ctx.memory(|memory| memory.focused());
        if focused.is_some() && focused != previous_focus {
            // A later user interaction owns focus; asynchronous completion cannot steal it.
            self.returning_from = None;
            self.origin = None;
            return;
        }
        if busy {
            return;
        }
        let Some((_, opener)) = self.origin else {
            self.returning_from = None;
            return;
        };
        let response = self
            .controls
            .iter()
            .find(|response| response.id == opener && response.enabled())
            .or_else(|| self.fallback.as_ref().filter(|response| response.enabled()));
        if let Some(response) = response {
            response.request_focus();
            self.returning_from = None;
            self.origin = None;
        }
    }
}

/// Stable semantic scope: a reloaded or reordered row never inherits another row's opener.
pub(super) fn opener_control(
    ui: &mut egui::Ui,
    key: impl std::hash::Hash + std::fmt::Debug,
    draw: impl FnOnce(&mut egui::Ui) -> egui::Response,
) -> egui::Response {
    ui.scope_builder(
        egui::UiBuilder::new().id(egui::Id::new(("console-dialog-opener", key))),
        draw,
    )
    .inner
}
