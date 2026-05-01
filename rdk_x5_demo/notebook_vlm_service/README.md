# MiniCPM-V 行为复核服务

这个目录是笔记本侧的本地语义服务骨架，用于：

- 接收 `RDK X5` 发来的关键帧组
- 调用 `Ollama` 上的 `MiniCPM-V`
- 返回结构化行为判断结果

## 准备

1. 确保笔记本已安装并启动 `Ollama`
2. 确保 `MiniCPM-V` 模型可用
3. 复制环境变量文件：

```bash
cp .env.example .env
```

4. 修改以下变量：

- `OLLAMA_BASE_URL`
- `OLLAMA_MODEL`
- `VLM_SERVICE_PORT`

## 启动

```bash
bash run_vlm_review_service.sh
```

默认监听：

```text
http://0.0.0.0:9000/analyze
```

## 请求格式

```json
{
  "event_id": "...",
  "camera_id": "usb_cam_0",
  "frames": ["frame1.jpg", "frame2.jpg"],
  "frame_images": ["base64...", "base64..."],
  "metadata": {
    "person_confidence": 0.91,
    "bbox": [120, 80, 320, 400],
    "video_path": "/path/event.mp4"
  }
}
```

## 返回格式

```json
{
  "activity_label": "normal_cleaning",
  "risk_level": "normal",
  "description": "Person appears to be cleaning normally with stable posture.",
  "confidence": 0.84,
  "status": "ok"
}
```
