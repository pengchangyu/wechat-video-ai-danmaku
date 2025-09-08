# 微信视频号助手（阶段一：发送消息 MVP）

Minimal macOS helper to send messages into a WeChat Channels (视频号) live room via GUI automation.

## Quick Start

1) Grant permissions: System Settings → Privacy & Security → Accessibility → enable for your Terminal (or Python).

2) Run app:

```bash
scripts/start.sh
```

3) In WeChat, open a 视频号直播间.

4) In the app:
   - Click “激活微信” (optional)
   - Click “捕捉输入框位置” → 在倒计时内把鼠标移到直播间输入框上（自动记录坐标）
   - Optionally adjust delay and keep “发送时最小化本应用” enabled
   - Optionally enable “使用坐标点击聚焦输入框”（若你的系统权限允许）
   - Enter a message and click “发送到直播间” (the app activates WeChat, optionally clicks the saved position to focus, then pastes + Return)

5) Stop app:

```bash
scripts/stop.sh
```

## Notes

- Works on macOS only (AppleScript via System Events + Swift clicker for mouse click).
- Clipboard is used to paste text (Cmd+V) and press Return to send.
- If sending fails, verify Accessibility permissions and recalibrate the input position.

### Accessibility
Grant Accessibility permissions to allow keyboard and mouse automation:
- System Settings → Privacy & Security → Accessibility → enable your Terminal (or Python/IDE).

### Logs
- App writes logs to `logs/app.log` with timestamps for troubleshooting.

### Build Swift Clicker (optional, auto-built on first send)
- To build manually:
  - `scripts/build_clicker.sh`
- This compiles `tools/wxclick.swift` into `scripts/wxclick` used for reliable click focus.

## Roadmap

- Robust input detection without manual calibration
- Read live chat text (OCR/AX) and ASR for host speech
- Persona and interaction strategy engine
