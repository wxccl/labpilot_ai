# Packaging And Release

LabPilot AI is packaged with `pyproject.toml` and setuptools. The first public release target is a safe-by-default desktop tool for existing labscript-suite environments.

## Labscript-Suite Compatibility

Install LabPilot AI inside an environment that already contains the tested labscript-suite stack whenever possible:

```powershell
conda activate labscript
cd E:\Labpilot\labpilot_ai
pip install -e .
```

LabPilot AI intentionally does **not** declare `labscript-suite`, `labscript`, `runmanager`, `blacs`, or `lyse` as default dependencies. This prevents pip from upgrading or replacing packages that are already known to work with the lab hardware.

The core dependency ranges are broad and capped:

- `PyQt5>=5.12,<6`
- `numpy>=1.20,<3`
- `pandas>=1.3,<3`
- `h5py>=3.0,<4`
- `matplotlib>=3.5,<4`

These ranges are designed to accept the versions commonly present in labscript-suite v3 environments, including the local reference environment used during development:

- `labscript-suite==3.2.0`
- `labscript==3.3.1`
- `runmanager==3.2.1`
- `blacs==3.2.1`
- `lyse==3.2.3`
- `numpy==1.26.2`
- `pandas==2.2.1`
- `h5py==3.14.0`
- `matplotlib==3.8.4`
- `PyQt5==5.15.10`

For a brand-new environment only, install labscript-suite first following the official labscript-suite documentation. If you explicitly want pip to install or check labscript-suite packages together with LabPilot, use:

```powershell
pip install -e ".[labscript]"
```

Do not use this extra casually on a hardware-control machine with a working labscript-suite environment, because dependency resolution may change labscript-suite package versions.

## Optional Extras

Install optional features only when needed:

```powershell
pip install -e ".[voice]"      # sounddevice + faster-whisper
pip install -e ".[tts]"        # pyttsx3 spoken replies
pip install -e ".[fit,opt]"    # scipy + scikit-optimize/optuna
pip install -e ".[docs]"       # pypdf
pip install -e ".[dev]"        # pytest/black/ruff
```

Voice/GPU packages can pull large binary dependencies. Install them after the base UI works.

## Entry Points

```toml
[project.scripts]
labpilot-ai = "labpilot_ai.main:main"
labpilot-blacs-bridge = "labpilot_ai.blacs_ctrl.manual_bridge_server:main"
```

After installation:

```powershell
labpilot-ai
```

## Release Checklist

1. Confirm no API key, local H5 data, `labpilot_outputs/`, pycache, build output, or egg-info enters the package.
2. Run:

```powershell
python -m compileall -q labpilot_ai
python -m pytest -q
git diff --check
python -m pip check
```

3. Build wheel/sdist:

```powershell
python -m build --no-isolation
```

4. Inspect package contents. The wheel should include source code, `label.png`, `templates/configs/*.yaml`, `templates/manual/**/*.md`, and example plugins only.
5. Install in a clean test environment and launch `labpilot-ai`.
6. Click `Init/repair project templates` and verify local `configs/`, `plugins/`, and `manual/` are created without overwriting existing user files.

## Windows Executable Notes

PyInstaller can be added later for non-developer lab computers. Keep these rules:

- Do not bundle API keys.
- Keep voice models as user-managed downloads or configured local paths.
- Include `label.png`, default config templates, manual templates, and example plugins.
- Test CPU STT and GPU STT separately because CUDA/cuDNN DLL search paths differ between environments.

## Compatibility Rules

- Do not modify labscript suite, runmanager, BLACS, or lyse internals.
- Use stable interfaces, HDF5/lyse-compatible data structures, and localhost bridge boundaries.
- Keep Co-Sequence restricted to the active sequence file and active connection table file.
- Store LabPilot analysis, plots, fitting parameters, reports, and logs in LabPilot outputs/SQLite/JSONL. Do not rewrite original H5 files in the first release.
