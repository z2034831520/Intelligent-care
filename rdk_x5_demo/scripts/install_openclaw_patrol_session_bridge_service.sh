#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WORKSPACE_DIR="${SMART_CARE_HOME:-$(cd "${SCRIPT_DIR}/.." && pwd)}"
SERVICE_DIR="${HOME}/.config/systemd/user"
SERVICE_FILE="${SERVICE_DIR}/openclaw-patrol-session-bridge.service"

mkdir -p "${SERVICE_DIR}"

cat > "${SERVICE_FILE}" <<EOF
[Unit]
Description=OpenClaw patrol session bridge
After=network-online.target

[Service]
Type=simple
ExecStart=/usr/bin/env bash ${WORKSPACE_DIR}/scripts/run_openclaw_patrol_session_bridge.sh
Restart=always
RestartSec=3
WorkingDirectory=${WORKSPACE_DIR}

[Install]
WantedBy=default.target
EOF

systemctl --user daemon-reload
systemctl --user enable openclaw-patrol-session-bridge.service
systemctl --user restart openclaw-patrol-session-bridge.service

cat <<EOF
Installed and started:
  ${SERVICE_FILE}

Check status:
  systemctl --user status openclaw-patrol-session-bridge.service
  tail -f ~/rdk_x5_demo/logs/openclaw_patrol_session_bridge.log
EOF
