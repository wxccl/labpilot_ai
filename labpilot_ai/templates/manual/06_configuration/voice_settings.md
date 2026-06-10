# 语音配置

语音配置在 `configs/project_settings.yaml` 的 `voice` 部分。

## 字段说明

```yaml
voice:
  model_size: "small"
  profile: "balanced"
  device: "cpu"
  compute_type: "int8"
  gpu_compute_type: "float16"
  gpu_enabled: false
  language: "zh,en"
  isolated_stt: true
  wake_name: "labscript"
  samplerate: 16000
  silence_threshold: 0.01
  silence_seconds: 1.2
```

字段含义：

- `model_size`：faster-whisper 模型大小。
- `profile`：UI 预设档位。
- `device`：`cpu` 或 `cuda`。
- `compute_type`：CPU 计算类型，推荐 `int8`。
- `gpu_compute_type`：GPU 计算类型，RTX 3090 推荐 `float16`。
- `gpu_enabled`：默认是否启用 GPU。
- `language`：默认 `zh,en`。
- `isolated_stt`：是否使用独立子进程，推荐开启。
- `wake_name`：唤醒词。
- `samplerate`：录音采样率。
- `silence_threshold`：静音阈值。
- `silence_seconds`：自动停止前需要持续静音的秒数。

## CPU 推荐配置

```yaml
voice:
  model_size: "small"
  device: "cpu"
  compute_type: "int8"
  isolated_stt: true
```

## GPU 推荐配置

```yaml
voice:
  model_size: "small"
  device: "cuda"
  gpu_compute_type: "float16"
  isolated_stt: true
```

## 空转写排查

如果日志显示：

```text
raw= corrected=
```

说明 STT 成功返回但没有识别到文字。检查：

- 麦克风 input signal 是否有声音。
- wav 文件是否真的录到人声。
- 录音是否太短。
- 模型是否过小。
- 环境噪声是否太大。
- 语言是否选择 Chinese + English auto。
