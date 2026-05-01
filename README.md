#  智能看护系统简介

## 图片演示
<img width="801" height="774" alt="1777646402781" src="https://github.com/user-attachments/assets/af9ed747-fb7f-4c23-80c2-8c4720132872" />

<img width="801" height="774" alt="Snipaste_2026-05-01_22-38-06" src="https://github.com/user-attachments/assets/af6e0b61-28ea-4058-a864-580083785c93" />

<img width="801" height="774" alt="1777646151180" src="https://github.com/user-attachments/assets/6ebe7b03-bb0d-4fc4-83e8-8fa07f2bc5f5" />

这个目录提供了一套面向最终成品方向的工程骨架，用于完成以下链路：

`EMEET C960 -> RDK X5 人体候选检测 -> 本地截图/短视频/关键帧留证 -> R9000P 上的 Ollama + MiniCPM-V 行为复核 -> 飞书分级通知`

这一版的核心思想是：

- 候选事件一出现就立即留证
- `MiniCPM-V` 不参与实时人体检测
- `MiniCPM-V` 只负责对已留证事件做行为复核
- 只有 `warning / alarm` 结果才发飞书
- `OpenClaw` 继续留在后续摘要和问答阶段，不进入实时主链路

当前项目的阶段盘点与能力对照表见：

- [PROJECT_STATUS.md](/Users/zhou/Documents/Codex/2026-04-26-files-mentioned-by-the-user-ai-2/rdk_x5_demo/PROJECT_STATUS.md)
- [RDK_X5_HARDWARE_BRINGUP_CHECKLIST.md](/Users/zhou/Documents/Codex/2026-04-26-files-mentioned-by-the-user-ai-2/rdk_x5_demo/RDK_X5_HARDWARE_BRINGUP_CHECKLIST.md)

## 目录结构

```text
rdk_x5_demo/
  .smart_care.env.example
  README.md
  notebook_vlm_service/
    .env.example
    README.md
    ollama_review_service.py
    run_vlm_review_service.sh
  scripts/
    check_camera.sh
    run_body_detection.sh
    run_bridge.sh
    run_evidence_file_server.sh
    run_patrol_gateway.sh
    run_patrol_once.sh
    run_daily_report_once.sh
    run_record_buffer.sh
  ros2_ws/
    src/
      smart_care_bridge/
```

## 1. 拷贝到 RDK X5

将整个目录复制到开发板，例如：

```bash
mkdir -p ~/smart-care-demo
cp -r rdk_x5_demo/* ~/smart-care-demo/
cd ~/smart-care-demo
```

## 2. 准备板端环境

如未安装常用工具，先安装：

```bash
sudo apt update
sudo apt install -y v4l-utils ffmpeg curl
```

如未安装官方人体检测包，执行：

```bash
source /opt/tros/humble/setup.bash
ros2 pkg list | grep mono2d_body_detection || sudo apt install -y tros-humble-mono2d-body-detection
```

创建板端环境变量文件：

```bash
cp .smart_care.env.example ~/.smart_care.env
vim ~/.smart_care.env
```

至少要填写：

- `FEISHU_WEBHOOK_URL`
- `VLM_SERVER_URL`
- `EVIDENCE_PUBLIC_BASE_URL`
- `DETECTOR_MODE=rdk_x5_ros2_image`
- 其他阈值和路径按需修改

为了让飞书中的视频链接更容易被浏览器和群内预览直接播放，留证视频默认会编码为浏览器友好的 H.264 MP4。相关参数：

- `EVIDENCE_VIDEO_CODEC`
- `EVIDENCE_VIDEO_PRESET`
- `EVIDENCE_VIDEO_CRF`

为了进一步缓解飞书和浏览器的媒体兼容性问题，`warning / alarm` 告警还会从留证视频中额外生成一个 GIF 预览，并在飞书消息里优先发送 `GIF URL`。相关参数：

- `EVIDENCE_GIF_DIR`
- `EVIDENCE_GIF_FPS`
- `EVIDENCE_GIF_WIDTH`
- `EVIDENCE_GIF_SECONDS`

如果你希望 `warning / alarm` 告警在飞书里附带可访问的视频证据，需要同时：

- 在 `~/.smart_care.env` 中设置 `EVIDENCE_PUBLIC_BASE_URL`
- 在板端运行 `bash scripts/run_evidence_file_server.sh`

例如：

```bash
export EVIDENCE_PUBLIC_BASE_URL="http://RDK_X5_IP:8080/evidence"
```

当前默认检测模式已经切到 `rdk_x5_ros2_image`。这会在每次巡视时临时拉起官方
`mono2d_body_detection`，对刚抓到的图片做一次单图人体检测；如果你要回退到自定义检测脚本，
再把 `DETECTOR_MODE` 改成 `json_command` 并填写 `DETECTOR_COMMAND`。

