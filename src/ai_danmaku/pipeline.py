from __future__ import annotations

import time
from pathlib import Path
from typing import List

from .config import AppConfig, default_paths
from .storage import db as dbmod
from .automation.safari import SafariController, Selectors as SafariSelectors
from .generation.llm import build_prompt, try_ollama_generate, template_fallback
from .tts.macos import say_to_file


class Pipeline:
    def __init__(self, cfg: AppConfig, paths: dict[str, Path]):
        self.cfg = cfg
        self.paths = paths
        self.conn = dbmod.connect(paths["db"])
        self.controller = SafariController(
            cfg.live_url,
            SafariSelectors(
                chat_items=cfg.selectors.chat_items,
                chat_text=cfg.selectors.chat_text,
                send_button=cfg.selectors.send_button,
            ),
        )
        self.recent_cache: List[str] = []

    def start(self):
        self.controller.start()

    def stop(self):
        self.controller.stop()

    def _update_recent(self):
        items = self.controller.scrape_danmaku(limit=60)
        if not items:
            return
        # naive de-dup
        for t in items:
            if t not in self.recent_cache:
                self.recent_cache.append(t)
        self.recent_cache = self.recent_cache[-100:]

    def generate_candidate(self) -> str:
        ctx = self.recent_cache[-10:]
        prompt = build_prompt(ctx)
        out = try_ollama_generate(self.cfg.ollama.base_url, self.cfg.ollama.model, prompt, self.cfg.ollama.timeout_sec)
        if not out:
            out = template_fallback(ctx)
        return out.strip()

    def tts_and_archive(self, text: str, msg_id: int) -> Path:
        out_dir = self.paths["tts"]
        out = out_dir / f"msg_{msg_id}"
        audio = say_to_file(text, out, voice=self.cfg.tts.voice, fmt=self.cfg.tts.format)
        dbmod.insert_tts(self.conn, msg_id, audio, duration_sec=0.0, voice=self.cfg.tts.voice)
        return audio

    def send(self, text: str) -> bool:
        # Prefer DOM sending when selectors provided
        ok = False
        if self.cfg.selectors.chat_text:
            ok = self.controller.send_text_dom(text)
        if not ok:
            ok = self.controller.send_text_paste(text)
        return ok

