//! Text fields shared by machine settings, provider credentials and data deletion.

use eframe::egui;

#[derive(Clone, Copy)]
pub(super) enum TextInput {
    Singleline,
    Multiline,
    Password,
}

impl TextInput {
    pub(super) fn show(self, ui: &mut egui::Ui, id: egui::Id, text: &mut String) -> egui::Response {
        #[cfg(target_os = "macos")]
        let native_changed = self.apply_native_value(ui, id, text);

        let widget = match self {
            Self::Singleline => egui::TextEdit::singleline(text),
            Self::Multiline => egui::TextEdit::multiline(text).desired_rows(4),
            Self::Password => egui::TextEdit::singleline(text)
                .password(true)
                .hint_text("API key"),
        };
        #[allow(unused_mut)]
        let mut response = ui.add(widget.id(id));

        #[cfg(target_os = "macos")]
        {
            if response.enabled() {
                ui.ctx().accesskit_node_builder(id, |node| {
                    node.add_action(egui::accesskit::Action::SetValue);
                });
            }
            if native_changed {
                response.mark_changed();
            }
        }
        response
    }

    #[cfg(target_os = "macos")]
    fn apply_native_value(self, ui: &egui::Ui, id: egui::Id, text: &mut String) -> bool {
        use egui::accesskit::{Action, ActionData};
        use egui::text::{CCursor, CCursorRange};

        // macOS exposes writable AXValue for text ranges. Own that action here:
        // egui 0.36.1 handles text selection and keyboard events, but not SetValue.
        // Consume before the widget so a future toolkit handler cannot replay it.
        let enabled = ui.is_enabled();
        let mut replacement = None;
        ui.input_mut(|input| {
            input.consume_accesskit_action_requests(id, |request| {
                if request.action != Action::SetValue {
                    return false;
                }
                if enabled && let Some(ActionData::Value(value)) = &request.data {
                    replacement = Some(match self {
                        Self::Multiline => value.to_string(),
                        _ => value.replace(['\r', '\n'], " "),
                    });
                }
                true
            });
        });
        let Some(value) = replacement.filter(|value| value != text) else {
            return false;
        };
        let mut state = egui::TextEdit::load_state(ui.ctx(), id).unwrap_or_default();
        let mut undoer = state.undoer();
        let previous_cursor = state
            .cursor
            .char_range()
            .unwrap_or_else(|| CCursorRange::one(CCursor::new(text.chars().count())));
        undoer.add_undo(&(previous_cursor, text.clone()));
        *text = value;
        let cursor = CCursorRange::one(CCursor::new(text.chars().count()));
        state.cursor.set_char_range(Some(cursor));
        undoer.add_undo(&(cursor, text.clone()));
        state.set_undoer(undoer);
        state.store(ui.ctx(), id);
        true
    }
}

#[cfg(all(test, target_os = "macos"))]
mod tests {
    use super::*;
    use egui::accesskit::{Action, ActionData, ActionRequest, TreeId};

    fn request(id: egui::Id, data: ActionData) -> egui::Event {
        egui::Event::AccessKitActionRequest(ActionRequest {
            action: Action::SetValue,
            target_tree: TreeId::ROOT,
            target_node: id.accesskit_id(),
            data: Some(data),
        })
    }

    fn draw(
        ctx: &egui::Context,
        text: &mut String,
        enabled: bool,
        events: Vec<egui::Event>,
    ) -> egui::Response {
        let mut response = None;
        let mut output = ctx.run_ui(
            egui::RawInput {
                events,
                ..Default::default()
            },
            |ui| {
                ui.add_enabled_ui(enabled, |ui| {
                    response = Some(TextInput::Singleline.show(ui, egui::Id::new("field"), text));
                });
            },
        );
        output.textures_delta.clear();
        response.unwrap()
    }

    #[test]
    fn native_set_value_is_targeted_enabled_typed_and_consumed_once() {
        let ctx = egui::Context::default();
        let mut text = String::from("before");
        let id = egui::Id::new("field");
        draw(&ctx, &mut text, true, vec![]);
        for (enabled, event) in [
            (
                true,
                request(
                    egui::Id::new("other"),
                    ActionData::Value("wrong field".into()),
                ),
            ),
            (false, request(id, ActionData::Value("disabled".into()))),
            (true, request(id, ActionData::NumericValue(42.0))),
        ] {
            assert!(!draw(&ctx, &mut text, enabled, vec![event]).changed());
            assert_eq!(text, "before");
        }
        let response = draw(
            &ctx,
            &mut text,
            true,
            vec![request(id, ActionData::Value("café\nname".into()))],
        );
        assert!(response.changed());
        assert_eq!(text, "café name");
        assert!(!ctx.input(|input| input.has_accesskit_action_request(id, Action::SetValue)));
        assert!(
            !draw(
                &ctx,
                &mut text,
                true,
                vec![request(id, ActionData::Value("café name".into()))]
            )
            .changed()
        );
    }

    #[test]
    fn keyboard_continues_after_native_unicode_replacement_and_undo_restores_it() {
        let ctx = egui::Context::default();
        let mut text = String::from("before");
        let id = egui::Id::new("field");
        draw(&ctx, &mut text, true, vec![]);
        ctx.memory_mut(|memory| memory.request_focus(id));
        draw(
            &ctx,
            &mut text,
            true,
            vec![request(id, ActionData::Value("café".into()))],
        );
        draw(&ctx, &mut text, true, vec![egui::Event::Text("!".into())]);
        assert_eq!(text, "café!");
        draw(
            &ctx,
            &mut text,
            true,
            vec![egui::Event::Key {
                key: egui::Key::Z,
                physical_key: None,
                pressed: true,
                repeat: false,
                modifiers: egui::Modifiers::COMMAND,
            }],
        );
        assert_eq!(text, "café");
    }
}
