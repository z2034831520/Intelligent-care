# OpenClaw Patrol Session Bridge

## Why this exists

The GUI-packaged OpenClaw build on the RDK X5 receives Feishu group messages and replies with the default `main` agent, but it does not reliably execute text `/bash` commands in Feishu.

The stable workaround is a local sidecar service:

1. OpenClaw still receives the group message
2. The sidecar watches OpenClaw session JSONL files
3. When it sees a user message in the target group with a patrol trigger, it starts the existing patrol command bridge

This avoids patching the bundled OpenClaw internals.

## Supported trigger messages

The sidecar reacts to either of these:

- `@openclaw 巡视一下`
- `@openclaw patrol-now`

`patrol-now` is the more reliable trigger because it avoids Chinese encoding edge cases.

## One-time board setup

1. Sync the new files and rebuild ROS2:

```bash
cd ~/rdk_x5_demo/ros2_ws
set +u
source /opt/tros/humble/setup.bash
colcon build
source install/setup.bash
```

2. Install the user service:

```bash
bash ~/rdk_x5_demo/scripts/install_openclaw_patrol_session_bridge_service.sh
```

3. Verify service status:

```bash
systemctl --user status openclaw-patrol-session-bridge.service
tail -f ~/rdk_x5_demo/logs/openclaw_patrol_session_bridge.log
```

## Runtime behavior

When the sidecar detects a patrol trigger in the OpenClaw main session logs, it runs:

```bash
bash ~/rdk_x5_demo/scripts/run_openclaw_group_patrol.sh
```

That command sends:

1. `已开始巡视，请稍候`
2. patrol result text
3. GIF image

## Known tradeoff

The default `main` agent may still send its own conversational reply or status card, because this solution does not replace the GUI build's internal chat routing. It only guarantees that the patrol action will fire reliably.
