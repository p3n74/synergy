"""Mac controller. Cross the right edge of the laptop to drive the Windows PC.

The process starts at login and reconnects whenever the laptop wakes.
Input injection runs only after the Windows agent accepts the shared token.
"""

from __future__ import annotations

import argparse
import os
import queue
import signal
import socket
import sys
import threading
import time

from .config import load_config
from .edge import quartz_y_from_frac, should_cross_out, y_frac_from_quartz
from .keys import is_modifier, mac_to_vk
from .protocol import DEFAULT_PORT, AuthError, ProtocolError, recv_obj, send_obj, tune_socket

# Gather a fast swipe into one packet. Slow moves still leave within a frame.
MOUSE_BATCH = 0.008
CLIPBOARD_INTERVAL = 0.05

HOTKEY_MOD_CTRL = 0x00040000
HOTKEY_MOD_ALT = 0x00080000
MAC_RIGHT = 124
MAC_LEFT = 123
MAC_ESCAPE = 53
PID_PATH = __import__("pathlib").Path.home() / ".homesynergy" / "agent.pid"


def log(msg: str) -> None:
    print(time.strftime("%H:%M:%S"), msg, flush=True)


class Link:
    def __init__(self, token: str) -> None:
        self.token = token
        self.sock: socket.socket | None = None
        self.lock = threading.Lock()
        self.geometry: dict | None = None
        self.connected = threading.Event()
        self.inbox: queue.Queue = queue.Queue()
        self.cv = threading.Condition()
        self.events: list[dict] = []
        self.pending_dx = 0.0
        self.pending_dy = 0.0

    def send(self, obj: dict) -> None:
        with self.cv:
            if obj.get("t") == "mouse":
                self.pending_dx += float(obj["dx"])
                self.pending_dy += float(obj["dy"])
            else:
                self.events.append(obj)
            self.cv.notify()

    def take_batch(self) -> tuple[float, float, list[dict]]:
        """Mouse waits a few milliseconds so a swipe is one move. Keys do not."""
        with self.cv:
            if not self.events and not self.pending_dx and not self.pending_dy:
                self.cv.wait(0.5)
            if not self.events and (self.pending_dx or self.pending_dy):
                self.cv.wait(MOUSE_BATCH)
            dx, dy = self.pending_dx, self.pending_dy
            self.pending_dx = 0.0
            self.pending_dy = 0.0
            events = self.events
            self.events = []
        return dx, dy, events

    def close(self) -> None:
        with self.lock:
            sock = self.sock
            self.sock = None
            self.connected.clear()
            self.geometry = None
        if sock is not None:
            try:
                sock.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
            sock.close()


def _writer(link: Link, stop: threading.Event) -> None:
    while not stop.is_set():
        dx, dy, events = link.take_batch()
        if stop.is_set():
            break
        outgoing: list[dict] = []
        if dx or dy:
            outgoing.append({"t": "mouse", "dx": dx, "dy": dy})
        outgoing.extend(events)
        for obj in outgoing:
            with link.lock:
                sock = link.sock
            if sock is None:
                break
            try:
                send_obj(sock, link.token, obj)
            except OSError as exc:
                log(f"send failed: {exc}")
                link.close()
                break


def _connect_loop(link: Link, cfg: dict, stop: threading.Event, wake_main) -> None:
    host = cfg["windows_host"]
    port = int(cfg["port"])
    while not stop.is_set():
        try:
            log(f"connecting to {host}:{port}")
            sock = socket.create_connection((host, port), timeout=5)
            tune_socket(sock)
            sock.settimeout(None)
            send_obj(sock, link.token, {"t": "hello", "v": 1, "name": "mac"})
            reply = recv_obj(sock, link.token)
            if not reply or reply.get("t") != "hello_ok":
                raise ProtocolError(f"unexpected hello reply: {reply}")
            with link.lock:
                link.sock = sock
                link.geometry = reply
            link.connected.set()
            log(
                "connected "
                f"{reply.get('width')}x{reply.get('height')} "
                f"at {reply.get('left')},{reply.get('top')}"
            )
            while not stop.is_set():
                msg = recv_obj(sock, link.token)
                if msg is None:
                    break
                link.inbox.put(msg)
                wake_main()
        except AuthError as exc:
            log(f"auth failed: {exc}")
        except (OSError, ProtocolError, TimeoutError) as exc:
            log(f"link down: {exc}")
        finally:
            link.close()
        if stop.wait(2):
            break


