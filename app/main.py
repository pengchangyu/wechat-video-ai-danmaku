import json
import os
import subprocess
import time
import tkinter as tk
from tkinter import messagebox

from macos.osascript import activate_wechat, quit_wechat, paste_via_applescript_and_return, paste_only_via_applescript, grant_permissions_hint
import threading
import queue
import base64
import signal
import urllib.request
import urllib.error

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG_PATH = os.path.join(ROOT_DIR, 'config.json')


def load_config():
    if os.path.exists(CONFIG_PATH):
        with open(CONFIG_PATH, 'r') as f:
            return json.load(f)
    return {}


def save_config(cfg):
    with open(CONFIG_PATH, 'w') as f:
        json.dump(cfg, f, indent=2)


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title('微信视频号助手 - 发送消息 MVP')
        # Dynamic window size (~90% of screen), resizable
        try:
            sw, sh = self.winfo_screenwidth(), self.winfo_screenheight()
            target_w = max(1100, min(1600, int(sw * 0.9)))
            target_h = max(800, min(1200, int(sh * 0.9)))
            self.geometry(f"{target_w}x{target_h}")
        except Exception:
            self.geometry('1400x1000')
        self.resizable(True, True)
        # Grid layout: allow middle column to expand
        try:
            for c in range(4):
                self.grid_columnconfigure(c, weight=1 if c == 1 else 0)
        except Exception:
            pass
        # Improve readability on HiDPI but avoid overscaling which can clip UI
        try:
            self.tk.call('tk', 'scaling', 1.0)
        except Exception:
            pass

        # Ensure background workers are stopped when window closes
        try:
            self.protocol("WM_DELETE_WINDOW", self.on_close)
        except Exception:
            pass

        self.cfg = load_config()
        self.log_path = os.path.join(ROOT_DIR, 'logs')
        os.makedirs(self.log_path, exist_ok=True)
        self.log_file = os.path.join(self.log_path, 'app.log')
        # ASR logs
        self.asr_rec_log_path = os.path.join(self.log_path, 'asr_recorder.log')
        self.asr_worker_log_path = os.path.join(self.log_path, 'asr_worker.log')
        # Restore saved input position if any
        self.input_pos = None
        try:
            if isinstance(self.cfg.get('input_position'), list) and len(self.cfg['input_position']) == 2:
                self.input_pos = (float(self.cfg['input_position'][0]), float(self.cfg['input_position'][1]))
        except Exception:
            self.input_pos = None
        # Restore send button position
        self.send_btn_pos = None
        try:
            if isinstance(self.cfg.get('send_button_position'), list) and len(self.cfg['send_button_position']) == 2:
                self.send_btn_pos = (float(self.cfg['send_button_position'][0]), float(self.cfg['send_button_position'][1]))
        except Exception:
            self.send_btn_pos = None

        # Comments region: [x1, y1, x2, y2]
        self.comments_rect = None
        try:
            cr = self.cfg.get('comments_region')
            if isinstance(cr, list) and len(cr) == 4:
                self.comments_rect = (float(cr[0]), float(cr[1]), float(cr[2]), float(cr[3]))
        except Exception:
            self.comments_rect = None

        # OCR runtime (cloud-only)
        self.ocr_proc = None
        self.ocr_thread = None
        self.ocr_stop = threading.Event()
        self.ocr_queue = queue.Queue()
        self.recent_texts = []  # [(ts, text)]
        # Cloud OCR
        self.cloud_thread = None
        # Agent (DeepSeek)
        self.agent_thread = None
        self.agent_stop = threading.Event()
        self.agent_last_idx = { 'ocr': 0, 'asr': 0 }
        # Agent de-dup memory (recent)
        self.agent_seen_ocr_set = set()
        self.agent_seen_ocr_list = []  # keep order for trimming
        self.agent_seen_asr_set = set()
        self.agent_seen_asr_list = []

        # Scrollable container
        container = tk.Frame(self)
        container.pack(fill='both', expand=True)
        canvas = tk.Canvas(container, highlightthickness=0)
        vbar = tk.Scrollbar(container, orient='vertical', command=canvas.yview)
        canvas.configure(yscrollcommand=vbar.set)
        vbar.pack(side='right', fill='y')
        canvas.pack(side='left', fill='both', expand=True)
        self.content = tk.Frame(canvas)
        canvas.create_window((0, 0), window=self.content, anchor='nw')
        def _on_cfg(event):
            canvas.configure(scrollregion=canvas.bbox('all'))
        self.content.bind('<Configure>', _on_cfg)

        # Controls
        row = 0
        tk.Label(self.content, text='第一阶段：在直播间中自动发送消息', font=('Helvetica', 16, 'bold')).grid(row=row, column=0, columnspan=3, pady=10, sticky='w')
        row += 1

        tk.Button(self.content, text='退出微信', command=self.quit_wechat_cmd, width=14).grid(row=row, column=0, padx=6, pady=4)
        tk.Button(self.content, text='激活微信', command=self.activate_wechat_cmd, width=14).grid(row=row, column=1, padx=6, pady=4)
        tk.Button(self.content, text='权限提示', command=self.perm_hint_cmd, width=14).grid(row=row, column=2, padx=6, pady=4)
        tk.Button(self.content, text='一键开始', command=self.start_all_cmd, width=14).grid(row=row, column=3, padx=6, pady=4)
        row += 1
        tk.Button(self.content, text='一键停止', command=self.stop_all_cmd, width=14).grid(row=row, column=3, padx=6, pady=4)
        row += 1

        # Calibration UI
        tk.Label(self.content, text='校准：点击“捕捉输入框位置/发送按钮位置”后有倒计时，请在倒计时内把鼠标移动到目标上，无需再点击。').grid(row=row, column=0, columnspan=3, pady=6, sticky='w')
        row += 1

        tk.Button(self.content, text='捕捉输入框位置', command=self.capture_input_pos_cmd, width=18).grid(row=row, column=0, padx=6, pady=4)
        self.pos_label = tk.Label(self.content, text=self._pos_text())
        self.pos_label.grid(row=row, column=1, columnspan=2, sticky='w')
        row += 1

        tk.Button(self.content, text='捕捉发送按钮位置', command=self.capture_send_btn_pos_cmd, width=18).grid(row=row, column=0, padx=6, pady=4)
        self.send_pos_label = tk.Label(self.content, text=self._send_pos_text())
        self.send_pos_label.grid(row=row, column=1, columnspan=2, sticky='w')
        row += 1

        tk.Label(self.content, text='发送内容').grid(row=row, column=0, sticky='e')
        self.msg_var = tk.StringVar(value='测试消息：你好，主播！')
        tk.Entry(self.content, textvariable=self.msg_var, width=48).grid(row=row, column=1, columnspan=2, sticky='w', pady=6)
        row += 1

        # Options
        tk.Label(self.content, text='延时(秒)').grid(row=row, column=0, sticky='e')
        self.delay_var = tk.DoubleVar(value=1.0)
        tk.Entry(self.content, textvariable=self.delay_var, width=8).grid(row=row, column=1, sticky='w')
        # 默认不最小化，避免 Dock 隐现及前台切换闪烁
        self.minimize_var = tk.BooleanVar(value=False)
        tk.Checkbutton(self.content, text='发送时最小化本应用', variable=self.minimize_var).grid(row=row, column=2, sticky='w')
        row += 1

        self.use_click_var = tk.BooleanVar(value=True)
        tk.Checkbutton(self.content, text='使用坐标点击聚焦输入框', variable=self.use_click_var).grid(row=row, column=1, columnspan=2, sticky='w')
        row += 1

        tk.Label(self.content, text='点击后延时(秒)').grid(row=row, column=0, sticky='e')
        self.post_click_delay_var = tk.DoubleVar(value=1.0)
        tk.Entry(self.content, textvariable=self.post_click_delay_var, width=8).grid(row=row, column=1, sticky='w')
        row += 1

        self.double_click_var = tk.BooleanVar(value=True)
        tk.Checkbutton(self.content, text='双击聚焦（展开后再点一次）', variable=self.double_click_var).grid(row=row, column=1, columnspan=2, sticky='w')
        row += 1

        tk.Label(self.content, text='第二次点击延时(秒)').grid(row=row, column=0, sticky='e')
        self.second_click_delay_var = tk.DoubleVar(value=1.0)
        tk.Entry(self.content, textvariable=self.second_click_delay_var, width=8).grid(row=row, column=1, sticky='w')
        row += 1

        self.countdown_only_var = tk.BooleanVar(value=False)
        tk.Checkbutton(self.content, text='仅倒计时发送（不激活/不点击，需手动先点到输入框）', variable=self.countdown_only_var).grid(row=row, column=1, columnspan=2, sticky='w')
        row += 1

        tk.Button(self.content, text='发送到直播间', command=self.send_message_cmd, width=20).grid(row=row, column=0, padx=6, pady=8, sticky='w')
        self.status_var = tk.StringVar(value='Ready')
        tk.Label(self.content, textvariable=self.status_var, fg='#555').grid(row=row, column=1, columnspan=2, sticky='w')
        row += 1

        tk.Label(self.content, text='提示：进入直播间后可用“捕捉输入框位置”记录坐标（倒计时捕捉），发送时可选择是否使用点击聚焦。').grid(row=row, column=0, columnspan=3, pady=6, sticky='w')
        row += 1
        tk.Label(self.content, text='提示：若回车不发送，请校准“发送按钮位置”，程序将粘贴后点击按钮提交。').grid(row=row, column=0, columnspan=3, pady=6, sticky='w')

        # --- Comments OCR Section ---
        row += 1
        tk.Label(self.content, text='第二阶段：抓取直播间评论（云 OCR）', font=('Helvetica', 15, 'bold')).grid(row=row, column=0, columnspan=3, pady=10, sticky='w')
        row += 1
        tk.Button(self.content, text='捕捉评论区左上', command=self.capture_comments_tl_cmd, width=18).grid(row=row, column=0, padx=6, pady=4)
        tk.Button(self.content, text='捕捉评论区右下', command=self.capture_comments_br_cmd, width=18).grid(row=row, column=1, padx=6, pady=4)
        self.comments_label = tk.Label(self.content, text=self._comments_text())
        self.comments_label.grid(row=row, column=2, sticky='w')
        row += 1
        tk.Button(self.content, text='开始抓取评论', command=self.start_ocr_cmd, width=16).grid(row=row, column=2, sticky='w')
        row += 1
        tk.Button(self.content, text='停止抓取评论', command=self.stop_ocr_cmd, width=16).grid(row=row, column=2, sticky='w')
        row += 1
        # Cloud OCR (OpenAI)
        tk.Label(self.content, text='云 OCR（OpenAI）').grid(row=row, column=0, sticky='e')
        self.cloud_enabled_var = tk.BooleanVar(value=True)
        tk.Checkbutton(self.content, text='启用', variable=self.cloud_enabled_var).grid(row=row, column=1, sticky='w')
        tk.Label(self.content, text='间隔(秒)').grid(row=row, column=2, sticky='e')
        self.cloud_interval_var = tk.DoubleVar(value=5.0)
        tk.Entry(self.content, textvariable=self.cloud_interval_var, width=8).grid(row=row, column=3, sticky='w')
        row += 1
        tk.Label(self.content, text='OpenAI API Key').grid(row=row, column=0, sticky='e')
        self.openai_key_var = tk.StringVar(value=self.cfg.get('openai_api_key', os.environ.get('OPENAI_API_KEY', '')))
        tk.Entry(self.content, textvariable=self.openai_key_var, width=44, show='*').grid(row=row, column=1, columnspan=2, sticky='w')
        tk.Button(self.content, text='保存Key', command=self.save_openai_key_cmd, width=10).grid(row=row, column=3, sticky='w')
        row += 1
        tk.Label(self.content, text='OpenAI 模型').grid(row=row, column=0, sticky='e')
        # Default to gpt-4o; if config仍为旧的 mini，则提升为 gpt-4o
        default_model = 'gpt-4o'
        cfg_model = self.cfg.get('openai_model')
        if cfg_model in (None, '', 'gpt-4o-mini'):
            self.cfg['openai_model'] = default_model
            try:
                save_config(self.cfg)
            except Exception:
                pass
            cfg_model = default_model
        self.openai_model_var = tk.StringVar(value=cfg_model)
        tk.OptionMenu(self.content, self.openai_model_var, 'gpt-4o-mini', 'gpt-4o').grid(row=row, column=1, sticky='w')
        row += 1
        tk.Label(self.content, text='说明：需授予“屏幕录制”权限；调高 FPS 会占用更多 CPU。').grid(row=row, column=0, columnspan=4, pady=6, sticky='w')

        # Keyboard shortcuts
        try:
            # Cmd+Enter and Ctrl+Enter to send
            self.bind_all('<Command-Return>', lambda e: self.send_message_cmd())
            self.bind_all('<Control-Return>', lambda e: self.send_message_cmd())
            # F7 capture input, F8 capture send button
            self.bind_all('<F7>', lambda e: self.capture_input_pos_cmd())
            self.bind_all('<F8>', lambda e: self.capture_send_btn_pos_cmd())
        except Exception:
            pass

        # --- ASR (Mic) Section ---
        row += 1
        tk.Label(self.content, text='第三阶段：ASR（麦克风外放）', font=('Helvetica', 15, 'bold')).grid(row=row, column=0, columnspan=4, pady=10, sticky='w')
        row += 1
        tk.Label(self.content, text='设备(avfoundation)').grid(row=row, column=0, sticky='e')
        self.asr_device_var = tk.StringVar(value=self.cfg.get('asr_device', ':0'))
        tk.Entry(self.content, textvariable=self.asr_device_var, width=16).grid(row=row, column=1, sticky='w')
        tk.Label(self.content, text='分段(秒)').grid(row=row, column=2, sticky='e')
        self.asr_seg_var = tk.IntVar(value=int(self.cfg.get('asr_segment_secs', 6)))
        tk.Entry(self.content, textvariable=self.asr_seg_var, width=8).grid(row=row, column=3, sticky='w')
        row += 1
        tk.Label(self.content, text='模型').grid(row=row, column=0, sticky='e')
        self.asr_model_var = tk.StringVar(value=self.cfg.get('asr_model', 'small'))
        tk.Entry(self.content, textvariable=self.asr_model_var, width=16).grid(row=row, column=1, sticky='w')
        tk.Label(self.content, text='compute').grid(row=row, column=2, sticky='e')
        self.asr_compute_var = tk.StringVar(value=self.cfg.get('asr_compute', 'int8'))
        tk.Entry(self.content, textvariable=self.asr_compute_var, width=16).grid(row=row, column=3, sticky='w')
        row += 1
        tk.Button(self.content, text='开始ASR', command=self.start_asr_cmd, width=16).grid(row=row, column=0, sticky='w', padx=6)
        tk.Button(self.content, text='停止ASR', command=self.stop_asr_cmd, width=16).grid(row=row, column=1, sticky='w', padx=6)
        tk.Button(self.content, text='列出设备', command=self.list_audio_devs_cmd, width=16).grid(row=row, column=2, sticky='w', padx=6)
        row += 1
        tk.Label(self.content, text='ASR 输出：logs/asr.jsonl（每段一行）').grid(row=row, column=0, columnspan=4, sticky='w')
        row += 1

        # --- Agent (DeepSeek) Section ---
        tk.Label(self.content, text='第四阶段：DeepSeek Agent（自动互动）', font=('Helvetica', 15, 'bold')).grid(row=row, column=0, columnspan=4, pady=10, sticky='w')
        row += 1
        self.agent_enabled_var = tk.BooleanVar(value=False)
        tk.Checkbutton(self.content, text='启用 Agent（试验性）', variable=self.agent_enabled_var).grid(row=row, column=0, sticky='w')
        tk.Label(self.content, text='轮询间隔(秒)').grid(row=row, column=1, sticky='e')
        self.agent_interval_var = tk.DoubleVar(value=float(self.cfg.get('agent_interval', 10)))
        tk.Entry(self.content, textvariable=self.agent_interval_var, width=8).grid(row=row, column=2, sticky='w')
        row += 1
        tk.Label(self.content, text='DeepSeek API Key').grid(row=row, column=0, sticky='e')
        self.deepseek_key_var = tk.StringVar(value=self.cfg.get('deepseek_api_key', ''))
        tk.Entry(self.content, textvariable=self.deepseek_key_var, width=44, show='*').grid(row=row, column=1, columnspan=2, sticky='w')
        tk.Button(self.content, text='保存Key', command=self.save_deepseek_key_cmd, width=10).grid(row=row, column=3, sticky='w')
        row += 1
        tk.Label(self.content, text='模型').grid(row=row, column=0, sticky='e')
        self.deepseek_model_var = tk.StringVar(value=self.cfg.get('deepseek_model', 'deepseek-chat'))
        tk.Entry(self.content, textvariable=self.deepseek_model_var, width=20).grid(row=row, column=1, sticky='w')
        tk.Label(self.content, text='API Base').grid(row=row, column=2, sticky='e')
        self.deepseek_base_var = tk.StringVar(value=self.cfg.get('deepseek_base', 'https://api.deepseek.com/v1/chat/completions'))
        tk.Entry(self.content, textvariable=self.deepseek_base_var, width=38).grid(row=row, column=3, sticky='w')
        row += 1
        self.agent_auto_send_var = tk.BooleanVar(value=bool(self.cfg.get('agent_auto_send', False)))
        tk.Checkbutton(self.content, text='自动发送（谨慎开启）', variable=self.agent_auto_send_var).grid(row=row, column=0, sticky='w')
        self.agent_ignore_history_var = tk.BooleanVar(value=bool(self.cfg.get('agent_ignore_history', True)))
        tk.Checkbutton(self.content, text='启动时忽略历史（只读新内容）', variable=self.agent_ignore_history_var).grid(row=row, column=1, sticky='w')
        tk.Button(self.content, text='启动Agent', command=self.start_agent_cmd, width=14).grid(row=row, column=2, sticky='w')
        tk.Button(self.content, text='停止Agent', command=self.stop_agent_cmd, width=14).grid(row=row, column=3, sticky='w')
        row += 1
        tk.Label(self.content, text='说明：Agent 聚合评论/语音转写，经 DeepSeek 生成简短回复；建议先关闭自动发送，仅记录建议。').grid(row=row, column=0, columnspan=4, sticky='w')
        row += 1

    def _pos_text(self):
        return f"输入框坐标: {self.input_pos}" if self.input_pos else "输入框坐标: 未设置"

    def _comments_text(self):
        return f"评论区: {self.comments_rect}" if self.comments_rect else "评论区: 未设置"

    def quit_wechat_cmd(self):
        quit_wechat()
        self.status_var.set('已发送退出指令（若未退出，请手动）')
        self._log('quit_wechat issued')

    def activate_wechat_cmd(self):
        activate_wechat()
        self.status_var.set('已激活微信')
        self._log('activate_wechat issued')

    def perm_hint_cmd(self):
        messagebox.showinfo('权限提示', grant_permissions_hint())
        self._log('perm hint shown')

    def send_message_cmd(self):
        msg = self.msg_var.get().strip()
        if not msg:
            messagebox.showwarning('内容为空', '请输入要发送的内容。')
            return

        # Copy to clipboard
        try:
            subprocess.run(['pbcopy'], input=msg.encode('utf-8'), check=True)
        except Exception as e:
            messagebox.showerror('复制失败', f'设置剪贴板失败: {e}')
            self._log(f'pbcopy failed: {e}')
            return

        # Optionally minimize this app to avoid stealing focus
        try:
            did_minimize = False
            if self.minimize_var.get():
                self.iconify()
                did_minimize = True
                self._log('window iconified before send')
        except Exception:
            pass

        delay = 0.2
        try:
            delay = float(self.delay_var.get())
        except Exception:
            pass
        delay = max(0.0, delay)
        if self.countdown_only_var.get():
            # Do NOT activate WeChat; assume user will focus it during countdown
            self._log(f'countdown-only mode; sleeping {delay}s before paste')
            time.sleep(delay)
        else:
            # Activate WeChat and allow a short delay for input to be ready
            activate_wechat()
            self._log(f'activated wechat; sleeping {delay}s before paste')
            time.sleep(delay)

        # Optionally click the captured input position to focus (lazy import to avoid startup crashes)
        if (not self.countdown_only_var.get()) and self.use_click_var.get() and self.input_pos:
            try:
                x, y = self.input_pos
                click_bin = os.path.join(ROOT_DIR, 'scripts', 'wxclick')
                if not os.path.exists(click_bin):
                    # Try to build it
                    build_sh = os.path.join(ROOT_DIR, 'scripts', 'build_clicker.sh')
                    self._log('wxclick not found; attempting build_clicker.sh')
                    _ = subprocess.run(["bash", build_sh], capture_output=True, text=True)
                r = subprocess.run([click_bin, str(x), str(y)], capture_output=True, text=True)
                self._log(f'wxclick rc={r.returncode} out={r.stdout!r} err={r.stderr!r}')
                # Extra wait after click to allow the input to become editable
                try:
                    post_delay = float(self.post_click_delay_var.get())
                except Exception:
                    post_delay = 0.8
                post_delay = max(0.0, post_delay)
                self._log(f'post-click sleep {post_delay}s before paste')
                time.sleep(post_delay)

                # Optional second click to ensure caret enters the text field
                if self.double_click_var.get():
                    try:
                        sec_delay = float(self.second_click_delay_var.get())
                    except Exception:
                        sec_delay = 0.5
                    sec_delay = max(0.0, sec_delay)
                    self._log(f'second-click after {sec_delay}s')
                    time.sleep(sec_delay)
                    r2 = subprocess.run([click_bin, str(x), str(y)], capture_output=True, text=True)
                    self._log(f'wxclick second rc={r2.returncode} out={r2.stdout!r} err={r2.stderr!r}')
                    # small settle time
                    time.sleep(0.1)
            except Exception as e:
                self._log(f'wxclick error: {e}')
                self.status_var.set(f'点击聚焦失败，已跳过')

        # Paste only (Cmd+V)
        r = paste_only_via_applescript()
        self._log(f'paste-only rc={r.returncode} out={r.stdout!r} err={r.stderr!r}')
        # Optional short delay for text to settle
        paste_settle = 0.2
        time.sleep(paste_settle)
        # Click the send button if calibrated; adapt to vertical drift by scanning downward a short range.
        sent_ok = False
        if self.send_btn_pos:
            try:
                x2, y0 = self.send_btn_pos
                click_bin = os.path.join(ROOT_DIR, 'scripts', 'wxclick')
                if not os.path.exists(click_bin):
                    # ensure built
                    build_sh = os.path.join(ROOT_DIR, 'scripts', 'build_clicker.sh')
                    _ = subprocess.run(["bash", build_sh], capture_output=True, text=True)
                # Scan config: up to +60px, step 6px; small upward try first (+/- 6px)
                max_down = 40  # reduced vertical scan span by ~1/3 to avoid hitting other UI
                step = 3
                tried = []
                # Try nominal, then small upward, then downward increments
                candidates = [0, -6] + list(range(0, max_down + 1, step))
                any_ok = False
                for dy in candidates:
                    y = y0 + dy
                    r3 = subprocess.run([click_bin, str(x2), str(y)], capture_output=True, text=True)
                    tried.append(dy)
                    self._log(f'wxclick send-scan dy={dy} rc={r3.returncode} out={r3.stdout!r} err={r3.stderr!r}')
                    # small spacing between scan clicks to make movement可见
                    time.sleep(0.08)
                    if r3.returncode == 0:
                        any_ok = True
                sent_ok = any_ok
                self._log(f'send-scan tried offsets={tried}')
            except Exception as e:
                self._log(f'wxclick send-scan error: {e}')
        if not sent_ok:
            r2 = paste_via_applescript_and_return()
            self._log(f'fallback return rc={r2.returncode} out={r2.stdout!r} err={r2.stderr!r}')
            sent_ok = (r2.returncode == 0)
        if sent_ok:
            self.status_var.set('已发送（按钮/回车）')
        else:
            self.status_var.set('发送失败（请检查权限/按钮坐标）')
        # Restore window仅在确实最小化过时
        try:
            if 'did_minimize' in locals() and did_minimize:
                self.deiconify()
                self.lift()
        except Exception:
            pass

    def capture_input_pos_cmd(self):
        # Countdown to allow user to place mouse on input box; optionally minimize app to not obstruct
        try:
            # Briefly show countdown in status
            for i in range(10, 0, -1):
                self.status_var.set(f'将在 {i} 秒后捕捉鼠标位置…请把鼠标移到直播间输入框上')
                self.update()
                time.sleep(1)
            # Optionally minimize before capture to avoid covering the input box
            try:
                if not self.state() == 'iconic' and self.minimize_var.get():
                    self.iconify()
                    time.sleep(0.1)
            except Exception:
                pass

            # Capture pointer position (screen coordinates)
            self.update_idletasks()
            x = self.winfo_pointerx()
            y = self.winfo_pointery()
            self.input_pos = (float(x), float(y))
            self.cfg['input_position'] = [float(x), float(y)]
            save_config(self.cfg)
            self.pos_label.config(text=self._pos_text())
            self.status_var.set(f'已记录坐标: {x}, {y}')
            self._log(f'captured input pos {x},{y}')
            # Restore window to foreground after capture
            try:
                self.deiconify()
                self.lift()
            except Exception:
                pass
        except Exception as e:
            messagebox.showerror('捕捉失败', f'无法获取鼠标位置: {e}')
            self._log(f'capture failed: {e}')

    def _send_pos_text(self):
        return f"发送按钮坐标: {self.send_btn_pos}" if self.send_btn_pos else "发送按钮坐标: 未设置"

    def capture_send_btn_pos_cmd(self):
        try:
            for i in range(10, 0, -1):
                self.status_var.set(f'将在 {i} 秒后捕捉发送按钮位置…请把鼠标移到按钮上')
                self.update()
                time.sleep(1)
            try:
                if not self.state() == 'iconic' and self.minimize_var.get():
                    self.iconify()
                    time.sleep(0.1)
            except Exception:
                pass
            self.update_idletasks()
            x = self.winfo_pointerx()
            y = self.winfo_pointery()
            self.send_btn_pos = (float(x), float(y))
            self.cfg['send_button_position'] = [float(x), float(y)]
            save_config(self.cfg)
            self.send_pos_label.config(text=self._send_pos_text())
            self.status_var.set(f'已记录发送按钮坐标: {x}, {y}')
            self._log(f'captured send btn pos {x},{y}')
            try:
                self.deiconify()
                self.lift()
            except Exception:
                pass
        except Exception as e:
            messagebox.showerror('捕捉失败', f'无法获取鼠标位置: {e}')
            self._log(f'capture send-btn failed: {e}')

    def capture_comments_tl_cmd(self):
        try:
            for i in range(10, 0, -1):
                self.status_var.set(f'将在 {i} 秒后捕捉评论区左上…将鼠标移到左上角')
                self.update(); time.sleep(1)
            try:
                if not self.state() == 'iconic' and self.minimize_var.get():
                    self.iconify(); time.sleep(0.1)
            except Exception:
                pass
            self.update_idletasks()
            x = self.winfo_pointerx(); y = self.winfo_pointery()
            # If we already have BR, keep it; else placeholder
            if self.comments_rect:
                _, _, x2, y2 = self.comments_rect
                self.comments_rect = (float(x), float(y), float(x2), float(y2))
            else:
                self.comments_rect = (float(x), float(y), float(x), float(y))
            self.cfg['comments_region'] = [self.comments_rect[0], self.comments_rect[1], self.comments_rect[2], self.comments_rect[3]]
            save_config(self.cfg)
            self.comments_label.config(text=self._comments_text())
            self.status_var.set(f'已记录评论区左上: {x}, {y}')
            try:
                self.deiconify(); self.lift()
            except Exception:
                pass
            self._log(f'captured comments TL {x},{y}')
        except Exception as e:
            messagebox.showerror('捕捉失败', f'无法获取鼠标位置: {e}')
            self._log(f'capture comments TL failed: {e}')

    def capture_comments_br_cmd(self):
        try:
            for i in range(10, 0, -1):
                self.status_var.set(f'将在 {i} 秒后捕捉评论区右下…将鼠标移到右下角')
                self.update(); time.sleep(1)
            try:
                if not self.state() == 'iconic' and self.minimize_var.get():
                    self.iconify(); time.sleep(0.1)
            except Exception:
                pass
            self.update_idletasks()
            x = self.winfo_pointerx(); y = self.winfo_pointery()
            if self.comments_rect:
                x1, y1, _, _ = self.comments_rect
            else:
                x1, y1 = float(x), float(y)
            self.comments_rect = (float(x1), float(y1), float(x), float(y))
            self.cfg['comments_region'] = [self.comments_rect[0], self.comments_rect[1], self.comments_rect[2], self.comments_rect[3]]
            save_config(self.cfg)
            self.comments_label.config(text=self._comments_text())
            self.status_var.set(f'已记录评论区右下: {x}, {y}')
            try:
                self.deiconify(); self.lift()
            except Exception:
                pass
            self._log(f'captured comments BR {x},{y}')
        except Exception as e:
            messagebox.showerror('捕捉失败', f'无法获取鼠标位置: {e}')
            self._log(f'capture comments BR failed: {e}')

    def _ensure_wxocr(self):
        try:
            click_bin = os.path.join(ROOT_DIR, 'scripts', 'wxocr')
            if not os.path.exists(click_bin):
                build_sh = os.path.join(ROOT_DIR, 'scripts', 'build_ocr.sh')
                self._log('wxocr not found; attempting build_ocr.sh')
                r = subprocess.run(["bash", build_sh], capture_output=True, text=True)
                self._log(f'build_ocr rc={r.returncode} out={r.stdout!r} err={r.stderr!r}')
            return os.path.join(ROOT_DIR, 'scripts', 'wxocr')
        except Exception as e:
            self._log(f'ensure wxocr failed: {e}')
            return None

    def start_ocr_cmd(self):
        if self.ocr_proc is not None or (self.cloud_thread is not None and self.cloud_thread.is_alive()):
            messagebox.showinfo('已在运行', '评论抓取已在运行。')
            return
        if not self.comments_rect:
            messagebox.showwarning('未设置区域', '请先捕捉评论区左上/右下坐标。')
            return
        try:
            self.ocr_stop.clear()
            self.ocr_log_file = os.path.join(self.log_path, 'ocr.log')
            # 本地 OCR 已禁用：不再启动 wxocr 进程
            self.ocr_proc = None
            self.ocr_thread = None
            # Cloud OCR thread
            if self.cloud_enabled_var.get():
                self.cloud_thread = threading.Thread(target=self._cloud_ocr_loop, daemon=True)
                self.cloud_thread.start()
            self.status_var.set('评论抓取已启动')
            self._log('ocr started (cloud-only)')
        except Exception as e:
            self._log(f'ocr start failed: {e}')
            messagebox.showerror('启动失败', f'无法启动 OCR：{e}')

    def stop_ocr_cmd(self):
        self.ocr_stop.set()
        if self.ocr_proc is not None:
            try:
                self._terminate_proc(self.ocr_proc)
            except Exception:
                pass
            self.ocr_proc = None
        # No hard join to avoid GUI block; threads are daemons and will exit
        self.status_var.set('评论抓取已停止')
        self._log('ocr stopped')

    def _ocr_reader(self):
        # Read stdout lines (JSON per frame), write new comments to ocr.log with de-dup
        try:
            if self.ocr_proc is None or self.ocr_proc.stdout is None:
                return
            for line in self.ocr_proc.stdout:
                if self.ocr_stop.is_set():
                    break
                line = line.strip()
                if not line:
                    continue
                try:
                    data = json.loads(line)
                    ts = data.get('ts')
                    lines = data.get('lines', [])
                    new_count = 0
                    for item in lines:
                        text = (item.get('text') or '').strip()
                        if not text:
                            continue
                        # Basic noise filter: keep Chinese lines or sufficiently long tokens
                        try:
                            if not any('\u4e00' <= ch <= '\u9fff' for ch in text) and len(text) < 3:
                                continue
                        except Exception:
                            pass
                        if self._dedupe_seen(text):
                            continue
                        self._append_ocr_log(ts, text)
                        new_count += 1
                    if new_count:
                        self.status_var.set(f'OCR 新评论: {new_count}')
                except Exception as e:
                    self._log(f'ocr parse error: {e}')
        except Exception as e:
            self._log(f'ocr reader error: {e}')

    def _dedupe_seen(self, text: str, window_size: int = 200, ttl_sec: float = 60.0) -> bool:
        now = time.time()
        # expire
        self.recent_texts = [(t, s) for (t, s) in self.recent_texts if now - t < ttl_sec]
        for _, s in self.recent_texts:
            if s == text:
                return True
        self.recent_texts.append((now, text))
        if len(self.recent_texts) > window_size:
            self.recent_texts = self.recent_texts[-window_size:]
        return False

    def _append_ocr_log(self, ts: str, text: str):
        try:
            with open(self.ocr_log_file, 'a', encoding='utf-8') as f:
                f.write(f'[{ts}] {text}\n')
        except Exception:
            pass


    def save_openai_key_cmd(self):
        try:
            key = (self.openai_key_var.get() or '').strip()
            if not key:
                messagebox.showwarning('Key 为空', '请输入 OpenAI API Key。')
                return
            self.cfg['openai_api_key'] = key
            self.cfg['openai_model'] = self.openai_model_var.get()
            save_config(self.cfg)
            messagebox.showinfo('已保存', 'OpenAI Key 已保存到本地配置（仅本机）。')
        except Exception as e:
            self._log(f'save_openai_key failed: {e}')
            messagebox.showerror('保存失败', f'无法保存 Key：{e}')

    def _cloud_ocr_loop(self):
        try:
            # Resolve API key
            api_key = (self.openai_key_var.get() or '').strip() or os.environ.get('OPENAI_API_KEY', '')
            if not api_key:
                self._log('cloud-ocr: no API key; disabled')
                return
            try:
                interval = float(self.cloud_interval_var.get())
            except Exception:
                interval = 5.0
            interval = max(2.0, min(60.0, interval))
            model = self.openai_model_var.get()
            frames_dir = os.path.join(self.log_path, 'frames')
            os.makedirs(frames_dir, exist_ok=True)
            out_jsonl = os.path.join(self.log_path, 'ocr.openai.jsonl')
            self._log(f'cloud-ocr started interval={interval}s model={model}')
            while not self.ocr_stop.is_set():
                # Capture
                if not self.comments_rect:
                    time.sleep(0.5); continue
                x1, y1, x2, y2 = self.comments_rect
                rx, ry = int(min(x1, x2)), int(min(y1, y2))
                rw, rh = int(abs(x2 - x1)), int(abs(y2 - y1))
                if rw <= 0 or rh <= 0:
                    time.sleep(0.5); continue
                ts = time.strftime('%Y%m%d-%H%M%S')
                img_path = os.path.join(frames_dir, f'cloud-{ts}.png')
                r = subprocess.run(['screencapture', '-x', '-R', f'{rx},{ry},{rw},{rh}', img_path], capture_output=True, text=True)
                if r.returncode != 0 or not os.path.exists(img_path):
                    self._log(f'cloud-ocr capture fail rc={r.returncode} err={r.stderr!r}')
                    # Sleep a bit and retry next loop
                    for _ in range(int(interval * 10)):
                        if self.ocr_stop.is_set(): break
                        time.sleep(0.1)
                    continue
                # Encode image as data URI
                try:
                    with open(img_path, 'rb') as f:
                        b64 = base64.b64encode(f.read()).decode('ascii')
                    data_uri = f'data:image/png;base64,{b64}'
                except Exception as e:
                    self._log(f'cloud-ocr encode fail: {e}')
                    time.sleep(1.0)
                    continue
                # Build payload: relaxed prompt -> pure transcription (one line per comment)
                prompt = (
                    '只做OCR逐行转写：按屏幕从上到下输出评论文本，尽量还原中文与表情。'
                    '只输出纯文本，每条评论占一行，不要任何解释或附加内容。'
                )
                payload = {
                    'model': model,
                    'messages': [
                        {
                            'role': 'user',
                            'content': [
                                {'type': 'text', 'text': prompt},
                                {'type': 'image_url', 'image_url': {'url': data_uri, 'detail': 'high'}},
                            ],
                        }
                    ],
                    'max_tokens': 1200,
                }
                try:
                    import urllib.request, urllib.error
                    req = urllib.request.Request(
                        url='https://api.openai.com/v1/chat/completions',
                        data=json.dumps(payload).encode('utf-8'),
                        headers={'Authorization': f'Bearer {api_key}', 'Content-Type': 'application/json'},
                        method='POST',
                    )
                    with urllib.request.urlopen(req, timeout=60) as resp:
                        raw = resp.read().decode('utf-8', errors='replace')
                    resp_obj = json.loads(raw)
                    content = ''
                    try:
                        content = resp_obj['choices'][0]['message']['content']
                    except Exception:
                        content = raw
                    # Parse pure-text lines into list
                    lines = []
                    for ln in (content or '').splitlines():
                        s = ln.strip()
                        if s:
                            lines.append(s)
                    rec = {
                        'ts': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
                        'model': model,
                        'image': img_path,
                        'lines': lines,
                        'raw': content,
                    }
                    with open(out_jsonl, 'a', encoding='utf-8') as f:
                        f.write(json.dumps(rec, ensure_ascii=False) + '\n')
                    self.status_var.set('云OCR 已写入一批结果')
                except Exception as e:
                    self._log(f'cloud-ocr request fail: {e}')
                # sleep until next
                for _ in range(int(interval * 10)):
                    if self.ocr_stop.is_set():
                        break
                    time.sleep(0.1)
            self._log('cloud-ocr stopped')
        except Exception as e:
            self._log(f'cloud-ocr loop error: {e}')

    # === ASR Mic integration ===
    def start_asr_cmd(self):
        # Persist config
        try:
            self.cfg['asr_device'] = self.asr_device_var.get()
            self.cfg['asr_segment_secs'] = int(self.asr_seg_var.get())
            self.cfg['asr_model'] = self.asr_model_var.get()
            self.cfg['asr_compute'] = self.asr_compute_var.get()
            save_config(self.cfg)
        except Exception:
            pass
        try:
            seg = max(3, min(15, int(self.asr_seg_var.get())))
        except Exception:
            seg = 6
        device_spec = self.asr_device_var.get() or ':0'
        env = os.environ.copy()
        env['SEG_SECS'] = str(seg)
        env['DEVICE_SPEC'] = device_spec
        audio_dir = os.path.join(self.log_path, 'audio')
        os.makedirs(audio_dir, exist_ok=True)
        # 录音进程（ffmpeg 分段）
        rec_sh = os.path.join(ROOT_DIR, 'scripts', 'asr_mic.sh')
        try:
            # Recorder log file
            self._asr_rec_log = open(self.asr_rec_log_path, 'a', encoding='utf-8')
            self.asr_rec_proc = subprocess.Popen(
                ['bash', rec_sh],
                stdout=self._asr_rec_log, stderr=subprocess.STDOUT,
                text=True, env=env, start_new_session=True,
            )
            # Write recorder pidfile
            try:
                pdir = os.path.join(self.log_path, 'pids')
                os.makedirs(pdir, exist_ok=True)
                with open(os.path.join(pdir, 'asr_rec.pid'), 'w') as f:
                    f.write(str(self.asr_rec_proc.pid))
            except Exception:
                pass
        except Exception as e:
            self._log(f'asr rec start fail: {e}')
            messagebox.showerror('ASR启动失败', f'无法启动录音：{e}')
            return
        # 转写进程（faster-whisper）
        asr_py = os.path.join(ROOT_DIR, 'asr', 'transcribe.py')
        asr_out = os.path.join(self.log_path, 'asr.jsonl')
        env2 = os.environ.copy()
        env2['FWHISPER_MODEL'] = self.asr_model_var.get()
        env2['FWHISPER_DEVICE'] = 'auto'
        env2['FWHISPER_COMPUTE'] = self.asr_compute_var.get()
        try:
            # Transcriber log file
            self._asr_worker_log = open(self.asr_worker_log_path, 'a', encoding='utf-8')
            self.asr_proc = subprocess.Popen(
                ['python3', asr_py, '--watch', audio_dir, '--out', asr_out],
                stdout=self._asr_worker_log, stderr=subprocess.STDOUT,
                text=True, env=env2, start_new_session=True,
            )
            # Write transcriber pidfile
            try:
                pdir = os.path.join(self.log_path, 'pids')
                os.makedirs(pdir, exist_ok=True)
                with open(os.path.join(pdir, 'asr_trans.pid'), 'w') as f:
                    f.write(str(self.asr_proc.pid))
            except Exception:
                pass
        except Exception as e:
            self._log(f'asr transcriber start fail: {e}')
            messagebox.showerror('ASR启动失败', f'无法启动转写：{e}')
            try:
                self._terminate_proc(self.asr_rec_proc)
            except Exception:
                pass
            return
        self.status_var.set('ASR 已启动（麦克风外放）')
        self._log('asr started (mic)')

    def stop_asr_cmd(self):
        for p in ['asr_proc', 'asr_rec_proc']:
            proc = getattr(self, p, None)
            if proc is not None:
                try:
                    self._terminate_proc(proc)
                except Exception:
                    pass
                setattr(self, p, None)
        # Close log files if opened
        for h in ['_asr_rec_log', '_asr_worker_log']:
            fh = getattr(self, h, None)
            if fh:
                try:
                    fh.close()
                except Exception:
                    pass
                setattr(self, h, None)
        # Also try pidfiles
        try:
            pdir = os.path.join(self.log_path, 'pids')
            for name in ('asr_trans.pid', 'asr_rec.pid'):
                pf = os.path.join(pdir, name)
                if os.path.exists(pf):
                    with open(pf, 'r') as f:
                        spid = f.read().strip()
                    try:
                        os.kill(int(spid), signal.SIGTERM)
                    except Exception:
                        pass
                    try:
                        os.remove(pf)
                    except Exception:
                        pass
        except Exception:
            pass
        self.status_var.set('ASR 已停止')
        self._log('asr stopped')

    def list_audio_devs_cmd(self):
        try:
            out = subprocess.run(['bash', os.path.join(ROOT_DIR, 'scripts', 'audio_devices.sh')], capture_output=True, text=True)
            if out.returncode == 0:
                messagebox.showinfo('音频设备', out.stdout[:4000])
                self._log('audio devices listed')
            else:
                messagebox.showerror('错误', out.stderr)
        except Exception as e:
            self._log(f'list audio devs error: {e}')
            messagebox.showerror('错误', str(e))

    # === One-click orchestration ===
    def start_all_cmd(self):
        # Ensure keys present
        oai = (self.openai_key_var.get() or '').strip()
        if not oai:
            messagebox.showwarning('缺少 OpenAI Key', '请先在云 OCR 区域填写并保存 OpenAI API Key。')
            return
        dsk = (self.deepseek_key_var.get() or '').strip()
        if not dsk:
            messagebox.showwarning('缺少 DeepSeek Key', '请先在 Agent 区域填写并保存 DeepSeek API Key。')
            return
        # Comments region required
        if not self.comments_rect:
            messagebox.showwarning('未设置评论区', '请先用“捕捉评论区左上/右下”标定区域。')
            return
        # Bring WeChat live room to foreground first
        try:
            activate_wechat()
            self._log('one-click: activated wechat to foreground')
            time.sleep(0.4)
        except Exception:
            pass
        # Clear previous history (logs and segments) to avoid contamination
        try:
            self._clear_history()
        except Exception as e:
            self._log(f'clear history error: {e}')
        # Start OCR
        try:
            self.cloud_enabled_var.set(True)
            self.start_ocr_cmd()
        except Exception:
            pass
        # Start ASR
        try:
            self.start_asr_cmd()
        except Exception:
            pass
        # Start Agent with ignore history
        try:
            self.agent_enabled_var.set(True)
            self.agent_ignore_history_var.set(True)
            self.start_agent_cmd()
        except Exception:
            pass
        self.status_var.set('一键开始：OCR/ASR/Agent 已启动')
        self._log('one-click start issued')

    def stop_all_cmd(self):
        try:
            self.stop_agent_cmd()
        except Exception:
            pass
        try:
            self.stop_asr_cmd()
        except Exception:
            pass
        try:
            self.stop_ocr_cmd()
        except Exception:
            pass
        self.status_var.set('一键停止：已停止 OCR/ASR/Agent')
        self._log('one-click stop issued')

    def _clear_history(self):
        # Truncate/remove previous OCR/ASR/Agent outputs and segments/images
        try:
            # Files to remove
            for fn in ('ocr.openai.jsonl', 'asr.jsonl', 'agent.jsonl'):
                p = os.path.join(self.log_path, fn)
                if os.path.exists(p):
                    try:
                        os.remove(p)
                        self._log(f'cleared file: {p}')
                    except Exception:
                        pass
            # Audio segments
            audio_dir = os.path.join(self.log_path, 'audio')
            if os.path.isdir(audio_dir):
                for name in os.listdir(audio_dir):
                    if name.startswith('seg-') and name.lower().endswith('.wav'):
                        fp = os.path.join(audio_dir, name)
                        try:
                            os.remove(fp)
                        except Exception:
                            pass
                self._log('cleared audio segments')
            # Frames images
            frames_dir = os.path.join(self.log_path, 'frames')
            if os.path.isdir(frames_dir):
                for name in os.listdir(frames_dir):
                    if name.endswith('.png'):
                        fp = os.path.join(frames_dir, name)
                        try:
                            os.remove(fp)
                        except Exception:
                            pass
                self._log('cleared frames images')
            # PID files
            pids_dir = os.path.join(self.log_path, 'pids')
            if os.path.isdir(pids_dir):
                for name in os.listdir(pids_dir):
                    if name.endswith('.pid'):
                        fp = os.path.join(pids_dir, name)
                        try:
                            os.remove(fp)
                        except Exception:
                            pass
            # Reset in-memory de-dupe/state
            self.agent_last_idx = {'ocr': 0, 'asr': 0}
            self.agent_seen_ocr_set.clear(); self.agent_seen_ocr_list.clear()
            self.agent_seen_asr_set.clear(); self.agent_seen_asr_list.clear()
            self.recent_texts = []
        except Exception as e:
            self._log(f'_clear_history error: {e}')

    # === DeepSeek Agent integration ===
    def save_deepseek_key_cmd(self):
        try:
            self.cfg['deepseek_api_key'] = (self.deepseek_key_var.get() or '').strip()
            self.cfg['deepseek_model'] = self.deepseek_model_var.get()
            self.cfg['deepseek_base'] = self.deepseek_base_var.get()
            self.cfg['agent_interval'] = float(self.agent_interval_var.get())
            self.cfg['agent_auto_send'] = bool(self.agent_auto_send_var.get())
            # persona & rate limits
            try:
                persona = self.agent_persona_txt.get('1.0', 'end').strip()
            except Exception:
                persona = ''
            self.cfg['agent_persona'] = persona or '你是直播间的友好观众，用中文自然口吻简短回应，避免敏感内容。限制：不超过40字；可适度使用表情；没内容就返回空字符串。'
            try:
                self.cfg['agent_min_interval'] = int(self.agent_min_interval_var.get())
            except Exception:
                self.cfg['agent_min_interval'] = 10
            try:
                self.cfg['agent_max_per_min'] = int(self.agent_max_per_min_var.get())
            except Exception:
                self.cfg['agent_max_per_min'] = 4
            self.cfg['agent_ignore_history'] = bool(self.agent_ignore_history_var.get())
            save_config(self.cfg)
            messagebox.showinfo('已保存', 'DeepSeek 配置已保存。')
        except Exception as e:
            self._log(f'save_deepseek_key failed: {e}')
            messagebox.showerror('保存失败', f'无法保存：{e}')

    def start_agent_cmd(self):
        if self.agent_thread and self.agent_thread.is_alive():
            messagebox.showinfo('已在运行', 'Agent 已在运行。')
            return
        if not self.agent_enabled_var.get():
            messagebox.showwarning('未启用', '请先勾选“启用 Agent（试验性）”。')
            return
        key = (self.deepseek_key_var.get() or '').strip()
        if not key:
            messagebox.showwarning('Key 为空', '请先填写 DeepSeek API Key 并保存。')
            return
        self.agent_stop.clear()
        try:
            self._init_agent_offsets(ignore_history=self.agent_ignore_history_var.get())
        except Exception:
            pass
        self.agent_thread = threading.Thread(target=self._agent_loop, daemon=True)
        self.agent_thread.start()
        self._log('agent started')
        self.status_var.set('Agent 已启动')

    def stop_agent_cmd(self):
        try:
            self.agent_stop.set()
        except Exception:
            pass
        self._log('agent stopped')
        self.status_var.set('Agent 已停止')

    def _agent_loop(self):
        try:
            out_jsonl = os.path.join(self.log_path, 'agent.jsonl')
            ocr_path = os.path.join(self.log_path, 'ocr.openai.jsonl')
            asr_path = os.path.join(self.log_path, 'asr.jsonl')
            interval = float(self.agent_interval_var.get() or 10)
            interval = max(5.0, min(60.0, interval))
            while not self.agent_stop.is_set():
                # Read new OCR lines
                ocr_lines = self._read_new_ocr_lines(ocr_path)
                asr_texts = self._read_new_asr_lines(asr_path)
                if ocr_lines or asr_texts:
                    prompt = self._build_agent_prompt(ocr_lines, asr_texts)
                    reply = self._call_deepseek(prompt)
                    rec = {
                        'ts': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
                        'prompt_preview': prompt[:4000],
                        'reply': reply,
                        'auto_sent': False,
                    }
                    # Auto send if configured, reply non-empty, and under rate limits
                    if reply and self.agent_auto_send_var.get():
                        if self._can_send_now():
                            try:
                                self.msg_var.set(reply)
                                self.send_message_cmd()
                                rec['auto_sent'] = True
                                self._mark_sent()
                            except Exception as e:
                                self._log(f'agent send failed: {e}')
                        else:
                            rec['auto_sent'] = False
                            rec['rate_limited'] = True
                    try:
                        with open(out_jsonl, 'a', encoding='utf-8') as f:
                            f.write(json.dumps(rec, ensure_ascii=False) + '\n')
                    except Exception:
                        pass
                # sleep
                for _ in range(int(interval*10)):
                    if self.agent_stop.is_set():
                        break
                    time.sleep(0.1)
        except Exception as e:
            self._log(f'agent loop error: {e}')

    # Rate limiting helpers
    def _can_send_now(self) -> bool:
        try:
            now = time.time()
            # min interval
            try:
                min_iv = int(self.agent_min_interval_var.get())
            except Exception:
                min_iv = 10
            if hasattr(self, 'agent_send_times') and self.agent_send_times:
                if now - self.agent_send_times[-1] < max(1, min_iv):
                    return False
            # per-minute cap
            try:
                cap = int(self.agent_max_per_min_var.get())
            except Exception:
                cap = 4
            window_start = now - 60
            recent = [t for t in getattr(self, 'agent_send_times', []) if t >= window_start]
            if len(recent) >= max(1, cap):
                return False
            return True
        except Exception:
            return True

    def _mark_sent(self):
        try:
            now = time.time()
            self.agent_send_times.append(now)
            if len(self.agent_send_times) > 120:
                self.agent_send_times = self.agent_send_times[-120:]
        except Exception:
            pass

    def _init_agent_offsets(self, ignore_history: bool):
        ocr_path = os.path.join(self.log_path, 'ocr.openai.jsonl')
        asr_path = os.path.join(self.log_path, 'asr.jsonl')
        if ignore_history:
            try:
                if os.path.exists(ocr_path):
                    with open(ocr_path, 'r', encoding='utf-8') as f:
                        self.agent_last_idx['ocr'] = sum(1 for _ in f)
                else:
                    self.agent_last_idx['ocr'] = 0
            except Exception:
                self.agent_last_idx['ocr'] = 0
            try:
                if os.path.exists(asr_path):
                    with open(asr_path, 'r', encoding='utf-8') as f:
                        self.agent_last_idx['asr'] = sum(1 for _ in f)
                else:
                    self.agent_last_idx['asr'] = 0
            except Exception:
                self.agent_last_idx['asr'] = 0
            self._log(f'agent offsets initialized to EOF: ocr={self.agent_last_idx["ocr"]} asr={self.agent_last_idx["asr"]}')
        else:
            self.agent_last_idx = {'ocr': 0, 'asr': 0}
            self._log('agent offsets initialized to BOF (process history)')

    def _read_new_ocr_lines(self, path: str):
        try:
            lines = []
            if not os.path.exists(path):
                return lines
            with open(path, 'r', encoding='utf-8') as f:
                all_lines = f.readlines()
            start = self.agent_last_idx.get('ocr', 0)
            for ln in all_lines[start:]:
                try:
                    obj = json.loads(ln)
                    for s in obj.get('lines', [])[:12]:
                        t = (s or '').strip()
                        if not t:
                            continue
                        # De-dup across frames: skip if seen recently
                        if t in self.agent_seen_ocr_set:
                            continue
                        lines.append(t)
                        self.agent_seen_ocr_set.add(t)
                        self.agent_seen_ocr_list.append(t)
                        # Trim memory to 500 items
                        if len(self.agent_seen_ocr_list) > 500:
                            old = self.agent_seen_ocr_list.pop(0)
                            self.agent_seen_ocr_set.discard(old)
                except Exception:
                    continue
            self.agent_last_idx['ocr'] = len(all_lines)
            return lines[-10:]
        except Exception:
            return []

    def _read_new_asr_lines(self, path: str):
        try:
            texts = []
            if not os.path.exists(path):
                return texts
            with open(path, 'r', encoding='utf-8') as f:
                all_lines = f.readlines()
            start = self.agent_last_idx.get('asr', 0)
            for ln in all_lines[start:]:
                try:
                    obj = json.loads(ln)
                    txt = ((obj.get('result') or {}).get('text') or '').strip()
                    if not txt:
                        continue
                    if txt in self.agent_seen_asr_set:
                        continue
                    texts.append(txt)
                    self.agent_seen_asr_set.add(txt)
                    self.agent_seen_asr_list.append(txt)
                    if len(self.agent_seen_asr_list) > 200:
                        old = self.agent_seen_asr_list.pop(0)
                        self.agent_seen_asr_set.discard(old)
                except Exception:
                    continue
            self.agent_last_idx['asr'] = len(all_lines)
            return texts[-5:]
        except Exception:
            return []

    def _build_agent_prompt(self, ocr_lines, asr_texts) -> str:
        ctx = []
        if asr_texts:
            ctx.append('【主播语音要点】\n' + '\n'.join(f'- {t}' for t in asr_texts))
        if ocr_lines:
            ctx.append('【观众评论】\n' + '\n'.join(f'- {l}' for l in ocr_lines))
        ctx_str = '\n\n'.join(ctx) if ctx else '（暂无上下文）'
        try:
            sys_prompt = self.agent_persona_txt.get('1.0', 'end').strip()
        except Exception:
            sys_prompt = ''
        if not sys_prompt:
            sys_prompt = '你是直播间的友好观众，用中文自然口吻简短回应，避免敏感内容。限制：不超过40字；可适度使用表情；没内容就返回空字符串。'
        user_prompt = f'{ctx_str}\n\n请给出一句自然的互动回复：'
        return sys_prompt + '\n\n' + user_prompt

    def _call_deepseek(self, prompt: str) -> str:
        try:
            api_key = (self.deepseek_key_var.get() or '').strip()
            model = self.deepseek_model_var.get() or 'deepseek-chat'
            url = self.deepseek_base_var.get() or 'https://api.deepseek.com/v1/chat/completions'
            payload = {
                'model': model,
                'messages': [
                    {'role': 'user', 'content': prompt}
                ],
                'max_tokens': 120,
            }
            req = urllib.request.Request(
                url=url,
                data=json.dumps(payload).encode('utf-8'),
                headers={'Authorization': f'Bearer {api_key}', 'Content-Type': 'application/json'},
                method='POST'
            )
            with urllib.request.urlopen(req, timeout=60) as resp:
                raw = resp.read().decode('utf-8', errors='replace')
            obj = json.loads(raw)
            content = ''
            try:
                content = obj['choices'][0]['message']['content']
            except Exception:
                content = raw
            return (content or '').strip()
        except Exception as e:
            self._log(f'deepseek error: {e}')
            return ''

    def _terminate_proc(self, proc: subprocess.Popen):
        try:
            # Gracefully terminate whole process group
            pgid = os.getpgid(proc.pid)
            os.killpg(pgid, signal.SIGTERM)
        except Exception:
            try:
                proc.terminate()
            except Exception:
                pass
        # Wait briefly, then force kill if needed
        try:
            proc.wait(timeout=2.0)
        except Exception:
            try:
                pgid = os.getpgid(proc.pid)
                os.killpg(pgid, signal.SIGKILL)
            except Exception:
                try:
                    proc.kill()
                except Exception:
                    pass

    def on_close(self):
        # Stop OCR and ASR workers before quitting
        try:
            self.stop_ocr_cmd()
        except Exception:
            pass
        try:
            self.stop_asr_cmd()
        except Exception:
            pass
        try:
            self.destroy()
        except Exception:
            pass

    # frame saver removed (cloud-only mode)

    def _log(self, msg: str):
        try:
            ts = time.strftime('%Y-%m-%d %H:%M:%S')
            with open(self.log_file, 'a', encoding='utf-8') as f:
                f.write(f'[{ts}] {msg}\n')
        except Exception:
            pass


if __name__ == '__main__':
    app = App()
    app.mainloop()
