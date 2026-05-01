#!/usr/bin/env bash
set -eo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WORKSPACE_DIR="${SMART_CARE_HOME:-$(cd "${SCRIPT_DIR}/.." && pwd)}"

set +u
source /opt/tros/humble/setup.bash
set -u

cd "${WORKSPACE_DIR}"

if [[ ! -d "${WORKSPACE_DIR}/config" ]]; then
  cp -r /opt/tros/${TROS_DISTRO}/lib/mono2d_body_detection/config/ "${WORKSPACE_DIR}/"
fi

export CAM_TYPE=usb
ros2 launch mono2d_body_detection mono2d_body_detection.launch.py
