#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WORKSPACE_DIR="${SMART_CARE_HOME:-$(cd "${SCRIPT_DIR}/.." && pwd)}"
ENV_FILE="${SMART_CARE_ENV_FILE:-${HOME}/.smart_care.env}"
LOG_DIR="${WORKSPACE_DIR}/logs"
EVIDENCE_LOG="${LOG_DIR}/evidence_file_server.log"
PATROL_LOG="${LOG_DIR}/patrol_gateway.log"
EVIDENCE_PID_FILE="${LOG_DIR}/evidence_file_server.pid"
PATROL_PID_FILE="${LOG_DIR}/patrol_gateway.pid"

mkdir -p "${LOG_DIR}" \
  "${WORKSPACE_DIR}/tmp/segments" \
  "${WORKSPACE_DIR}/evidence/images" \
  "${WORKSPACE_DIR}/evidence/videos" \
  "${WORKSPACE_DIR}/evidence/gifs" \
  "${WORKSPACE_DIR}/evidence/frames"

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
source /opt/tros/humble/setup.bash
if [[ ! -d "${WORKSPACE_DIR}/config" ]]; then
  cp -r "/opt/tros/${TROS_DISTRO}/lib/mono2d_body_detection/config/" "${WORKSPACE_DIR}/"
fi
set -u

start_if_missing() {
  local name="$1"
  local pattern="$2"
  local pid_file="$3"
  local log_file="$4"
  shift 4

  if pgrep -f "${pattern}" >/dev/null 2>&1; then
    echo "${name} already running"
    return
  fi

  nohup "$@" >"${log_file}" 2>&1 &
  local pid=$!
  echo "${pid}" >"${pid_file}"
  echo "started ${name} pid=${pid}"
}

start_if_missing \
  "evidence_file_server" \
  "smart_care_bridge evidence_file_server" \
  "${EVIDENCE_PID_FILE}" \
  "${EVIDENCE_LOG}" \
  bash "${WORKSPACE_DIR}/scripts/run_evidence_file_server.sh"

start_if_missing \
  "patrol_gateway" \
  "smart_care_bridge patrol_gateway" \
  "${PATROL_PID_FILE}" \
  "${PATROL_LOG}" \
  bash "${WORKSPACE_DIR}/scripts/run_patrol_gateway.sh"

echo "board stack startup complete"
echo "logs:"
echo "  ${EVIDENCE_LOG}"
echo "  ${PATROL_LOG}"

