# Knowledge Sources

LabPilot AI can build a local reference database from lab files. The database is used for AI parsing, protocol suggestions, and error advice. It is not used to execute arbitrary code.

## Sources

Configure these fields in Settings -> Project Paths:

- `sequence_dir`: labscript sequence folder.
- `connection_table`: labscript connection table file.
- `single_modules_dir`: lyse single-shot modules.
- `multi_modules_dir`: lyse multi-shot modules.
- `labscript_source_dir`: labscript source/reference folder.
- `manual_dir`: manuals and local documentation.
- `paper_dir`: papers, notes, or protocol references.
- `knowledge_db_path`: SQLite database path.
- `knowledge_context_enabled`: master switch for retrieved AI context.

Supported files:

- `.py`, `.md`, `.txt`, `.yaml`, `.yml`, `.json`, `.ini`, `.cfg`, `.labscript`
- `.pdf` with optional `pypdf`
- image files are indexed as path metadata only; no OCR is performed.

## Workflow

1. Fill or browse the source paths.
2. Open the Knowledge page.
3. Click `Scan sources`.
4. Click `Build/Rebuild index`.
5. Search terms such as `Rabi`, `Ramsey`, `TOF`, a device name, or an error string.
6. Preview snippets or send a snippet to Protocol Designer.

Remote AI only receives short retrieved snippets with file path and line numbers. Full source trees are not sent.
