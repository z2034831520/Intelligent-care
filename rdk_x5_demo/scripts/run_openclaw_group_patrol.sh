#!/usr/bin/env bash
set -eo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WORKSPACE_DIR="${SMART_CARE_HOME:-$(cd "${SCRIPT_DIR}/.." && pwd)}"

exec bash "${WORKSPACE_DIR}/scripts/run_openclaw_patrol_command.sh" \
  --chat-id "oc_8d557d445f504afc2291ca5a9fedc0c9" \
  --text "patrol-now"
