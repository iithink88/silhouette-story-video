# -*- coding: utf-8 -*-
"""
silhouette-story-video · 公共工具
无凭证依赖：本技能完全本地运行（PIL 渲染 + edge-tts 配音 + ffmpeg 合成），
不需要任何 API Key / 付费服务。
"""
import sys
from pathlib import Path

# ── UTF-8 强制（Windows 控制台/管道 GBK 乱码防护）──
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")


def log(*args):
    """UTF-8 安全日志"""
    msg = " ".join(str(a) for a in args)
    try:
        print(msg, flush=True)
    except UnicodeEncodeError:
        print(msg.encode("utf-8", "replace").decode("utf-8", "replace"), flush=True)


def out_dir_from_arg(arg: str) -> Path:
    """从命令行参数解析工作目录，并确保子目录存在"""
    d = Path(arg).expanduser().resolve()
    (d / "audios").mkdir(parents=True, exist_ok=True)
    (d / "videos").mkdir(parents=True, exist_ok=True)
    (d / "animated_segments").mkdir(parents=True, exist_ok=True)
    return d
