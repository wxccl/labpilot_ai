# Directory

Directory is the central path workbench for LabPilot AI.

It records the meaning and current value of paths used by runmanager, BLACS, lyse, Knowledge, Co-Sequence, and Experiment Log.

## Important Paths

- `sequence_dir`: folder containing labscript sequence files.
- `active_sequence_file`: the selected labscript sequence `.py` file. This can be applied to a running runmanager with `runmanager.remote.set_labscript_file()`.
- `connection_table`: labscript connection table `.py` file.
- `active_connection_table`: the selected connection table `.py` file Co-Sequence may edit.
- `runmanager_globals_path`: runmanager globals HDF5 file, usually `.h5` or `.hdf5`. This is not a sequence Python file.
- `blacs_connection_context_path`: optional BLACS connection table context, usually `connection_table.h5` from labconfig or the corresponding `connection_table.py`.
- `h5_output_dir`: folder containing H5 shot files.
- `single_modules_dir` and `multi_modules_dir`: lyse analysis modules.
- `labscript_source_dir`: optional local labscript source reference.
- `manual_dir` and `paper_dir`: local documents indexed into Knowledge.
- `knowledge_db_path`: SQLite FTS Knowledge database.
- `co_sequence_log_dir`, `experiment_log_dir`, `command_log_dir`: release logging folders.

## Buttons

- `Save paths`: writes local `configs/project_settings.yaml`.
- `Validate paths`: checks whether configured files and folders exist.
- `Detect active files`: best-effort helper; manual paths remain authoritative.
- `Detect from labscript apps`: reads runmanager remote state, runmanager autoload config, and labscript LabConfig. It fills active sequence, globals H5, connection table, and H5 output paths when available.
- `Apply to running apps`: applies supported live paths back to runmanager. The first release applies `active_sequence_file` and `h5_output_dir`. `runmanager_globals_path` is displayed as the active globals HDF5 reference, but live globals H5 switching is not exposed by `runmanager.remote`; LabPilot changes global values through `set_globals()`.
- `Index to Knowledge`: rebuilds or refreshes the Knowledge index.
- `Open selected folder`: opens the folder that contains the selected path.

The page is intentionally explicit: laboratory operators should be able to see which file each subsystem is using before AI-assisted changes or experiment logging.

## File Type Rules

- Sequence files: `.py`
- Connection table source files: `.py`
- Runmanager globals files: `.h5` or `.hdf5`
- H5 output path: folder, not a file
- Knowledge database: `.sqlite` or `.db`
