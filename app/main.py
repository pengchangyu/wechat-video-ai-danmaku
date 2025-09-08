import json
import os
import subprocess
import time
import tkinter as tk
from tkinter import messagebox

from macos.osascript import activate_wechat, quit_wechat, paste_via_applescript_and_return, paste_only_via_applescript, grant_permissions_hint

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
