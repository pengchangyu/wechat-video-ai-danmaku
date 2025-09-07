# 技术方案 - 微信视频号 AI 弹幕助手（离线优先 MVP）

## 架构概览（离线优先）
- 采集：Selenium+Safari 轮询 DOM 获取弹幕（CSS 可配置）。
- 生成：Ollama(本地) → 回退模板生成。
- 发送：
  - 半自动：终端审核 → osascript 粘贴+回车（对 DOM 免耦合）。
  - 自动（可选）：Selenium 定位输入框并发送。
- TTS：macOS `say` 输出 AIFF/WAV，保存到 `data/tts/`。
- 存储：SQLite（`data/app.db`）。
- ASR：接口预留，后续对接 BlackHole + sherpa-onnx。

## 模块划分
- `automation.safari`: SafariDriver 管理、DOM 抓取、发送回退（剪贴板+osascript）。
- `generation.llm`: Ollama 客户端（可选）与模板回退。
- `tts.macos`: `say` 封装与文件归档。
- `storage.db`: SQLite 初始化与 DAO。
- `pipeline`: 调度循环（抓取→生成→审核→TTS→发送→入库）。
- `cli`: 命令行入口与半自动审核交互。

## 数据库设计（SQLite）
Tables
- `messages` (id, ts, role['user'|'ai'|'system'|'asr'], text, source, extra_json)
- `actions` (id, ts, kind['generate'|'send'|'tts'], ref_id, status, info)
- `tts_records` (id, msg_id, path, duration_sec, voice)

## 配置
`config.yaml`
- `live_url`: 直播页面URL
- `selectors`: { chat_items: "", chat_text: "", send_button: "" }
- `ollama`: { base_url: "http://localhost:11434", model: "qwen2.5:7b" }
- `tts`: { voice: "Ting-Ting", format: "aiff" }
- `loop`: { gen_interval_sec: 45 }

## 关键流程
1) 启动 SafariDriver，打开 `live_url`，人工完成登录。
2) 周期抓取最新弹幕（去重）。
3) 组装上下文（最近弹幕N条 + 简短规约），请求 LLM 生成候选。
4) 半自动审核：CLI 展示候选 → [e]dit / [y]es / [n]o。
5) TTS：使用 `say` 生成音频文件并入库记录。
6) 发送：优先 DOM；若无选择器，使用 osascript 粘贴+回车（需先聚焦输入框）。
7) 写入存储：消息、动作与 TTS 记录。

## 失败与回退
- Safari 自动化失败 → 提示开启 Develop/Allow Remote Automation。
- DOM 选择器失效 → 回退到 osascript 粘贴发送。
- Ollama 不可用 → 模板回退（安全提示 + 多样化模板）。
- `say` 失败 → 记录错误并跳过音频，不阻断文本发送。

