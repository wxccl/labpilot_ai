# LabPilot AI

LabPilot AI is an industrial-style local AI copilot for labscript-suite experiments. It does not modify labscript, runmanager, BLACS, or lyse internals. Instead, it wraps stable boundaries: registry whitelists, local safety validation, runmanager/BLACS/lyse adapters, HDF5-compatible data, SQLite/JSONL logs, and a PyQt5 desktop UI.

The first release is designed to be safe by default: Mock LLM, Mock runmanager/BLACS, and Dry-run workflows can demonstrate the full loop before any real hardware action is enabled.

## Main Features

- Industrial PyQt5 UI: Command, Runmanager, BLACS Manual, Lyse, Optimizer, Co-Sequence, Experiment Log, Protocol, Knowledge, Directory, Diagnostics, Error Center, and Settings.
- Voice input: manual recording, standby wake mode, Chinese/English transcription, CPU/GPU faster-whisper backends, scientific-term correction, and microphone signal display.
- AI command schema: strict JSON actions using `type`, including `set_global`, `set_blacs_manual`, `engage`, `load_h5`, `run_single_lyse`, `run_multi_lyse`, `plot`, `fit`, `start_optimization`, and `generate_report`.
- Safety layer: whitelist validation, type/range/array checks, high-risk confirmations, dry-run previews, diffs, rollback hooks, SQLite audit records, and Error Center reporting.
- runmanager control: globals read/write, float/int/bool/array scan handling, shot preview, and engage through adapters.
- BLACS manual workflow: mock/localhost bridge client, readonly discovery/readback (`/status`, `/channels`, `/values`), and registered manual actions gated by the SafetyValidator.
- lyse/HDF5 workflow: H5 folder/file loading, table row/column management, original lyse `.py` script compatibility (`lyse.path`, `Run(path)`, `lyse.data()`), LabPilot module selection, result table merging, JSONL/SQLite cache, plots, fits, and reports.
- Optimizer: grid and Bayesian ask/tell, plus supervised auto loop: set parameters, engage, wait for new H5, run checked lyse modules, evaluate objective, and continue safely.
- Knowledge base: local SQLite FTS index over sequence code, connection table, lyse modules, labscript source, manuals, papers, and registries. Remote LLMs only receive short retrieved snippets.
- Protocol Designer: import text/Markdown/PDF text and image paths to generate experiment-design suggestions without executing them.
- Co-Sequence: AI-assisted restricted diffs for only the active sequence file and active connection table, with validation, backup, review, color tags, and change logs.
- Experiment Log: daily Markdown/LaTeX/DokuWiki logs from natural-language commands, run records, optimizer/analysis records, Co-Sequence changes, errors, and Knowledge snippets.
- Directory: the primary path console for active sequence, connection table, globals, BLACS context, lyse folders, H5 output, Knowledge sources, manuals, papers, and log folders.
- Package templates: PyPI installs include default configs, example plugins, `label.png`, and the manual templates.

## First-Release Limits

- LabPilot AI does not modify labscript-suite internals.
- Co-Sequence never edits arbitrary files; it is restricted to the active sequence `.py` and active connection table `.py`.
- Co-Sequence does not automatically run experiments after code edits.
- lyse fitting and plotting parameters are stored in LabPilot analysis records, JSONL, SQLite, and reports. The first release does not write fitting results back into original H5 files.
- Knowledge snippets are short context references only; LabPilot AI does not execute arbitrary source code from the Knowledge database.
- Real runmanager/BLACS/lyse hardware workflows must be validated in the lab in stages: low-risk globals, one shot, small grid scan, then BLACS single-channel tests.
- v0.1.3 BLACS integration is intentionally conservative: readonly discovery/readback is the first real-bridge target. Real manual writes should only be enabled after a lab-side BLACS plugin/bridge has been reviewed and staged on low-risk channels.

## Install

Use the labscript conda environment or another environment that can import the labscript suite:

```powershell
conda activate labscript
cd E:\Labpilot\labpilot_ai
pip install -e .
```

Optional extras:

```powershell
pip install -e ".[voice]"      # sounddevice + faster-whisper
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

DeepSeek/OpenAI-compatible settings can be entered in the UI or provided as environment variables:

```powershell
$env:DEEPSEEK_API_KEY="your key"
$env:DEEPSEEK_BASE_URL="https://api.deepseek.com"
$env:DEEPSEEK_MODEL="deepseek-v4-pro"
```

If no key is available, keep `Mock LLM` enabled to test parsing and safety flows offline.

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
