import subprocess
from typing import Optional


def osa(script: str) -> subprocess.CompletedProcess:
    return subprocess.run(["osascript", "-e", script], capture_output=True, text=True)


def activate_wechat():
    return osa('tell application "WeChat" to activate')


def quit_wechat():
    # Try polite quit first
    proc = osa('tell application "WeChat" to quit')
    return proc


def paste_via_applescript_and_return():
    script = (
        'tell application "System Events"\n'
        '  keystroke "v" using {command down}\n'
        '  key code 36\n'
        'end tell'
    )
    return osa(script)


def grant_permissions_hint() -> str:
    return (
        "On macOS, grant Accessibility permissions to Terminal/iTerm or the built app:\n"
        "System Settings > Privacy & Security > Accessibility > enable for your terminal/Python."
    )

