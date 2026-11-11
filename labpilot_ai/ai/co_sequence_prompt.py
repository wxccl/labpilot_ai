import json
from pathlib import Path


def _read_limited(path, max_chars):
    path = Path(path)
    text = path.read_text(encoding="utf-8", errors="replace")
    truncated = len(text) > max_chars
    if truncated:
        text = text[:max_chars] + "\n\n# [LabPilot truncated this file for prompt budget]\n"
    return text, truncated


def build_co_sequence_prompt(
    instruction,
    sequence_path,
    connection_table_path,
    *,
    project_context="",
    max_file_chars=60000,
):
    sequence_text, sequence_truncated = _read_limited(sequence_path, max_file_chars)
    connection_text, connection_truncated = _read_limited(connection_table_path, max_file_chars)
    return f"""
You are LabPilot Co-Sequence, a code editing assistant for labscript experiments.
You may propose changes ONLY to the selected sequence file and selected connection table file.
Do not propose changes to any other file. Do not run hardware. Do not include Markdown fences.

User instruction:
{instruction}

Project knowledge snippets:
{project_context or "No local knowledge snippets were retrieved."}

Selected editable files:
1. sequence_path={sequence_path}
truncated={sequence_truncated}
```python
{sequence_text}
```

2. connection_table_path={connection_table_path}
truncated={connection_truncated}
```python
{connection_text}
```

Return strict JSON with this shape:
{{
  "summary": "short summary",
  "risk_level": "low|medium|high",
  "files": [
    {{"path": "...", "unified_diff": "unified diff for that exact file"}}
  ],
  "consistency_checks": ["how sequence and connection table stay consistent"],
  "color_tags": ["yellow: reason", "red: reason"],
  "warnings": ["operator-facing warning"]
}}

Rules:
- Every file path must be exactly one of the two selected paths.
- Use unified diffs only. No full file replacement.
- Include exact unchanged context lines from the provided file; do not skip lines between the context before and after your insertion.
- For timing edits after an `if` block's cleanup actions, keep indentation consistent with the intended block and include nearby lines such as the final cleanup call and `stop(...)`.
- Keep sequence and connection table device/channel/global names consistent.
- Prefer small, reviewable patches.
- If the request is unsafe or underspecified, return an empty files list and put the issue in warnings.
""".strip()


def mock_co_sequence_plan(instruction, sequence_path, connection_table_path):
    return {
        "summary": "Mock Co-Sequence did not modify code. Enable an API key to generate real diffs.",
        "risk_level": "low",
        "files": [],
        "consistency_checks": [
            "Mock mode keeps sequence and connection table unchanged.",
            f"Sequence target: {Path(sequence_path).name if sequence_path else ''}",
            f"Connection table target: {Path(connection_table_path).name if connection_table_path else ''}",
        ],
        "color_tags": ["gray: mock"],
        "warnings": ["No patch was generated in Mock LLM mode."],
        "instruction": instruction,
    }


def compact_plan_text(plan):
    return json.dumps(plan or {}, ensure_ascii=False, indent=2)
