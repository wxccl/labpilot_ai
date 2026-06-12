# Voice Settings

Voice settings live in `configs/project_settings.yaml` under the `voice` section. LabPilot separates voice input from spoken replies so an experiment computer never starts speaking unexpectedly.

## Recommended Defaults

```yaml
voice:
  input_enabled: true
  reply_enabled: false
  reply_on_wake: true
  reply_before_parse: true
  reply_before_execute: true
  reply_after_execute: true
  reply_on_error: true
  tts_backend: "system"
  tts_rate: 180
  tts_volume: 0.85
  tts_max_chars: 240
  model_size: "small"
  profile: "balanced"
  device: "cpu"
  compute_type: "int8"
  gpu_compute_type: "float16"
  language: "zh,en"
  isolated_stt: true
  wake_name: "labscript"
  samplerate: 16000
  silence_threshold: 0.01
  silence_seconds: 1.2
```

## Voice Input

- `input_enabled`: master switch for recording, audio-file transcription, and wake standby.
- `wake_name`: standby wake name, default `labscript`.
- `language`: `zh,en` keeps Chinese and English terms available.
- `model_lifetime`: use `isolated_release` when stability and GPU memory release are more important than latency.

When voice input is disabled, the UI disables `Start voice recording`, `Transcribe audio file`, and `Standby wake mode`.

## Spoken Replies

- `reply_enabled`: master switch for text-to-speech replies.
- `reply_on_wake`: greet after standby wake detection.
- `reply_before_parse`: announce parsing and safety validation.
- `reply_before_execute`: summarize validated safe actions before execution.
- `reply_after_execute`: announce completion or shot submission.
- `reply_on_error`: announce short error categories.
- `tts_backend`: `system` uses local Windows SAPI through PowerShell; `pyttsx3` can be installed with `labpilot-ai[tts]`.
- `tts_rate`, `tts_volume`, `tts_max_chars`: control speed, loudness, and maximum spoken text length.

Spoken replies summarize only local `SafetyValidator` output. They do not read API keys, full tracebacks, long paths, or raw Knowledge snippets.

## UI Controls

The Command page Voice input panel includes:

- `Enable voice input`
- `Enable spoken replies`
- `Test speaker`
- `Stop speaking`
- `TTS rate`
- `TTS volume`

The Diagnostics page reports whether the speaker backend is available and can run a short speaker test.
