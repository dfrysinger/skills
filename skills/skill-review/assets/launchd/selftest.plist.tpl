<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>__LABEL__</string>
  <key>ProgramArguments</key>
  <array>
    <string>/bin/bash</string>
    <string>__REPO__/skills/skill-review/scripts/daemon-selftest.sh</string>
  </array>
  <key>RunAtLoad</key>
  <false/>
  <key>StandardOutPath</key>
  <string>__HOME__/.copilot/skill-state/daemon-logs/launchd-selftest.out</string>
  <key>StandardErrorPath</key>
  <string>__HOME__/.copilot/skill-state/daemon-logs/launchd-selftest.err</string>
  <key>EnvironmentVariables</key>
  <dict>
    <key>HOME</key><string>__HOME__</string>
    <key>PATH</key><string>__HOME__/.local/bin:/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin</string>
  </dict>
  <key>ProcessType</key>
  <string>Background</string>
</dict>
</plist>
