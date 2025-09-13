# 微信视频号助手（阶段一：发送消息 MVP）

Minimal macOS helper to send messages into a WeChat Channels (视频号) live room via GUI automation.

## Teammate Setup (Clone & Run)

- Prereqs: macOS, Python3 (with Tk), Xcode Command Line Tools (`xcode-select --install`), and `ffmpeg` (`brew install ffmpeg` for ASR).
- Permissions: System Settings → Privacy & Security → Accessibility (Terminal/Python) and Screen Recording (for OCR screenshots).
- Config:
  - Copy `config.example.json` to `config.json` and fill your own API keys, or export env vars (e.g., `OPENAI_API_KEY`). Keep `agent_auto_send=false` initially.
  - Calibrate coordinates in the GUI: input box, send button, and comments region.
- Run:
  - `scripts/start.sh` to open the GUI; follow on-screen steps (send test, then cloud OCR, optional ASR, optional Agent).
- Stop:
  - `scripts/stop.sh`.

Notes: `config.json` is intentionally not tracked (secrets). Do not commit your keys. Use `config.example.json` as a template.

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
   - If Return does not send, also “捕捉发送按钮位置” and enable click-send flow
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

### Tips
- Use input box center-left when capturing coordinates to avoid edge hits.
- Increase `延时(秒)` if WeChat takes longer to come to foreground.
- If click focuses but paste doesn’t appear, increase `点击后延时(秒)` (e.g., 0.8–1.0s).
- If Return inserts a newline instead of sending, capture “发送按钮位置”. The app pastes then clicks the button; fallback to Return if not set.
- Shortcuts: `Cmd+Enter`/`Ctrl+Enter` to send, `F7` capture input, `F8` capture send button.
- Enable `双击聚焦` so the app clicks the input twice (with `第二次点击延时`) to ensure the caret enters the text field on live pages that expand the input on first click.

## Roadmap

- Robust input detection without manual calibration
- Read live chat text (OCR/AX) and ASR for host speech
- Persona and interaction strategy engine

---

## Phase 2: Live Comments OCR (Cloud, OpenAI)

This phase uses cloud OCR via OpenAI to read comments from a WeChat Channels live room. Local Vision OCR is disabled by default.

### Setup

1) Grant Screen Recording permission:
   - System Settings → Privacy & Security → Screen Recording → enable for your Terminal (or Python/IDE).
2) Build the OCR tool (auto on first run; manual build if needed):

```bash
scripts/build_ocr.sh
```

### Usage in App

1) In the GUI:
   - Click “捕捉评论区左上/右下”以标定评论区域。
   - 在“云 OCR（OpenAI）”处填写并保存 API Key，选择模型与间隔。
   - 点击“开始抓取评论”启动云 OCR；点击“停止抓取评论”停止。

2) Behind the scenes:
   - The app periodically screenshots the calibrated region, sends it to OpenAI, and writes structured results to JSONL with timestamps.

### Logs

- Cloud OCR results: `logs/ocr.openai.jsonl` (one JSON per line: `{ts, model, image, lines, raw}`)
- Cloud screenshots: `logs/frames/cloud-*.png`
- App log: `logs/app.log` (includes cloud-ocr start/stop/errors)

### ASR (Mic) outputs

- Audio segments: `logs/audio/seg-*.wav` (default 6s each)
- Transcripts: `logs/asr.jsonl` (one JSON per segment; `result.text` contains text)
- Recorder log: `logs/asr_recorder.log`
- Worker log: `logs/asr_worker.log`

## Phase 4: DeepSeek Agent

- Purpose: Aggregate OCR comments + ASR transcripts, ask DeepSeek for a short, human-like reply, and optionally auto-send via the existing WeChat sender.
- Enable in app under “DeepSeek Agent（自动互动）”. Configure:
  - `DeepSeek API Key`, `模型` (e.g., `deepseek-chat`), `API Base` (default `https://api.deepseek.com/v1/chat/completions`)
  - Poll interval and auto-send toggle (keep off initially)
- Outputs:
  - `logs/agent.jsonl` — one JSON per decision: `{ts, prompt_preview, reply, auto_sent}`
- Notes:
  - The agent uses recent OCR lines and ASR text (last few items) as context.
  - Keep auto-send off for initial validation; turn on once results look good.

### Notes

- OCR depends on visual clarity of the comments area; if accuracy is low, re-calibrate the region and consider light/dark theme contrast.
- FPS range 0.5–10 is supported; 1–3 is recommended for steady accuracy/performance.
