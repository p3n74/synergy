#!/bin/sh
# Double-click in Finder. Starts the login agent, or installs it the first time.
cd "$(dirname "$0")" || exit 1
UID_NUM="$(id -u)"
LABEL="gui/${UID_NUM}/com.homesynergy.agent"
PLIST="${HOME}/Library/LaunchAgents/com.homesynergy.agent.plist"

if [ ! -f "${PLIST}" ]; then
  ./macos/install.sh
else
  launchctl kickstart -k "${LABEL}"
fi

printf '\n%s\n' "HomeSynergy log:"
touch "${HOME}/Library/Logs/homesynergy.log"
tail -n 20 "${HOME}/Library/Logs/homesynergy.log"
printf '\n%s\n' "Leave this window open if you want to watch the log. Closing it does not stop the agent."
printf '%s\n' "Press Return to close."
read -r _
