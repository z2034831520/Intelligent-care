#!/usr/bin/env bash
set -euo pipefail

DEVICE="${1:-/dev/video0}"

echo "== lsusb =="
lsusb || true
echo

echo "== v4l2 devices =="
v4l2-ctl --list-devices
echo

echo "== video nodes =="
ls -l /dev/video* || true
echo

echo "== dmesg tail =="
dmesg | tail -n 50 || true
echo

echo "== formats for ${DEVICE} =="
v4l2-ctl -d "${DEVICE}" --list-formats-ext
echo

if command -v ffmpeg >/dev/null 2>&1; then
  echo "== capture single frame =="
  ffmpeg -y -f v4l2 -input_format mjpeg -video_size 1920x1080 -i "${DEVICE}" -frames:v 1 test.jpg
  ls -lh test.jpg
else
  echo "ffmpeg not installed; skip frame capture"
fi
