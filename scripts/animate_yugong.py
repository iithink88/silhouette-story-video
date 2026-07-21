# -*- coding: utf-8 -*-
"""
愚公移山 · 几何剪影动画引擎（纯 PIL 逐帧渲染，无浏览器依赖）
风格：暖米纸底 + 黑/灰剪影 + 橙红点缀（对标《愚公移山》剪纸风）
角色：愚公(老)、子孙(青壮)、智叟(老)、小孩；动作：挖山、运土、炊烟、子子孙孙逐个出现。

用法：python animate_yugong.py   # 渲染 9 段到 animated_segments/
"""
import sys, math, subprocess
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.stderr.reconfigure(encoding="utf-8", errors="replace")
from pathlib import Path
from PIL import Image, ImageDraw

# ── 画布与帧率 ───────────────────────────────────────
W, H = 1344, 768
FPS = 25
GROUND_Y = 640          # 地面线（脚底基准）

# ── 调色板 ───────────────────────────────────────────
PAPER   = (244, 240, 224)   # 米纸底
PAPER2  = (233, 227, 206)   # 远端纸色
INK     = (38, 34, 30)      # 主剪影（近）
INK2    = (70, 63, 55)      # 次剪影
MOUNT_A = (96, 88, 80)      # 近山（深剪影）
MOUNT_B = (140, 132, 122)    # 远山
ORANGE  = (196, 78, 46)     # 橙红点缀（太阳/锄光）
SUN     = (205, 120, 60)
BEARD   = (60, 54, 48)

# 工作目录：默认运行脚本时的当前目录（无硬编码路径，方便分享）
ROOT = Path.cwd()
ANIM_DIR = ROOT / "animated_segments"
ANIM_DIR.mkdir(parents=True, exist_ok=True)


# ─────────────────────────────────────────────────────
# 基础绘制
# ─────────────────────────────────────────────────────
def paper_bg(draw, tint_top=PAPER, tint_bot=PAPER2):
    """竖直渐变纸底"""
    for y in range(H):
        t = y / H
        r = int(tint_top[0] + (tint_bot[0] - tint_top[0]) * t)
        g = int(tint_top[1] + (tint_bot[1] - tint_top[1]) * t)
        b = int(tint_top[2] + (tint_bot[2] - tint_top[2]) * t)
        draw.line([(0, y), (W, y)], fill=(r, g, b))


def draw_mountain(draw, cx, base_y, h, w, color):
    """带圆润峰的剪影山"""
    left = cx - w / 2
    right = cx + w / 2
    peak = base_y - h
    pts = [
        (left, base_y),
        (cx - w * 0.32, base_y - h * 0.55),
        (cx - w * 0.14, peak + h * 0.18),
        (cx, peak),
        (cx + w * 0.14, peak + h * 0.18),
        (cx + w * 0.32, base_y - h * 0.55),
        (right, base_y),
    ]
    draw.polygon([(int(x), int(y)) for x, y in pts], fill=color)


def draw_sun(draw, cx, cy, r, color):
    draw.ellipse([cx - r, cy - r, cx + r, cy + r], fill=color)
    # 光晕
    for i in range(3):
        rr = r + (i + 1) * 10
        draw.ellipse([cx - rr, cy - rr, cx + rr, cy + rr],
                     outline=(color[0], color[1], color[2], 60 - i * 18))


def draw_house(draw, x, y, scale, color):
    """简易屋 + 烟囱（y 为屋基脚线）"""
    s = scale
    ww = 150 * s
    hh = 90 * s
    # 墙体
    draw.rectangle([x - ww / 2, y - hh, x + ww / 2, y], fill=color)
    # 屋顶
    draw.polygon([
        (int(x - ww / 2 - 14 * s), int(y - hh)),
        (int(x), int(y - hh - 60 * s)),
        (int(x + ww / 2 + 14 * s), int(y - hh)),
    ], fill=color)
    # 门
    draw.rectangle([x - 18 * s, y - 56 * s, x + 18 * s, y], fill=PAPER)
    # 窗
    draw.rectangle([x + 40 * s, y - 60 * s, x + 70 * s, y - 30 * s], fill=PAPER)
    # 烟囱
    draw.rectangle([x + 30 * s, y - hh - 50 * s, x + 46 * s, y - hh - 8 * s], fill=color)


