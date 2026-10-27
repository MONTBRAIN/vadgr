// Based on the neighboring AccessKit interface structure.
// Copyright 2022 The AccessKit Authors. All rights reserved.
// Licensed under the Apache License, Version 2.0 (found in
// the LICENSE-APACHE file) or the MIT license (found in
// the LICENSE-MIT file), at your option.
// Local Vadgr addition: native whole-value editing; see ../../../PATCHES.md.

use accesskit_atspi_common::PlatformNode;
use zbus::{fdo, interface};

pub(crate) struct EditableTextInterface(PlatformNode);

impl EditableTextInterface {
    pub fn new(node: PlatformNode) -> Self {
        Self(node)
    }
}

#[interface(name = "org.a11y.atspi.EditableText")]
impl EditableTextInterface {
    fn set_text_contents(&self, new_contents: &str) -> fdo::Result<bool> {
        self.0
            .set_text_contents(new_contents)
            .map_err(|error| crate::util::map_error_from_node(&self.0, error))
    }

    // AccessKit SetValue supports whole-value replacement. Do not pretend to
    // implement clipboard or partial editing, particularly for secret fields.
    fn copy_text(&self, _start_pos: i32, _end_pos: i32) -> fdo::Result<()> {
        Err(fdo::Error::NotSupported(
            "Clipboard editing is not supported".into(),
        ))
    }

    fn cut_text(&self, _start_pos: i32, _end_pos: i32) -> bool {
        false
    }

    fn delete_text(&self, _start_pos: i32, _end_pos: i32) -> bool {
        false
    }

    fn insert_text(&self, _position: i32, _text: &str, _length: i32) -> bool {
        false
    }

    fn paste_text(&self, _position: i32) -> bool {
        false
    }
}

#[cfg(test)]
mod vadgr_regression_tests {
    use super::*;
    use accesskit::{
        Action, ActionData, ActionHandler, ActionRequest, Node, NodeId, Role, Tree, TreeId,
        TreeUpdate,
    };
    use accesskit_atspi_common::{
        Adapter, AdapterCallback, AppContext, Event, InterfaceSet, WindowBounds,
    };
    use std::sync::{Arc, Mutex};

    struct Callback;
    impl AdapterCallback for Callback {
        fn register_interfaces(
            &self,
            _: &Adapter,
            _: accesskit_atspi_common::NodeId,
            _: InterfaceSet,
        ) {
        }
        fn unregister_interfaces(
            &self,
            _: &Adapter,
            _: accesskit_atspi_common::NodeId,
            _: InterfaceSet,
        ) {
        }
        fn emit_event(&self, _: &Adapter, _: Event) {}
    }

    struct Requests(Arc<Mutex<Vec<ActionRequest>>>);
    impl ActionHandler for Requests {
        fn do_action(&mut self, request: ActionRequest) {
            self.0.lock().unwrap().push(request);
        }
    }

    fn update(disabled: bool) -> TreeUpdate {
        let mut node = Node::new(Role::TextInput);
        node.add_action(Action::SetValue);
        if disabled {
            node.set_disabled();
        }
        TreeUpdate {
            nodes: vec![(NodeId(0), node)],
            tree: Some(Tree::new(NodeId(0))),
            tree_id: TreeId::ROOT,
            focus: NodeId(0),
        }
    }

    #[test]
    fn native_replacement_dispatches_typed_value_and_rechecks_disabled_state() {
        let requests = Arc::new(Mutex::new(Vec::new()));
        let mut adapter = Adapter::new(
            &AppContext::new(None),
            Callback,
            update(false),
            false,
            WindowBounds::default(),
            Requests(requests.clone()),
        );
        let interface = EditableTextInterface::new(adapter.platform_node(adapter.root_id()));
        assert!(interface.set_text_contents("café").unwrap());
        {
            let requests = requests.lock().unwrap();
            assert_eq!(requests.len(), 1);
            assert_eq!(requests[0].action, Action::SetValue);
            assert!(
                matches!(&requests[0].data, Some(ActionData::Value(value)) if &**value == "café")
            );
        }
        adapter.update(update(true));
        assert!(!interface.set_text_contents("disabled").unwrap());
        assert!(!interface.cut_text(0, 1));
        assert!(!interface.delete_text(0, 1));
        assert!(!interface.insert_text(0, "ignored", 7));
        assert!(!interface.paste_text(0));
        assert!(matches!(
            interface.copy_text(0, 1),
            Err(fdo::Error::NotSupported(_))
        ));
        assert_eq!(requests.lock().unwrap().len(), 1);
    }
}
