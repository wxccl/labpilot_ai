# Directory

Directory is the central path workbench for LabPilot AI.

It records the meaning and current value of paths used by runmanager, BLACS, lyse, Knowledge, Co-Sequence, and Experiment Log.

## Important Paths

- `sequence_dir`: folder containing labscript sequence files.
- `active_sequence_file`: the selected sequence file Co-Sequence may edit.
- `connection_table`: labscript connection table file.
- `active_connection_table`: the selected connection table Co-Sequence may edit.
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
- `Index to Knowledge`: rebuilds or refreshes the Knowledge index.
- `Open selected folder`: opens the folder that contains the selected path.

The page is intentionally explicit: laboratory operators should be able to see which file each subsystem is using before AI-assisted changes or experiment logging.
