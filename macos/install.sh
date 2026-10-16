#!/bin/sh
# Install the Mac agent so it starts at login and restarts if it exits.
set -eu
ROOT="$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)"
PYTHON="${ROOT}/.venv/bin/python"
PLIST="${HOME}/Library/LaunchAgents/com.homesynergy.agent.plist"
LOG_DIR="${HOME}/Library/Logs"
UID_NUM="$(id -u)"

python3 -m venv "${ROOT}/.venv"
"${PYTHON}" -m pip install --upgrade pip
"${PYTHON}" -m pip install -r "${ROOT}/requirements.txt"
"${PYTHON}" -m homesynergy.config
mkdir -p "${LOG_DIR}" "${HOME}/Library/LaunchAgents"

cat > "${PLIST}" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>com.homesynergy.agent</string>
  <key>ProgramArguments</key>
  <array>
    <string>${PYTHON}</string>
    <string>-m</string>
    <string>homesynergy.mac_agent</string>
  </array>
  <key>WorkingDirectory</key>
  <string>${ROOT}</string>
  <key>EnvironmentVariables</key>
  <dict>
    <key>PYTHONUNBUFFERED</key>
    <string>1</string>
  </dict>
  <key>RunAtLoad</key>
  <true/>
  <key>KeepAlive</key>
  <true/>
  <key>ThrottleInterval</key>
  <integer>5</integer>
  <key>StandardOutPath</key>
  <string>${LOG_DIR}/homesynergy.log</string>
  <key>StandardErrorPath</key>
  <string>${LOG_DIR}/homesynergy.log</string>
</dict>
</plist>
EOF

launchctl bootout "gui/${UID_NUM}" "${PLIST}" 2>/dev/null || true
sleep 1
launchctl bootstrap "gui/${UID_NUM}" "${PLIST}"
launchctl enable "gui/${UID_NUM}/com.homesynergy.agent"
launchctl kickstart -k "gui/${UID_NUM}/com.homesynergy.agent"
printf '%s\n' "Installed. Config: ${HOME}/.homesynergy/config.json"
printf '%s\n' "Copy that file to the Windows profile as %USERPROFILE%/.homesynergy/config.json"
printf '%s\n' "Then grant Accessibility to: ${PYTHON}"
