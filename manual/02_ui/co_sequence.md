# Co-Sequence

Co-Sequence is a restricted AI code editing workbench for labscript experiments.

It may only edit two files:

- the active sequence `.py`
- the active connection table `.py`

The page uses Knowledge snippets, the selected files, and the configured LLM API to propose a strict JSON patch plan. LabPilot then validates the patch locally before any file is written.

## Workflow

1. Open `Directory` and confirm `active_sequence_file` and `active_connection_table`.
2. Open `Co-Sequence`.
3. Type the requested code change in natural language.
4. Click `Generate patch`.
5. Click `Validate patch`.
6. Review the diff, warnings, and consistency checks.
7. Click `Approve & apply` only after review.

## Safety Rules

- No file outside the active sequence and active connection table can be modified.
- New files, deleted files, binary patches, and non-unified diffs are rejected.
- Python syntax is checked with `ast.parse`.
- Sequence device references are compared with connection table declarations and surfaced as warnings.
- Every applied change creates a `.bak` backup and a log entry.
- Co-Sequence never runs hardware.

## Logs

Logs are saved under:

```text
labpilot_outputs/co_sequence_logs/YYYY-MM-DD/
```

Each day folder contains JSONL records, Markdown summaries, and patch files. Use color tags such as `yellow: timing` or `red: hardware risk` to highlight important changes.
