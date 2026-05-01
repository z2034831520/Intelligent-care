#!/usr/bin/env bash
set -euo pipefail

echo "evidence server:"
pgrep -af "smart_care_bridge evidence_file_server" || true
echo
echo "patrol gateway:"
pgrep -af "smart_care_bridge patrol_gateway" || true
echo
echo "health:"
curl -s http://127.0.0.1:8080/health || true

