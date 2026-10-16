"""Shared config. The token never travels on the wire; both machines read this file."""

from __future__ import annotations

import json
import os
import secrets
from pathlib import Path

DEFAULT_PATH = Path.home() / ".homesynergy" / "config.json"


def config_path() -> Path:
    env = os.environ.get("HOMESYNERGY_CONFIG")
    if env:
        return Path(env)
    if DEFAULT_PATH.exists():
        return DEFAULT_PATH
    local = Path.cwd() / "config.json"
    if local.exists():
        return local
    return DEFAULT_PATH


def load_config() -> dict:
    path = config_path()
    if not path.exists():
        raise SystemExit(
            f"Missing {path}. On the Mac run: python -m homesynergy.config "
            "and copy that file to the Windows machine."
        )
    with path.open() as fh:
        cfg = json.load(fh)
    token = str(cfg.get("token", ""))
    if len(token) < 16:
        raise SystemExit(f"{path} token is missing or too short")
    cfg.setdefault("windows_host", "172.20.20.241")
    cfg.setdefault("bind", "0.0.0.0")
    cfg.setdefault("port", 24864)
    cfg.setdefault("edge", "right")
    cfg.setdefault("edge_px", 3)
    cfg.setdefault("speed", 1.0)
    cfg.setdefault("command_is_control", True)
    return cfg


def write_default(host: str = "172.20.20.241") -> Path:
    DEFAULT_PATH.parent.mkdir(parents=True, exist_ok=True)
    if DEFAULT_PATH.exists():
        return DEFAULT_PATH
    cfg = {
        "windows_host": host,
        "bind": "0.0.0.0",
        "port": 24864,
        "token": secrets.token_hex(32),
        "edge": "right",
        "edge_px": 3,
        "speed": 1.0,
        "command_is_control": True,
    }
    DEFAULT_PATH.write_text(json.dumps(cfg, indent=2) + "\n")
    os.chmod(DEFAULT_PATH, 0o600)
    return DEFAULT_PATH


def main() -> None:
    path = write_default()
    print(path)


if __name__ == "__main__":
    main()
