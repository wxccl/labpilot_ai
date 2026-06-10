# lyse and HDF5 workflow

LabPilot AI keeps the original labscript-suite HDF5 format intact. The Lyse page reads H5 files, runs selected analysis routines, merges returned columns into the UI table, and stores LabPilot analysis records in local JSONL/SQLite/report outputs.

## v0.1.3 native lyse script support

LabPilot can run two kinds of analysis routines:

- `mode: labpilot_module`: a LabPilot plugin with a `run(...)` function.
- `mode: lyse_script`: an original top-level lyse `.py` routine executed in an isolated subprocess.

For single-shot lyse scripts, the subprocess provides:

- `lyse.path`
- `from lyse import path`
- `from lyse import Run`
- `Run(path).save_result(name, value)`
- `Run(path).save_result_array(name, value)`

For multi-shot lyse scripts, the subprocess provides:

- `lyse.data()`, returning the current LabPilot H5 table as a pandas DataFrame.
- `lyse.save_result(name, value)`
- `lyse.save_result_array(name, value)`

Single-shot script results are read back from the script return capture and the compatible `/results/<script_name>/...` H5 group. Multi-shot script results are captured into LabPilot analysis records. First-release fitting and report outputs are not written back into the original H5 files.

## Registry example

```yaml
single_modules:
  atom_number:
    path: "E:/lab/analysis/single/atom_number.py"
    mode: lyse_script
    enabled_by_default: true
    order: 10
    params: {}
    outputs:
      - N_total
      - temperature_uK

multi_modules:
  rabi_scan:
    path: "E:/lab/analysis/multi/rabi_scan.py"
    mode: lyse_script
    enabled_by_default: false
    order: 20
    params: {}
    outputs:
      - contrast
      - pi_time_us
```

## UI tools

The Lyse page includes:

- Add H5 files.
- Load H5 folder.
- Remove selected rows.
- Clear table.
- Reload selected rows.
- Column chooser with show/hide/save view.
- Send selected columns to Plot.
- Send selected columns to Fit.
- Add/remove `.py` routines.
- Add all `.py` files from a folder.
- Enable/disable selected routine.
- Move routine order up/down.
- Open routine file or containing folder.
- Run selected single on selected shot.
- Run checked singles on selected shot or table.
- Run selected/checked multi on table.
- Generate multi report.

## Data and safety rules

- Original H5 files are treated as experimental records. LabPilot only writes the compatible `results` group when running a single-shot lyse script that explicitly calls `save_result`.
- Plotting, fitting, optimizer history, and reports are stored in `labpilot_outputs/` and LabPilot SQLite/JSONL records.
- AI may choose only registered lyse modules and result fields.
- If an analysis routine raises an exception, the main UI remains open, the Error Center records the traceback, and hardware automation pauses at the next safe boundary.
