# Pi Host Fidelity Guide

本指南说明在编写演示舞台前，应从哪些真实来源核对当前版本的 Pi 宿主与插件渲染细节，避免硬编码过期样式或遗漏宿主固定行为。

## Where to Inspect Ground Truth

每次为插件制作演示前，按以下顺序读取真实源文件，以代码为准：

1. **主题配色**：读取目标插件的 `extensions/<plugin>/themes/*.json`（重点看 `vars`、`colors` 中的背景、边框、思考态、Diff 增删底色与特殊模式色）。
2. **欢迎区、输入框与底栏**：读取 `extensions/<plugin>/src/` 下的 header / editor / footer / palette 文件，核对：
   - 边框字符、列宽计算、窄屏单栏切换阈值与底栏紧凑态阈值；
   - 特殊输入模式（如 `!` Bash 态）下输入框内是否保留触发字符、以及边框/提示符/底栏的同步变色；
   - 思考等级文字、颜色与快捷键提示的真实文案。
3. **Working 与实时速率**：读取目标插件的 `working.ts` 及 `shared/ui/working-activity.ts`，核对刷新节奏（`WORKING_FRAME_MS`）、星号帧序列、流光/动词文本、实时速率前缀格式以及任务结束后是否清空速率。
4. **Markdown、思考块与工具流**：读取目标插件的 `markdown.ts` 与工具渲染文件（如 `claude-tools.ts` / `tools.ts`），核对用户与助手消息前缀、思考块标题与折叠文案、工具标题圆点状态色、分支连接符以及 Diff 摘要和行号格式。
5. **Pi 宿主固定容器**：读取 `node_modules/@earendil-works/pi-coding-agent/dist/modes/interactive/components/`（尤其是 `user-message.js`、`assistant-message.js`）以及 `shared/ui/keybinding-hints.ts`，重点核对插件无法绕过的宿主行为：
   - `UserMessageComponent` 的 `paddingX`（`Output padding`，默认 `1`）与 `paddingY`（如 `paddingY = 1` 会让带 `userMessageBg` 的用户消息呈现为 3 行高直角矩形块，而非单行或圆角气泡）；
   - 默认快捷键提示是否动态来自 `keybindings.json`。
6. **行为验收对照**：参考对应插件的验证 skill（如 [verify-pi-claude-code-ui](../../verify-pi-claude-code-ui/SKILL.md) 或 [verify-pi-codex-ui](../../verify-pi-codex-ui/SKILL.md)）中的断言与特征说明，快速确认容易忽略的交互状态。

## PTY Capture Sync Rule

仅当某项宿主行为无法仅凭读源码确认时，再使用隔离的 `PI_CODING_AGENT_DIR` 与离线 provider 在 PTY 中运行真实 Pi 做一次性取证，且采集脚本必须遵守两条终端协议规则：

- **DEC Mode 2026 Synchronized Output**：`pi-tui` 重绘屏幕时用 `\x1b[?2026h`（开始）和 `\x1b[?2026l`（结束）包裹每一帧。使用 `pyte` 捕获时必须在同步块内只喂数据不截帧，收到 `\x1b[?2026l` 时才原子提交快照，否则会截出双份行或残缺旧内容的撕裂帧。
- **SGR Dim 保留**：标准 `pyte.Screen` 默认丢弃 SGR 2（`dim`），若需核对 dim 文本（如 Diff 删行与行号槽），须通过 `Screen` 子类追踪 SGR 2 / SGR 22。
