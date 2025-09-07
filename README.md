# 微信视频号 AI 弹幕助手（离线优先 MVP）

目标：在微信视频号直播中充当“像真人观众”的 AI 弹幕助手，离线优先，仅登录/观看直播需联网。

快速路线（macOS M1 开发环境）：
- 浏览器自动化：Selenium + SafariDriver（macOS 自带）
- 半自动发送：终端审核后，自动粘贴+回车，或 DOM 选择器发送
- 本地 TTS：macOS `say` 命令，产出音频并归档
- 存储：SQLite 记录弹幕、ASR(预留)、生成文案、发送日志
- LLM：优先使用本地 Ollama，如不可用则启用简单模板回退

开发运行（首次）
1) 在 Safari 菜单：Develop -> Allow Remote Automation（需先在 Safari 偏好设置启用 Develop 菜单）
2) 打开视频号直播页并登录（保持页面可用）
3) 终端执行：
```bash
uv run python -m ai_danmaku.cli --live-url "<直播页面URL>" --semi
```

注意：
- 半自动模式会在终端提示，先在 Safari 聚焦弹幕输入框，再回车确认发送。
- 若需 DOM 精准发送，编辑 `config.yaml` 填入 CSS 选择器。

目录
- docs/PRD.md：产品需求与验收标准
- docs/TECH_DESIGN.md：技术方案与模块接口
- src/ai_danmaku：源代码
- data/: 运行期产生的数据库与音频归档

一键启动/停止
- 首次赋权：`chmod +x start.sh stop.sh`
- 启动（默认半自动）：`./start.sh`
  - 环境变量可选：`LIVE_URL`（覆盖 config.json）、`INTERVAL=45`、`SEMI=1|0`
- 停止：`./stop.sh`
