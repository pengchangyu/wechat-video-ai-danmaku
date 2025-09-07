from __future__ import annotations

import json
import urllib.request
import urllib.error
from typing import List, Optional


def try_ollama_generate(base_url: str, model: str, prompt: str, timeout: int = 10) -> Optional[str]:
    url = f"{base_url.rstrip('/')}/api/generate"
    data = json.dumps({"model": model, "prompt": prompt, "stream": False}).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            j = json.loads(resp.read().decode("utf-8"))
            return j.get("response")
    except (urllib.error.URLError, urllib.error.HTTPError):
        return None


def template_fallback(context: List[str]) -> str:
    base = ["哈哈这个观点挺有意思，想问：", "感觉很有料，能不能再多说说：", "我有个小问题：", "听起来很专业，想了解下："]
    pref = base[hash("|".join(context)) % len(base)]
    hint = context[-1][:40] if context else "刚才的话题"
    return f"{pref}{hint}?"


def build_prompt(context: List[str]) -> str:
    recent = "\n".join(context[-6:])
    sys = (
        "你是直播间里自然互动的观众。要求：简短、友好、避免广告语，"
        "像人与人聊天一样，不要连续发太多。现在请基于最近的语境，提出一个自然的问题或评论。\n"
    )
    return f"{sys}\n[最近弹幕]\n{recent}\n[输出]"

