---
name: create-pi-ui-demo
description: "Produce 1080p60 UI motion product demo videos for pi-ext terminal plugins (codex-ui, claude-code-ui, or new Pi themes). Use when creating, updating, or re-rendering a release video, feature trailer, or animated product showcase."
---

# Create Pi UI Demo

为 `pi-ext` 中的终端界面插件（`codex-ui`、`claude-code-ui` 或新增 Pi 插件/主题）制作 1080p60 无旁白 UI Motion 产品演示视频。所有单次创作的中间文件与成品输出到 `.scratch/<demo-name>/`（已被 `.gitignore` 忽略），不向跟踪目录写入临时产物。

完整参考案例见 [examples/claude-code-ui/demo.html](examples/claude-code-ui/demo.html) 与 [examples/claude-code-ui/events.json](examples/claude-code-ui/events.json)，用于快速把握分镜节奏、2D 虚拟运镜、双语动态字幕、按键胶囊与音效卡点写法；新演示不必拘泥于其视觉布局。

## Workflow

按顺序执行以下六个步骤，每步满足完成标准后再进入下一步。

### 1. Align Scope

仅在用户尚未明确时确认以下三项边界：

- **时长与节奏**：紧凑交互秀（30–45s）或完整特性介绍（60–90s）。
- **展示范围**：单个插件/主题、多插件对比，或特定版本的新特性清单。
- **字幕与音频**：字幕语言（中英双语 / 英文 / 中文），以及是否用内置合成器生成 BGM 与交互 SFX。

完成标准：时长、展示特性清单、字幕语言与音频方案全部明确。

### 2. Inspect Source and Pi Host Fidelity

写界面前必须按 [Pi Host Fidelity Guide](references/pi-host-fidelity.md) 从目标插件源码与 Pi 宿主中核对真实视觉与交互细节（颜色变量、欢迎区与窄屏阈值、输入框与底栏状态切换、Working 动画与速率生命周期、Markdown 变换、工具与 Diff 渲染、以及宿主写死的容器边距）。