def run_check(cfg: dict) -> int:
    host = cfg["windows_host"]
    port = int(cfg["port"])
    token = cfg["token"]
    log(f"check {host}:{port}")
    sock = socket.create_connection((host, port), timeout=5)
    try:
        send_obj(sock, token, {"t": "hello", "v": 1, "name": "mac"})
        reply = recv_obj(sock, token)
    finally:
        sock.close()
    if not reply or reply.get("t") != "hello_ok":
        log(f"bad reply: {reply}")
        return 1
    log(f"windows ready {reply}")
    return 0


def main(argv: list[str] | None = None) -> None:
    if sys.platform != "darwin":
        raise SystemExit("mac_agent runs on macOS")

    parser = argparse.ArgumentParser(description="HomeSynergy Mac controller")
    parser.add_argument("--check", action="store_true", help="connect once and print the Windows screen")
    args = parser.parse_args(argv)
    cfg = load_config()
    if args.check:
        raise SystemExit(run_check(cfg))

    import Quartz
    from AppKit import NSPasteboard, NSScreen, NSWorkspace
    from Foundation import NSObject, NSRunLoop, NSTimer

    edge_px = float(cfg["edge_px"])
    speed = float(cfg["speed"])
    command_is_control = bool(cfg["command_is_control"])
    link = Link(cfg["token"])
    stop = threading.Event()
    remote = {"on": False, "skip_delta": False, "hold_until": 0.0}
    reset_requested = {"on": False}
    held_mods: set[int] = set()
    last_clip = {"text": None, "change": None}
    display = {"right": 0.0, "origin_y": 0.0, "height": 1.0}

    def refresh_display() -> None:
        main_id = Quartz.CGMainDisplayID()
        bounds = Quartz.CGDisplayBounds(main_id)
        right = bounds.origin.x + bounds.size.width
        origin_y = bounds.origin.y
        height = bounds.size.height
        try:
            listed = Quartz.CGGetOnlineDisplayList(32, None, None)
            err = listed[0]
            ids = listed[1] if len(listed) > 1 else None
            if not err and ids:
                for display_id in ids:
                    rect = Quartz.CGDisplayBounds(display_id)
                    edge = rect.origin.x + rect.size.width
                    if edge >= right:
                        right = edge
                        origin_y = rect.origin.y
                        height = rect.size.height
        except Exception as exc:
            log(f"display list failed, using main display: {exc}")
        display["right"] = right
        display["origin_y"] = origin_y
        display["height"] = height or 1.0

    def y_frac_at(quartz_y: float) -> float:
        return y_frac_from_quartz(quartz_y, display["origin_y"], display["height"])

    def force_local() -> None:
        """Return the pointer to the Mac even if the handoff never started moving."""
        remote["on"] = False
        remote["skip_delta"] = False
        remote["hold_until"] = time.time() + 0.6
        Quartz.CGAssociateMouseAndMouseCursorPosition(True)
        if tap_holder[0] is not None:
            Quartz.CGEventTapEnable(tap_holder[0], True)
        bounds = Quartz.CGDisplayBounds(Quartz.CGMainDisplayID())
        Quartz.CGWarpMouseCursorPosition(
            Quartz.CGPointMake(
                bounds.origin.x + bounds.size.width / 2,
                bounds.origin.y + bounds.size.height / 2,
            )
        )
        link.send({"t": "leave"})
        for code in list(held_mods):
            vk = mac_to_vk(code, command_is_control)
            if vk is not None:
                link.send({"t": "key", "down": False, "vk": vk, "mac": code})
        held_mods.clear()
        log("failsafe: pointer back on mac")

    def release_remote(y_frac: float | None = None) -> None:
        if not remote["on"]:
            Quartz.CGAssociateMouseAndMouseCursorPosition(True)
            return
        remote["on"] = False
        Quartz.CGAssociateMouseAndMouseCursorPosition(True)
        if y_frac is not None:
            y = quartz_y_from_frac(y_frac, display["origin_y"], display["height"])
            Quartz.CGWarpMouseCursorPosition(Quartz.CGPointMake(display["right"] - 20, y))
        for code in list(held_mods):
            vk = mac_to_vk(code, command_is_control)
            if vk is not None:
                link.send({"t": "key", "down": False, "vk": vk, "mac": code})
        held_mods.clear()
        log("pointer back on mac")

    def enter_remote(quartz_y: float) -> None:
        if remote["on"] or not link.connected.is_set():
            return
        refresh_display()
        remote["on"] = True
        remote["skip_delta"] = True
        Quartz.CGAssociateMouseAndMouseCursorPosition(False)
        frac = y_frac_at(quartz_y)
        link.send({"t": "enter", "y_frac": frac})
        flags = Quartz.CGEventSourceFlagsState(Quartz.kCGEventSourceStateHIDSystemState)
        synthetic = []
        if flags & Quartz.kCGEventFlagMaskShift:
            synthetic.append(56)
        if flags & Quartz.kCGEventFlagMaskControl:
            synthetic.append(59)
        if flags & Quartz.kCGEventFlagMaskAlternate:
            synthetic.append(58)
        if flags & Quartz.kCGEventFlagMaskCommand:
            synthetic.append(55)
        for code in synthetic:
            vk = mac_to_vk(code, command_is_control)
            if vk is None:
                continue
            held_mods.add(code)
            link.send({"t": "key", "down": True, "vk": vk, "mac": code})
        log("pointer on windows")

    def send_key(code: int, down: bool) -> None:
        vk = mac_to_vk(code, command_is_control)
        if vk is None:
            log(f"unmapped mac keycode {code}")
            return
        link.send({"t": "key", "down": down, "vk": int(vk), "mac": int(code)})

    def tap_callback(proxy, event_type, event, refcon):
        del proxy, refcon
        if event_type in (
            Quartz.kCGEventTapDisabledByTimeout,
            Quartz.kCGEventTapDisabledByUserInput,
        ):
            log("event tap disabled, re-enabling")
            Quartz.CGEventTapEnable(tap_holder[0], True)
            return event

        keycode = int(Quartz.CGEventGetIntegerValueField(event, Quartz.kCGKeyboardEventKeycode))
        flags = int(Quartz.CGEventGetFlags(event))
        hotkey = flags & HOTKEY_MOD_CTRL and flags & HOTKEY_MOD_ALT

        if reset_requested["on"] or (event_type == Quartz.kCGEventKeyDown and hotkey and keycode == MAC_ESCAPE):
            reset_requested["on"] = False
            force_local()
            return None
        if event_type == Quartz.kCGEventKeyDown and hotkey and keycode == MAC_RIGHT:
            loc = Quartz.CGEventGetLocation(event)
            enter_remote(loc.y)
            return None
        if event_type == Quartz.kCGEventKeyDown and hotkey and keycode == MAC_LEFT and remote["on"]:
            link.send({"t": "leave"})
            release_remote(0.5)
            return None

        if event_type in (Quartz.kCGEventMouseMoved, Quartz.kCGEventLeftMouseDragged,
                          Quartz.kCGEventRightMouseDragged, Quartz.kCGEventOtherMouseDragged):
            loc = Quartz.CGEventGetLocation(event)
            dx = float(Quartz.CGEventGetIntegerValueField(event, Quartz.kCGMouseEventDeltaX))
            dy = float(Quartz.CGEventGetIntegerValueField(event, Quartz.kCGMouseEventDeltaY))
            if not remote["on"]:
                if (
                    time.time() >= remote["hold_until"]
                    and cfg["edge"] == "right"
                    and should_cross_out(loc.x, dx, display["right"], edge_px)
                ):
                    enter_remote(loc.y)
                    return None
                return event
            if remote["skip_delta"]:
                remote["skip_delta"] = False
                return None
            link.send({"t": "mouse", "dx": dx * speed, "dy": dy * speed})
            return None

        if not remote["on"]:
            return event

        if event_type == Quartz.kCGEventScrollWheel:
            lines = int(Quartz.CGEventGetIntegerValueField(event, Quartz.kCGScrollWheelEventDeltaAxis1))
            horiz = int(Quartz.CGEventGetIntegerValueField(event, Quartz.kCGScrollWheelEventDeltaAxis2))
            link.send({"t": "wheel", "dy": lines, "dx": horiz})
            return None

        if event_type in (Quartz.kCGEventLeftMouseDown, Quartz.kCGEventLeftMouseUp,
                          Quartz.kCGEventRightMouseDown, Quartz.kCGEventRightMouseUp,
                          Quartz.kCGEventOtherMouseDown, Quartz.kCGEventOtherMouseUp):
            button = "left"
            if event_type in (Quartz.kCGEventRightMouseDown, Quartz.kCGEventRightMouseUp):
                button = "right"
            elif event_type in (Quartz.kCGEventOtherMouseDown, Quartz.kCGEventOtherMouseUp):
                number = int(Quartz.CGEventGetIntegerValueField(event, Quartz.kCGMouseEventButtonNumber))
                button = "middle" if number == 2 else "left"
            down = event_type in (
                Quartz.kCGEventLeftMouseDown,
                Quartz.kCGEventRightMouseDown,
                Quartz.kCGEventOtherMouseDown,
            )
            link.send({"t": "button", "button": button, "down": down})
            return None

        if event_type == Quartz.kCGEventFlagsChanged and is_modifier(keycode):
            if keycode in held_mods:
                held_mods.discard(keycode)
                send_key(keycode, False)
            else:
                held_mods.add(keycode)
                send_key(keycode, True)
            return None

        if event_type == Quartz.kCGEventKeyDown:
            repeat = Quartz.CGEventGetIntegerValueField(event, Quartz.kCGKeyboardEventAutorepeat)
            if repeat:
                return None
            if not is_modifier(keycode):
                send_key(keycode, True)
            return None
        if event_type == Quartz.kCGEventKeyUp:
            if not is_modifier(keycode):
                send_key(keycode, False)
            return None
        return None

    def poll(_timer) -> None:
        if reset_requested["on"]:
            reset_requested["on"] = False
            force_local()
        while True:
            try:
                msg = link.inbox.get_nowait()
            except queue.Empty:
                break
            kind = msg.get("t")
            if kind == "leave":
                release_remote(float(msg.get("y_frac", 0.5)))
            elif kind == "clipboard":
                apply_clipboard(str(msg.get("text", "")))
            elif kind == "ping":
                link.send({"t": "pong", "id": msg.get("id", 0)})
        push_clipboard()

    def apply_clipboard(text: str) -> None:
        if text == last_clip["text"]:
            return
        pb = NSPasteboard.generalPasteboard()
        pb.clearContents()
        pb.setString_forType_(text, "public.utf8-plain-text")
        last_clip["text"] = text
        last_clip["change"] = pb.changeCount()

    def push_clipboard() -> None:
        if not link.connected.is_set():
            return
        pb = NSPasteboard.generalPasteboard()
        change = pb.changeCount()
        if change == last_clip["change"]:
            return
        value = pb.stringForType_("public.utf8-plain-text")
        last_clip["change"] = change
        if value is None:
            return
        text = str(value)
        if text == last_clip["text"]:
            return
        if len(text) > 200_000:
            log("clipboard too large, skipped")
            return
        last_clip["text"] = text
        link.send({"t": "clipboard", "text": text})

    def on_wake(note) -> None:
        del note
        log("laptop woke, reconnecting")
        release_remote(None)
        link.close()

    refresh_display()
    Quartz.CGAssociateMouseAndMouseCursorPosition(True)
    mask = 0
    for event_type in (
        Quartz.kCGEventMouseMoved,
        Quartz.kCGEventLeftMouseDown,
        Quartz.kCGEventLeftMouseUp,
        Quartz.kCGEventRightMouseDown,
        Quartz.kCGEventRightMouseUp,
        Quartz.kCGEventOtherMouseDown,
        Quartz.kCGEventOtherMouseUp,
        Quartz.kCGEventLeftMouseDragged,
        Quartz.kCGEventRightMouseDragged,
        Quartz.kCGEventOtherMouseDragged,
        Quartz.kCGEventScrollWheel,
        Quartz.kCGEventKeyDown,
        Quartz.kCGEventKeyUp,
        Quartz.kCGEventFlagsChanged,
    ):
        mask |= 1 << event_type

    tap = Quartz.CGEventTapCreate(
        Quartz.kCGSessionEventTap,
        Quartz.kCGHeadInsertEventTap,
        Quartz.kCGEventTapOptionDefault,
        mask,
        tap_callback,
        None,
    )
    if tap is None:
        log(
            "Accessibility is not granted. Enable Python and this will attach on the next start: "
            f"{sys.executable}"
        )
        raise SystemExit(1)
    tap_holder = [None]
    tap_holder[0] = tap
    source = Quartz.CFMachPortCreateRunLoopSource(None, tap, 0)
    Quartz.CFRunLoopAddSource(
        Quartz.CFRunLoopGetCurrent(),
        source,
        Quartz.kCFRunLoopCommonModes,
    )
    Quartz.CGEventTapEnable(tap, True)

    workspace = NSWorkspace.sharedWorkspace()
    wake_observer = workspace.notificationCenter().addObserverForName_object_queue_usingBlock_(
        "NSWorkspaceDidWakeNotification",
        None,
        None,
        on_wake,
    )
    del wake_observer, NSObject, NSScreen

    timer = NSTimer.scheduledTimerWithTimeInterval_repeats_block_(CLIPBOARD_INTERVAL, True, poll)
    NSRunLoop.currentRunLoop().addTimer_forMode_(timer, "NSRunLoopCommonModes")
    Quartz.CGSetLocalEventsSuppressionInterval(0.0)

    main_loop = Quartz.CFRunLoopGetCurrent()

    def wake_main() -> None:
        Quartz.CFRunLoopPerformBlock(main_loop, Quartz.kCFRunLoopCommonModes, lambda: poll(None))
        Quartz.CFRunLoopWakeUp(main_loop)

    threading.Thread(target=_writer, args=(link, stop), name="hs-writer", daemon=True).start()
    threading.Thread(
        target=_connect_loop,
        args=(link, cfg, stop, wake_main),
        name="hs-link",
        daemon=True,
    ).start()
    threading.Thread(target=_keepalive, args=(link, stop), name="hs-ping", daemon=True).start()

    log(f"watching the right edge for {cfg['windows_host']}:{cfg.get('port', DEFAULT_PORT)}")
    log("control+option+right jumps, control+option+left or control+option+escape comes back")
    log("or run: synergy reset")

    def stop_loop(signum, frame):
        del signum, frame
        Quartz.CFRunLoopStop(Quartz.CFRunLoopGetCurrent())

    def request_reset(signum, frame):
        del signum, frame
        reset_requested["on"] = True
        Quartz.CFRunLoopPerformBlock(main_loop, Quartz.kCFRunLoopCommonModes, lambda: poll(None))
        Quartz.CFRunLoopWakeUp(main_loop)

    PID_PATH.parent.mkdir(parents=True, exist_ok=True)
    PID_PATH.write_text(str(os.getpid()))

    signal.signal(signal.SIGINT, stop_loop)
    signal.signal(signal.SIGTERM, stop_loop)
    signal.signal(signal.SIGUSR1, request_reset)
    try:
        Quartz.CFRunLoopRun()
    finally:
        stop.set()
        with link.cv:
            link.cv.notify_all()
        release_remote(None)
        link.close()
        PID_PATH.unlink(missing_ok=True)


def _keepalive(link: Link, stop: threading.Event) -> None:
    ident = 0
    while not stop.wait(2):
        if link.connected.is_set():
            ident += 1
            link.send({"t": "ping", "id": ident})


if __name__ == "__main__":
    main()
