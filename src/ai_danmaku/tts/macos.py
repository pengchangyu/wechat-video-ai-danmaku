from __future__ import annotations

import subprocess
import time
from pathlib import Path
from typing import Optional


def say_to_file(text: str, out_path: Path, voice: str = "Ting-Ting", fmt: str = "aiff") -> Path:
    out_path = out_path.with_suffix(f".{fmt}")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    # Use macOS built-in 'say' command
    cmd = [
        "say",
        "-v",
        voice,
        "-o",
        str(out_path),
        text,
    ]
    subprocess.run(cmd, check=True)
    return out_path

