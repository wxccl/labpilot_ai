# Quick Start

## Recommended Install

Use the labscript-suite environment that already runs your experiment:

```powershell
conda activate labscript
cd E:\Labpilot\labpilot_ai
pip install -e .
```

LabPilot AI does not install or upgrade `labscript-suite`, `runmanager`, `blacs`, or `lyse` by default. This is intentional: the experiment-control environment should keep the labscript-suite versions that were already tested with the apparatus.

Optional features can be installed separately:

```powershell
pip install -e ".[voice]"      # voice input / faster-whisper
pip install -e ".[tts]"        # local spoken replies
pip install -e ".[fit,opt]"    # fitting and optimization extras
pip install -e ".[docs]"       # PDF text import
```

For a brand-new environment only, install labscript-suite first following the official labscript-suite documentation. The optional `.[labscript]` extra is available for explicit dependency checking, but should not be used casually on a working hardware-control computer:

```powershell
pip install -e ".[labscript]"
```

## Launch

```powershell
labpilot-ai
```

or:

```powershell
python -m labpilot_ai
```

## First Run

1. Open `Settings`.
2. Click `Init/repair project templates`.
3. Open `Directory` and confirm the active sequence file, connection table, runmanager globals H5, H5 output folder, single lyse folder, and multi lyse folder.
4. Open `Command`.
5. Keep `Dry run` enabled for the first parser test.
6. Enter a safe command, for example:

```text
Set duration_tof_ms to 17 ms, do not run.
```

7. Click `Parse`.
8. Confirm the validated action is `set_global`.
9. Use `Dry-run preview` before executing real hardware changes.

## Minimum Safe Hardware Loop

Before real hardware execution:

- The global or BLACS channel must be registered in the corresponding registry.
- Type, range, array length, and risk checks must pass.
- The UI must show a clear old/new value diff.
- High-risk actions still require human confirmation.
- Start with a low-risk variable, then one shot, then a small grid scan, then a single BLACS channel.
