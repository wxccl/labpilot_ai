# LabPilot AI

LabPilot connects an operator or Harness to an existing labscript-suite installation. Inspect the active sequence and output, review a finite experiment, and trace each shot from Runmanager through BLACS to its analysis report.

**Start here:** [中文安装、配置、测试和使用指南](https://github.com/wxccl/labpilot_ai/blob/v0.3.6rc2/manual/START_ZH.md) · [CLI and MCP reference](https://github.com/wxccl/labpilot_ai/blob/v0.3.6rc2/labpilot_ai/AUTOMATION.md).

Install with `python -m pip install --no-deps labpilot-ai==0.3.6rc2` in an existing suite environment. Use `labpilot --profile PROFILE context` to inspect a reviewed profile. In a new empty directory, `labpilot init` creates a simulation instead. No model credential, voice service or desktop extension is needed for these commands.

Use the same profile for approval and execution. A managed BLACS completion receipt, a validated analysis result, and calibrated evidence of a physical signal are different things. Hardware and custom routines require site acceptance. The optional legacy workbench remains available for existing installations; it is not the production writer.

The release candidate opens the workflow GUI with `labpilot-ai`. For native Lyse result observation and the operator workflow see [the GUI guide](manual/NATIVE_GUI_ZH.md). Existing workbench users can run `labpilot-workbench`.

## Install

Install the original desktop in a separate Python environment:

```powershell
python -m pip install "labpilot-ai[desktop,ai]"
```

LabPilot AI intentionally does not install or upgrade `labscript-suite`, `runmanager`, `blacs`, or `lyse` by default. This avoids pip changing a working labscript-suite environment. The core dependency ranges are deliberately broad and capped (`PyQt5<6`, `numpy<3`, `pandas<3`, `h5py<4`, `matplotlib<4`) so an existing labscript-suite install can keep its tested versions.

For a brand-new environment only, install labscript-suite first using the labscript-suite documentation, then install LabPilot AI. If you explicitly want pip to install/check the labscript-suite packages as part of LabPilot installation, use the optional extra:

```powershell
pip install -e ".[labscript]"
```

For a working hardware setup, point the new LabPilot profile at the existing Labscript interpreter. Follow the automation guide to configure the host and check each capability before enabling it.

Optional extras:

```powershell
pip install -e ".[voice]"      # sounddevice + faster-whisper
pip install -e ".[tts]"        # optional pyttsx3 spoken replies
pip install -e ".[fit,opt]"    # scipy + scikit-optimize/optuna
pip install -e ".[docs]"       # pypdf
pip install -e ".[dev]"        # pytest/black/ruff
```

Launch:

```powershell
labpilot-ai
```

or:

```powershell
python -m labpilot_ai
```

## API Configuration

DeepSeek/OpenAI-compatible settings can be entered on the Command page or provided as environment variables. On startup, the API key field is populated from the first available source: local `configs/project_settings.yaml` `ai.api_key` if present, then `DEEPSEEK_API_KEY`, then `OPENAI_API_KEY`. The field is password-hidden by default.

Changing the Command page API key, base URL, or model affects runtime LLM calls after clicking `Apply API settings` or leaving the edited field. `Save base/model` writes only non-secret settings to local `configs/project_settings.yaml`; API keys are intentionally not saved by default.

```powershell
$env:DEEPSEEK_API_KEY="your key"
$env:DEEPSEEK_BASE_URL="https://api.deepseek.com"
$env:DEEPSEEK_MODEL="deepseek-v4-pro"
```

If no key is available, LabPilot falls back to a small local mock parser for basic dry-run testing. Serious experiment planning and Co-Sequence patch generation require a real DeepSeek/OpenAI-compatible API key.

## Project Templates

On first run, click `Init/repair project templates` in Settings to copy clean local templates:

- `configs/global_registry.yaml`
- `configs/blacs_manual_registry.yaml`
- `configs/lyse_registry.yaml`
- `configs/project_settings.yaml`
- `plugins/single_modules/`
- `plugins/multi_modules/`
- `manual/`

Existing local files are not overwritten. Registry saves create `.bak` backups.

## Voice And CUDA Notes

CPU mode is the most stable default:

```yaml
voice:
  device: "cpu"
  compute_type: "int8"
  model_size: "small"
  isolated_stt: true
```

Spoken replies are disabled by default so the app does not unexpectedly speak in the lab. Enable `Enable spoken replies` in the Command page Voice input panel, or configure:

```yaml
voice:
  input_enabled: true
  reply_enabled: true
  reply_on_wake: true
  reply_before_execute: true
  tts_backend: "system"
  tts_rate: 180
  tts_volume: 0.85
```

On Windows, LabPilot can use the local SAPI speaker through PowerShell without sending text to a remote API. Installing `labpilot-ai[tts]` adds the optional `pyttsx3` backend.

GPU STT on RTX cards can use:

```yaml
voice:
  device: "cuda"
  gpu_compute_type: "float16"
```

If Windows reports `Library cublas64_12.dll is not found or cannot be loaded`, run Diagnostics. LabPilot AI includes CUDA DLL path discovery for CUDA Toolkit, `nvidia-cublas-cu12`, `nvidia-cudnn-cu12`, and CTranslate2 directories. See `manual/01_voice/cuda_troubleshooting.md`.

## Release Checks

```powershell
cd E:\Labpilot\labpilot_ai
python -m compileall -q labpilot_ai
python -m pytest -q
git diff --check
```

Before publishing, confirm the wheel/sdist does not contain API keys, experiment H5 data, `labpilot_outputs/`, pycache, build folders, or egg-info.