def draw_smoke(draw, x, base_y, t, color=(210, 205, 195)):
    """炊烟上升：多团漂移圆，随时间升高变淡变大"""
    for k in range(5):
        prog = ((t * 0.18) + k * 0.2) % 1.0
        yy = base_y - prog * 220
        xx = x + math.sin(prog * 6.0 + k) * (18 + prog * 30)
        rr = 8 + prog * 22
        a = int(150 * (1 - prog))
        draw.ellipse([xx - rr, yy - rr, xx + rr, yy + rr],
                     fill=(color[0], color[1], color[2], a))


# ─────────────────────────────────────────────────────
# 人物剪影
# ─────────────────────────────────────────────────────
def draw_person(draw, cx, foot_y, scale=1.0, color=INK, pose="stand",
                phase=0.0, beard=False):
    """
    通用人物剪影。
    pose: stand / walk / carry / dig / point / cheer
    phase: 动画相位（弧度系）
    beard: 老年须
    """
    s = scale
    hr = 13 * s                      # 头半径
    head_cx = cx
    head_cy = foot_y - 78 * s
    shoulder_y = foot_y - 60 * s
    hip_y = foot_y - 30 * s
    body_top = shoulder_y
    body_bot = hip_y

    bob = 0.0
    # ── 各姿态参数 ──
    if pose == "walk" or pose == "carry":
        sp = math.sin(phase)
        bob = abs(sp) * 3 * s
        # 腿交替
        lfx = cx - 9 * s + sp * 12 * s
        rfx = cx + 9 * s - sp * 12 * s
        lfy = foot_y if sp >= 0 else foot_y - 8 * s
        rfy = foot_y if sp < 0 else foot_y - 8 * s
        # 手臂反摆
        arm_swing = sp * 10 * s
    elif pose == "dig":
        sp = math.sin(phase)
        lfx = cx - 14 * s; rfx = cx + 14 * s
        lfy = foot_y; rfy = foot_y
        bob = sp * 2 * s
        arm_swing = 0
    elif pose == "point":
        lfx = cx - 10 * s; rfx = cx + 10 * s
        lfy = foot_y; rfy = foot_y
        bob = 0
        arm_swing = 0
    elif pose == "cheer":
        sp = math.sin(phase)
        lfx = cx - 12 * s; rfx = cx + 12 * s
        lfy = foot_y; rfy = foot_y
        bob = abs(sp) * 9 * s
        arm_swing = 0
    else:  # stand
        lfx = cx - 9 * s; rfx = cx + 9 * s
        lfy = foot_y; rfy = foot_y
        bob = math.sin(phase) * 1.5 * s
        arm_swing = 0

    head_cy -= bob
    shoulder_y -= bob
    hip_y -= bob

    # ── 腿 ──
    draw.line([(int(cx - 3 * s), int(hip_y)), (int(lfx), int(lfy))],
              fill=color, width=max(2, int(7 * s)))
    draw.line([(int(cx + 3 * s), int(hip_y)), (int(rfx), int(rfy))],
              fill=color, width=max(2, int(7 * s)))
    # 脚
    draw.ellipse([int(lfx) - 7 * s, int(lfy) - 5 * s, int(lfx) + 7 * s, int(lfy) + 5 * s], fill=color)
    draw.ellipse([int(rfx) - 7 * s, int(rfy) - 5 * s, int(rfx) + 7 * s, int(rfy) + 5 * s], fill=color)

    # ── 躯干 ──
    draw.polygon([
        (int(cx - 11 * s), int(body_top)),
        (int(cx + 11 * s), int(body_top)),
        (int(cx + 8 * s), int(body_bot)),
        (int(cx - 8 * s), int(body_bot)),
    ], fill=color)

    # ── 头 ──
    draw.ellipse([int(head_cx - hr), int(head_cy - hr),
                  int(head_cx + hr), int(head_cy + hr)], fill=color)
    # 发髻（老头）
    draw.ellipse([int(head_cx - hr * 0.5), int(head_cy - hr * 1.5),
                  int(head_cx + hr * 0.5), int(head_cy - hr * 0.7)], fill=color)
    if beard:
        draw.polygon([
            (int(head_cx - hr * 0.8), int(head_cy + hr * 0.4)),
            (int(head_cx + hr * 0.8), int(head_cy + hr * 0.4)),
            (int(head_cx), int(head_cy + hr * 2.2)),
        ], fill=color)

    # ── 手臂 ──
    if pose == "dig":
        # 双手举锄头：手臂上举
        axe_up = (math.sin(phase) + 1) / 2  # 0..1 起落
        hand_y = shoulder_y - (10 + axe_up * 30) * s
        hand_x = cx + 6 * s
        draw.line([(int(cx - 4 * s), int(shoulder_y)), (int(hand_x), int(hand_y))],
                  fill=color, width=max(2, int(6 * s)))
        draw.line([(int(cx + 4 * s), int(shoulder_y)), (int(hand_x), int(hand_y))],
                  fill=color, width=max(2, int(6 * s)))
        # 锄头杆
        draw.line([(int(hand_x), int(hand_y)), (int(hand_x + 38 * s), int(hand_y - 26 * s))],
                  fill=INK2, width=max(2, int(5 * s)))
        # 锄头刃
        draw.polygon([
            (int(hand_x + 38 * s), int(hand_y - 32 * s)),
            (int(hand_x + 60 * s), int(hand_y - 14 * s)),
            (int(hand_x + 38 * s), int(hand_y - 12 * s)),
        ], fill=ORANGE)
    elif pose == "carry":
        # 扁担 + 两筐
        pole_y = shoulder_y - 4 * s
        draw.line([(int(cx - 40 * s), int(pole_y)), (int(cx + 40 * s), int(pole_y))],
                  fill=INK2, width=max(2, int(5 * s)))
        for sx in (-1, 1):
            bx = cx + sx * 40 * s
            draw.line([(int(bx), int(pole_y)), (int(bx), int(pole_y + 20 * s))],
                      fill=INK2, width=max(2, int(3 * s)))
            draw.ellipse([int(bx - 14 * s), int(pole_y + 18 * s),
                          int(bx + 14 * s), int(pole_y + 40 * s)], fill=color)
        # 手臂搭扁担
        draw.line([(int(cx - 4 * s), int(shoulder_y)), (int(cx - 30 * s), int(pole_y))],
                  fill=color, width=max(2, int(6 * s)))
        draw.line([(int(cx + 4 * s), int(shoulder_y)), (int(cx + 30 * s), int(pole_y))],
                  fill=color, width=max(2, int(6 * s)))
    elif pose == "point":
        # 一臂前指
        draw.line([(int(cx + 4 * s), int(shoulder_y)), (int(cx + 34 * s), int(shoulder_y - 18 * s))],
                  fill=color, width=max(2, int(6 * s)))
        draw.line([(int(cx - 4 * s), int(shoulder_y)), (int(cx - 22 * s), int(shoulder_y + 6 * s))],
                  fill=color, width=max(2, int(6 * s)))
    elif pose == "cheer":
        draw.line([(int(cx - 4 * s), int(shoulder_y)), (int(cx - 26 * s), int(shoulder_y - 34 * s))],
                  fill=color, width=max(2, int(6 * s)))
        draw.line([(int(cx + 4 * s), int(shoulder_y)), (int(cx + 26 * s), int(shoulder_y - 34 * s))],
                  fill=color, width=max(2, int(6 * s)))
    else:  # stand / walk 手臂自然摆
        draw.line([(int(cx - 4 * s), int(shoulder_y)), (int(cx - 18 * s + arm_swing), int(hip_y))],
                  fill=color, width=max(2, int(6 * s)))
        draw.line([(int(cx + 4 * s), int(shoulder_y)), (int(cx + 18 * s - arm_swing), int(hip_y))],
                  fill=color, width=max(2, int(6 * s)))


