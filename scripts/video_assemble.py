#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
video_assemble.py v3 — 剪影视频合成器（静止画面 + 交叉淡入淡出版）
特性:
  · 每段图片**完全静止**(无 Ken Burns 缩放、无镜头平移 —— 用户反馈"晃")
  · 段间用 ffmpeg xfade 做真正的 crossfade 交叉淡入淡出转场
  · 字幕烧录: 从 plan.json narration 自动生成 SRT, 白字黑描边底部居中
  · 音视频时长对齐(段时长补偿), 旁白完整不截断
  · 支持 Seedance 真·视频片段替换（优先用 videos/seedance_XX.mp4）

用法: python video_assemble.py <plan.json目录>
输出: videos/final.mp4 (带字幕烧录的完整视频)
"""

import sys
import os
import json
import subprocess
import shutil
import tempfile
from pathlib import Path

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPT_DIR)
from common import log

# ── 常量 ──────────────────────────────────────────────
W, H = 1344, 768          # 画布尺寸（与 image_maker 一致）
FPS = 20                  # 帧率（与原版愚公移山一致）
XFADE_DUR = 0.6           # 段间交叉淡入淡出时长(秒)
FADE_EDGE = 0.35          # 首段淡入 / 末段淡出时长(秒)
TITLE_CARD_DUR = 3.0      # 片头标题卡时长(秒); 设为 0 可关闭片头
TITLE_SUB = ""  # 标题卡副标题：留空=不显示副标题（用户要求删除），写文字则所有标题卡统一显示，改这里即全局生效

# 每段的运动预设 (pan_from_x, pan_from_y, pan_to_x, pan_to_y, zoom_from, zoom_to)
# pan 坐标: 0=左/上, 1=右/下; 仅在 iw*(1-1/zoom) 范围内平移(所以幅度由 zoom 决定)
# 【2026-07-21 用户反馈两轮】① 镜头平移"太晃了"→ 去掉 pan(锁定中心 0.5)
#   ② 居中缩放也"有些晃"→ 去掉 zoom(恒为 1.0)
#   ⇒ 现在每段是**完全静止**的图片, 只有段间用 xfade 交叉淡入淡出转场(用户认可保留)
#   字幕 / 完整旁白(音视频时长对齐) 仍保留
MOTION_PRESETS = [
    (0.5, 0.5, 0.5, 0.5, 1.00, 1.00),   # 完全静止
    (0.5, 0.5, 0.5, 0.5, 1.00, 1.00),   # 完全静止
    (0.5, 0.5, 0.5, 0.5, 1.00, 1.00),   # 完全静止
    (0.5, 0.5, 0.5, 0.5, 1.00, 1.00),   # 完全静止
    (0.5, 0.5, 0.5, 0.5, 1.00, 1.00),   # 完全静止
    (0.5, 0.5, 0.5, 0.5, 1.00, 1.00),   # 完全静止
    (0.5, 0.5, 0.5, 0.5, 1.00, 1.00),   # 完全静止
    (0.5, 0.5, 0.5, 0.5, 1.00, 1.00),   # 完全静止
    (0.5, 0.5, 0.5, 0.5, 1.00, 1.00),   # 完全静止
]


def out_dir_from_arg(arg: str) -> Path:
    return Path(arg).resolve()


def load_plan(directory: Path) -> dict:
    plan_path = directory / "plan.json"
    if not plan_path.exists():
        print(f"[ERROR] plan.json not found in {directory}")
        sys.exit(1)
    return json.loads(plan_path.read_text(encoding="utf-8"))


def get_ffmpeg():
    ff = shutil.which("ffmpeg")
    if not ff:
        print("[ERROR] ffmpeg not found in PATH")
        sys.exit(1)
    return ff


# ── 音频时长 ───────────────────────────────────────────

def get_audio_duration(audio_path: Path) -> float:
    """获取音频时长(秒)，回退固定值"""
    try:
        import mutagen.mp3
        return mutagen.mp3.MP3(str(audio_path)).info.length
    except Exception:
        pass
    try:
        import mutagen
        return mutagen.File(str(audio_path)).info.length
    except Exception:
        pass
    return 5.0


# ── SRT 字幕生成 ──────────────────────────────────────

def generate_srt(plan: dict, out_dir: Path) -> Path:
    storyboards = plan.get("storyboards", [])
    srt_lines = []
    accum_time = 0.0
    for idx, sb in enumerate(storyboards, 1):
        audio_path = out_dir / "audios" / f"{idx:02d}.mp3"
        dur = get_audio_duration(audio_path)
        # 字幕整体偏移 TITLE_CARD_DUR 秒，与「静音片头+正文旁白」对齐，片头期间不显示字幕
        start_s = accum_time + TITLE_CARD_DUR
        end_s = accum_time + dur + TITLE_CARD_DUR
        start_ts = _seconds_to_srt(start_s)
        end_ts = _seconds_to_srt(end_s)
        text = _wrap_text(sb.get("narration", "").replace("\r", " ").replace("\n", " ").strip(),
                          cpl=18, max_lines=2)
        srt_lines.append(f"{idx}")
        srt_lines.append(f"{start_ts} --> {end_ts}")
        srt_lines.append(text)
        srt_lines.append("")
        accum_time += dur   # 只累加旁白时长, 标题卡时长仅在首段加一次(TITLE_CARD_DUR)
    srt_path = out_dir / "subtitles.srt"
    srt_path.write_text("\n".join(srt_lines), encoding="utf-8-sig")
    log("SRT", f"字幕文件已生成: {srt_path.name} ({len(storyboards)} 条)")
    return srt_path


def _wrap_text(text: str, cpl: int = 18, max_lines: int = 2) -> str:
    """
    按「显示宽度」把字幕折成最多 max_lines 行（SRT 内部用真实换行符 \\n）。
    中文/日文等全角字符记 1.0 宽，ASCII/数字记 0.55 宽；每行约 cpl 个全角字符。
    超长时前 max_lines-1 行各占 cpl，最后一行容纳剩余（仍过长则硬截加省略号）。
    """
    def wch(ch: str) -> float:
        return 1.0 if ord(ch) > 0x2E80 else 0.55

    cur, cur_w, lines = "", 0.0, []
    for ch in text:
        cw = wch(ch)
        if cur_w + cw > cpl and cur:
            lines.append(cur)
            cur, cur_w = ch, cw
        else:
            cur += ch
            cur_w += cw
    if cur:
        lines.append(cur)

    if len(lines) > max_lines:
        head = lines[:max_lines - 1]
        tail = "".join(lines[max_lines - 1:])
        if sum(wch(c) for c in tail) > cpl * 1.6:
            tail = tail[:int(cpl * 1.6)] + "…"
        lines = head + [tail]
    return "\n".join(lines)


def _seconds_to_srt(seconds: float) -> str:
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    ms = int((seconds % 1) * 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


# ── 单段视频合成（Ken Burns 缩放+平移 + 淡入/淡出） ──

def make_segment_video(idx: int, img_path: Path, output_path: Path,
                        ff: str, duration: float, motion, is_first, is_last):
    """
    合成单段「视频画面」(无音轨):
      - Ken Burns: zoom(zoom_from→zoom_to) + pan(pan_from→pan_to)
      - 首段淡入 FADE_EDGE 秒, 末段淡出 FADE_EDGE 秒 (供 xfade 衔接)
    平移幅度由 zoom 自动约束在 iw*(1-1/zoom) 范围内, 不会露黑边。
    """
    fx, fy, tx, ty, z0, z1 = motion
    total = max(2, int(round(duration * FPS)))

    # zoompan 表达式: on=输出帧序号(从0), progress p=on/total
    z_expr = f"{z0} + ({z1}-{z0})*(on/{total})"
    # x/y 用 pan 比例 * 可用平移范围(iw*(1-1/zoom))
    x_expr = f"({fx} + ({tx}-{fx})*(on/{total}))*iw*(1-1/zoom)"
    y_expr = f"({fy} + ({ty}-{fy})*(on/{total}))*ih*(1-1/zoom)"

    zoom_cmd = (
        f"zoompan=z='{z_expr}':"
        f"x='{x_expr}':"
        f"y='{y_expr}':"
        f"d={total}:s={W}x{H}:fps={FPS}"
    )
    pad_cmd = f"pad=width={W}:height={H}:x=(ow-iw)/2:y=(oh-ih)/2:color={_hex_to_ff_color('#F5F3EE')}"

    # 淡入/淡出
    fades = []
    if is_first:
        fades.append(f"fade=t=in:st=0:d={FADE_EDGE}:alpha=1")
    if is_last:
        fades.append(f"fade=t=out:st={duration-FADE_EDGE:.3f}:d={FADE_EDGE}:alpha=1")
    fade_cmd = "," + ",".join(fades) if fades else ""

    filter_complex = f"[0:v]{zoom_cmd},{pad_cmd}{fade_cmd}[vout]"

    cmd = [
        ff, "-y",
        "-loop", "1", "-i", str(img_path),
        "-filter_complex", filter_complex,
        "-map", "[vout]",
        "-c:v", "libx264", "-preset", "medium", "-crf", "18",
        "-t", f"{duration:.3f}",
        "-pix_fmt", "yuv420p",
        "-movflags", "+faststart",
        str(output_path),
    ]
    log("SEG", f"shot {idx:02d}: {duration:.1f}s 运动(pan {fx:.2f},{fy:.2f}→{tx:.2f},{ty:.2f} zoom {z0:.2f}→{z1:.2f}) → {output_path.name}")
    result = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if result.returncode != 0:
        log("SEG_ERR", f"shot {idx:02d} FAILED: {result.stderr[-300:]}")

    return output_path.exists()


def _hex_to_ff_color(hex_color: str) -> str:
    return hex_color.replace("#", "0x")


# ── 音频拼接 ───────────────────────────────────────────

def concat_audio(audio_paths: list, out_audio: Path, ff: str):
    """把多段 mp3 按原顺序拼接成一个音频文件(用于最终 mux)"""
    if len(audio_paths) == 1:
        shutil.copy2(audio_paths[0], out_audio)
        return True
    # 用 filter_complex concat (避免文件头不一致问题)
    inputs = []
    for p in audio_paths:
        inputs += ["-i", str(p)]
    n = len(audio_paths)
    cmd = [ff, "-y"] + inputs + [
        "-filter_complex",
        f"concat=n={n}:v=0:a=1[out]",
        "-map", "[out]", "-c:a", "aac", "-b:a", "128k",
        str(out_audio),
    ]
    r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if r.returncode != 0:
        log("AUD_ERR", r.stderr[-300:])
        return False
    return out_audio.exists()


def build_xfade_audio(audio_paths: list, durations: list, out_audio: Path, ff: str):
    """
    与视频 xfade 配套：音频也用 acrossfade 交叉淡化，offset 与视频完全一致，
    这样音频时长 = Σdur - (n-1)*T，与视频对齐，转场处旁白平滑溶解而非被截断。
    """
    n = len(audio_paths)
    if n == 1:
        shutil.copy2(audio_paths[0], out_audio)
        return True
    inputs = []
    for p in audio_paths:
        inputs += ["-i", str(p)]
    parts = []
    prev = "[0:a]"
    for k in range(1, n):
        offset = sum(durations[:k]) - k * XFADE_DUR
        out_tag = f"[ax{k}]" if k < n - 1 else "[afinal]"
        parts.append(
            f"{prev}[{k}:a]acrossfade=c1=tri:c2=tri:duration={XFADE_DUR}:offset={offset:.3f}{out_tag}")
        prev = out_tag
    filter_complex = ";".join(parts)
    cmd = [ff, "-y"] + inputs + [
        "-filter_complex", filter_complex,
        "-map", "[afinal]", "-c:a", "aac", "-b:a", "128k",
        str(out_audio),
    ]
    log("AXFADE", f"音频交叉淡化拼接 {n} 段 (每段 {XFADE_DUR}s, 与视频对齐)")
    r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if r.returncode != 0:
        log("AXFADE_ERR", r.stderr[-400:])
        # 兜底：退回普通 concat（此时音视频时长可能不一致，仅保底）
        return concat_audio(audio_paths, out_audio, ff)
    return out_audio.exists()


# ── 视频 xfade 交叉淡入淡出拼接 ───────────────────────

def build_xfade_video(seg_videos: list, durations: list,
                      out_video: Path, ff: str):
    """
    用 ffmpeg xfade 把所有段视频做成真正的 crossfade 转场。
    offset_k = sum(durations[0..k-1]) - k*XFADE_DUR
    """
    n = len(seg_videos)
    if n == 1:
        shutil.copy2(seg_videos[0], out_video)
        return True

    # 输入
    inputs = []
    for p in seg_videos:
        inputs += ["-i", str(p)]

    # 构建 filter_complex
    parts = []
    # 给每段打标签 [0:v][1:v]...
    prev = "[0:v]"
    for k in range(1, n):
        offset = sum(durations[:k]) - k * XFADE_DUR
        out_tag = f"[xf{k}]" if k < n - 1 else "[vfinal]"
        parts.append(f"{prev}[{k}:v]xfade=transition=fade:duration={XFADE_DUR}:offset={offset:.3f}{out_tag}")
        prev = out_tag
    filter_complex = ";".join(parts)

    cmd = [ff, "-y"] + inputs + [
        "-filter_complex", filter_complex,
        "-map", "[vfinal]" if n > 1 else "[0:v]",
        "-c:v", "libx264", "-preset", "medium", "-crf", "18",
        "-pix_fmt", "yuv420p",
        "-movflags", "+faststart",
        str(out_video),
    ]
    log("XFADE", f"交叉淡入淡出拼接 {n} 段 (每段 {XFADE_DUR}s fade)")
    r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if r.returncode != 0:
        log("XFADE_ERR", r.stderr[-400:])
        return False
    return out_video.exists()


# ── 片头标题卡 ─────────────────────────────────────────

def _draw_fallback_chars(d, orange, grey):
    """PIL 手绘抽象兔/龟（无即梦抠图时的回退方案）"""
    def draw_rabbit(cx, cy, c):
        d.ellipse([cx - 55, cy - 30, cx + 55, cy + 45], fill=c)
        d.ellipse([cx + 30, cy - 70, cx + 90, cy - 15], fill=c)
        d.polygon([(cx + 38, cy - 65), (cx + 54, cy - 140), (cx + 62, cy - 65)], fill=c)
        d.polygon([(cx + 62, cy - 65), (cx + 78, cy - 140), (cx + 86, cy - 60)], fill=c)
        d.ellipse([cx - 74, cy - 5, cx - 42, cy + 25], fill=c)

    def draw_turtle(cx, cy, c):
        d.ellipse([cx - 72, cy - 25, cx + 72, cy + 42], fill=c)
        d.ellipse([cx + 62, cy - 10, cx + 98, cy + 22], fill=c)
        d.ellipse([cx - 56, cy + 24, cx - 26, cy + 52], fill=c)
        d.ellipse([cx + 24, cy + 24, cx + 54, cy + 52], fill=c)

    draw_rabbit(380, 548, orange)
    draw_turtle(962, 548, grey)


# ── 片头标题卡（三级优先） ─────────────────────────────

def _make_title_seg_from_png(png_path: Path, ff: str, label: str):
    """把一张 PNG 转成静止视频段（通用辅助函数）"""
    seg = png_path.parent / "videos" / "_title_seg.mp4"
    r = subprocess.run([ff, "-y", "-loop", "1", "-i", str(png_path),
                        "-t", str(TITLE_CARD_DUR), "-r", str(FPS),
                        "-pix_fmt", "yuv420p",
                        "-c:v", "libx264", "-preset", "medium", "-crf", "18",
                        str(seg)],
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    if r.returncode != 0:
        log("TITLE_SEG_ERR", r.stderr[-200:]); return None
    log("TITLE", f"片头已生成: {label} ({png_path.name})")
    return seg


def make_title_card(plan: dict, out_dir: Path, ff: str):
    """
    三级优先生成片头标题卡（PNG + 静止视频段）：
      ① title_card_jimeng.png — 即梦完整标题卡（背景+角色+文字全AI画+PIL叠加中文）
         （最高优先：整张图都是即梦生成，风格与分镜完全一致）
      ② title_rabbit.png + title_turtle.png — 从即梦分镜图抠取角色 + PIL拼标题
      ③ 回退 PIL 手绘（椭圆兔龟 + 文字）
    返回视频段路径; 失败返回 None(不影响正文生成)。
    """
    # ── 优先级 ①：即梦完整标题卡（用户手动或脚本预先生成）──
    jimeng_card = out_dir / "title_card_jimeng.png"
    if jimeng_card.exists():
        seg = _make_title_seg_from_png(jimeng_card, ff, "即梦完整标题卡")
        if seg:
            return seg

    # ── 优先级 ②：抠图角色 + PIL 标题 ──────────────────────
    try:
        from PIL import Image as _PIL, ImageDraw, ImageFont
    except Exception as e:
        log("TITLE_IMPORT_ERR", repr(e)[:120])
        return None
    theme = plan.get("theme", "剪影故事")
    BG = (245, 243, 238); INK = (46, 42, 38); ORANGE = (200, 85, 61)
    GREY = (74, 69, 64); SUB = (138, 129, 117); FAINT = (176, 168, 156)
    img = _PIL.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(img)

    def font(p, s):
        try: return ImageFont.truetype(p, s)
        except Exception: return ImageFont.load_default()
    fb = "C:/Windows/Fonts/msyhbd.ttc"; fr = "C:/Windows/Fonts/msyh.ttc"
    f_title = font(fb, 150); f_sub = font(fr, 54); f_en = font(fr, 30)

    r_png = out_dir / "title_rabbit.png"
    t_png = out_dir / "title_turtle.png"
    if r_png.exists() and t_png.exists():
        try:
            pr = _PIL.open(r_png).convert("RGBA")
            pt = _PIL.open(t_png).convert("RGBA")
            img.paste(pr.resize((260, 300), _PIL.LANCZOS), (280, 450), pr.resize((260, 300), _PIL.LANCZOS))
            img.paste(pt.resize((240, 170), _PIL.LANCZOS), (960, 540), pt.resize((240, 170), _PIL.LANCZOS))
            d = ImageDraw.Draw(img)
            log("TITLE_CHAR", f"使用即梦抠图角色 ({r_png.name}, {t_png.name})")
        except Exception as e:
            log("TITLE_PASTE_ERR", repr(e)[:120])
            _draw_fallback_chars(d, ORANGE, GREY)
    else:
        log("TITLE_FALLBACK", "未找到 title_rabbit/turtle.png，使用回退手绘")
        _draw_fallback_chars(d, ORANGE, GREY)

    bb = d.textbbox((0, 0), theme, font=f_title)
    tw = bb[2] - bb[0]; th = bb[3] - bb[1]
    tx = (W - tw) // 2 - bb[0]; ty = 255 - bb[1]
    d.text((tx, ty), theme, font=f_title, fill=INK)
    line_w = 170
    d.rectangle([(W - line_w) // 2, ty + th + 28, (W + line_w) // 2, ty + th + 32], fill=ORANGE)
    sub = TITLE_SUB
    if sub:
        bb2 = d.textbbox((0, 0), sub, font=f_sub); sw = bb2[2] - bb2[0]
        d.text(((W - sw) // 2 - bb2[0], ty + th + 66), sub, font=f_sub, fill=SUB)
    en = "A  SILHOUETTE  STORY"
    bb3 = d.textbbox((0, 0), en, font=f_en); ew = bb3[2] - bb3[0]
    d.text(((W - ew) // 2 - bb3[0], 640), en, font=f_en, fill=FAINT)

    png = out_dir / "title_card.png"
    img.save(png)
    return _make_title_seg_from_png(png, ff, f"PIL标题卡({theme})")


# ── 字幕烧录 ───────────────────────────────────────────

def _burn_subtitles(input_video: Path, srt_path: Path,
                    output_video: Path, ff: str):
    """
    用 ffmpeg subtitles 滤镜将字幕烧录到视频上。

    ⚠️ Windows 致命坑（已修）：ffmpeg 的 subtitles 滤镜对**绝对路径**里
    的冒号（如 `C:/Users/...`）会当成滤镜选项分隔符，报 `Invalid argument`。
    彻底解法：把字幕转成 .ass 放到「视频所在目录」，再用**相对文件名** +
    `cwd=视频目录` 调用 ffmpeg，路径里完全不出现盘符冒号。
    """
    style = (
        "FontName=Microsoft YaHei,"
        "FontSize=20,"
        "PrimaryColour=&H00FFFFFF,"
        "OutlineColour=&H00000000,"
        "Outline=2,"
        "BorderStyle=3,"
        "BackColour=&H99000000,"
        "MarginV=24,"
        "Alignment=2,"
        "Bold=1"
    )
    vdir = input_video.parent
    ass_path = vdir / "subtitles.ass"

    # srt -> ass（这一步 -i 用绝对路径没问题，只是普通输入）
    conv = subprocess.run([ff, "-y", "-i", str(srt_path), str(ass_path)],
                          capture_output=True, text=True, encoding="utf-8", errors="replace")
    if conv.returncode != 0:
        log("SUB_ASS_ERR", conv.stderr[-200:])
        return

    # 关键：相对文件名 + cwd=vdir，避开 C: 冒号
    cmd = [
        ff, "-y",
        "-i", input_video.name,
        "-vf", f"subtitles={ass_path.name}:force_style='{style}'",
        "-c:v", "libx264", "-preset", "medium", "-crf", "18",
        "-c:a", "copy",
        "-movflags", "+faststart",
        output_video.name,
    ]
    log("SUB", f"正在烧录字幕... ({ass_path.name}, 相对路径规避Windows冒号)")
    result = subprocess.run(cmd, cwd=str(vdir), capture_output=True, text=True,
                            encoding="utf-8", errors="replace")
    if result.returncode != 0:
        log("SUB_ERR", f"字幕烧录失败: {result.stderr[-400:]}")
        subprocess.run([ff, "-y", "-i", str(input_video), "-c", "copy",
                        str(output_video)], capture_output=True)
        log("SUB_FALLBACK", "已回退为无字幕版本")
    else:
        sz_mb = output_video.stat().st_size / (1024 * 1024)
        log("SUB_OK", f"字幕烧录完成! ({sz_mb:.1f} MB)")


# ════════════════════════════════════════════════════════
#  主入口
# ════════════════════════════════════════════════════════

def main():
    if len(sys.argv) < 2:
        print("用法: python video_assemble.py <plan.json输出目录>")
        sys.exit(1)

    out_dir = out_dir_from_arg(sys.argv[1])
    ff = get_ffmpeg()
    plan = load_plan(out_dir)
    storyboards = plan.get("storyboards", [])
    n = len(storyboards)
    videos_dir = out_dir / "videos"
    videos_dir.mkdir(parents=True, exist_ok=True)

    print(f"\n{'='*50}")
    print(f"  剪影视频合成 v3（动画增强版）")
    print(f"  特性: Ken Burns 平移+缩放 + 交叉淡入淡出转场 + 字幕")
    print(f"{'='*50}\n")

    srt_path = generate_srt(plan, out_dir)

    # 第一遍: 收集有效分镜(图像存在且非 seedance)
    entries = []
    for i, sb in enumerate(storyboards):
        idx = i + 1
        img_path = out_dir / "images" / f"{idx:02d}.png"
        audio_path = out_dir / "audios" / f"{idx:02d}.mp3"
        if not img_path.exists():
            log("MISSING", f"shot {idx:02d}: 图片不存在，跳过")
            continue
        entries.append({
            "idx": idx, "img": img_path, "audio": audio_path,
            "dur": get_audio_duration(audio_path),
            "motion": MOTION_PRESETS[(idx - 1) % len(MOTION_PRESETS)],
            "is_first": i == 0, "is_last": i == n - 1,
        })
    if not entries:
        print("[ERROR] 没有任何可用的视频段!")
        sys.exit(1)

    # 关键: xfade 会让视频总时长压缩 (段数-1)*XFADE_DUR 秒。
    # 为让「视频总时长 == 音频总时长」(旁白不被截断), 给每段视频均匀补 EXTRA 时长。
    n_seg = len(entries)
    title_seg = make_title_card(plan, out_dir, ff)
    has_title = bool(title_seg and title_seg.exists())
    if has_title:
        # 每段补偿一个 xfade 时长: 正文经 xfade 后总时长=Σaudio,
        # 视频总时长=标题卡 + Σaudio (标题卡期间静音, 见音频处理)
        EXTRA = XFADE_DUR
    else:
        EXTRA = (n_seg - 1) * XFADE_DUR / n_seg

    seg_videos = []
    seg_durations = []   # 扩展后(用于 xfade offset, 总长=Σ音频)
    audio_paths = []
    audio_durations = []
    for e in entries:
        seg_vid = videos_dir / f"_seg{e['idx']:02d}.mp4"
        seg_dur = e["dur"] + EXTRA
        ok = make_segment_video(e["idx"], e["img"], seg_vid, ff, seg_dur,
                                e["motion"], e["is_first"], e["is_last"])
        if ok:
            seg_videos.append(seg_vid)
            seg_durations.append(seg_dur)
            audio_paths.append(e["audio"])
            audio_durations.append(e["dur"])

    # 标题卡作为第 0 段插入视频流(若有)
    if has_title:
        seg_videos.insert(0, title_seg)
        seg_durations.insert(0, TITLE_CARD_DUR)

    # ① xfade 拼接视频(段时长已含 EXTRA, 总时长=标题卡 + Σaudio)
    xfade_out = videos_dir / "_xfade.mp4"
    if not build_xfade_video(seg_videos, seg_durations, xfade_out, ff):
        print("[ERROR] xfade 拼接失败")
        sys.exit(1)

    # ② 拼接音频: 标题卡期间静音 + 正文旁白, 总时长=标题卡 + Σaudio (与视频对齐)
    audio_out = videos_dir / "_audio.m4a"
    audio_inputs = list(audio_paths)
    if has_title:
        silent = videos_dir / "_silent.aac"
        rs = subprocess.run([ff, "-y", "-f", "lavfi", "-i",
                             "anullsrc=r=44100:cl=stereo", "-t", str(TITLE_CARD_DUR),
                             "-c:a", "aac", "-b:a", "128k", str(silent)],
                            capture_output=True, text=True, encoding="utf-8", errors="replace")
        if rs.returncode == 0 and silent.exists():
            audio_inputs = [silent] + audio_inputs
        else:
            log("SILENT_ERR", rs.stderr[-150:])
    if not concat_audio(audio_inputs, audio_out, ff):
        print("[ERROR] 音频拼接失败")
        sys.exit(1)

    # ③ mux 音视频
    pre_sub = videos_dir / "merged_no_sub.mp4"
    mux = [
        ff, "-y",
        "-i", str(xfade_out),
        "-i", str(audio_out),
        "-c", "copy",
        "-movflags", "+faststart",
        "-shortest",
        str(pre_sub),
    ]
    r = subprocess.run(mux, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if r.returncode != 0:
        log("MUX_ERR", r.stderr[-300:])

    # ④ 烧录字幕
    final_out = videos_dir / "final.mp4"
    if pre_sub.exists():
        _burn_subtitles(pre_sub, srt_path, final_out, ff)
    else:
        _burn_subtitles(xfade_out, srt_path, final_out, ff)

    # 清理中间文件
    for f in [xfade_out, audio_out, pre_sub]:
        if f.exists():
            f.unlink()
    for p in seg_videos:
        if p.exists():
            p.unlink()
    for extra in [videos_dir / "_silent.aac", videos_dir / "_title_seg.mp4"]:
        if extra.exists():
            extra.unlink()

    if final_out.exists():
        sz_mb = final_out.stat().st_size / (1024 * 1024)
        print(f"\n  done! {final_out.name} ({sz_mb:.1f} MB)")


def _probe_duration(path: Path, ff: str) -> float:
    try:
        out = subprocess.run(
            [ff, "-v", "error", "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1", str(path)],
            capture_output=True, text=True, encoding="utf-8", errors="replace")
        return float(out.stdout.strip())
    except Exception:
        return 0.0




def shift_up(input_video: Path, output_video: Path, ff: str,
             shift_px: int = 72, bg_color: str = "#F3E7CE"):
    """
    画面上移 shift_px 像素，底部补背景色留白给字幕（避免字幕遮挡动画主体）。
    顶部裁掉的只是天空/留白，不影响画面内容。bg_color 用 #RRGGBB 形式。
    """
    from common import log as _log
    crop_pad = (
        f"crop={W}:{H - shift_px}:0:{shift_px},"
        f"pad={W}:{H}:0:0:color={bg_color.replace('#', '0x')}"
    )
    cmd = [
        ff, "-y", "-i", str(input_video),
        "-vf", crop_pad,
        "-c:v", "libx264", "-preset", "fast", "-crf", "18",
        "-pix_fmt", "yuv420p", "-movflags", "+faststart",
        str(output_video),
    ]
    r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if r.returncode != 0:
        _log("SHIFT_ERR", r.stderr[-300:]); return False
    return output_video.exists()


if __name__ == "__main__":
    main()
