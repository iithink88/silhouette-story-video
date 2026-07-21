# -*- coding: utf-8 -*-
"""龟兔赛跑 · 几何剪影动画合成脚本（参数化，无硬编码路径，无 Key）。
用法:
    python rebuild_animated.py [--workdir DIR]
前置: 先跑 animate_segments.py（生成 animated_segments/）和 gen_audio.py（生成 audios/）
产出: <workdir>/videos/final.mp4
"""
import sys, subprocess, argparse, importlib.util, os
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.stderr.reconfigure(encoding="utf-8", errors="replace")

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import video_assemble as V
from pathlib import Path

W, H = V.W, V.H
TITLE_CARD_DUR = V.TITLE_CARD_DUR
XFADE_DUR = V.XFADE_DUR
BG_SHIFT = "#F3E7CE"          # 画面底部留白补色（与动画纸色一致）


def log(*a):
    print("[ANIM-BUILD]", *a, flush=True)


def load_story(workdir: Path):
    p = workdir / "story.py"
    spec = importlib.util.spec_from_file_location("story", str(p))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.NARRATIONS, getattr(mod, "THEME", "剪影故事")


def build(workdir: Path):
    WORK = Path(workdir).resolve()
    VIDEOS = WORK / "videos"
    VIDEOS.mkdir(parents=True, exist_ok=True)
    ANIM_DIR = WORK / "animated_segments"
    ff = "ffmpeg"

    narrations, theme = load_story(WORK)
    plan = {"storyboards": [{"narration": t} for t in narrations]}

    # 1) 标题卡（优先用工作目录里的 title_card.png / title_card_jimeng.png；否则 PIL 手绘）
    custom = None
    for cand in ["title_card_jimeng.png", "title_card.png"]:
        if (WORK / cand).exists():
            custom = WORK / cand
            break
    if custom:
        seg = VIDEOS / "_title_seg.mp4"
        r = subprocess.run([ff, "-y", "-loop", "1", "-i", str(custom),
                            "-t", str(TITLE_CARD_DUR), "-r", "25",
                            "-pix_fmt", "yuv420p", "-c:v", "libx264",
                            "-preset", "fast", "-crf", "18", str(seg)],
                           capture_output=True, text=True, encoding="utf-8", errors="replace")
        if r.returncode != 0:
            log("TITLE_ERR", r.stderr[-200:]); sys.exit(1)
        title_seg = seg
        log("title card:", custom.name)
    else:
        title_seg = V.make_title_card(plan, WORK, ff)
        if title_seg is None:
            log("TITLE FAIL"); sys.exit(1)

    # 统一标题卡 25fps
    title_seg_25 = VIDEOS / "_title_seg25.mp4"
    subprocess.run([ff, "-y", "-i", str(title_seg), "-r", "25",
                   "-c:v", "libx264", "-pix_fmt", "yuv420p",
                   "-preset", "fast", "-crf", "18", str(title_seg_25)],
                  capture_output=True, check=True)

    # 2) 动画段（25fps 重编码以统一时间基）
    seg_videos, seg_durations, audio_paths = [], [], []
    for i in range(1, 10):
        anim = ANIM_DIR / f"seg_{i:02d}.mp4"
        audio = WORK / "audios" / f"{i:02d}.mp3"
        if not anim.exists():
            log(f"ERROR: {anim.name} 缺失！请先跑 animate_segments.py"); sys.exit(1)
        dur = V.get_audio_duration(audio)
        anim25 = VIDEOS / f"_seg25_{i:02d}.mp4"
        re = subprocess.run([ff, "-y", "-i", str(anim), "-r", "25",
                             "-c:v", "libx264", "-pix_fmt", "yuv420p",
                             "-preset", "fast", "-crf", "18", str(anim25)],
                            capture_output=True, text=True, encoding="utf-8", errors="replace")
        if re.returncode != 0:
            log(f"REENC ERR seg{i}", re.stderr[-200:]); sys.exit(1)
        seg_videos.append(anim25)
        seg_durations.append(dur)
        audio_paths.append(audio)
        log(f"seg {i:02d}: {dur:.2f}s")

    # 3) 插入标题卡
    seg_videos.insert(0, title_seg_25)
    seg_durations.insert(0, TITLE_CARD_DUR)

    # 4) xfade 交叉淡入淡出
    xfade_out = VIDEOS / "_xfade.mp4"
    if not V.build_xfade_video(seg_videos, seg_durations, xfade_out, ff):
        log("XFADE FAIL"); sys.exit(1)

    # 4.5) 画面上移：内容整体上移 72px，底部补纸色留白给字幕（避免字幕挡动画）
    shifted = VIDEOS / "_xfade_shifted.mp4"
    if not V.shift_up(xfade_out, shifted, ff, shift_px=72, bg_color=BG_SHIFT):
        log("SHIFT FAIL"); sys.exit(1)

    # 5) 音频：静音 3 秒 + 9 段旁白
    silent = VIDEOS / "_silent.aac"
    subprocess.run([ff, "-y", "-f", "lavfi", "-i", "anullsrc=r=44100:cl=stereo",
                    "-t", str(TITLE_CARD_DUR), "-c:a", "aac", "-b:a", "128k", str(silent)],
                   capture_output=True, text=True, encoding="utf-8", errors="replace")
    audio_out = VIDEOS / "_audio.m4a"
    if not V.concat_audio([silent] + audio_paths, audio_out, ff):
        log("AUDIO FAIL"); sys.exit(1)

    # 6) 合并音视频（无字幕）
    pre_sub = VIDEOS / "_merged_no_sub.mp4"
    mr = subprocess.run([ff, "-y", "-i", str(shifted), "-i", str(audio_out),
                         "-c", "copy", "-movflags", "+faststart", "-shortest", str(pre_sub)],
                        capture_output=True, text=True, encoding="utf-8", errors="replace")
    if mr.returncode != 0:
        log("MUX FAIL", mr.stderr[-300:]); sys.exit(1)

    # 7) 字幕（从 narration 生成 SRT，+3s 偏移对齐片头）
    srt_path = V.generate_srt(plan, WORK)

    # 8) 烧录字幕
    final_out = VIDEOS / "final.mp4"
    V._burn_subtitles(pre_sub, srt_path, final_out, ff)

    # 9) 清理
    for f in [xfade_out, shifted, audio_out, pre_sub, silent, title_seg_25]:
        if f.exists():
            f.unlink()
    for i in range(1, 10):
        p = VIDEOS / f"_seg25_{i:02d}.mp4"
        if p.exists():
            p.unlink()

    log("=" * 50)
    log("FINAL:", final_out, f"{final_out.stat().st_size/1024/1024:.1f} MB")
    log("DONE!")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--workdir", default=".", help="工作目录（默认当前目录）")
    a = ap.parse_args()
    build(a.workdir)
