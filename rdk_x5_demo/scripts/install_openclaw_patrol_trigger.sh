#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WORKSPACE_DIR="${SMART_CARE_HOME:-$(cd "${SCRIPT_DIR}/.." && pwd)}"
OPENCLAW_CONFIG="${OPENCLAW_CONFIG_PATH:-${HOME}/.openclaw/openclaw.json}"
LOCAL_BIN_DIR="${HOME}/.local/bin"
COMMAND_PATH="${LOCAL_BIN_DIR}/openclaw-patrol-now"
SENDER_OPEN_ID=""

usage() {
  cat <<'EOF'
Usage:
  install_openclaw_patrol_trigger.sh --sender-open-id ou_xxx

What it does:
  1. Installs ~/.local/bin/openclaw-patrol-now
  2. Enables OpenClaw text /bash commands
  3. Enables elevated exec and allowlists the specified Feishu sender open_id

After install:
  1. Restart the OpenClaw gateway
  2. In the Feishu group, send:
     /bash ~/.local/bin/openclaw-patrol-now
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --sender-open-id)
      SENDER_OPEN_ID="${2:-}"
      shift 2
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "unknown argument: $1" >&2
      usage >&2
      exit 1
      ;;
  esac
done

if [[ -z "${SENDER_OPEN_ID}" ]]; then
  echo "missing required --sender-open-id" >&2
  usage >&2
  exit 1
fi

if [[ ! -f "${WORKSPACE_DIR}/scripts/run_openclaw_group_patrol.sh" ]]; then
  echo "missing patrol wrapper: ${WORKSPACE_DIR}/scripts/run_openclaw_group_patrol.sh" >&2
  exit 1
fi

if [[ ! -f "${OPENCLAW_CONFIG}" ]]; then
  echo "missing OpenClaw config: ${OPENCLAW_CONFIG}" >&2
  exit 1
fi

mkdir -p "${LOCAL_BIN_DIR}"

cat > "${COMMAND_PATH}" <<EOF
#!/usr/bin/env bash
set -euo pipefail
exec bash "${WORKSPACE_DIR}/scripts/run_openclaw_group_patrol.sh"
EOF
chmod +x "${COMMAND_PATH}"

python3 - "${OPENCLAW_CONFIG}" "${SENDER_OPEN_ID}" <<'PY'
import json
import shutil
import sys
from pathlib import Path

config_path = Path(sys.argv[1])
sender_open_id = sys.argv[2]

raw = config_path.read_text(encoding="utf-8")
data = json.loads(raw)

backup_path = config_path.with_suffix(config_path.suffix + ".bak_patrol")
shutil.copy2(config_path, backup_path)

commands = data.setdefault("commands", {})
commands["text"] = True
commands["bash"] = True
commands["bashForegroundMs"] = 0

tools = data.setdefault("tools", {})
elevated = tools.setdefault("elevated", {})
elevated["enabled"] = True
allow_from = elevated.setdefault("allowFrom", {})
feishu_allow = allow_from.setdefault("feishu", [])
if sender_open_id not in feishu_allow:
    feishu_allow.append(sender_open_id)

config_path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

print(f"updated config: {config_path}")
print(f"backup saved: {backup_path}")
print(f"feishu elevated allowlist: {feishu_allow}")
PY

cat <<EOF

Installed patrol trigger command:
  ${COMMAND_PATH}

Next steps:
  1. Restart OpenClaw:
     openclaw gateway restart
  2. In Feishu, send this exact message:
     /bash ~/.local/bin/openclaw-patrol-now
EOF