def draw_dust(draw, x, y, phase, color=(200, 190, 175)):
    """挖山扬起的尘土"""
    for k in range(4):
        prog = ((phase / (2 * math.pi)) + k * 0.25) % 1.0
        xx = x + 20 + prog * 60
        yy = y - prog * 50
        rr = 4 + prog * 14
        a = int(160 * (1 - prog))
        draw.ellipse([xx - rr, yy - rr, xx + rr, yy + rr],
                     fill=(color[0], color[1], color[2], a))


# ─────────────────────────────────────────────────────
# 分镜场景定义（9 段）
# ─────────────────────────────────────────────────────
def _scene1():  # 两座大山
    return dict(
        tint=(PAPER, PAPER2), mountains=[
            (W * 0.30, GROUND_Y + 40, 360, 540, MOUNT_A),
            (W * 0.72, GROUND_Y + 40, 400, 620, MOUNT_B),
        ], sun=(W - 180, 150, 46, SUN), chars=[
            dict(kind="tiny", cx=W * 0.5, foot_y=GROUND_Y + 20, scale=0.45, pose="stand", speed=0.6),
        ],
    )


def _scene2():  # 屋 + 炊烟 + 愚公望山
    return dict(
        tint=(PAPER, PAPER2), mountains=[
            (W * 0.78, GROUND_Y + 40, 360, 600, MOUNT_B),
        ], sun=(150, 140, 40, SUN), house=(W * 0.22, GROUND_Y + 30, 1.0),
        chars=[
            dict(kind="yu", cx=W * 0.40, foot_y=GROUND_Y + 20, scale=1.0, pose="stand", speed=0.8, beard=True),
        ],
    )


