---
name: silhouette-story-video
description: |
  几何剪影动画故事视频生成器（纯本地、零 API Key）。输入一个故事主题，自动产出「配音 + 9 段几何剪影动画 + 片头标题卡 + 交叉淡入淡出转场 + 两行字幕」的完整 mp4。
  主角用 Python PIL 逐帧绘制的实心剪影（兔/龟/愚公/智叟等），并做跑步、爬行、挖山、运土、炊烟、子子孙孙等动画；全程离线运行，配音用 edge-tts（免费），合成用 ffmpeg，不需要任何付费服务或 Key。
  内置两个完整故事：龟兔赛跑（animate_segments.py）、愚公移山（animate_yugong.py），可直接一键生成；也可仿照写自己的故事。
trigger_keywords: [剪影动画, 几何剪影, 故事视频, 动画故事视频, 剪影视频动画, silhouette animation, 剪纸动画, 寓言动画]
---

# 几何剪影动画故事视频生成器（silhouette-story-video）

把任意故事主题，变成「几何剪影主角 + 真·动画 + 配音 + 字幕」的可播放视频。
**全程本地运行，零 API Key，零付费**：主角用 PIL 逐帧绘制剪影并做动作动画，配音用 edge-tts 免费晓晓声，合成用 ffmpeg。

> 与旧版区别：旧版用即梦 AI 出分镜图（需 JIMENG_KEY，静止画面）。本版是**几何剪影 + 逐帧动画**，完全免费，角色会真的跑/爬/挖/运。

---

## 你（AI）要做的事

这是一个「半自动」技能：AI 负责编排，本地 Python 脚本负责生成。

### 第一步：收集 2 个参数

| # | 参数 | 含义 | 示例 |
|---|---|---|---|
| 1 | 主题 (theme) | 故事主题：寓言 / 历史故事 / 成语故事 | "龟兔赛跑" / "愚公移山" / "守株待兔" |
| 2 | 工作目录 (workdir) | 绝对路径，所有产物（audios/、animated_segments/、videos/）都放这里 | `D:/videos/yugong` |

若用户已说清，直接整理确认；否则分轮问。

### 第二步：准备故事文案（story.py）

每个视频 = 9 段，每段一句旁白。二选一：

- **用内置示例**：把 `examples/guitubisai_story.py`（龟兔）或 `examples/yugong_story.py`（愚公）复制到 `<workdir>/story.py`。
- **新故事**：照示例写 `story.py`，含 `THEME = "故事名"` 和 `NARRATIONS = [9 段文案]`。

### 第三步：运行生成链路（用托管 Python 完整路径）

```bash
PY="$HOME/.workbuddy/binaries/python/versions/3.13.12/python.exe"  # 任意 Python 3.10+，需装 pillow/edge-tts
SKILL="$HOME/.workbuddy/skills/silhouette-story-video"
WORK="D:/videos/yugong"                       # 你的工作目录

# ① 配音（edge-tts 免费，生成 audios/01~09.mp3）
$PY "$SKILL/scripts/gen_audio.py" --workdir "$WORK"

# ② 渲染 9 段几何剪影动画（生成 animated_segments/seg_01~09.mp4）
#    龟兔赛跑：
$PY "$SKILL/scripts/animate_segments.py"
#    愚公移山（或你写的同类引擎）：
# $PY "$SKILL/scripts/animate_yugong.py"

# ③ 合成成品（标题卡 + xfade + 字幕 + 旁白 → videos/final.mp4）
#    龟兔：
$PY "$SKILL/scripts/rebuild_animated.py" --workdir "$WORK"
#    愚公：
# $Y "$SKILL/scripts/rebuild_yugong.py" --workdir "$WORK"
```

> 跑完告诉用户输出位置：`<workdir>/videos/final.mp4`。

### 第四步（可选）：精美标题卡

默认标题卡是 PIL 手绘的剪影装饰 + 主题文字。若想用 AI 生成的整图标题卡：
把一张 `title_card_jimeng.png`（或 `title_card.png`）放到 `<workdir>/`，再跑 rebuild 脚本，会自动优先使用。本技能不提供出图能力（避免引入付费 Key），朋友可另用即梦等工具生成后放入。

---

## 风格与边界

- **视觉风格固定**：暖米纸底 + 黑/灰剪影 + 橙红点缀，剪纸/绘本感。
- **结构固定**：恰好 9 段，每段一句旁白（约 25~45 秒/段，总时长 45~75 秒）。
- **配音**：默认 edge-tts `zh-CN-XiaoxiaoNeural`（中文自然女声），免费；可换 `--voice`。
- **字幕**：自动按中文字宽折成最多 2 行，底部留白带半透明背板，不遮挡上方动画主体（画面整体上移 72px 给字幕留白）。
- **转场**：段间 ffmpeg `xfade` 交叉淡入淡出（0.6s）；片头 3 秒静音标题卡。
- **零凭证**：本技能不读取任何 API Key，不联网调用付费模型。

## 扩展新故事（给 AI 的进阶指引）

内置两个引擎是「示例 + 模板」。做新故事时：
1. 复制 `animate_yugong.py` 为 `animate_<story>.py`，改 `SCENES`（9 段场景定义）和人物绘制类（参考其中的 `draw_person` / `draw_child`：头、身、四肢、扁担、锄头等用 `ImageDraw` 几何图元 + 按 `frame_idx` 做动作相位）。
2. 写对应 `rebuild_<story>.py`（复制 `rebuild_yugong.py`，改标题卡函数 `make_title_card_<story>` 与 bg 补色）。
3. `story.py` 提供 `NARRATIONS` + `THEME`。
4. 跑 ①②③ 三步。
动作设计套路：身体位置用 `math.sin(phase)` 做呼吸/弹跳；四肢用相位偏移画摆角；特效（炊烟/尘土/旗帜）用上升 + 透明度衰减粒子。

## 触发关键词
`剪影动画` / `几何剪影` / `故事视频` / `动画故事视频` / `剪影视频动画` / `剪纸动画` / `寓言动画`

## 依赖安装
```bash
PY="$HOME/.workbuddy/binaries/python/versions/3.13.12/python.exe"
$PY -m pip install pillow edge-tts -i https://pypi.tuna.tsinghua.edu.cn/simple
```
ffmpeg 需已在 PATH（本机已捆绑；朋友机器需自行安装并加入 PATH）。

## 常见错误
| 报错 | 原因 | 解决 |
|---|---|---|
| `未找到 story.py` | 工作目录缺 story.py | 从 examples/ 复制并改名，或自己写 NARRATIONS |
| `seg_XX.mp4 缺失` | 没跑 animate 引擎 | 先跑 animate_*.py 渲染 9 段 |
| edge-tts 无声音/超时 | 未联网或被墙 | 检查网络；或换 `--voice` 其它区域音色 |
| ffmpeg 找不到 | 未在 PATH | 安装 ffmpeg 并加入 PATH，或用绝对路径 |
| 字体找不到 | 非 Windows / 缺 msyh | 代码已 `load_default()` 兜底，仅标题卡字体略变 |
