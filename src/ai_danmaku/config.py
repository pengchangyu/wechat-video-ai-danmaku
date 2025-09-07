from __future__ import annotations

import dataclasses
import json
import os
from pathlib import Path
from typing import Optional, Dict, Any


@dataclasses.dataclass
class Selectors:
    chat_items: Optional[str] = None
    chat_text: Optional[str] = None
    send_button: Optional[str] = None


@dataclasses.dataclass
class OllamaConfig:
    base_url: str = "http://localhost:11434"
    model: str = "qwen2.5:7b"
    timeout_sec: int = 10


@dataclasses.dataclass
class TTSConfig:
    voice: str = "Ting-Ting"
    format: str = "aiff"


@dataclasses.dataclass
class LoopConfig:
    gen_interval_sec: int = 45


@dataclasses.dataclass
class AppConfig:
    live_url: str = ""
    selectors: Selectors = dataclasses.field(default_factory=Selectors)
    ollama: OllamaConfig = dataclasses.field(default_factory=OllamaConfig)
    tts: TTSConfig = dataclasses.field(default_factory=TTSConfig)
    loop: LoopConfig = dataclasses.field(default_factory=LoopConfig)

    @staticmethod
    def load(path: Path) -> "AppConfig":
        if not path.exists():
            return AppConfig()
        data = json.loads(path.read_text(encoding="utf-8"))
        return AppConfig(
            live_url=data.get("live_url", ""),
            selectors=Selectors(**data.get("selectors", {})),
            ollama=OllamaConfig(**data.get("ollama", {})),
            tts=TTSConfig(**data.get("tts", {})),
            loop=LoopConfig(**data.get("loop", {})),
        )

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(dataclasses.asdict(self), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )


def default_paths(base: Optional[Path] = None) -> Dict[str, Path]:
    if base is None:
        base = Path(__file__).resolve().parents[2]
    data = base / "data"
    return {
        "base": base,
        "data": data,
        "db": data / "app.db",
        "tts": data / "tts",
        "config": base / "config.json",
    }
