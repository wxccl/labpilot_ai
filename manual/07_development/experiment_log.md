# Experiment Log

Experiment Log generates daily lab notes from LabPilot AI records.

It reads:

- natural-language command records
- Co-Sequence code-change logs
- analysis and optimizer records
- Error Center records
- active sequence and connection table paths
- optional Knowledge snippets
- operator notes typed into the page

## Output Formats

The page supports:

- Markdown
- LaTeX
- DokuWiki

Length modes:

- `N paragraphs`
- `One A4 page`
- `Full report`

Generated logs are saved under:

```text
labpilot_outputs/experiment_logs/YYYY-MM-DD/
```

## Command Records

Command records are appended when a natural-language command is parsed, dry-run previewed, executed, cancelled, or fails. They are stored in SQLite and mirrored to:

```text
labpilot_outputs/command_logs/YYYY-MM-DD/commands.jsonl
```

This makes the daily report reproducible without relying on the visible UI console.
