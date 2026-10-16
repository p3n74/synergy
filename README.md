# HomeSynergy

Use the Mac keyboard, trackpad, and clipboard on the Windows PC at `172.20.20.241`. Traffic stays on the local network. There is no account, relay, or cloud service.

The Mac is the computer you type on. The Windows PC stays logged in. When you open the laptop, the Mac agent starts, connects, and waits. Push the pointer off the right edge of the Mac display and it continues on the Windows desktop. Push back through the left edge and you are on the Mac again. Copied text follows you.

## What the installed share app is doing

Synergy is not installed on this Mac. ShareMouse is, and it is the same kind of tool. REA traced the app without running it:

- The main binary links CoreGraphics, Carbon, CFNetwork, SystemConfiguration, IOKit, and Security. That is an event tap, TCP, reachability, wake, and a local secret.
- A login-item helper (`sminst`) and a launch agent start it with the session. The bundle’s agent plist is limited to the login window.
- Strings in the binary name the behaviors we kept: `procScreenEdges`, `Start clipboard watcher`, `handleDidWakeEvent`, `launchAtLogin`, a TCP socket, and a UDP presence channel.
- REA could not decompile the binary. Hopper and Ghidra are not installed, so this is a new protocol, not a clone of ShareMouse’s.

HomeSynergy uses one authenticated TCP connection to the address you configured. It does not install a login-window plugin and it does not change `authorizationdb`.

## Layout

Windows sits to the right of the Mac. `command` is sent as Ctrl, so Command-C copies on Windows. Control-Option-Right jumps over even if you are not on the edge. Control-Option-Left comes back.

## Mac

```sh
./macos/install.sh
```

That creates `~/.homesynergy/config.json`, installs a login agent, and starts it. The first time, macOS will block the event tap until you allow this binary:

`System Settings → Privacy & Security → Accessibility`

Enable the Python listed at the end of the installer. Then:

```sh
launchctl kickstart -k gui/$(id -u)/com.homesynergy.agent
```

Quit ShareMouse while you use this. Both apps grab the same event tap.

Log: `~/Library/Logs/homesynergy.log`

## Windows

The Windows desktop has to be logged in. Input injection from a session-0 service never reaches the screen, so this is a logon task, not a service.

1. Install Python 3.
2. Copy `~/.homesynergy/config.json` from the Mac to `%USERPROFILE%\.homesynergy\config.json`.
3. Copy this repo to the PC.
4. In an elevated PowerShell window, from the repo:

```powershell
.\windows\install-startup.ps1
```

The firewall rule allows TCP `24864` on the Private profile only. The agent also drops any peer that is not a private, link-local, or loopback address. Frames are HMAC-SHA256 with the shared token, so a neighbor who can see the port still cannot inject input without that file.

From the Mac, after Windows is listening:

```sh
.venv/bin/python -m homesynergy.mac_agent --check
```

## Checks

```sh
python3 -m unittest discover -s tests
```