仅在源码无法确认某项宿主行为时，才用隔离 PTY 跑一次真实 Pi 取证；取证脚本须遵守 [PTY Capture Sync Rule](references/pi-host-fidelity.md#pty-capture-sync-rule)。

完成标准：所有待演示界面的色值、文案格式、布局阈值与宿主行为均已从源码核实。

### 3. Build Deterministic 60fps Stage

在 `.scratch/<demo-name>/demo.html` 编写确定性动效舞台，统一暴露纯函数 `window.renderAt(t)`（`t` 为秒）：

- **动效路线**：视频主画面使用 HTML/CSS/JS 高保真重建的确定性舞台，而非直接拿 PTY 录屏帧当视频源，以保证 60fps 连续缩放、丝滑滚屏、零过程噪点与帧级音画同步。
- **锐度约束**：
  - 终端与文字主层仅做纯 2D `translate3d` + `scale` 运镜；立体层次交给背景光晕与网格的 2.5D 视差（`translate3d` 按镜头位移 12%–18% 跟随），避免 3D `rotateX/rotateY` 造成小号等宽字发虚。
  - 终端画布保持深色高对比，`dim` 文字不透明度不低于 `0.75`。
  - 块状像素图形（如角色图标、大徽章）使用单路径 `fill-rule="evenodd"` + `shape-rendering="crispEdges"` 矢量 `<svg>` 绘制，避免相邻 Unicode 块字符（`█`）在字体抗锯齿与缩放下产生黑色亚像素竖线。
- **布局约束**：
  - 等宽终端区使用系统已安装的 Nerd Font（如 `JetBrainsMono Nerd Font Mono`），关闭连字（`font-variant-ligatures: none`）；`white-space: pre` 仅作用在终端行节点上，避免父容器继承把 HTML 缩进算作行高而裁切底栏。
  - 精确匹配终端像素宽度与字符列数，宽窄两态均保持边框闭合且底栏左右完整同框。
  - 放大特写时为侧边字幕区叠柔和渐变遮罩；检查中文字幕断行，避免单字寡行；按键胶囊（Keystroke HUD）落在留白处，不压关键文本。

完成标准：`.scratch/<demo-name>/demo.html` 就绪，可独立在浏览器中通过 `window.renderAt(t)` 渲染任意时刻画面。

### 4. Visual QA via 2x Preview and 1:1 Sharpness Crop

全量渲染前必须先跑预览，快速暴露布局与锐度问题：

```bash
conda run -n codex-py312 python .cursor/skills/create-pi-ui-demo/scripts/render_demo.py \
  --html .scratch/<demo-name>/demo.html \
  --preview \
  --stamps 0.6,3.8,7.2,10.2,12.2,14.4,15.6,18.4,21.6,25.4,31.2,35.5 \
  --crop-stamp 18.4 \
  --out .scratch/<demo-name>
```

使用当前环境支持的图像查看能力亲自检查生成的 `preview_sheet.png` 与 `sharpness_1to1.png`，逐项确认：

- 全部关键帧底栏完整可见、无右侧裁切、无边框错位、无按键胶囊压字、无中文单字换行；
- `sharpness_1to1.png` 中代码、Diff 与斜体文字边缘锐利无雾感；
- 像素图标内部纯平无黑色竖线。

若有问题，修完 `demo.html` 后重跑 `--preview` 直至全部通过。

完成标准：接触表与 1:1 锐度特写全部目视通过。

### 5. Synthesize Synced Audio (Optional)

若范围确认阶段选择静音出片或由用户另行配乐，跳过本步。

在 `.scratch/<demo-name>/events.json` 中记录与 `demo.html` 时间轴对齐的 SFX 事件（参考 [examples/claude-code-ui/events.json](examples/claude-code-ui/events.json) 或运行 `synth_bgm.py --help`），生成 48kHz 立体声 `audio.wav`：

```bash
conda run -n codex-py312 python .cursor/skills/create-pi-ui-demo/scripts/synth_bgm.py \
  --duration 38.0 \
  --bpm 112 \
  --events .scratch/<demo-name>/events.json \
  --out .scratch/<demo-name>/audio.wav
```

完成标准（选择合成音频时）：`.scratch/<demo-name>/audio.wav` 生成完成，时长与视频一致。

### 6. Render Final 1080p60 Video and Inspect

调用内置 2x Retina 渲染器出片（默认 `3840×2160` 无损 PNG 管道 → Lanczos 下采样 `1080p60` → 单次 `crf 13` 编码 → `-c:v copy` 无二次转码合流，自动清理本次独立分片临时目录）。静音成片省略 `--audio` 参数：

```bash
conda run --no-capture-output -n codex-py312 python .cursor/skills/create-pi-ui-demo/scripts/render_demo.py \
  --html .scratch/<demo-name>/demo.html \
  --audio .scratch/<demo-name>/audio.wav \
  --out .scratch/<demo-name>/<demo-name>.mp4 \
  --duration 38.0 \
  --fps 60 \
  --workers 6
```

完成后必须执行最终验收：

- 画面与节奏：若当前环境支持直接检视视频文件，直接观看成品 MP4 核对运镜流畅度与音画同步；否则使用 `ffmpeg` 按秒抽帧拼成接触表目视核对画面，并在交付时提示用户播放确认音画同步；
- 流元数据：用 `ffprobe` 核对视频流为 `1920×1080`、`60/1`、`bt709` 且时长匹配；含音轨时同步核对音频流为 `aac`、`48000Hz`、`2 channels`，并用 `ffmpeg -i <mp4> -af volumedetect -f null -` 确认音轨非静音；
- 仓库洁净度：核对 `git status` 确认未向仓库跟踪目录写入临时产物。

完成标准：成片画面、流元数据与仓库洁净度全部验收通过，内联展示成品并附路径链接。

## Runtime Prerequisites

- Python 环境：`codex-py312`（需具备 `playwright`、`PIL`、`numpy`、`scipy`）。
- 浏览器：本机 Chrome（默认 `/Applications/Google Chrome.app/Contents/MacOS/Google Chrome`，可用 `--chrome` 覆盖）。
- 音视频工具：`ffmpeg`、`ffprobe`。
- 终端字体：系统已安装支持 Powerline 与 Box Drawing 的等宽 Nerd Font（如 `JetBrainsMono Nerd Font Mono`）。