def _scene3():  # 聚室而谋
    return dict(
        tint=(PAPER, PAPER2), mountains=[
            (W * 0.82, GROUND_Y + 40, 300, 520, MOUNT_B),
        ], chars=[
            dict(kind="yu", cx=W * 0.42, foot_y=GROUND_Y + 20, scale=1.05, pose="point", speed=1.2, beard=True),
            dict(kind="son", cx=W * 0.58, foot_y=GROUND_Y + 20, scale=0.9, pose="stand", speed=0.9),
            dict(kind="son", cx=W * 0.68, foot_y=GROUND_Y + 20, scale=0.9, pose="stand", speed=1.0),
            dict(kind="son", cx=W * 0.50, foot_y=GROUND_Y + 20, scale=0.85, pose="stand", speed=1.1),
        ],
    )


def _scene4():  # 挖山 + 运土
    return dict(
        tint=(PAPER, PAPER2), mountains=[
            (W * 0.85, GROUND_Y + 40, 340, 560, MOUNT_B),
        ], chars=[
            dict(kind="yu", cx=W * 0.30, foot_y=GROUND_Y + 20, scale=1.0, pose="dig", speed=4.0, beard=True),
            dict(kind="son", cx=W * 0.45, foot_y=GROUND_Y + 20, scale=0.95, pose="dig", speed=4.4),
            dict(kind="son", cx=W * 0.62, foot_y=GROUND_Y + 20, scale=0.92, pose="carry", speed=2.4),
            dict(kind="son", cx=W * 0.74, foot_y=GROUND_Y + 20, scale=0.9, pose="carry", speed=2.0),
        ], dust=True,
    )


def _scene5():  # 小孩蹦跳来帮忙
    return dict(
        tint=(PAPER, PAPER2), mountains=[
            (W * 0.85, GROUND_Y + 40, 320, 520, MOUNT_B),
        ], chars=[
            dict(kind="child", cx=W * 0.30, foot_y=GROUND_Y + 20, scale=0.6, pose="cheer", speed=6.0),
            dict(kind="son", cx=W * 0.70, foot_y=GROUND_Y + 20, scale=0.92, pose="carry", speed=2.2),
        ],
    )


