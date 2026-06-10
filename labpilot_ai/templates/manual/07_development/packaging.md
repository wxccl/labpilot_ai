# Packaging And Release

LabPilot AI 使用 `pyproject.toml` 和 setuptools 打包。第一版发布目标是：默认安全、Mock/Dry-run 可演示、模板和手册完整、真实硬件接入由实验室分阶段验证。

## Editable Install

```powershell
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

## Entry Point

```toml
[project.scripts]
labpilot-ai = "labpilot_ai.main:main"
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
```

3. Build wheel/sdist:

```powershell
python -m build
```

4. Inspect package contents. The wheel should include source code, `label.png`, `templates/configs/*.yaml`, `templates/manual/**/*.md`, and example plugins only.
5. Install in a clean environment and launch `labpilot-ai`.
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
