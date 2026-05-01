# OpenClaw Stable Patrol Trigger

## Why this path

`@openclaw 巡视一下` is still handled by the default `main` agent first, so the model can reply with a status card instead of executing patrol.

The stable path is to use an OpenClaw Gateway text command that is handled before the model sees the message.

Official references:

- Feishu uses text commands rather than native slash menus: [Feishu docs](https://docs.openclaw.ai/channels/feishu)
- `/bash <command>` is handled by the Gateway and bypasses normal chat flow when enabled: [Slash commands docs](https://docs.openclaw.ai/zh-CN/tools/slash-commands)
- `/bash` requires `commands.bash: true` and `tools.elevated.allowFrom`: [Elevated mode docs](https://docs.openclaw.ai/tools/elevated)

## Stable trigger message

Send this exact message in the Feishu group:

```text
/bash ~/.local/bin/openclaw-patrol-now
```

## One-time board setup

1. Find your Feishu sender `open_id` (`ou_xxx`)
   - Send `/id` to the bot
   - Or run `openclaw logs --follow` and inspect the sender id

2. Run the install script on the RDK X5:

```bash
bash ~/rdk_x5_demo/scripts/install_openclaw_patrol_trigger.sh --sender-open-id ou_xxx
```

3. Restart OpenClaw:

```bash
openclaw gateway restart
```

## What the installed command does

`~/.local/bin/openclaw-patrol-now` calls:

```bash
bash ~/rdk_x5_demo/scripts/run_openclaw_group_patrol.sh
```

That wrapper triggers the existing patrol command bridge using the fixed ASCII command alias `patrol-now`, avoiding Chinese text encoding issues.