def _scene6():  # 寒暑易节，日升月落
    return dict(
        tint=(PAPER, PAPER2), mountains=[
            (W * 0.5, GROUND_Y + 40, 380, 760, MOUNT_A),
        ], time_cycle=True, chars=[
            dict(kind="yu", cx=W * 0.40, foot_y=GROUND_Y + 20, scale=1.0, pose="dig", speed=3.6, beard=True),
            dict(kind="son", cx=W * 0.55, foot_y=GROUND_Y + 20, scale=0.9, pose="carry", speed=2.2),
            dict(kind="son", cx=W * 0.66, foot_y=GROUND_Y + 20, scale=0.88, pose="dig", speed=4.0),
        ], dust=True,
    )


def _scene7():  # 智叟笑而止之
    return dict(
        tint=(PAPER, PAPER2), mountains=[
            (W * 0.8, GROUND_Y + 40, 300, 500, MOUNT_B),
        ], chars=[
            dict(kind="zhisou", cx=W * 0.28, foot_y=GROUND_Y + 20, scale=1.0, pose="point", speed=1.4, beard=True),
            dict(kind="yu", cx=W * 0.66, foot_y=GROUND_Y + 20, scale=1.05, pose="point", speed=1.0, beard=True),
        ],
    )


def _scene8():  # 子子孙孙无穷匮
    return dict(
        tint=(PAPER, PAPER2), mountains=[],
        descendants=True, chars=[
            dict(kind="yu", cx=W * 0.5, foot_y=GROUND_Y + 20, scale=1.1, pose="stand", speed=0.7, beard=True),
        ],
    )


def _scene9():  # 天帝命夸娥氏负二山
    return dict(
        tint=(PAPER, PAPER2), mountains_anim=True, rays=True, chars=[
            dict(kind="yu", cx=W * 0.5, foot_y=GROUND_Y + 20, scale=1.05, pose="cheer", speed=3.0, beard=True),
            dict(kind="son", cx=W * 0.40, foot_y=GROUND_Y + 20, scale=0.95, pose="cheer", speed=3.4),
            dict(kind="son", cx=W * 0.60, foot_y=GROUND_Y + 20, scale=0.95, pose="cheer", speed=3.2),
            dict(kind="child", cx=W * 0.32, foot_y=GROUND_Y + 20, scale=0.6, pose="cheer", speed=5.0),
        ],
    )


SCENES = [_scene1(), _scene2(), _scene3(), _scene4(), _scene5(),
          _scene6(), _scene7(), _scene8(), _scene9()]


