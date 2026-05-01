# RDK X5 实机联调清单

## Summary

目标是按真实设备顺序，把这条链路逐段打通并留证：

`USB 摄像头 -> RDK X5 抓图/录像 -> RDK X5 官方人体检测 -> R9000P 上 Ollama + MiniCPM-V -> 飞书即时通知 -> 巡视循环 -> 每日报告`

联调原则固定为：

- 先验证单点能力，再做端到端联调
- 每一阶段都要有明确通过标准
- 在真实检测未稳定前，不引入 GIF、OpenClaw 问答、多摄像头扩展

## 1. 板端环境准备

在 `RDK X5` 上执行：

```bash
mkdir -p ~/smart-care-demo
cp -r rdk_x5_demo/* ~/smart-care-demo/
cd ~/smart-care-demo
sudo apt update
sudo apt install -y v4l-utils ffmpeg curl
source /opt/tros/humble/setup.bash
ros2 pkg list | grep mono2d_body_detection || sudo apt install -y tros-humble-mono2d-body-detection
cp .smart_care.env.example ~/.smart_care.env
vim ~/.smart_care.env
cd ~/smart-care-demo/ros2_ws
source /opt/tros/humble/setup.bash
colcon build
source install/setup.bash
```

必须确认：

- `VIDEO_DEVICE=/dev/video0`
- `DETECTOR_MODE=rdk_x5_ros2_image`
- `PERSON_TOPIC=/hobot_mono2d_body_detection`
- `DETECTOR_SETUP_SCRIPT=/opt/tros/humble/setup.bash`
- `VLM_SERVER_URL=http://<R9000P局域网IP>:9000/analyze`
- `FEISHU_WEBHOOK_URL=...`

通过标准：

- `ros2 pkg list | grep mono2d_body_detection` 有结果
- `colcon build` 成功
- `~/.smart_care.env` 已完成配置

## 2. 摄像头与本地采集联调

先只看 `USB 摄像头 + ffmpeg`：

```bash
cd ~/smart-care-demo
bash scripts/check_camera.sh
```

确认：

- 存在 `/dev/video0`
- `v4l2-ctl` 能列出 `MJPEG`
- `ffmpeg` 能抓出 `test.jpg`

再验证项目采集层：

```bash
cd ~/smart-care-demo
bash scripts/run_patrol_once.sh
```

通过标准：

- 生成 1 张截图
- 生成 1 段 5 秒视频
- 生成 `KEY_FRAME_COUNT` 张关键帧
- 截图、视频、关键帧都能正常打开

失败优先排查：

- `VIDEO_INPUT_FORMAT`
- `VIDEO_SIZE`
- `/dev/video0` 权限
- `ffmpeg` 是否支持当前格式

## 3. 真实检测模式联调

先手工验证官方检测：

```bash
cd ~/smart-care-demo
bash scripts/run_body_detection.sh
```

确认：

- 浏览器可访问 `http://RDK_X5_IP:8000`
- 人站在镜头前能看到检测框

再验证巡视模式单图检测：

- 保持 `DETECTOR_MODE=rdk_x5_ros2_image`
- 再次运行：

```bash
cd ~/smart-care-demo
bash scripts/run_patrol_once.sh
```

通过标准：

- 有人场景返回 `target_detected=true`
- 空场景返回 `target_detected=false`
- `detection_confidence` 合理
- 不会出现检测进程提前退出或永久超时

重点确认：

- 巡视模式走的是“抓拍图 -> 临时拉起官方检测 -> 订阅 `PerceptionTargets` -> 解析候选框”
- 不是依赖常驻检测节点

## 4. 笔记本侧 Ollama + MiniCPM-V 联调

在 `R9000P` 上执行：

```bash
cd notebook_vlm_service
cp .env.example .env
vim .env
bash run_vlm_review_service.sh
```

必须填写：

- `OLLAMA_MODEL`
- `VLM_SERVICE_HOST`
- `VLM_SERVICE_PORT`

确认：

- Ollama 中已能运行目标 `MiniCPM-V`
- 服务已监听 `http://<R9000P局域网IP>:9000/analyze`

通过标准：

- `/analyze` 返回稳定 JSON
- 正常活动样本能返回 `normal`
- 异常姿态样本至少返回 `warning` 或 `alarm`
- 单次响应时间满足巡视节奏

失败优先排查：

- `OLLAMA_MODEL` 名称
- 多图输入是否被 Ollama 接收
- JSON schema 输出是否被正确约束

## 5. 板端到笔记本的复核链路联调

在板端确认：

- `VLM_SERVER_URL` 指向笔记本局域网地址

然后运行一次完整巡视：

```bash
cd ~/smart-care-demo
bash scripts/run_patrol_once.sh
```

检查巡视日志：

- `activity_label`
- `risk_level`
- `vlm_description`
- `vlm_status`

通过标准：

- 板端能成功访问笔记本服务
- 日志里出现有效 `vlm_*` 字段
- VLM 失败时进入回退逻辑，不会让巡视流程崩掉

## 6. 飞书通知联调

先验证日报生成，不和实时检测混在一起：

```bash
cd ~/smart-care-demo
bash scripts/run_daily_report_once.sh
bash scripts/run_daily_report_once.sh --send
```

再验证即时通知：

- 用真实巡视结果验证
- `normal` 不发
- `warning` 发提醒
- `alarm` 发警告

通过标准：

- webhook 可用
- 即时通知内容包含时间、风险等级、行为描述、截图路径、视频路径
- 日报统计与原始日志一致

## 7. 端到端巡视联调

按顺序启动：

1. 笔记本侧：

```bash
cd notebook_vlm_service
bash run_vlm_review_service.sh
```

2. 板端：

```bash
source ~/.smart_care.env
cd ~/smart-care-demo
bash scripts/run_patrol_gateway.sh
```

测试三种场景：

- 空房间
- 人正常活动
- 人异常姿态

预期结果：

- 空房间：只写轻量日志，不发飞书
- 正常活动：留证、复核、写日志，不发即时消息
- 异常姿态：留证、复核、发飞书提醒或报警

通过标准：

- 整个链路不需要人工介入
- 日志、证据、VLM、飞书结果一致
- 没有因单个子系统失败导致巡视循环退出

## 8. 定时报表与长期运行固化

联调通过后，再做长期运行：

1. 先用 `patrol_gateway.py` 的循环跑 `1~2` 小时
2. 观察：
   - 巡视是否按周期触发
   - 是否有日志堆积异常
   - 是否有重复通知
3. 再固化成长期运行方式：
   - 首选 `systemd service`
   - 后续再补 `systemd timer`

通过标准：

- 开机可恢复运行
- 日报只发送一次
- 巡视周期稳定
- 失败日志可定位问题
