#!/usr/bin/env python3
"""One chooser-selected Wayland WINDOW, via portal and scoped PipeWire remote.

Requires system Python GI, Gio, Gst and pipewiresrc/videoconvert/pngenc/appsink.
No window is automatically selected. No monitor, desktop or crop fallback.
The operator must inspect the resulting image and independently prove focus.
Protocol: https://flatpak.github.io/xdg-desktop-portal/docs/doc-org.freedesktop.portal.ScreenCast.html
"""

import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import signal
import struct
import sys
import time
import uuid


SERVICE = "org.freedesktop.portal.Desktop"
OBJECT = "/org/freedesktop/portal/desktop"
SCREENCAST = "org.freedesktop.portal.ScreenCast"
REQUEST = "org.freedesktop.portal.Request"
SESSION = "org.freedesktop.portal.Session"


class CaptureError(Exception):
    """Only fixed, non-private diagnostic codes cross the CLI boundary."""


def source_options():
    return {"types": 2, "multiple": False}


def window_stream(results):
    streams = results.get("streams", [])
    if len(streams) != 1:
        raise CaptureError("expected_one_window_stream")
    node, properties = streams[0]
    if type(node) is not int or node <= 0:
        raise CaptureError("invalid_stream_node")
    if "source_type" in properties and (
        type(properties["source_type"]) is not int or properties["source_type"] != 2
    ):
        raise CaptureError("non_window_stream_rejected")
    return node, properties


def event(name, **fields):
    print(json.dumps({"event": name, **fields}), file=sys.stderr, flush=True)


class Portal:
    def __init__(self, Gio, GLib, timeout):
        self.Gio, self.GLib = Gio, GLib
        self.deadline = time.monotonic() + timeout
        self.bus = Gio.bus_get_sync(Gio.BusType.SESSION, None)
        self.session = None
        self.pending = None

    def remaining(self):
        left = self.deadline - time.monotonic()
        if left <= 0:
            raise CaptureError("timeout")
        return left

    def call(self, path, interface, method, arguments, cleanup=False):
        return self.bus.call_sync(
            SERVICE, path, interface, method, arguments, None,
            self.Gio.DBusCallFlags.NONE,
            2000 if cleanup else max(1, int(self.remaining() * 1000)), None,
        )

    def request(self, method, signature, prefix, options):
        token = "capture_" + uuid.uuid4().hex
        options = dict(options, handle_token=self.GLib.Variant("s", token))
        sender = self.bus.get_unique_name()[1:].replace(".", "_")
        expected = f"{OBJECT}/request/{sender}/{token}"
        response = []
        loop = self.GLib.MainLoop()

        def received(_bus, _sender, _path, _interface, _signal, parameters, _data):
            response.append(parameters.unpack())
            loop.quit()

        # Subscribe before the method call; fast responses must not be lost.
        subscription = self.bus.signal_subscribe(
            SERVICE, REQUEST, "Response", expected, None,
            self.Gio.DBusSignalFlags.NONE, received, None,
        )
        timer = None
        self.pending = expected
        try:
            reply = self.call(OBJECT, SCREENCAST, method,
                              self.GLib.Variant(signature, (*prefix, options)))
            actual = reply.unpack()[0]
            if actual != expected:
                self.pending = actual
                raise CaptureError("unexpected_request_path")

            def expired():
                loop.quit()
                return False

            timer = self.GLib.timeout_source_new(max(1, int(self.remaining() * 1000)))
            timer.set_callback(lambda *_: expired())
            timer.attach(None)
            if not response:
                loop.run()
            if not response:
                raise CaptureError("timeout")
            self.pending = None
            code, results = response[0]
            if code != 0:
                raise CaptureError("cancelled" if code == 1 else "portal_request_failed")
            return results
        finally:
            if timer is not None:
                timer.destroy()
            self.bus.signal_unsubscribe(subscription)

    def start(self):
        token = "session_" + uuid.uuid4().hex
        sender = self.bus.get_unique_name()[1:].replace(".", "_")
        # Retain the predicted handle so cancellation during creation can close it.
        self.session = f"{OBJECT}/session/{sender}/{token}"
        result = self.request("CreateSession", "(a{sv})", (), {
            "session_handle_token": self.GLib.Variant("s", token),
        })
        if result.get("session_handle") != self.session:
            raise CaptureError("unexpected_session_path")
        options = source_options()
        self.request("SelectSources", "(oa{sv})", (self.session,), {
            "types": self.GLib.Variant("u", options["types"]),
            "multiple": self.GLib.Variant("b", options["multiple"]),
        })
        result = self.request("Start", "(osa{sv})", (self.session, ""), {})
        return window_stream(result)

    def open_remote(self):
        reply, descriptors = self.bus.call_with_unix_fd_list_sync(
            SERVICE, OBJECT, SCREENCAST, "OpenPipeWireRemote",
            self.GLib.Variant("(oa{sv})", (self.session, {})),
            self.GLib.VariantType.new("(h)"), self.Gio.DBusCallFlags.NONE,
            max(1, int(self.remaining() * 1000)), None, None,
        )
        return descriptors.get(reply.unpack()[0])

    def delay(self, seconds):
        until = time.monotonic() + seconds
        context = self.GLib.MainContext.default()
        while time.monotonic() < until:
            self.remaining()
            while context.pending():
                context.iteration(False)
            time.sleep(min(0.05, max(0, until - time.monotonic())))

    def close(self):
        for attribute, interface in (("pending", REQUEST), ("session", SESSION)):
            path = getattr(self, attribute)
            setattr(self, attribute, None)
            if path:
                try:
                    self.call(path, interface, "Close", None, cleanup=True)
                except Exception:
                    event("cleanup_warning", resource=attribute)


