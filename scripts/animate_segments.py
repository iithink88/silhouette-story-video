# -*- coding: utf-8 -*-
"""
Sprite-based Animation Renderer for 龟兔赛跑
==============================================
Uses 即梦 title-card character cutouts (title_rabbit.png / title_turtle.png)
as transparent PNG sprites composited onto PIL-rendered scene backgrounds.
Replaces pure geometric silhouette drawing with consistent Jimeng-style characters.

Usage:
    python animate_segments.py                          # render all 9 segments
    python animate_segments.py --seg 4                   # render only segment 4
    python animate_segments.py --fps 15 --preview        # lower fps for fast preview
"""

import sys, os, math, json, argparse, subprocess, shutil
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.stderr.reconfigure(encoding="utf-8", errors="replace")

from PIL import Image, ImageDraw, ImageFont

# ============================================================
# Constants
# ============================================================
W, H = 1344, 768          # canvas size (16:9)
FPS = 25                   # frame rate
BG_COLOR = (243, 231, 206)   # warm rice-cream #F3E7CE
TREE_COLOR = (80, 75, 70)     # dark warm gray for trees/mountains
PATH_COLOR = (210, 200, 185)  # light path/ground
SKY_ACCENT = (230, 180, 150)  # subtle sky gradient hint
SUN_COLOR = (230, 120, 50)    # orange-red sun
CLOUD_COLOR = (255, 250, 240) # near-white clouds

FINISH_LINE_COLOR = (180, 60, 30) # red finish line
TEXT_COLOR = (40, 40, 40)         # dark text
ZZZ_COLOR = (100, 100, 140, 180)  # semi-transparent blue-gray Zzz
DUST_COLOR = (190, 170, 140, 140) # dust particles
FLAG_COLOR = (200, 60, 30)         # red flag

# 工作目录：默认运行脚本时的当前目录（无硬编码路径，方便分享）
PROJECT = Path.cwd()
OUT_DIR = PROJECT / "animated_segments"
FRAMES_DIR = PROJECT / "_anim_frames"

# ── 即梦角色精灵（可选）：仅 USE_SPRITE=True 且存在 PNG 时加载；
#    缺图自动回退到几何剪影（默认 USE_SPRITE=False 即纯几何，无需任何外部素材）──
_SPRITE_CACHE = {}
def _get_sprite(kind):
    if kind in _SPRITE_CACHE:
        return _SPRITE_CACHE[kind]
    fname = "title_rabbit.png" if kind == "rabbit" else "title_turtle.png"
    p = PROJECT / fname
    _SPRITE_CACHE[kind] = Image.open(p).convert("RGBA") if p.exists() else None
    return _SPRITE_CACHE[kind]

# Base display size for each sprite at scale=1.0 (pixels on canvas)
# These are tuned so characters look proportional to scene elements
RABBIT_BASE_H = 220     # target height of rabbit at scale=1.0
TURTLE_BASE_H = 160     # target height of turtle at scale=1.0


# ============================================================
# Shape helpers (background only — kept unchanged)
# ============================================================

def _rgba(c):
    """Ensure 4-tuple RGBA."""
    if isinstance(c, (list, tuple)) and len(c) == 3:
        return (*c, 255)
    return tuple(c)


def _ellipse(draw, box, fill, outline=None):
    """Safe ellipse with optional outline."""
    draw.ellipse(list(box), fill=_rgba(fill), outline=_rgba(outline) if outline else None)


def _rounded_rect(draw, box, radius, fill):
    x0, y0, x1, y1 = box
    r = radius
    draw.rectangle([x0+r, y0, x1-r, y1], fill=_rgba(fill))
    draw.rectangle([x0, y0+r, x1, y1-r], fill=_rgba(fill))
    draw.pieslice([x0, y0, x0+2*r, y0+2*r], 180, 270, fill=_rgba(fill))
    draw.pieslice([x1-2*r, y0, x1, y0+2*r], 270, 360, fill=_rgba(fill))
    draw.pieslice([x0, y1-2*r, x0+2*r, y1], 90, 180, fill=_rgba(fill))
    draw.pieslice([x1-2*r, y1-2*r, x1, y1], 0, 90, fill=_rgba(fill))


def _polygon(draw, points, fill):
    draw.polygon([tuple(p) for p in points], fill=_rgba(fill))


def _line(draw, p1, p2, fill, width=2):
    draw.line([tuple(p1), tuple(p2)], fill=_rgba(fill), width=width)


def _draw_sun(draw, cx, cy, r=28):
    _ellipse(draw, [cx-r, cy-r, cx+r, cy+r], SUN_COLOR)


