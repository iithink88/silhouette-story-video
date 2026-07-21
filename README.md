# 几何剪影动画故事视频生成器

把任意故事（龟兔赛跑、愚公移山、或你自编的寓言）变成一支**主角会动起来的剪影动画视频**。
**全程在你电脑上运行，完全免费，不需要任何账号、Key 或付费服务。**

- 🐇 主角用代码绘制的实心剪影，会**跑、爬、挖山、运土、冒炊烟、子子孙孙接力**……
- 🔊 配音用微软晓晓声（edge-tts，免费）
- 🎬 片头标题卡 + 9 段动画 + 交叉淡入淡出转场 + 两行字幕
- 🔒 隐私安全：素材不出本机，无云端调用

---

## 三步上手

### 第 1 步：准备环境（只需一次）

1. 安装 Python 3.10+（勾选 "Add to PATH"）。
2. 安装 ffmpeg 并加入 PATH（百度"windows 安装 ffmpeg"跟着做）。
3. 装两个 Python 包（在命令行执行）：
   ```bash
   pip install pillow edge-tts -i https://pypi.tuna.tsinghua.edu.cn/simple
   ```

### 第 2 步：准备故事

本技能自带两个故事示例。想做哪个，就把对应文件复制到你的**工作目录**并改名为 `story.py`：

| 想做的视频 | 复制这个文件 |
|---|---|
| 龟兔赛跑 | `examples/guitubisai_story.py` |
| 愚公移山 | `examples/yugong_story.py` |

> 想做自己的故事：打开任一个示例，把 `NARRATIONS` 里的 9 句话换成你的旁白，把 `THEME` 换成标题即可。

### 第 3 步：运行生成

新建一个空文件夹作为**工作目录**（例如 `D:/videos/yugong`），在命令行里 `cd` 进去，然后按顺序跑：

```bash
PY="python"          # 如果 python 不在 PATH，用完整路径
SKILL="C:/你的路径/silhouette-story-video"   # 本技能文件夹位置

# ① 生成配音（audios/01~09.mp3）
python "$SKILL/scripts/gen_audio.py" --workdir .

# ② 渲染 9 段剪影动画（animated_segments/seg_01~09.mp4）
#    龟兔赛跑：
python "$SKILL/scripts/animate_segments.py"
#    愚公移山（二选一，不要两个都跑）：
# python "$SKILL/scripts/animate_yugong.py"

# ③ 合成成品（videos/final.mp4）
#    龟兔：
python "$SKILL/scripts/rebuild_animated.py" --workdir .
#    愚公：
# python "$SKILL/scripts/rebuild_yugong.py" --workdir .
```

跑完打开 `<工作目录>/videos/final.mp4` 就是成品！

---

## 目录结构

```
silhouette-story-video/
├── SKILL.md              # 技能说明（给 AI 助手看）
├── README.md             # 本文件
├── examples/             # 故事文案示例（龟兔 / 愚公）
│   ├── guitubisai_story.py
│   └── yugong_story.py
└── scripts/              # 生成脚本（无需改动即可用）
    ├── common.py         # 公共工具
    ├── video_assemble.py # 通用合成管线（字幕/转场/上移）
    ├── gen_audio.py      # edge-tts 配音
    ├── animate_segments.py   # 龟兔赛跑动画引擎
    ├── animate_yugong.py     # 愚公移山动画引擎
    ├── rebuild_animated.py   # 龟兔合成
    └── rebuild_yugong.py     # 愚公合成
```

## 常见问题

- **要联网吗？** 配音（edge-tts）需要联网；动画渲染和合成完全离线。
- **要 Key / 付费吗？** 不需要。本技能不调用任何付费 AI 或 API。
- **想换配音声音？** 加 `--voice` 参数，例如 `--voice zh-CN-YunxiNeural`（男声）。
- **想用自己做的精美标题图？** 把一张图命名为 `title_card.png` 放到工作目录，再跑合成脚本即可自动使用。
- **做新故事？** 复制 `animate_yugong.py` 改成你的角色与分镜，参考脚本内注释即可（稍需 Python 基础）。
