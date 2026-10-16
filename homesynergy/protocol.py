"""Length-prefixed JSON frames with an HMAC so LAN peers must know the token."""

from __future__ import annotations

import hashlib
import hmac
import json
import socket
import struct

MAX_FRAME = 1_048_576
DEFAULT_PORT = 24864


class ProtocolError(Exception):
    pass


class AuthError(ProtocolError):
    pass


def _mac(token: str, payload: bytes) -> bytes:
    return hmac.new(token.encode("utf-8"), payload, hashlib.sha256).digest()


def encode_frame(token: str, obj: dict) -> bytes:
    if not token:
        raise ProtocolError("empty token")
    payload = json.dumps(obj, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    if len(payload) > MAX_FRAME:
        raise ProtocolError("frame too large")
    return struct.pack(">I", len(payload)) + payload + _mac(token, payload)


def decode_frame(token: str, payload: bytes, mac: bytes) -> dict:
    expected = _mac(token, payload)
    if not hmac.compare_digest(expected, mac):
        raise AuthError("bad frame mac")
    try:
        obj = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ProtocolError("bad json") from exc
    if not isinstance(obj, dict) or "t" not in obj:
        raise ProtocolError("missing type")
    return obj


def _recvall(sock: socket.socket, n: int) -> bytes | None:
    buf = bytearray()
    while len(buf) < n:
        chunk = sock.recv(n - len(buf))
        if not chunk:
            return None
        buf += chunk
    return bytes(buf)


def send_obj(sock: socket.socket, token: str, obj: dict) -> None:
    sock.sendall(encode_frame(token, obj))


def recv_obj(sock: socket.socket, token: str) -> dict | None:
    header = _recvall(sock, 4)
    if header is None:
        return None
    (length,) = struct.unpack(">I", header)
    if length <= 0 or length > MAX_FRAME:
        raise ProtocolError(f"bad length {length}")
    payload = _recvall(sock, length)
    mac = _recvall(sock, 32)
    if payload is None or mac is None:
        return None
    return decode_frame(token, payload, mac)
