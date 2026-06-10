# 待机唤醒模式

待机唤醒模式类似语音助手：先低成本监听声音片段，听到唤醒词后才录制完整命令。

## 默认行为

- 默认唤醒词：`labscript`
- UI 可修改 `Wake name`
- 检测到唤醒词后开始录命令
- 静音超过阈值后自动停止录音
- STT 转写后剥离唤醒词，只把真正命令填入输入框

## 为什么不一直跑 Whisper

一直用 Whisper 监听会占用 CPU/GPU，并且会让实验控制电脑变得不稳定。LabPilot AI 的待机模式先用低成本音量/VAD 检测说话片段，只对短片段做唤醒词判断。

## 相关代码

- `voice/wake_agent.py`：唤醒词匹配和剥离。
- `voice/vad.py`：静音检测和语音片段判断。
- `voice/recorder.py`：音频采集。
- `app/main_window.py`：UI 开关和状态显示。

## 配置

```yaml
voice:
  wake_name: "labscript"
  samplerate: 16000
  silence_threshold: 0.01
  silence_seconds: 1.2
```

如果环境比较吵，可以适当提高 `silence_threshold`。如果命令经常被截断，可以增加 `silence_seconds`。
