# 当前项目能力对照表

## Summary

这份文档将当前项目分成 3 类：

- 已具备的框架能力
- 已有代码但待实机联调的能力
- 尚未纳入当前框架的能力

目的很明确：

1. 看清现在这个项目已经能做什么
2. 区分哪些只是代码骨架，哪些已具备可运行结构
3. 明确离可演示成品还差哪几步

## 当前能力对照表

| 模块 | 当前状态 | 已具备/待完善 | 说明 |
| --- | --- | --- | --- |
| 定时巡视主控 | 已有代码 | 已具备框架 | [patrol_gateway.py](/Users/zhou/Documents/Codex/2026-04-26-files-mentioned-by-the-user-ai-2/rdk_x5_demo/ros2_ws/src/smart_care_bridge/smart_care_bridge/patrol_gateway.py) 已支持周期巡视与定时报表触发 |
| 单次巡视执行链路 | 已有代码 | 已具备框架 | [patrol_engine.py](/Users/zhou/Documents/Codex/2026-04-26-files-mentioned-by-the-user-ai-2/rdk_x5_demo/ros2_ws/src/smart_care_bridge/smart_care_bridge/patrol_engine.py) 已支持抓图、录视频、检测、复核、记录、通知 |
| USB 摄像头抓图 | 已有代码 | 待实机联调 | [patrol_capture.py](/Users/zhou/Documents/Codex/2026-04-26-files-mentioned-by-the-user-ai-2/rdk_x5_demo/ros2_ws/src/smart_care_bridge/smart_care_bridge/patrol_capture.py) 已调用 `ffmpeg`，但还需真实 `/dev/video0` 验证 |
| 5 秒短视频录制 | 已有代码 | 待实机联调 | 逻辑已写，需验证相机格式、编码、文件完整性 |
| 关键帧抽取 | 已有代码 | 待实机联调 | 已支持从视频等距抽帧，需验证输出质量和时序 |
| 巡视目标预筛 | 已有代码 | 已接入 `RDK X5` 检测方案，待实机联调 | 当前默认支持 `rdk_x5_ros2_image`，会在每次巡视时拉起官方 `mono2d_body_detection` 对抓拍图做单图检测；仍保留 `json_command` 作为回退 |
| MiniCPM-V 复核调用 | 已有代码 | 待实机联调 | [vlm_review_client.py](/Users/zhou/Documents/Codex/2026-04-26-files-mentioned-by-the-user-ai-2/rdk_x5_demo/ros2_ws/src/smart_care_bridge/smart_care_bridge/vlm_review_client.py) 已能调 HTTP 语义服务 |
| 笔记本侧 Ollama 服务 | 已有代码 | 待实机联调 | [ollama_review_service.py](/Users/zhou/Documents/Codex/2026-04-26-files-mentioned-by-the-user-ai-2/rdk_x5_demo/notebook_vlm_service/ollama_review_service.py) 已成型，需验证模型名和多图输入 |
| 风险分级策略 | 已有代码 | 已具备 | 已支持 `normal/warning/alarm` 和失败降级 |
| 飞书即时通知 | 已有代码 | 待实机联调 | 代码可发文本提醒，需验证真实 webhook |
| 每日报告生成 | 已有代码 | 已具备框架 | [daily_report.py](/Users/zhou/Documents/Codex/2026-04-26-files-mentioned-by-the-user-ai-2/rdk_x5_demo/ros2_ws/src/smart_care_bridge/smart_care_bridge/daily_report.py) 已可汇总日志 |
| 飞书日报推送 | 已有代码 | 待实机联调 | 已有接口，需验证真实发送效果 |
| 本地巡视日志 | 已有代码 | 已具备 | 当前已能记录巡视结果、风险等级、证据路径 |
| OpenClaw 问答入口 | 未接入 | 未具备 | 目前 OpenClaw 还不在主链路中 |
| 用户主动发起状态查询 | 未接入 | 未具备 | 飞书“现在家里什么样”这类查询型入口还没挂进框架 |
| GIF 动图生成与发送 | 未接入 | 未具备 | 当前只有截图/短视频，没有 GIF 生成链路 |
| 多摄像头巡视 | 设计可扩展 | 未具备 | 当前默认单 USB 摄像头 |
| 多传感器融合 | 未接入 | 未具备 | 目前框架主要是视觉巡视 |
| 萤石云 API 通道 | 未接入 | 未具备 | 当前方案明确默认只用 USB 摄像头 |

## 离“可演示成品”最近的必做项

按优先级排序，当前最需要补的不是新功能，而是把已有框架接成真链路：

1. 真实检测器实机联调  
   当前默认已切到 `DETECTOR_MODE=rdk_x5_ros2_image`，下一步是验证官方 `mono2d_body_detection` 在板端单图模式下能稳定返回人体检测结果

2. USB 摄像头实机联调  
   验证抓图、5 秒录制、关键帧抽取

3. Ollama 实机复核  
   确认 `MiniCPM-V` 的模型名，验证多图输入，验证输出 JSON 稳定性和速度

4. 飞书联调  
   验证即时提醒、日报推送、通知内容格式

5. 定时运行方式固化  
   当前是应用内循环，最终建议切到 `systemd service + timer`

## 当前不建议优先做的项

这些功能有价值，但不是现在最该做的：

- GIF 动图生成
- OpenClaw 飞书问答式查询
- 多摄像头扩展
- 多传感器融合
- 萤石云 API 支持
- `skill.md` 封装

原因很简单：

- 当前主链路还没实机闭环
- 先加这些只会让调试面变大
- 先跑通“巡视 -> 复核 -> 飞书 -> 日报”最重要

## 当前项目阶段判断

当前项目已经不是空白原型，而是：

**定时巡视 + 本地取证 + MiniCPM-V 行为复核 + 飞书分级通知 + 每日报告** 的可实现框架

但它还不是：

**已在真实 RDK X5 上稳定运行的成品**

所以当前阶段更准确地说是：

- 架构已经明确
- 主流程代码已经成型
- 还差真实设备与外部服务的接线和稳定性验证

## Test Plan

你接下来可以直接按下面顺序做验证：

1. 检测接入测试  
   验证 `rdk_x5_ros2_image -> 官方人体检测结果`

2. 采集链路测试  
   抓图、录像、抽帧

3. 复核链路测试  
   板端 -> 笔记本 -> Ollama -> 返回 JSON

4. 通知链路测试  
   即时告警、日报推送

5. 调度链路测试  
   2 分钟巡视、每日固定时间日报

## Assumptions

- 当前默认主控仍为 `RDK X5`
- 当前默认视频输入仍为单路 `USB 摄像头`
- 当前默认 `MiniCPM-V` 运行在 `R9000P + Ollama`
- 当前默认最优先目标是“形成可演示成品”，不是继续扩展新能力
