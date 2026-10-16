"""Windows receiver. Listens on the LAN and injects input into the logged-in session.

Run this in the interactive user session (a logon scheduled task), not as a
session-0 service. SendInput does not reach the desktop from session 0.
"""

from __future__ import annotations

import argparse
import ctypes
import ipaddress
import socket
import sys
import threading
import time
from ctypes import wintypes

from .config import load_config
from .keys import EXTENDED_VKS
from .protocol import AuthError, ProtocolError, recv_obj, send_obj, tune_socket
from .session import RemotePointer


def log(msg: str) -> None:
    print(time.strftime("%H:%M:%S"), msg, flush=True)


def is_lan_address(ip: str) -> bool:
    try:
        addr = ipaddress.ip_address(ip)
    except ValueError:
        return False
    return bool(addr.is_private or addr.is_loopback or addr.is_link_local)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="HomeSynergy Windows receiver")
    parser.add_argument("--check-config", action="store_true")
    args = parser.parse_args(argv)
    cfg = load_config()
    if args.check_config:
        print(f"ok {cfg['bind']}:{cfg['port']}")
        return
    if sys.platform != "win32":
        raise SystemExit("win_agent runs on Windows")
    serve(cfg)


def serve(cfg: dict) -> None:
    user32, kernel32 = _win32()
    geometry = _virtual_screen(user32)
    pointer = RemotePointer(geometry["left"], geometry["top"], geometry["width"], geometry["height"])
    held: dict[int, int] = {}
    held_lock = threading.Lock()
    clip_seq = {"n": _clipboard_sequence(user32), "text": _read_clipboard(user32, kernel32)}

    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind((cfg["bind"], int(cfg["port"])))
    sock.listen(1)
    log(
        f"listening on {cfg['bind']}:{cfg['port']} "
        f"screen {geometry['width']}x{geometry['height']}"
    )

    while True:
        conn, addr = sock.accept()
        peer = addr[0]
        if not is_lan_address(peer):
            log(f"rejected non-lan peer {peer}")
            conn.close()
            continue
        log(f"peer {peer}")
        tune_socket(conn)
        conn.settimeout(8)
        try:
            _serve_client(conn, cfg, user32, kernel32, pointer, held, held_lock, clip_seq, geometry)
        except AuthError as exc:
            log(f"auth failed from {peer}: {exc}")
        except (OSError, ProtocolError, TimeoutError) as exc:
            log(f"peer {peer} closed: {exc}")
        finally:
            _release_all(user32, held, held_lock)
            pointer.on_leave()
            try:
                conn.close()
            except OSError:
                pass


def _serve_client(conn, cfg, user32, kernel32, pointer, held, held_lock, clip_seq, geometry) -> None:
    token = cfg["token"]
    send_lock = threading.Lock()

    def send(obj: dict) -> None:
        with send_lock:
            send_obj(conn, token, obj)

    hello = recv_obj(conn, token)
    if not hello or hello.get("t") != "hello" or hello.get("v") != 1:
        raise ProtocolError("expected hello")
    send({"t": "hello_ok", "v": 1, "name": "windows", **geometry})
    conn.settimeout(None)
    stop = threading.Event()
    writer = threading.Thread(
        target=_clipboard_loop,
        args=(send, user32, kernel32, clip_seq, stop),
        daemon=True,
    )
    writer.start()
    try:
        while True:
            msg = recv_obj(conn, token)
            if msg is None:
                break
            _handle(msg, send, user32, kernel32, pointer, held, held_lock, clip_seq)
    finally:
        stop.set()


