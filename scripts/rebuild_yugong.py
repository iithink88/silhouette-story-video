# -*- coding: utf-8 -*-
"""愚公移山 · 几何剪影动画合成脚本（参数化，无硬编码路径，无 Key）。
用法:
    python rebuild_yugong.py [--workdir DIR]
前置: 先跑 animate_yugong.py（生成 animated_segments/）和 gen_audio.py（生成 audios/）
产出: <workdir>/videos/final.mp4
"""
import sys, subprocess, argparse, importlib.util, os
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.stderr.reconfigure(encoding="utf-8", errors="replace")

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import video_assemble as V
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

W, H = V.W, V.H
TITLE_CARD_DUR = V.TITLE_CARD_DUR
XFADE_DUR = V.XFADE_DUR
BG_SHIFT = "#E9E3CE"          # 画面底部留白补色（与愚公纸色一致）


def log(*a):
    print("[YF-BUILD]", *a, flush=True)


def font(p, s):
    try:
        return ImageFont.truetype(p, s)
    except Exception:
        return ImageFont.load_default()


def make_title_card_yugong(WORK: Path, ff: str, theme: str):
    """纸剪风标题卡：米纸底 + 双山剪影 + 标题 + 橙红点缀线。"""
    BG = (244, 240, 224); INK = (38, 34, 30); MOUNT = (96, 88, 80)
    MOUNT2 = (140, 132, 122); ORANGE = (196, 78, 46)
    img = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(img, "RGBA")

    def mtn(cx, base_y, h, w, color):
        left = cx - w/2; right = cx + w/2; peak = base_y - h
        d.polygon([(int(left), int(base_y)), (int(cx - w*0.3), int(base_y - h*0.55)),
                   (int(cx), int(peak)), (int(cx + w*0.3), int(base_y - h*0.55)),
                   (int(right), int(base_y))], fill=color)
    mtn(W*0.30, H*0.78, 300, 520, MOUNT2)
    mtn(W*0.74, H*0.80, 340, 600, MOUNT)
    d.rectangle([0, int(H*0.82), W, H], fill=(206, 196, 176))

    f_title = font("C:/Windows/Fonts/msyhbd.ttc", 132)
    f_en = font("C:/Windows/Fonts/msyh.ttc", 30)
    bb = d.textbbox((0, 0), theme, font=f_title)
    tw = bb[2]-bb[0]; th = bb[3]-bb[1]
    tx = (W-tw)//2-bb[0]; ty = int(H*0.30)-bb[1]
    d.text((tx, ty), theme, font=f_title, fill=INK)
    line_w = 200
    d.rectangle([(W-line_w)//2, ty+th+30, (W+line_w)//2, ty+th+35], fill=ORANGE)
    en = "A  SILHOUETTE  STORY"
    bb3 = d.textbbox((0, 0), en, font=f_en); ew = bb3[2]-bb3[0]
    d.text(((W-ew)//2-bb3[0], int(H*0.30)+th+70), en, font=f_en, fill=(150, 142, 130))

    png = WORK / "videos" / "_title_yugong.png"
    png.parent.mkdir(parents=True, exist_ok=True)
    img.save(png)
    seg = WORK / "videos" / "_title_seg_yg.mp4"
    r = subprocess.run([ff, "-y", "-loop", "1", "-i", str(png),
                        "-t", str(TITLE_CARD_DUR), "-r", "25",
                        "-pix_fmt", "yuv420p", "-c:v", "libx264",
                        "-preset", "fast", "-crf", "18", str(seg)],
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    if r.returncode != 0:
        log("TITLE_ERR", r.stderr[-200:]); sys.exit(1)
    return seg


def build(workdir: Path):
    WORK = Path(workdir).resolve()
    VIDEOS = WORK / "videos"
    VIDEOS.mkdir(parents=True, exist_ok=True)
    ANIM_DIR = WORK / "animated_segments"
    ff = "ffmpeg"

    p = WORK / "story.py"
    spec = importlib.util.spec_from_file_location("story", str(p))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    narrations = mod.NARRATIONS
    theme = getattr(mod, "THEME", "愚公移山")
    plan = {"storyboards": [{"narration": t} for t in narrations]}

    # 1) 标题卡（愚公专用 PIL 标题卡）
    title_seg = make_title_card_yugong(WORK, ff, theme)

    # 2) 动画段（25fps 重编码以统一时间基）
    seg_videos, seg_durations, audio_paths = [], [], []
    for i in range(1, 10):
        anim = ANIM_DIR / f"seg_{i:02d}.mp4"
        audio = WORK / "audios" / f"{i:02d}.mp3"
        if not anim.exists():
            log(f"ERROR: {anim.name} 缺失！请先跑 animate_yugong.py"); sys.exit(1)
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
    seg_videos.insert(0, title_seg)
    seg_durations.insert(0, TITLE_CARD_DUR)

    # 4) xfade
    xfade_out = VIDEOS / "_xfade.mp4"
    if not V.build_xfade_video(seg_videos, seg_durations, xfade_out, ff):
        log("XFADE FAIL"); sys.exit(1)

    # 4.5) 画面上移
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

    # 6) mux
    pre_sub = VIDEOS / "_merged_no_sub.mp4"
    mr = subprocess.run([ff, "-y", "-i", str(shifted), "-i", str(audio_out),
                         "-c", "copy", "-movflags", "+faststart", "-shortest", str(pre_sub)],
                        capture_output=True, text=True, encoding="utf-8", errors="replace")
    if mr.returncode != 0:
        log("MUX FAIL", mr.stderr[-300:]); sys.exit(1)

    # 7) 字幕
    srt_path = V.generate_srt(plan, WORK)

    # 8) 烧录字幕
    final_out = VIDEOS / "final.mp4"
    V._burn_subtitles(pre_sub, srt_path, final_out, ff)

    # 9) 清理
    for f in [xfade_out, shifted, audio_out, pre_sub, silent, title_seg]:
        if f.exists():
            f.unlink()
    for i in range(1, 10):
        pp = VIDEOS / f"_seg25_{i:02d}.mp4"
        if pp.exists():
            pp.unlink()

    log("=" * 50)
    log("FINAL:", final_out, f"{final_out.stat().st_size/1024/1024:.1f} MB")
    log("DONE!")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--workdir", default=".", help="工作目录（默认当前目录）")
    a = ap.parse_args()
    build(a.workdir)