def _draw_cloud(draw, cx, cy, w=120, h=35):
    c = CLOUD_COLOR
    rx, ry = w/2, h/2
    _ellipse(draw, [cx-rx*0.6, cy-ry*0.5, cx+rx*0.6, cy+ry*0.8], c)
    _ellipse(draw, [cx-rx, cy-ry*0.2, cx+rx*0.2, cy+ry*0.6], c)
    _ellipse(draw, [cx-rx*0.2, cy-ry*0.7, cx+rx*0.8, cy+ry*0.5], c)


def _draw_tree_simple(draw, bx, by, w=70, h=130):
    tip_x = bx + w // 2
    points = [[tip_x, by - h], [bx - w//3, by], [bx + w + w//3, by]]
    _polygon(draw, points, TREE_COLOR)
    tw, th = 12, 25
    draw.rectangle([tip_x - tw//2, by, tip_x + tw//2, by + th], fill=_rgba(TREE_COLOR))


def _draw_big_tree(draw, cx, base_y, scale=1.0):
    s = scale
    trunk_w, trunk_h = int(22*s), int(55*s)
    canopy_r = int(75*s)
    draw.rectangle([cx - trunk_w//2, base_y - trunk_h, cx + trunk_w//2, base_y], fill=_rgba(TREE_COLOR))
    _ellipse(draw, [cx - canopy_r, base_y - trunk_h - canopy_r + 10,
                     cx + canopy_r, base_y - trunk_h + canopy_r - 10], TREE_COLOR)


def _draw_mountain(draw, peak_x, peak_h, base_w, base_y):
    hw = base_w // 2
    _polygon(draw, [[peak_x, base_y - peak_h],
                     [peak_x - hw, base_y],
                     [peak_x + hw, base_y]], TREE_COLOR)


def _draw_ground_path(draw, y, curve_amp=15):
    pts = []
    for x in range(0, W + 20, 20):
        yy = y + math.sin(x * 0.008) * curve_amp
        pts.append([x, yy])
    if len(pts) >= 2:
        for i in range(len(pts)-1):
            _line(draw, pts[i], pts[i+1], PATH_COLOR, width=3)


def _draw_finish_line(draw, x, top_y, bottom_y):
    dash_len = 12; gap = 8
    y = top_y
    while y < bottom_y:
        _line(draw, [x, y], [x, min(y + dash_len, bottom_y)], FINISH_LINE_COLOR, width=3)
        y += dash_len + gap


def _draw_flag_pole(draw, x, top_y, bottom_y):
    _line(draw, [x, top_y], [x, bottom_y], TREE_COLOR, width=3)
    flag_w, flag_h = 45, 28
    return [x, top_y, x + flag_w, top_y + flag_h]


def _draw_flag_waving(draw, rect, phase):
    x0, y0, x1, y1 = rect
    wave = math.sin(phase) * 5
    points = [
        [x0, y0],
        [x1 + wave, y0 + 3],
        [x1 + wave * 0.7, y1],
        [x0, y1],
    ]
    _polygon(draw, points, FLAG_COLOR)


# ============================================================
# Sprite compositing engine
# ============================================================

def _resize_sprite(sprite, target_h):
    """Resize sprite to approximately target_h pixels height, keeping aspect ratio."""
    sw, sh = sprite.size
    if sh == 0:
        return sprite
    ratio = target_h / sh
    new_w = max(1, int(sw * ratio))
    new_h = max(1, int(sh * ratio))
    return sprite.resize((new_w, new_h), Image.LANCZOS)


def draw_sprite(img, sprite, cx, cy, *,
                facing_right=True,
                scale=1.0,
                rotation=0,
                target_h=None):
    """
    Composite a transparent PNG sprite onto img at position (cx, cy) as center point.

    Args:
        img: RGBA PIL Image to composite onto
        sprite: RGBA PIL Image (transparent PNG)
        cx, cy: center position on canvas
        facing_right: False = flip horizontally
        scale: additional scale multiplier on top of target_h
        rotation: degrees counter-clockwise (positive = CCW)
        target_h: target height in pixels (uses default if None)
    """
    # Start with a copy of the sprite
    s = sprite.copy()

    # Horizontal flip for facing left
    if not facing_right:
        s = s.transpose(Image.FLIP_LEFT_RIGHT)

    # Resize to target height
    if target_h is not None:
        th = int(target_h * scale)
        s = _resize_sprite(s, th)

    # Apply rotation (expand=True to avoid clipping)
    if rotation != 0:
        s = s.rotate(rotation, expand=True, resample=Image.BICUBIC)

    # Calculate paste position (centered at cx, cy)
    sw, sh = s.size
    px = int(cx - sw // 2)
    py = int(cy - sh // 2)

    # Alpha composite
    if px + sw > 0 and py + sh > 0:  # only paste if visible
        img.paste(s, (px, py), s)


# ============================================================
# Character: RABBIT / TURTLE — 双模式 (sprite 或 geometry silhouette)
# ============================================================
# USE_SPRITE=False → 几何剪影主角（画面风格同 final_static_backup.mp4）
# USE_SPRITE=True  → 即梦标题卡精灵图（画面风格同 final_jimeng.mp4）
USE_SPRITE = False
RABBIT_GEO = (198, 52, 44)     # 暖红兔剪影
TURTLE_GEO = (70, 72, 78)      # 深灰龟剪影
GLAYER = 360                   # 离屏图层尺寸（角色居中绘制）


def _rabbit_geo_layer(pose, leg_phase, facing_right):
    """在 GLAYER×GLAYER 透明图层上绘制兔（标准尺寸，居中），返回 RGBA。"""
    layer = Image.new('RGBA', (GLAYER, GLAYER), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    R = RABBIT_GEO
    f = 1.0 if facing_right else -1.0
    cl = GLAYER // 2
    s = 1.0
    bw, bh = 84 * s, 48 * s
    bx, by = cl, cl + 10 * s
    d.ellipse([bx - bw/2, by - bh/2, bx + bw/2, by + bh/2], fill=R)        # body
    hx = bx + f * 48 * s; hy = by - 30 * s; hr = 25 * s
    d.ellipse([hx - hr, hy - hr*0.82, hx + hr, hy + hr*0.82], fill=R)      # head
    ear_x = hx - f * 4 * s; ear_y = hy - hr * 0.5
    for k in (-1, 1):
        ex = ear_x + k * 9 * s
        etop = ear_y - 56 * s
        d.line([(ex, ear_y), (ex + f*5*s, etop)], fill=R, width=int(11*s))
        d.ellipse([ex - 6*s + f*5*s, etop - 6*s, ex + 6*s + f*5*s, etop + 6*s], fill=R)
    d.ellipse([bx - f*46*s - 11*s, by - 5*s, bx - f*46*s + 11*s, by + 15*s], fill=R)  # tail
    swing = math.sin(leg_phase * 2 * math.pi)
    if pose == 'run':
        fa, ba = 22 + swing*38, 22 - swing*38
    elif pose == 'laugh':
        fa, ba = 28 + swing*14, 18 - swing*14
    else:
        fa, ba = 20 + swing*10, 20 - swing*10
    ll = 36 * s
    fx0 = bx + f*32*s; fy0 = by + bh*0.28
    fx1 = fx0 + f*math.cos(math.radians(fa))*ll; fy1 = fy0 + math.sin(math.radians(fa))*ll
    d.line([(fx0, fy0), (fx1, fy1)], fill=R, width=int(10*s))
    d.ellipse([fx1-6*s, fy1-6*s, fx1+6*s, fy1+6*s], fill=R)
    bx0 = bx - f*32*s; by0 = by + bh*0.28
    bx1 = bx0 - f*math.cos(math.radians(ba))*ll; by1 = by0 + math.sin(math.radians(ba))*ll
    d.line([(bx0, by0), (bx1, by1)], fill=R, width=int(11*s))
    d.ellipse([bx1-6*s, by1-6*s, bx1+6*s, by1+6*s], fill=R)
    if pose != 'sleep':
        d.ellipse([hx + f*6*s - 4*s, hy - 4*s, hx + f*6*s + 4*s, hy + 4*s], fill=(245, 235, 220))
    return layer


def _turtle_geo_layer(pose, leg_phase, facing_right):
    """在 GLAYER 透明图层上绘制龟（标准尺寸，居中），返回 RGBA。"""
    layer = Image.new('RGBA', (GLAYER, GLAYER), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    T = TURTLE_GEO
    f = 1.0 if facing_right else -1.0
    cl = GLAYER // 2
    s = 1.0
    sw, sh = 96 * s, 60 * s
    sx, sy = cl, cl + 6 * s
    d.ellipse([sx - sw/2, sy - sh/2, sx + sw/2, sy + sh/2], fill=T)       # shell
    d.ellipse([sx - sw/2 - 4*s, sy + sh*0.1, sx + sw/2 + 4*s, sy + sh*0.55], fill=T)
    hx = sx + f*58*s; hy = sy - 4*s; hr = 18*s
    d.ellipse([hx - hr, hy - hr*0.7, hx + hr, hy + hr*0.7], fill=T)       # head
    d.polygon([(sx - f*48*s, sy+6*s), (sx - f*66*s, sy), (sx - f*48*s, sy+18*s)], fill=T)  # tail
    swing = math.sin(leg_phase * 2 * math.pi)
    la = 26 + swing*30
    ll = 30 * s
    for side in (-1, 1):
        base_x = sx + f*38*s*side
        y0 = sy + sh*0.28
        x1 = base_x + f*math.cos(math.radians(la*side))*ll
        y1 = y0 + math.sin(math.radians(la*side))*ll + 6*s
        d.line([(base_x, y0), (x1, y1)], fill=T, width=int(12*s))
        d.ellipse([x1-6*s, y1-6*s, x1+6*s, y1+6*s], fill=T)
    if pose != 'sleep':
        d.ellipse([hx + f*5*s - 3*s, hy - 3*s, hx + f*5*s + 3*s, hy + 3*s], fill=(235, 230, 220))
    return layer


def _composite_geo(img, layer, cx, cy, facing_right, scale, rotation, target_h):
    """缩放/旋转几何图层并贴到主图。"""
    s = layer.copy()
    th = int(target_h * scale)
    if s.height:
        r = th / s.height
        s = s.resize((max(1, int(s.width*r)), max(1, int(s.height*r))), Image.LANCZOS)
    if rotation != 0:
        s = s.rotate(rotation, expand=True, resample=Image.BICUBIC)
    px = int(cx - s.width//2); py = int(cy - s.height//2)
    if px + s.width > 0 and py + s.height > 0:
        img.paste(s, (px, py), s)


class Rabbit:
    """兔：默认几何剪影，USE_SPRITE=True 时即梦精灵。"""

    @staticmethod
    def draw_on(img, cx, cy, *,
                facing_right=True,
                pose='stand',
                leg_phase=0,
                bob_y=0,
                ear_angle=0,
                scale=1.0,
                t_sec=0):
        rot = 0; extra_scale = scale; y_off = 0
        if pose == 'run':
            rot = -12 if facing_right else 12
            y_off = bob_y + math.sin(leg_phase * math.pi * 4) * 6 * scale
            extra_scale = scale * (1.0 + abs(math.sin(leg_phase * math.pi * 4)) * 0.05)
        elif pose == 'stand':
            y_off = bob_y
        elif pose == 'laugh':
            shake = math.sin(t_sec * 12 * math.pi) * 5 * scale
            cx = cx + shake
            y_off = bob_y + abs(math.sin(t_sec * 24 * math.pi)) * 3 * scale
        elif pose == 'sleep':
            y_off = bob_y + int(RABBIT_BASE_H * 0.15 * scale)
            rot = 10 if facing_right else -10
            extra_scale = scale * 1.05
        elif pose == 'wake':
            jump_h = abs(math.sin(leg_phase * math.pi)) * 45 * scale
            y_off = -jump_h + bob_y
            stretch = 1.0 + jump_h / 80
            extra_scale = scale * stretch
            rot = -8 if facing_right else 8
        elif pose == 'slump':
            y_off = int(RABBIT_BASE_H * 0.18 * scale)
            rot = 8 if facing_right else -8
            extra_scale = scale * 0.92
        if USE_SPRITE:
            sp = _get_sprite("rabbit")
            if sp is not None:
                draw_sprite(img, sp, cx, cy + y_off,
                            facing_right=facing_right, scale=extra_scale,
                            rotation=rot, target_h=RABBIT_BASE_H)
            else:
                layer = _rabbit_geo_layer(pose, leg_phase, facing_right)
                _composite_geo(img, layer, cx, cy + y_off,
                               facing_right, extra_scale, rot, RABBIT_BASE_H)
        else:
            layer = _rabbit_geo_layer(pose, leg_phase, facing_right)
            _composite_geo(img, layer, cx, cy + y_off,
                           facing_right, extra_scale, rot, RABBIT_BASE_H)


class Turtle:
    """龟：默认几何剪影，USE_SPRITE=True 时即梦精灵。"""

    @staticmethod
    def draw_on(img, cx, cy, *,
                facing_right=True,
                pose='crawl',
                leg_phase=0,
                bob_y=0,
                scale=1.0,
                t_sec=0):
        rot = 0; extra_scale = scale; y_off = 0
        if pose == 'crawl':
            y_off = bob_y + math.sin(leg_phase * math.pi * 2) * 3 * scale
            rot = math.sin(leg_phase * math.pi * 2) * 3
        elif pose == 'stand':
            y_off = bob_y
        elif pose == 'celebrate':
            y_off = -abs(math.sin(t_sec * 4 * math.pi)) * 12 * scale + bob_y
            extra_scale = scale * (1.0 + abs(math.sin(t_sec * 8 * math.pi)) * 0.06)
            rot = -3 if facing_right else 3
        if USE_SPRITE:
            sp = _get_sprite("turtle")
            if sp is not None:
                draw_sprite(img, sp, cx, cy + y_off,
                            facing_right=facing_right, scale=extra_scale,
                            rotation=rot, target_h=TURTLE_BASE_H)
            else:
                layer = _turtle_geo_layer(pose, leg_phase, facing_right)
                _composite_geo(img, layer, cx, cy + y_off,
                               facing_right, extra_scale, rot, TURTLE_BASE_H)
        else:
            layer = _turtle_geo_layer(pose, leg_phase, facing_right)
            _composite_geo(img, layer, cx, cy + y_off,
                           facing_right, extra_scale, rot, TURTLE_BASE_H)


# ============================================================
# Effects
# ============================================================

def draw_zzz(draw, x, y, phase, scale=1.0):
    """Floating Zzz text effect."""
    s = scale
    alpha = int(180 - phase * 120)
    if alpha <= 0:
        return
    try:
        font = ImageFont.truetype("C:/Windows/Fonts/msyhbd.ttc", int(36 * s))
    except:
        font = ImageFont.load_default()
    yy = y - int(phase * 60 * s)
    xx = x + int(math.sin(phase * 3) * 10 * s)
    if alpha > 60:
        c = (80, 80, 120)
        draw.text((xx, yy), "Z z z...", font=font, fill=c)


def draw_dust_cloud(draw, cx, cy, phase, scale=1.0):
    """Small dust puff that expands and fades."""
    s = scale
    progress = phase
    r_base = 8 * s
    r = r_base + progress * 18 * s
    alpha = int(160 * (1 - progress))
    if alpha < 10:
        return
    c = (190, 170, 140)
    for i in range(3):
        ox = (i - 1) * r * 0.5 + math.sin(progress * 5 + i) * 5 * s
        oy = (i % 2) * r * 0.3 + math.cos(progress * 4 + i) * 3 * s
        cr = r * (0.4 + i * 0.2)
        _ellipse(draw, [cx + ox - cr, cy + oy - cr, cx + ox + cr, cy + oy + cr], c)


# ============================================================
# Scene definitions (9 segments) — same layout as before
# ============================================================

SCENES = [
    # Segment 1: 森林深处，兔龟对峙
    {
        "id": 1,
        "bg_elements": ["forest_bg", "sun", "clouds"],
        "characters": [
            {"type": "rabbit", "cx": 480, "cy": 520, "facing": True,
             "pose": "stand", "anim": {"bob_freq": 0.5, "bob_amp": 3}},
            {"type": "turtle", "cx": 800, "cy": 550, "facing": False,
             "pose": "crawl", "anim": {"leg_freq": 0.3, "bob_amp": 2}},
        ],
        "effects": [],
    },
    # Segment 2: 兔子嘲笑乌龟
    {
        "id": 2,
        "bg_elements": ["path_bg", "clouds"],
        "characters": [
            {"type": "rabbit", "cx": 500, "cy": 500, "facing": True,
             "pose": "laugh", "anim": {"shake_freq": 3.0}},
            {"type": "turtle", "cx": 850, "cy": 560, "facing": False,
             "pose": "stand", "anim": {}},
        ],
        "effects": [],
    },
    # Segment 3: 起跑挑战
    {
        "id": 3,
        "bg_elements": ["path_bg", "big_tree_far", "start_line", "clouds"],
        "characters": [
            {"type": "rabbit", "cx": 420, "cy": 540, "facing": True,
             "pose": "stand", "anim": {"bob_freq": 1.2, "bob_amp": 6}},
            {"type": "turtle", "cx": 350, "cy": 565, "facing": True,
             "pose": "stand", "anim": {"bob_freq": 0.8, "bob_amp": 3}},
        ],
        "effects": [],
    },
    # Segment 4: 兔子冲刺（★重点动作段）
    {
        "id": 4,
        "bg_elements": ["path_bg", "trees_side", "clouds"],
        "characters": [
            {"type": "rabbit", "cx": 350, "cy": 520, "facing": True,
             "pose": "run", "anim": {"leg_freq": 8.0, "move_speed": 120},
             "traverse": True},
            {"type": "turtle", "cx": 900, "cy": 570, "facing": True,
             "pose": "crawl", "anim": {"leg_freq": 0.5, "move_speed": 15},
             "scale": 0.45, "traverse": True},
        ],
        "effects": ["dust"],
    },
    # Segment 5: 兔回头看
    {
        "id": 5,
        "bg_elements": ["path_bg", "big_tree_mid", "clouds"],
        "characters": [
            {"type": "rabbit", "cx": 600, "cy": 510, "facing": True,
             "pose": "stand", "anim": {"look_back": True}},
            {"type": "turtle", "cx": 950, "cy": 575, "facing": True,
             "pose": "crawl", "anim": {"leg_freq": 0.4, "move_speed": 12},
             "scale": 0.5, "traverse": True},
        ],
        "effects": [],
    },
    # Segment 6: 兔子树下睡觉
    {
        "id": 6,
        "bg_elements": ["sleep_scene", "sun", "clouds_slow"],
        "characters": [
            {"type": "rabbit", "cx": 650, "cy": 560, "facing": True,
             "pose": "sleep", "anim": {"breathe_freq": 0.35, "breathe_amp": 4}},
        ],
        "effects": ["zzz"],
    },
    # Segment 7: 乌龟向前爬（★重点动作段）
    {
        "id": 7,
        "bg_elements": ["path_bg", "big_tree_near", "clouds_slow"],
        "characters": [
            {"type": "turtle", "cx": 300, "cy": 550, "facing": True,
             "pose": "crawl", "anim": {"leg_freq": 0.6, "move_speed": 45, "bob_amp": 3},
             "traverse": True},
        ],
        "effects": [],
    },
    # Segment 8: 兔子醒来惊慌（★动作段）
    {
        "id": 8,
        "bg_elements": ["path_bg", "big_tree_close", "finish_line_bg", "clouds"],
        "characters": [
            {"type": "rabbit", "cx": 400, "cy": 550, "facing": True,
             "pose": "wake", "anim": {"jump_freq": 1.5}},
            {"type": "turtle", "cx": 950, "cy": 565, "facing": True,
             "pose": "crawl", "anim": {"leg_freq": 0.5},
             "scale": 0.85},
        ],
        "effects": [],
    },
    # Segment 9: 乌龟冲线获胜
    {
        "id": 9,
        "bg_elements": ["finish_scene", "big_tree_finish", "clouds"],
        "characters": [
            {"type": "turtle", "cx": 750, "cy": 550, "facing": True,
             "pose": "celebrate", "anim": {"move_speed": 30},
             "traverse": True},
            {"type": "rabbit", "cx": 450, "cy": 570, "facing": True,
             "pose": "slump", "anim": {}, "scale": 0.9},
        ],
        "effects": ["flag_wave"],
    },
]


# ============================================================
# Background rendering functions per bg_element type (unchanged)
# ============================================================

def render_background(draw, elements, t, fps):
    """Render background elements based on scene config."""
    for el in elements:
        if el == "forest_bg":
            _draw_ground_path(draw, H * 0.78, curve_amp=12)
            _draw_mountain(draw, W * 0.65, H * 0.42, W * 0.55, int(H * 0.76))
            _draw_mountain(draw, W * 0.25, H * 0.30, W * 0.40, int(H * 0.74))
            _draw_tree_simple(draw, 120, int(H * 0.74), 60, 110)
            _draw_tree_simple(draw, 1080, int(H * 0.73), 75, 125)
            _draw_tree_simple(draw, 220, int(H * 0.71), 50, 95)
            _draw_tree_simple(draw, 950, int(H * 0.72), 55, 100)
            _draw_sun(draw, 200, 120, 26)

        elif el == "path_bg":
            _draw_ground_path(draw, H * 0.77, curve_amp=10)
            _draw_tree_simple(draw, 80, int(H * 0.73), 45, 85)
            _draw_tree_simple(draw, 1150, int(H * 0.73), 50, 90)

        elif el == "big_tree_far":
            _draw_ground_path(draw, H * 0.77, curve_amp=10)
            _draw_big_tree(draw, int(W * 0.78), int(H * 0.74), scale=0.7)

        elif el == "big_tree_mid":
            _draw_ground_path(draw, H * 0.77, curve_amp=10)
            _draw_big_tree(draw, int(W * 0.82), int(H * 0.73), scale=0.9)

        elif el == "big_tree_near":
            _draw_ground_path(draw, H * 0.77, curve_amp=8)
            _draw_big_tree(draw, int(W * 0.85), int(H * 0.72), scale=1.05)

        elif el == "big_tree_close":
            _draw_ground_path(draw, H * 0.77, curve_amp=8)
            _draw_big_tree(draw, int(W * 0.88), int(H * 0.70), scale=1.15)

        elif el == "big_tree_finish":
            _draw_ground_path(draw, H * 0.77, curve_amp=8)
            _draw_big_tree(draw, int(W * 0.83), int(H * 0.69), scale=1.2)

        elif el == "sleep_scene":
            _draw_ground_path(draw, H * 0.80, curve_amp=8)
            _draw_big_tree(draw, int(W * 0.55), int(H * 0.72), scale=1.1)
            for gx in range(150, W - 100, 180):
                gh = 12 + (gx % 7)
                _polygon(draw, [[gx - 4, H * 0.79], [gx, H * 0.79 - gh], [gx + 4, H * 0.79]],
                         (TREE_COLOR[0]+20, TREE_COLOR[1]+18, TREE_COLOR[2]+15))

        elif el == "finish_line_bg" or el == "finish_scene":
            _draw_ground_path(draw, H * 0.77, curve_amp=8)
            _draw_big_tree(draw, int(W * 0.83), int(H * 0.68), scale=1.25)
            fx = int(W * 0.72)
            _draw_finish_line(draw, fx, int(H * 0.38), int(H * 0.78))

        elif el == "start_line":
            sx = int(W * 0.28)
            _draw_finish_line(draw, sx, int(H * 0.45), int(H * 0.78))

        elif el == "sun":
            pulse = 1 + 0.03 * math.sin(t * 2)
            _draw_sun(draw, int(W * 0.15), int(H * 0.17), int(28 * pulse))

        elif el == "clouds":
            drift = (t * 8) % (W + 200) - 100
            _draw_cloud(draw, drift, 90, 130, 36)
            _draw_cloud(draw, (drift + 500) % (W + 200) - 100, 130, 100, 30)
            _draw_cloud(draw, (drift + 900) % (W + 200) - 100, 75, 140, 38)

        elif el == "clouds_slow":
            drift = (t * 3) % (W + 200) - 100
            _draw_cloud(draw, drift, 95, 120, 34)
            _draw_cloud(draw, (drift + 550) % (W + 200) - 100, 125, 105, 30)

        elif el == "trees_side":
            _draw_ground_path(draw, H * 0.77, curve_amp=15)
            _draw_tree_simple(draw, 100, int(H * 0.72), 55, 100)
            _draw_tree_simple(draw, 1120, int(H * 0.72), 60, 105)


# ============================================================
# Frame renderer (sprite mode)
# ============================================================

def render_frame(scene, frame_idx, total_frames, duration, fps):
    """Render a single frame. Returns PIL Image (RGBA)."""
    img = Image.new('RGBA', (W, H), (*BG_COLOR, 255))
    draw = ImageDraw.Draw(img)

    t = frame_idx / fps  # time in seconds

    # Background
    render_background(draw, scene["bg_elements"], t, fps)

    # Characters (sprite-composited)
    for ch in scene.get("characters", []):
        anim = ch.get("anim", {})
        ch_type = ch["type"]
        cx0 = ch["cx"]
        cy0 = ch["cy"]
        facing = ch.get("facing", True)
        pose = ch.get("pose", "stand")
        scale = ch.get("scale", 1.0)

        # Animation parameters
        leg_freq = anim.get("leg_freq", 1.0)
        leg_phase = (t * leg_freq) % 1.0
        bob_freq = anim.get("bob_freq", 0.5)
        bob_amp = anim.get("bob_amp", 0)
        bob_y = math.sin(t * bob_freq * 2 * math.pi) * bob_amp if bob_amp > 0 else 0
        move_speed = anim.get("move_speed", 0)

        # Traverse: character moves across screen
        if ch.get("traverse", False):
            direction = 1 if facing else -1
            cx = cx0 + direction * move_speed * t
            cx = max(-100, min(W + 100, cx))
        else:
            cx = cx0

        # Look-back animation for segment 5
        ear_adj = 0
        if anim.get("look_back"):
            ear_adj = 25 if math.sin(t * 1.5) > 0 else 0

        # Breathe override for sleep
        if pose == "sleep":
            bf = anim.get("breathe_freq", 0.35)
            ba = anim.get("breathe_amp", 4)
            bob_y = math.sin(t * bf * 2 * math.pi) * ba

        # Jump/wake amplitude
        if pose == "wake":
            jf = anim.get("jump_freq", 1.5)
            # handled inside wake pose via leg_phase

        # Draw character as sprite
        if ch_type == "rabbit":
            Rabbit.draw_on(img, cx, cy0, facing_right=facing,
                           pose=pose, leg_phase=leg_phase, bob_y=bob_y,
                           ear_angle=ear_adj, scale=scale, t_sec=t)
        elif ch_type == "turtle":
            Turtle.draw_on(img, cx, cy0, facing_right=facing,
                           pose=pose, leg_phase=leg_phase, bob_y=bob_y,
                           scale=scale, t_sec=t)

    # Effects (drawn on top of sprites where needed)
    effects = scene.get("effects", [])
    if "dust" in effects:
        rb = scene["characters"][0]
        speed = rb.get("anim", {}).get("move_speed", 100)
        rcx0 = rb["cx"]
        facing_r = rb.get("facing", True)
        dir_r = 1 if facing_r else -1
        dust_x = rcx0 + dir_r * speed * t - (30 if facing_r else -30)
        dust_y = rb["cy"] + 15
        for di in range(3):
            dp = ((t * 4 + di * 0.33) % 1.0)
            dx = dust_x - dir_r * dp * 40 + (di - 1) * 10
            dy = dust_y + math.sin(dp * 6 + di) * 8
            draw_dust_cloud(draw, dx, dy, dp, scale=rb.get("scale", 1.0))

    if "zzz" in effects:
        rb = scene["characters"][0]
        zphase = (t * 0.6) % 1.0
        draw_zzz(draw, rb["cx"] + 40, rb["cy"] - 30, zphase, scale=rb.get("scale", 1.0))
        zphase2 = (t * 0.6 + 0.5) % 1.0
        draw_zzz(draw, rb["cx"] + 55, rb["cy"] - 20, zphase2, scale=rb.get("scale", 1.0) * 0.8)

    if "flag_wave" in effects:
        flag_rect = [int(W * 0.72), int(H * 0.38), int(W * 0.72) + 45, int(H * 0.38) + 28]
        _draw_flag_waving(draw, flag_rect, t * 3)

    return img


# ============================================================
# Segment renderer → ffmpeg mp4
# ============================================================

def render_segment(seg_idx, duration, fps=FPS, out_dir=None):
    """Render one segment to mp4. Returns output path."""
    if out_dir is None:
        out_dir = OUT_DIR
    out_dir.mkdir(parents=True, exist_ok=True)

    seg_frames_dir = FRAMES_DIR / f"seg_{seg_idx:02d}"
    seg_frames_dir.mkdir(parents=True, exist_ok=True)

    total_frames = max(1, int(duration * fps))
    scene = SCENES[seg_idx - 1]

    print(f"[Seg {seg_idx}] Rendering {total_frames} frames ({duration}s @ {fps}fps)...")

    for fi in range(total_frames):
        frame = render_frame(scene, fi, total_frames, duration, fps)
        frame_path = seg_frames_dir / f"frame_{fi:05d}.png"
        frame.save(frame_path, 'PNG')
        if (fi + 1) % (total_frames // 4 or 1) == 0 or fi == 0:
            print(f"  frame {fi+1}/{total_frames}")

    out_mp4 = out_dir / f"seg_{seg_idx:02d}.mp4"
    cmd = [
        'ffmpeg', '-y', '-hide_banner', '-loglevel', 'error',
        '-framerate', str(fps),
        '-i', str(seg_frames_dir / 'frame_%05d.png'),
        '-c:v', 'libx264', '-pix_fmt', 'yuv420p',
        '-preset', 'medium', '-crf', '18',
        str(out_mp4),
    ]
    print(f"[Seg {seg_idx}] Encoding to {out_mp4.name}...")
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"  FFMPEG ERROR: {result.stderr[:300]}")
    else:
        size_mb = out_mp4.stat().st_size / (1024 * 1024)
        print(f"[Seg {seg_idx}] Done: {out_mp4.name} ({size_mb:.1f}MB)")

    shutil.rmtree(seg_frames_dir, ignore_errors=True)
    return out_mp4


# ============================================================
# Main
# ============================================================

def main():
    parser = argparse.ArgumentParser(description="几何剪影动画渲染器（龟兔赛跑）")
    parser.add_argument("--seg", type=int, default=None, help="Only render specific segment (1-9)")
    parser.add_argument("--fps", type=int, default=FPS, help="Frame rate")
    parser.add_argument("--preview", action="store_true", help="Low-quality fast preview (crf 28)")
    args = parser.parse_args()

    fps = args.fps
    crf = 28 if args.preview else 18

    # Read audio durations
    audios_dir = PROJECT / "audios"
    durations = []
    for i in range(1, 10):
        af = audios_dir / f"{i:02d}.mp3"
        if af.exists():
            r = subprocess.run(
                ['ffprobe', '-v', 'error', '-show_entries', 'format=duration',
                 '-of', 'default=noprint_wrappers=1:nokey=1', str(af)],
                capture_output=True, text=True
            )
            dur = float(r.stdout.strip())
            durations.append(dur)
            print(f"Segment {i}: narration {dur:.2f}s -> {int(dur * fps)} frames @ {fps}fps")
        else:
            durations.append(5.0)
            print(f"Segment {i}: no audio found, defaulting to 5s")

    seg_range = [args.seg] if args.seg else list(range(1, 10))
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    for si in seg_range:
        if 1 <= si <= 9:
            render_segment(si, durations[si - 1], fps=fps)

    print(f"\nAll done! Sprite-animated segments in: {OUT_DIR}")
    print("Next step: rebuild video with rebuild_animated.py")

if __name__ == "__main__":
    main()
