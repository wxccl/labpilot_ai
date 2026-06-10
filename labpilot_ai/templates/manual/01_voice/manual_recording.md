# 手动语音录入

手动语音是最稳定的语音入口，适合实验现场使用。

## 工作流程

1. 在 Command 页面找到 `Voice input` 区域。
2. 点击 `Start voice recording`。
3. 说出中文、英文或中英文混合命令。
4. 再按一次同一个按钮停止录音。
5. 软件保存临时 wav 文件，调用 STT 后端转写。
6. 转写文本经过术语纠错后填入自然语言命令框。

## 转写后动作

`After transcription` 有三种选择：

- `Fill command box only`：只填入命令框，最安全。
- `Parse after transcription`：填入后自动点击 Parse。
- `Parse and execute safe action`：填入、解析并执行通过安全层的动作。

真实硬件联机时建议先使用 `Fill command box only` 或 `Parse after transcription`，确认动作表无误后再人工执行。

## 麦克风信号

UI 中有实时 input signal：

- 进度条显示当前音量。
- 状态文字显示 `Silent`、`Low` 或 `Voice`。
- 如果说话时没有变化，先检查 Windows 输入设备、麦克风权限和 `sounddevice` 诊断结果。

## 临时音频文件

录音默认保存到系统临时目录，文件名类似：

```text
C:\Users\lenovo\AppData\Local\Temp\labpilot_voice_xxxxx.wav
```

如果转写为空，先确认：

- 麦克风信号条是否有变化。
- 音频文件是否真的包含声音。
- 语言选择是否为 Chinese + English auto。
- STT 后端是否成功加载。