## 3. 相机验机

执行：

```bash
bash scripts/check_camera.sh
```

预期结果：

- 存在 `/dev/video0`
- `v4l2-ctl` 能看到 `MJPEG`
- 如果系统有 `ffmpeg`，能够抓出 `test.jpg`

## 4. 构建板端 ROS2 包

```bash
cd ~/smart-care-demo/ros2_ws
source /opt/tros/humble/setup.bash
colcon build
source install/setup.bash
```

## 5. 启动官方人体检测

终端 A：

```bash
cd ~/smart-care-demo
bash scripts/run_body_detection.sh
```

该脚本内部会执行：

```bash
source /opt/tros/humble/setup.bash
export CAM_TYPE=usb
ros2 launch mono2d_body_detection mono2d_body_detection.launch.py
```

在同一局域网的电脑浏览器打开：

```text
http://RDK_X5_IP:8000
```

## 6. 启动本地缓冲录制服务

终端 B：

```bash
cd ~/smart-care-demo
bash scripts/run_record_buffer.sh
```

这个服务会：

- 常驻读取 `/dev/video0`
- 按分片方式缓存最近几秒视频
- 候选事件触发后导出截图、短视频和关键帧组

## 7. 启动笔记本端 MiniCPM-V 语义服务

在 `R9000P` 上：

```bash
cd notebook_vlm_service
cp .env.example .env
vim .env
bash run_vlm_review_service.sh
```

这个服务会：

- 接收板端上传的关键帧组
- 调用 `Ollama` 上的 `MiniCPM-V`
- 返回结构化行为判断结果

默认监听：

```text
http://0.0.0.0:9000/analyze
```

## 8. 启动桥接节点

终端 C：

```bash
cd ~/smart-care-demo
bash scripts/run_bridge.sh
```

这个脚本会加载：

- `~/.smart_care.env`
- `/opt/tros/humble/setup.bash`
- `~/smart-care-demo/ros2_ws/install/setup.bash`

随后执行：

```bash
ros2 run smart_care_bridge person_event_bridge
```

## 9. 端到端验证

1. 人进入画面
2. 官方人体检测输出候选目标
3. 桥接节点完成连续帧确认
4. 本地录制服务导出截图、短视频和关键帧
5. `RDK X5` 调用笔记本端 `MiniCPM-V`
6. 如果结果是 `normal`，只记录日志
7. 如果结果是 `warning / alarm`，飞书发送分级通知

## 10. 重要文件

- `ros2_ws/src/smart_care_bridge/smart_care_bridge/bridge_core.py`
  - 人体候选事件的确认与冷却逻辑
- `ros2_ws/src/smart_care_bridge/smart_care_bridge/person_event_bridge.py`
  - ROS2 桥接节点、留证编排、VLM 调用与通知决策
- `ros2_ws/src/smart_care_bridge/smart_care_bridge/record_buffer_service.py`
  - 本地分片缓冲、截图导出、短视频合并、关键帧抽取
- `ros2_ws/src/smart_care_bridge/smart_care_bridge/vlm_review_client.py`
  - 板端对笔记本语义服务的 HTTP 客户端
- `ros2_ws/src/smart_care_bridge/smart_care_bridge/review_policy.py`
  - 行为复核结果标准化与告警策略
- `notebook_vlm_service/ollama_review_service.py`
  - 笔记本端 `Ollama + MiniCPM-V` HTTP 服务

## 11. 本地日志与证据目录

默认日志路径：

```text
~/smart-care-demo/logs/person_events.jsonl
```

每条事件日志至少包含：

- `timestamp`
- `event_type`
- `confidence`
- `bbox`
- `image_path`
- `video_path`
- `frame_paths`
- `activity_label`
- `risk_level`
- `vlm_confidence`
- `vlm_description`
- `feishu_status`

默认证据目录：

```text
~/smart-care-demo/evidence/images
~/smart-care-demo/evidence/videos
~/smart-care-demo/evidence/frames
~/smart-care-demo/tmp/segments
```

## 12. 注意事项

- 这是“行为复核版”，不是多传感器融合终版。
- `MiniCPM-V` 不负责发现“有人”，只负责判断“人在做什么”。
- 关键帧通过局域网发给笔记本，而不是直接把整段视频喂给 `Ollama`。
- 如果 `MiniCPM-V` 服务掉线、超时或返回非法结果，系统会按 `warning` 降级提醒，而不会静默丢弃事件。
- 当前飞书仍然是文本通知，不上传图片或视频附件。
- `OpenClaw` 仍不在实时主链路中，后续可基于日志做摘要、问答和日报。
