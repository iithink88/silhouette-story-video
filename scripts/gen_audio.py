# -*- coding: utf-8 -*-
"""用 edge-tts (微软晓晓声，免费) 生成旁白 mp3。
用法:
    python gen_audio.py [--workdir DIR] [--story story.py] [--voice zh-CN-XiaoxiaoNeural]
输出: <workdir>/audios/01.mp3 .. 09.mp3

说明: 完全免费，无需任何 API Key。story.py 需含 NARRATIONS 列表（每段一句旁白）。
"""
import sys, asyncio, argparse, importlib.util, os
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.stderr.reconfigure(encoding="utf-8", errors="replace")
from pathlib import Path
import edge_tts


def load_narrations(story_path: Path):
    spec = importlib.util.spec_from_file_location("story", str(story_path))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.NARRATIONS


async def run(workdir: Path, story_path: Path, voice: str):
    narrations = load_narrations(story_path)
    aud = workdir / "audios"
    aud.mkdir(parents=True, exist_ok=True)
    for i, text in enumerate(narrations, 1):
        out = aud / f"{i:02d}.mp3"
        if out.exists():
            print(f"skip {out.name} (exists)")
            continue
        await edge_tts.Communicate(text, voice).save(str(out))
        print(f"OK {out.name} ({len(text)}字)")
    print("ALL AUDIO DONE")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--workdir", default=".", help="工作目录（默认当前目录）")
    ap.add_argument("--story", default=None, help="story.py 路径，默认 <workdir>/story.py")
    ap.add_argument("--voice", default="zh-CN-XiaoxiaoNeural", help="edge-tts 音色")
    a = ap.parse_args()
    sp = Path(a.story) if a.story else (Path(a.workdir) / "story.py")
    if not sp.exists():
        print(f"[ERROR] 未找到 {sp}，请先准备 story.py（含 NARRATIONS 列表）")
        sys.exit(1)
    asyncio.run(run(Path(a.workdir).resolve(), sp, a.voice))
