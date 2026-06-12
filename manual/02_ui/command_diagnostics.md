# Command 与 Diagnostics 页面

## Command 页面

Command 页面是自然语言和语音控制入口。

主要区域：

- 自然语言输入框。
- `Parse` 按钮：调用 LLM 或 Mock parser，把自然语言变成 JSON action。
- action 表：展示动作类型、目标变量、旧值、新值、风险和状态。
- `Execute last safe action`：只执行通过安全层的动作。
- Voice input：手动录音、待机唤醒、STT 后端、模型 profile、语言和转写后动作。
- `Clear command after Parse`：可选；勾选后只在 Parse 成功时清空自然语言输入框，失败时保留原指令方便修改。

## 推荐操作

真实硬件前：

1. 开启 `Dry run`。
2. 开启 `Mock runmanager`。
3. 用自然语言或语音生成动作。
4. 检查 action 表。
5. 再逐步关闭 Mock 和 Dry run。

## Diagnostics 页面

Diagnostics 用于定位环境问题，尤其是语音：

- `sounddevice` 是否可导入。
- 麦克风设备数量。
- `faster-whisper` 是否可导入。
- 当前 device 和 compute type。
- CUDA DLL 状态。
- 术语表加载状态。
- 错误类型分类。

## 常见错误提示

- `CUDA_RUNTIME_MISSING`：GPU STT 找不到 CUDA/cuBLAS/cuDNN。
- `OPENMP_DUPLICATE`：OpenMP runtime 重复初始化。
- `STT_EMPTY_TEXT`：录音成功但转写为空，通常是音频太短、音量太低或模型加载失败。

错误建议由 `ai/error_advisor.py` 和 `voice/diagnostics.py` 共同提供。

## Voice input and spoken replies

The Command page Voice input panel has two separate master switches:

- `Enable voice input`: enables manual recording, audio-file transcription, and standby wake mode.
- `Enable spoken replies`: enables local text-to-speech status replies.

When spoken replies are enabled, LabPilot announces wake greetings, parsing, dry-run status, validated action summaries, execution completion, and short error messages. Spoken replies are generated from local safe action summaries and do not read API keys, full tracebacks, or long Knowledge snippets.

## Auto Write And Shot Submission

LabPilot separates value writes from shot submission:

- `Auto write`: after Parse, execute safe write actions automatically. If the user text explicitly asks to run, submit, engage, or run a shot, LabPilot shows the normal shot confirmation dialog before engaging runmanager.
- `Auto write and run if requested`: after Parse, execute safe write actions automatically. If the user text explicitly asks to run, submit, engage, or run a shot, LabPilot submits the shot without the extra engage confirmation dialog.
- If the instruction only sets runmanager globals or BLACS manual/static values, LabPilot writes those values and does not run a shot.
- If the LLM returns an `engage` action but the original user text did not explicitly request a shot, LabPilot removes that engage action before validation.