def _handle(msg, send, user32, kernel32, pointer, held, held_lock, clip_seq) -> None:
    kind = msg.get("t")
    if kind == "ping":
        send({"t": "pong", "id": msg.get("id", 0)})
        return
    if kind == "pong":
        return
    if kind == "enter":
        _release_all(user32, held, held_lock)
        action = pointer.on_enter(float(msg.get("y_frac", 0.5)))
        _move(user32, pointer, action[1], action[2])
        log("mac took the pointer")
        return
    if kind == "leave":
        pointer.on_leave()
        _release_all(user32, held, held_lock)
        log("pointer returned to mac")
        return
    if kind == "mouse":
        actions = pointer.on_mouse(float(msg.get("dx", 0)), float(msg.get("dy", 0)))
        for action in actions:
            if action[0] == "move":
                _move(user32, pointer, action[1], action[2])
            elif action[0] == "leave":
                _release_all(user32, held, held_lock)
                send({"t": "leave", "y_frac": action[1]})
                log("pointer crossed back")
        return
    if kind == "button":
        if pointer.active:
            _button(user32, str(msg.get("button", "left")), bool(msg.get("down")))
        return
    if kind == "wheel":
        if pointer.active:
            _wheel(user32, int(msg.get("dy", 0)), int(msg.get("dx", 0)))
        return
    if kind == "key":
        if pointer.active or not msg.get("down", True):
            _key(user32, int(msg.get("vk", 0)), bool(msg.get("down")), held, held_lock)
        return
    if kind == "clipboard":
        text = str(msg.get("text", ""))
        if text != clip_seq["text"]:
            _write_clipboard(user32, kernel32, text)
            clip_seq["text"] = text
            clip_seq["n"] = _clipboard_sequence(user32)


def _clipboard_loop(send, user32, kernel32, clip_seq, stop: threading.Event) -> None:
    while not stop.wait(0.05):
        seq = _clipboard_sequence(user32)
        if seq == clip_seq["n"]:
            continue
        text = _read_clipboard(user32, kernel32)
        clip_seq["n"] = seq
        if text is None or text == clip_seq["text"]:
            continue
        if len(text) > 200_000:
            continue
        clip_seq["text"] = text
        try:
            send({"t": "clipboard", "text": text})
        except OSError:
            return


def _virtual_screen(user32) -> dict:
    left = int(user32.GetSystemMetrics(76))
    top = int(user32.GetSystemMetrics(77))
    width = int(user32.GetSystemMetrics(78))
    height = int(user32.GetSystemMetrics(79))
    if width <= 0 or height <= 0:
        width = int(user32.GetSystemMetrics(0))
        height = int(user32.GetSystemMetrics(1))
        left, top = 0, 0
    return {"left": left, "top": top, "width": width, "height": height}


def _move(user32, pointer: RemotePointer, x: int, y: int) -> None:
    width = pointer.width
    height = pointer.height
    abs_x = int(round((x - pointer.left) * 65535 / max(1, width - 1)))
    abs_y = int(round((y - pointer.top) * 65535 / max(1, height - 1)))
    _send_mouse(user32, abs_x, abs_y, 0, 0x0001 | 0x8000 | 0x4000)


def _button(user32, button: str, down: bool) -> None:
    flags = {
        ("left", True): 0x0002,
        ("left", False): 0x0004,
        ("right", True): 0x0008,
        ("right", False): 0x0010,
        ("middle", True): 0x0020,
        ("middle", False): 0x0040,
    }.get((button, down))
    if flags:
        _send_mouse(user32, 0, 0, 0, flags)


def _wheel(user32, dy_lines: int, dx_lines: int) -> None:
    if dy_lines:
        _send_mouse(user32, 0, 0, dy_lines * 120, 0x0800)
    if dx_lines:
        _send_mouse(user32, 0, 0, dx_lines * 120, 0x1000)


def _key(user32, vk: int, down: bool, held: dict[int, int], lock: threading.Lock) -> None:
    if vk <= 0 or vk > 0xFE:
        return
    with lock:
        count = held.get(vk, 0)
        if down:
            held[vk] = count + 1
            if count:
                return
        else:
            if count <= 1:
                held.pop(vk, None)
            else:
                held[vk] = count - 1
                return
    flags = 0 if down else 0x0002
    if vk in EXTENDED_VKS:
        flags |= 0x0001
    _send_key(user32, vk, flags)