def grab_png(Gst, portal, fd, node, properties):
    pipeline = Gst.Pipeline.new("window-still")
    try:
        elements = [Gst.ElementFactory.make(name) for name in (
            "pipewiresrc", "videoconvert", "pngenc", "appsink")]
        if any(element is None for element in elements):
            raise CaptureError("missing_gstreamer_element")
        source, convert, encoder, sink = elements
        source.set_property("fd", fd)
        serial = properties.get("pipewire-serial")
        if serial is not None:
            if type(serial) is not int or serial <= 0 or not source.find_property("target-object"):
                raise CaptureError("unsupported_stream_serial")
            source.set_property("target-object", str(serial))
        else:
            source.set_property("path", str(node))
        encoder.set_property("snapshot", True)
        sink.set_property("sync", False)
        sink.set_property("max-buffers", 1)
        for element in elements:
            pipeline.add(element)
        for upstream, downstream in zip(elements, elements[1:]):
            if not upstream.link(downstream):
                raise CaptureError("pipeline_link_failed")
        if pipeline.set_state(Gst.State.PLAYING) == Gst.StateChangeReturn.FAILURE:
            raise CaptureError("pipeline_start_failed")
        bus = pipeline.get_bus()
        while True:
            portal.remaining()
            sample = sink.emit("try-pull-sample", int(min(0.1, portal.remaining()) * Gst.SECOND))
            if sample is not None:
                buffer = sample.get_buffer()
                return buffer.extract_dup(0, buffer.get_size())
            if bus.pop_filtered(Gst.MessageType.ERROR):
                raise CaptureError("pipeline_error")
            if sink.get_property("eos"):
                raise CaptureError("stream_ended_without_frame")
    finally:
        pipeline.set_state(Gst.State.NULL)


def capture_bytes(portal, grab, delay):
    fd = None
    try:
        node, properties = portal.start()
        status = "verified_window" if "source_type" in properties else "not_exposed_window_requested"
        event("window_selected", source_type=status)
        portal.delay(delay)
        fd = portal.open_remote()
        return grab(portal, fd, node, properties), status
    finally:
        try:
            if fd is not None:
                os.close(fd)
        finally:
            portal.close()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path, help="New private PNG file; never overwritten")
    parser.add_argument("--timeout", type=float, default=60, help="Total seconds, 1 to 300")
    parser.add_argument("--delay", type=float, default=0, help="Seconds after window_selected before capture, 0 to 30")
    args = parser.parse_args(argv)
    if not math.isfinite(args.timeout) or not 1 <= args.timeout <= 300:
        parser.error("timeout must be 1 to 300 seconds")
    if not math.isfinite(args.delay) or not 0 <= args.delay <= 30 or args.delay >= args.timeout:
        parser.error("delay must be 0 to 30 seconds and less than timeout")

    def interrupted(_signum, _frame):
        raise CaptureError("interrupted")

    for signum in (signal.SIGINT, signal.SIGTERM):
        signal.signal(signum, interrupted)
    try:
        if args.output.exists() or args.output.is_symlink():
            raise CaptureError("output_exists")
        if not args.output.parent.is_dir():
            raise CaptureError("output_parent_missing")
        import gi
        gi.require_version("Gst", "1.0")
        from gi.repository import Gio, GLib, Gst
        Gst.init(None)
        portal = Portal(Gio, GLib, args.timeout)
        png, status = capture_bytes(portal, lambda *values: grab_png(Gst, *values), args.delay)
        if len(png) < 24 or png[:8] != b"\x89PNG\r\n\x1a\n" or png[12:16] != b"IHDR":
            raise CaptureError("invalid_png")
        width, height = struct.unpack(">II", png[16:24])
        descriptor = os.open(args.output, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, "wb") as output:
            output.write(png)
        print(json.dumps({"width": width, "height": height, "bytes": len(png),
                          "sha256": hashlib.sha256(png).hexdigest(), "source_type": status}))
        return 0
    except CaptureError as error:
        event("error", code=str(error))
    except Exception:
        # Native errors can contain application titles and private file paths.
        event("error", code="native_capture_failed")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
