# Startup Scripts

## 上位机

目录：

`rdk_x5_demo/notebook_vlm_service`

### 一键启动全部

```powershell
cd C:\Users\zhou\Documents\Codex\2026-04-26-files-mentioned-by-the-user-ai-2\rdk_x5_demo\notebook_vlm_service
powershell -ExecutionPolicy Bypass -File .\start_notebook_stack.ps1
```

会分别拉起：

1. `run_vlm_review_service.cmd`
2. `run_feishu_command_bridge.cmd`
3. `run_cloudflared_tunnel.ps1`

### 单独启动

```bat
run_vlm_review_service.cmd
run_feishu_command_bridge.cmd
```

```powershell
powershell -ExecutionPolicy Bypass -File .\run_cloudflared_tunnel.ps1
```

## 开发板

目录：

`~/rdk_x5_demo/scripts`

### 一键启动自动巡航相关服务

```bash
bash ~/rdk_x5_demo/scripts/start_board_stack.sh
```

会：

1. 检查并补 `~/rdk_x5_demo/config`
2. 启动 `evidence_file_server`
3. 启动 `patrol_gateway`

### 查看状态

```bash
bash ~/rdk_x5_demo/scripts/status_board_stack.sh
```

## 备注

- 上位机 `cloudflared` 使用临时域名时，每次重启 tunnel 地址都可能变化，需要同步更新飞书事件回调地址。
- 上位机 `ollama_review_service.py` 现在会自动读取同目录下的 `.env`。
- 开发板 `start_board_stack.sh` 不负责启动 OpenClaw，也不负责启动命令机器人，它只负责自动巡航本身。