# ─────────────────────────────────────────────────────
# 单帧渲染
# ─────────────────────────────────────────────────────
def render_frame(scene, fi, total, fps=FPS):
    img = Image.new("RGB", (W, H), PAPER)
    draw = ImageDraw.Draw(img, "RGBA")

    t = fi / fps                      # 当前秒
    prog = fi / max(1, total)         # 0..1 进度

    # 背景
    paper_bg(draw, *scene.get("tint", (PAPER, PAPER2)))

    # 太阳 / 日升月落
    if "sun" in scene:
        cx, cy, r, col = scene["sun"]
        draw_sun(draw, cx, cy, r, col)
    if scene.get("time_cycle"):
        # 太阳沿弧线移动，后半段变暗（昼夜）
        ang = prog * math.pi
        sx = 200 + ang / math.pi * (W - 400)
        sy = 200 + math.sin(ang) * -120 + 120
        day = prog < 0.5
        col = SUN if day else (120, 120, 140)
        draw_sun(draw, int(sx), int(sy), 40, col)

    # 山
    if scene.get("mountains_anim"):
        # 两段山向两侧退去（被背走）
        gap = prog * (W * 0.9)
        draw_mountain(draw, int(W * 0.30 - gap), GROUND_Y + 40, 360, 540, MOUNT_A)
        draw_mountain(draw, int(W * 0.72 + gap), GROUND_Y + 40, 400, 620, MOUNT_B)
    else:
        for m in scene.get("mountains", []):
            cx, by, h, w, col = m
            draw_mountain(draw, int(cx), int(by), h, w, col)

    # 天光（seg9）
    if scene.get("rays"):
        for k in range(7):
            a = k * (math.pi / 6) + prog * 0.3
            x2 = W * 0.5 + math.cos(a) * 700
            y2 = 120 + math.sin(a) * 700
            draw.line([(int(W * 0.5), 120), (int(x2), int(y2))],
                      fill=(210, 180, 110, int(50 * (1 - prog * 0.3))), width=6)

    # 地面
    draw.rectangle([0, GROUND_Y, W, H], fill=(206, 196, 176))

    # 房屋 + 炊烟
    if "house" in scene:
        hx, hy, hs = scene["house"]
        draw_house(draw, hx, hy, hs, INK)
        draw_smoke(draw, hx + 38 * hs, hy - 90 * hs, t)

    # 子子孙孙逐个出现
    if scene.get("descendants"):
        N = 18
        shown = int(prog * N) + 1
        base_y = GROUND_Y + 20
        positions = []
        # 排成略带弧度的队列
        for k in range(N):
            px = W * 0.5 + (k - (N - 1) / 2) * 46
            py = base_y - abs(k - (N - 1) / 2) * 1.0
            positions.append((px, py))
        for k in range(min(shown, N)):
            px, py = positions[k]
            # 最新一个弹出放大
            if k == shown - 1:
                ps = 1.0 + (1 - (prog * N) % 1.0) * 0.6
            else:
                ps = 1.0
            scale = 0.42 * ps
            # 大小交替（子孙）
            if k % 2 == 0:
                draw_person(draw, int(px), int(py), scale=scale, color=INK, pose="stand",
                            phase=t * 1.0 + k, beard=False)
            else:
                draw_person(draw, int(px), int(py), scale=scale * 0.92, color=INK2, pose="stand",
                            phase=t * 1.0 + k + 1.5, beard=False)

    # 角色
    for ch in scene.get("chars", []):
        cx = ch["cx"]
        fy = ch["foot_y"]
        scale = ch.get("scale", 1.0)
        pose = ch.get("pose", "stand")
        speed = ch.get("speed", 1.0)
        beard = ch.get("beard", False)
        color = INK if ch["kind"] in ("yu", "zhisou", "son") else (INK2 if ch["kind"] == "child" else INK)
        # tiny / child 用次色
        if ch["kind"] == "child":
            color = INK2
        phase = t * speed * math.pi
        draw_person(draw, int(cx), int(fy), scale=scale, color=color,
                    pose=pose, phase=phase, beard=beard)
        # 挖山尘土
        if pose == "dig" and scene.get("dust") and ch["kind"] in ("yu", "son"):
            draw_dust(draw, int(cx) + 30 * scale, int(fy) - 30 * scale, phase)

    # 转 RGB（去 alpha）
    return img.convert("RGB")


# ─────────────────────────────────────────────────────
# 批量渲染
# ─────────────────────────────────────────────────────
def get_audio_duration(path):
    try:
        import mutagen.mp3
        return mutagen.mp3.MP3(str(path)).info.length
    except Exception:
        return 5.0


def render_all():
    ff = "ffmpeg"
    for i, scene in enumerate(SCENES, 1):
        audio = ROOT / "audios" / f"{i:02d}.mp3"
        dur = get_audio_duration(audio)
        total = max(8, int(round(dur * FPS)))
        out = ANIM_DIR / f"seg_{i:02d}.mp4"
        cmd = [ff, "-y", "-f", "rawvideo", "-pix_fmt", "rgb24",
               "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-",
               "-an", "-c:v", "libx264", "-pix_fmt", "yuv420p",
               "-preset", "fast", "-crf", "18", str(out)]
        p = subprocess.Popen(cmd, stdin=subprocess.PIPE,
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        for fi in range(total):
            frame = render_frame(scene, fi, total, FPS)
            p.stdin.write(frame.tobytes())
        p.stdin.close()
        p.wait()
        print(f"[SEG {i:02d}] {out.name} dur={dur:.1f}s frames={total} -> "
              f"{out.stat().st_size/1024/1024:.2f}MB", flush=True)
    print("ALL SEGMENTS RENDERED")


if __name__ == "__main__":
    render_all()