def _release_all(user32, held: dict[int, int], lock: threading.Lock) -> None:
    with lock:
        vks = list(held)
        held.clear()
    for vk in vks:
        flags = 0x0002
        if vk in EXTENDED_VKS:
            flags |= 0x0001
        _send_key(user32, vk, flags)
    for flags in (0x0004, 0x0010, 0x0040):
        _send_mouse(user32, 0, 0, 0, flags)


def _send_mouse(user32, dx: int, dy: int, data: int, flags: int) -> None:
    extra = ctypes.c_ulong(0)
    inp = _INPUT()
    inp.type = 0
    inp.union.mi.dx = dx
    inp.union.mi.dy = dy
    inp.union.mi.mouseData = data
    inp.union.mi.dwFlags = flags
    inp.union.mi.time = 0
    inp.union.mi.dwExtraInfo = ctypes.pointer(extra)
    user32.SendInput(1, ctypes.byref(inp), ctypes.sizeof(inp))


def _send_key(user32, vk: int, flags: int) -> None:
    extra = ctypes.c_ulong(0)
    inp = _INPUT()
    inp.type = 1
    inp.union.ki.wVk = vk
    inp.union.ki.wScan = 0
    inp.union.ki.dwFlags = flags
    inp.union.ki.time = 0
    inp.union.ki.dwExtraInfo = ctypes.pointer(extra)
    user32.SendInput(1, ctypes.byref(inp), ctypes.sizeof(inp))


def _clipboard_sequence(user32) -> int:
    return int(user32.GetClipboardSequenceNumber())


def _read_clipboard(user32, kernel32) -> str | None:
    if not user32.OpenClipboard(None):
        return None
    try:
        handle = user32.GetClipboardData(13)
        if not handle:
            return ""
        ptr = kernel32.GlobalLock(handle)
        if not ptr:
            return ""
        try:
            return ctypes.wstring_at(ptr)
        finally:
            kernel32.GlobalUnlock(handle)
    finally:
        user32.CloseClipboard()


def _write_clipboard(user32, kernel32, text: str) -> None:
    data = (text + "\0").encode("utf-16-le")
    handle = kernel32.GlobalAlloc(0x0002, len(data))
    if not handle:
        return
    ptr = kernel32.GlobalLock(handle)
    if not ptr:
        return
    ctypes.memmove(ptr, data, len(data))
    kernel32.GlobalUnlock(handle)
    if not user32.OpenClipboard(None):
        return
    try:
        user32.EmptyClipboard()
        if not user32.SetClipboardData(13, handle):
            kernel32.GlobalFree(handle)
    finally:
        user32.CloseClipboard()


class _MOUSEINPUT(ctypes.Structure):
    _fields_ = (
        ("dx", wintypes.LONG),
        ("dy", wintypes.LONG),
        ("mouseData", wintypes.DWORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong)),
    )


class _KEYBDINPUT(ctypes.Structure):
    _fields_ = (
        ("wVk", wintypes.WORD),
        ("wScan", wintypes.WORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong)),
    )


class _HARDWAREINPUT(ctypes.Structure):
    _fields_ = (
        ("uMsg", wintypes.DWORD),
        ("wParamL", wintypes.WORD),
        ("wParamH", wintypes.WORD),
    )


class _INPUTUNION(ctypes.Union):
    _fields_ = (("mi", _MOUSEINPUT), ("ki", _KEYBDINPUT), ("hi", _HARDWAREINPUT))


class _INPUT(ctypes.Structure):
    _fields_ = (("type", wintypes.DWORD), ("union", _INPUTUNION))


def _win32():
    user32 = ctypes.WinDLL("user32", use_last_error=True)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    user32.SendInput.argtypes = (wintypes.UINT, ctypes.POINTER(_INPUT), ctypes.c_int)
    user32.SendInput.restype = wintypes.UINT
    return user32, kernel32


if __name__ == "__main__":
    main()
