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
