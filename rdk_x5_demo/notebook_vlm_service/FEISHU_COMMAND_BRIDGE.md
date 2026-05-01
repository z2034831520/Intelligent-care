# Feishu Command Bridge

这个服务运行在上位机，接收飞书自建应用的事件订阅回调，然后通过 SSH 触发开发板上的巡视命令。

## 作用

- 接收群消息事件
- 只处理目标群里的固定命令
- 通过 SSH 执行开发板上的：
  - `bash ~/.local/bin/openclaw-patrol-now`

巡视结果仍然由开发板现有后端发送：

- `已开始巡视，请稍候`
- 巡视结果文本
- GIF 图片

## 前提

1. 新的飞书自建应用已经加入目标群
2. 该应用开通了：
   - `im.message.receive_v1` 事件订阅
3. 飞书回调可以访问到这台上位机的 HTTPS 地址
4. 上位机可以无交互 SSH 登录开发板

## 需要配置的环境变量

编辑 `notebook_vlm_service/.env`，至少补齐：

```bash
export FEISHU_COMMAND_BRIDGE_HOST="0.0.0.0"
export FEISHU_COMMAND_BRIDGE_PORT="19100"
export FEISHU_COMMAND_VERIFICATION_TOKEN="飞书事件订阅里的 Verification Token"
export FEISHU_COMMAND_TARGET_CHAT_ID="oc_8d557d445f504afc2291ca5a9fedc0c9"
export FEISHU_COMMAND_BOT_OPEN_ID="命令机器人自己的 open_id"
export FEISHU_COMMAND_TRIGGER_TEXTS="patrol-now,巡视一下"

export PATROL_SSH_USER="sunrise"
export PATROL_SSH_HOST="172.30.148.147"
export PATROL_REMOTE_COMMAND="bash ~/.local/bin/openclaw-patrol-now"
export PATROL_SSH_OPTIONS="-o BatchMode=yes -o ConnectTimeout=10"
```

如果你用私钥登录开发板，再补：

```bash
export PATROL_SSH_IDENTITY_FILE="C:/Users/zhou/.ssh/id_ed25519"
```

## 启动

Windows:

```bat
cd C:\Users\zhou\Documents\Codex\2026-04-26-files-mentioned-by-the-user-ai-2\rdk_x5_demo\notebook_vlm_service
run_feishu_command_bridge.cmd
```

或者：

```bat
python feishu_command_bridge.py
```

## 健康检查

```bat
curl.exe http://127.0.0.1:19100/health
```

预期：

```json
{"status":"ok"}
```

## 飞书回调地址

建议把回调路径配成：

```text
https://你的公网域名/feishu/events
```

服务同时接受：

- `/`
- `/events`
- `/feishu/events`

## 触发词

群里推荐发送：

```text
@命令机器人 patrol-now
```

也兼容：

```text
@命令机器人 巡视一下
```

## 日志

默认日志文件：

```text
notebook_vlm_service/feishu_command_bridge.log
```
