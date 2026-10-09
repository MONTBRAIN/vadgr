"""Mocked harness checks, not installed-product or visual E2E."""

import importlib.util
from pathlib import Path
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch


HELPER = Path(__file__).resolve().parents[2] / "E2E/0.5.0/harness/linux_portal_capture.py"
SPEC = importlib.util.spec_from_file_location("linux_portal_capture", HELPER)
capture = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(capture)


class WindowRestrictionTests(unittest.TestCase):
    def test_only_window_requested(self):
        self.assertEqual(capture.source_options(), {"types": 2, "multiple": False})

    def test_monitor_virtual_and_mixed_types_rejected(self):
        for source_type in (1, 3, 4, 0, "2", None):
            with self.subTest(source_type=source_type):
                with self.assertRaises(capture.CaptureError):
                    capture.window_stream({"streams": [(12, {"source_type": source_type})]})

    def test_exactly_one_stream(self):
        for streams in ([], [(1, {}), (2, {})]):
            with self.assertRaises(capture.CaptureError):
                capture.window_stream({"streams": streams})

    def test_window_and_older_portal(self):
        self.assertEqual(capture.window_stream({"streams": [(12, {"source_type": 2})]})[0], 12)
        self.assertEqual(capture.window_stream({"streams": [(12, {})]})[1], {})

    def test_cleanup_after_success_and_capture_failure(self):
        for fail in (False, True):
            portal = Mock()
            portal.start.return_value = (12, {"source_type": 2})
            portal.open_remote.return_value = 42
            grab = Mock(return_value=b"png")
            if fail:
                grab.side_effect = capture.CaptureError("pipeline_error")
            with patch.object(capture.os, "close") as close:
                if fail:
                    with self.assertRaises(capture.CaptureError):
                        capture.capture_bytes(portal, grab, 0)
                else:
                    self.assertEqual(capture.capture_bytes(portal, grab, 0)[0], b"png")
                close.assert_called_once_with(42)
            portal.close.assert_called_once_with()

    def test_cleanup_after_selection_cancel_timeout_or_remote_failure(self):
        for stage in ("start", "open_remote"):
            for code in ("cancelled", "timeout", "portal_error"):
                portal = Mock()
                portal.start.return_value = (12, {})
                getattr(portal, stage).side_effect = capture.CaptureError(code)
                with patch.object(capture.os, "close") as close:
                    with self.assertRaises(capture.CaptureError):
                        capture.capture_bytes(portal, Mock(), 0)
                    close.assert_not_called()
                portal.close.assert_called_once_with()

    def test_request_timeout_unsubscribes_and_closes_request_and_session(self):
        portal = capture.Portal.__new__(capture.Portal)
        portal.GLib = Mock()
        portal.Gio = Mock()
        portal.bus = Mock()
        portal.bus.get_unique_name.return_value = ":1.8"
        portal.remaining = Mock(return_value=1)
        portal.session = "/session/test"
        portal.pending = None
        portal.call = Mock()

        def call(*args, **kwargs):
            if args[2] == "Start":
                reply = Mock()
                reply.unpack.return_value = (portal.pending,)
                return reply
        portal.call.side_effect = call
        with self.assertRaisesRegex(capture.CaptureError, "timeout"):
            portal.request("Start", "(osa{sv})", (portal.session, ""), {})
        portal.bus.signal_unsubscribe.assert_called_once()
        portal.GLib.timeout_source_new.return_value.destroy.assert_called_once()
        request = portal.pending
        portal.close()
        self.assertEqual(portal.call.call_args_list[-2].args[:3],
                         (request, capture.REQUEST, "Close"))
        self.assertEqual(portal.call.call_args_list[-1].args[:3],
                         ("/session/test", capture.SESSION, "Close"))

    def test_session_close_attempted_even_if_request_close_fails(self):
        portal = capture.Portal.__new__(capture.Portal)
        portal.pending, portal.session = "/request/test", "/session/test"
        portal.call = Mock(side_effect=RuntimeError("private upstream message"))
        with patch.object(capture, "event") as event:
            portal.close()
        self.assertEqual(portal.call.call_count, 2)
        self.assertNotIn("private", str(event.call_args_list))
        self.assertIsNone(portal.pending)
        self.assertIsNone(portal.session)

    def test_pipeline_failure_always_stops_and_never_uses_default_source(self):
        gst = Mock()
        gst.State = SimpleNamespace(PLAYING="playing", NULL="null")
        gst.StateChangeReturn = SimpleNamespace(FAILURE="failure")
        elements = [Mock() for _ in range(4)]
        gst.ElementFactory.make.side_effect = elements
        pipeline = gst.Pipeline.new.return_value
        pipeline.set_state.return_value = "failure"
        with self.assertRaisesRegex(capture.CaptureError, "pipeline_start_failed"):
            capture.grab_png(gst, Mock(), 42, 12, {})
        elements[0].set_property.assert_any_call("fd", 42)
        elements[0].set_property.assert_any_call("path", "12")
        self.assertEqual(pipeline.set_state.call_args.args, ("null",))

    def test_pipewire_serial_preferred_and_missing_plugin_fails_closed(self):
        gst = Mock()
        gst.State = SimpleNamespace(PLAYING="playing", NULL="null")
        gst.StateChangeReturn = SimpleNamespace(FAILURE="failure")
        elements = [Mock() for _ in range(4)]
        gst.ElementFactory.make.side_effect = elements
        gst.Pipeline.new.return_value.set_state.return_value = "failure"
        with self.assertRaises(capture.CaptureError):
            capture.grab_png(gst, Mock(), 42, 12, {"pipewire-serial": 81})
        elements[0].set_property.assert_any_call("target-object", "81")
        self.assertNotIn("path", [call.args[0] for call in elements[0].set_property.call_args_list])

    def test_existing_output_rejected_without_loading_native_libraries(self):
        with patch.object(capture.signal, "signal"), patch.object(capture, "event") as event:
            self.assertEqual(capture.main(["--output", str(HELPER)]), 1)
        event.assert_called_once_with("error", code="output_exists")


if __name__ == "__main__":
    unittest.main()
