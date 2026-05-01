#!/usr/bin/env bash
set -eo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WORKSPACE_DIR="${SMART_CARE_HOME:-$(cd "${SCRIPT_DIR}/.." && pwd)}"
ENV_FILE="${SMART_CARE_ENV_FILE:-${HOME}/.smart_care.env}"

if [[ ! -f "${ENV_FILE}" ]]; then
  echo "missing env file: ${ENV_FILE}" >&2
  exit 1
fi

if [[ ! -f "${WORKSPACE_DIR}/ros2_ws/install/setup.bash" ]]; then
  echo "missing ROS2 install setup: ${WORKSPACE_DIR}/ros2_ws/install/setup.bash" >&2
  echo "run: cd ${WORKSPACE_DIR}/ros2_ws && source /opt/tros/humble/setup.bash && colcon build" >&2
  exit 1
fi

set +u
source "${ENV_FILE}"
source /opt/tros/humble/setup.bash
source "${WORKSPACE_DIR}/ros2_ws/install/setup.bash"
set -u

ros2 run smart_care_bridge evidence_file_server
