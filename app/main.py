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
        # Larger default size; allow resizing
        self.geometry('1100x720')
        self.resizable(True, True)
        # Grid layout: allow middle column to expand
        try:
            for c in range(4):
                self.grid_columnconfigure(c, weight=1 if c == 1 else 0)
        except Exception:
            pass
        # Improve readability on HiDPI
        try:
            self.tk.call('tk', 'scaling', 1.25)
        except Exception:
            pass

        self.cfg = load_config()
        self.log_path = os.path.join(ROOT_DIR, 'logs')
        os.makedirs(self.log_path, exist_ok=True)
        self.log_file = os.path.join(self.log_path, 'app.log')
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

        # Controls
        row = 0
        tk.Label(self, text='第一阶段：在直播间中自动发送消息', font=('Helvetica', 16, 'bold')).grid(row=row, column=0, columnspan=3, pady=10, sticky='w')
        row += 1

        tk.Button(self, text='退出微信', command=self.quit_wechat_cmd, width=14).grid(row=row, column=0, padx=6, pady=4)
        tk.Button(self, text='激活微信', command=self.activate_wechat_cmd, width=14).grid(row=row, column=1, padx=6, pady=4)
        tk.Button(self, text='权限提示', command=self.perm_hint_cmd, width=14).grid(row=row, column=2, padx=6, pady=4)
        row += 1

        # Calibration UI
        tk.Label(self, text='校准：点击“捕捉输入框位置/发送按钮位置”后有倒计时，请在倒计时内把鼠标移动到目标上，无需再点击。').grid(row=row, column=0, columnspan=3, pady=6, sticky='w')
        row += 1

        tk.Button(self, text='捕捉输入框位置', command=self.capture_input_pos_cmd, width=18).grid(row=row, column=0, padx=6, pady=4)
        self.pos_label = tk.Label(self, text=self._pos_text())
        self.pos_label.grid(row=row, column=1, columnspan=2, sticky='w')
        row += 1

        tk.Button(self, text='捕捉发送按钮位置', command=self.capture_send_btn_pos_cmd, width=18).grid(row=row, column=0, padx=6, pady=4)
        self.send_pos_label = tk.Label(self, text=self._send_pos_text())
        self.send_pos_label.grid(row=row, column=1, columnspan=2, sticky='w')
        row += 1

        tk.Label(self, text='发送内容').grid(row=row, column=0, sticky='e')
        self.msg_var = tk.StringVar(value='测试消息：你好，主播！')
        tk.Entry(self, textvariable=self.msg_var, width=48).grid(row=row, column=1, columnspan=2, sticky='w', pady=6)
        row += 1

        # Options
        tk.Label(self, text='延时(秒)').grid(row=row, column=0, sticky='e')
        self.delay_var = tk.DoubleVar(value=1.5)
        tk.Entry(self, textvariable=self.delay_var, width=8).grid(row=row, column=1, sticky='w')
        self.minimize_var = tk.BooleanVar(value=True)
        tk.Checkbutton(self, text='发送时最小化本应用', variable=self.minimize_var).grid(row=row, column=2, sticky='w')
        row += 1

        self.use_click_var = tk.BooleanVar(value=False)
        tk.Checkbutton(self, text='使用坐标点击聚焦输入框', variable=self.use_click_var).grid(row=row, column=1, columnspan=2, sticky='w')
        row += 1

        tk.Label(self, text='点击后延时(秒)').grid(row=row, column=0, sticky='e')
        self.post_click_delay_var = tk.DoubleVar(value=0.8)
        tk.Entry(self, textvariable=self.post_click_delay_var, width=8).grid(row=row, column=1, sticky='w')
        row += 1

        self.double_click_var = tk.BooleanVar(value=True)
        tk.Checkbutton(self, text='双击聚焦（展开后再点一次）', variable=self.double_click_var).grid(row=row, column=1, columnspan=2, sticky='w')
        row += 1

        tk.Label(self, text='第二次点击延时(秒)').grid(row=row, column=0, sticky='e')
        self.second_click_delay_var = tk.DoubleVar(value=0.5)
        tk.Entry(self, textvariable=self.second_click_delay_var, width=8).grid(row=row, column=1, sticky='w')
        row += 1

        self.countdown_only_var = tk.BooleanVar(value=True)
        tk.Checkbutton(self, text='仅倒计时发送（不激活/不点击，需手动先点到输入框）', variable=self.countdown_only_var).grid(row=row, column=1, columnspan=2, sticky='w')
        row += 1

        tk.Button(self, text='发送到直播间', command=self.send_message_cmd, width=20).grid(row=row, column=0, padx=6, pady=8, sticky='w')
        self.status_var = tk.StringVar(value='Ready')
        tk.Label(self, textvariable=self.status_var, fg='#555').grid(row=row, column=1, columnspan=2, sticky='w')
        row += 1

        tk.Label(self, text='提示：进入直播间后可用“捕捉输入框位置”记录坐标（倒计时捕捉），发送时可选择是否使用点击聚焦。').grid(row=row, column=0, columnspan=3, pady=6, sticky='w')
        row += 1
        tk.Label(self, text='提示：若回车不发送，请校准“发送按钮位置”，程序将粘贴后点击按钮提交。').grid(row=row, column=0, columnspan=3, pady=6, sticky='w')

        # --- Comments OCR Section ---
        row += 1
        tk.Label(self, text='第二阶段：抓取直播间评论（云 OCR）', font=('Helvetica', 15, 'bold')).grid(row=row, column=0, columnspan=3, pady=10, sticky='w')
        row += 1
        tk.Button(self, text='捕捉评论区左上', command=self.capture_comments_tl_cmd, width=18).grid(row=row, column=0, padx=6, pady=4)
        tk.Button(self, text='捕捉评论区右下', command=self.capture_comments_br_cmd, width=18).grid(row=row, column=1, padx=6, pady=4)
        self.comments_label = tk.Label(self, text=self._comments_text())
        self.comments_label.grid(row=row, column=2, sticky='w')
        row += 1
        tk.Button(self, text='开始抓取评论', command=self.start_ocr_cmd, width=16).grid(row=row, column=2, sticky='w')
        row += 1
        tk.Button(self, text='停止抓取评论', command=self.stop_ocr_cmd, width=16).grid(row=row, column=2, sticky='w')
        row += 1
        # Cloud OCR (OpenAI)
        tk.Label(self, text='云 OCR（OpenAI）').grid(row=row, column=0, sticky='e')
        self.cloud_enabled_var = tk.BooleanVar(value=True)
        tk.Checkbutton(self, text='启用', variable=self.cloud_enabled_var).grid(row=row, column=1, sticky='w')
        tk.Label(self, text='间隔(秒)').grid(row=row, column=2, sticky='e')
        self.cloud_interval_var = tk.DoubleVar(value=5.0)
        tk.Entry(self, textvariable=self.cloud_interval_var, width=8).grid(row=row, column=3, sticky='w')
        row += 1
        tk.Label(self, text='OpenAI API Key').grid(row=row, column=0, sticky='e')
        self.openai_key_var = tk.StringVar(value=self.cfg.get('openai_api_key', os.environ.get('OPENAI_API_KEY', '')))
        tk.Entry(self, textvariable=self.openai_key_var, width=44, show='*').grid(row=row, column=1, columnspan=2, sticky='w')
        tk.Button(self, text='保存Key', command=self.save_openai_key_cmd, width=10).grid(row=row, column=3, sticky='w')
        row += 1
        tk.Label(self, text='OpenAI 模型').grid(row=row, column=0, sticky='e')
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
        tk.OptionMenu(self, self.openai_model_var, 'gpt-4o-mini', 'gpt-4o').grid(row=row, column=1, sticky='w')
        row += 1
        tk.Label(self, text='说明：需授予“屏幕录制”权限；调高 FPS 会占用更多 CPU。').grid(row=row, column=0, columnspan=4, pady=6, sticky='w')

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
            if self.minimize_var.get():
                self.iconify()
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
        # Click the send button if calibrated, else fall back to Return
        sent_ok = False
        if self.send_btn_pos:
            try:
                x2, y2 = self.send_btn_pos
                click_bin = os.path.join(ROOT_DIR, 'scripts', 'wxclick')
                r3 = subprocess.run([click_bin, str(x2), str(y2)], capture_output=True, text=True)
                self._log(f'wxclick send-btn rc={r3.returncode} out={r3.stdout!r} err={r3.stderr!r}')
                sent_ok = (r3.returncode == 0)
            except Exception as e:
                self._log(f'wxclick send-btn error: {e}')
        if not sent_ok:
            r2 = paste_via_applescript_and_return()
            self._log(f'fallback return rc={r2.returncode} out={r2.stdout!r} err={r2.stderr!r}')
            sent_ok = (r2.returncode == 0)
        if sent_ok:
            self.status_var.set('已发送（按钮/回车）')
        else:
            self.status_var.set('发送失败（请检查权限/按钮坐标）')
        # Restore window if minimized
        try:
            self.deiconify()
            self.lift()
        except Exception:
            pass

    def capture_input_pos_cmd(self):
        # Countdown to allow user to place mouse on input box; optionally minimize app to not obstruct
        try:
            # Briefly show countdown in status
            for i in range(3, 0, -1):
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
            for i in range(3, 0, -1):
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
            for i in range(3, 0, -1):
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
            for i in range(3, 0, -1):
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
                self.ocr_proc.terminate()
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
