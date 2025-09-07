from __future__ import annotations

import subprocess
import time
from dataclasses import dataclass
from typing import List, Optional

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys


@dataclass
class Selectors:
    chat_items: Optional[str] = None
    chat_text: Optional[str] = None
    send_button: Optional[str] = None


class SafariController:
    def __init__(self, live_url: str, selectors: Selectors):
        self.live_url = live_url
        self.selectors = selectors
        self.driver: Optional[webdriver.Safari] = None

    def start(self):
        # Requires Safari Develop -> Allow Remote Automation
        self.driver = webdriver.Safari()
        self.driver.set_window_size(1280, 900)
        # If live_url is empty, open a blank page and rely on paste fallback
        url = self.live_url.strip() or "about:blank"
        self.driver.get(url)

    def stop(self):
        try:
            if self.driver:
                self.driver.quit()
        except Exception:
            pass

    def scrape_danmaku(self, limit: int = 30) -> List[str]:
        if not self.driver:
            return []
        if not self.selectors.chat_items:
            return []
        try:
            nodes = self.driver.find_elements(By.CSS_SELECTOR, self.selectors.chat_items)
            texts = [n.text.strip() for n in nodes if n.text.strip()]
            return texts[-limit:]
        except Exception:
            return []

    def send_text_dom(self, text: str) -> bool:
        if not self.driver:
            return False
        if not self.selectors.chat_text:
            return False
        try:
            input_el = self.driver.find_element(By.CSS_SELECTOR, self.selectors.chat_text)
            input_el.click()
            input_el.clear()
            input_el.send_keys(text)
            # Either press Enter or click send button
            if self.selectors.send_button:
                try:
                    btn = self.driver.find_element(By.CSS_SELECTOR, self.selectors.send_button)
                    btn.click()
                except Exception:
                    input_el.send_keys(Keys.ENTER)
            else:
                input_el.send_keys(Keys.ENTER)
            return True
        except Exception:
            return False

    def send_text_paste(self, text: str) -> bool:
        # Fallback: bring Safari to front, copy to clipboard and paste+Enter via AppleScript
        try:
            subprocess.run(["/usr/bin/osascript", "-e", f'set the clipboard to "{text}"'], check=True)
            osa = (
                'tell application "Safari" to activate\n'
                'delay 0.2\n'
                'tell application "System Events" to keystroke "v" using command down\n'
                'delay 0.05\n'
                'tell application "System Events" to key code 36'  # return key
            )
            subprocess.run(["/usr/bin/osascript", "-e", osa], check=True)
            return True
        except Exception:
            return False
