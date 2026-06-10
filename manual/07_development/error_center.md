# Error Center

Error Center is the reliability layer for LabPilot AI. Normal UI, worker, STT, LLM, runmanager, BLACS, lyse, optimizer, and knowledge errors should be recorded here instead of closing the main program.

Records are written to:

- `labpilot_outputs/labpilot_state.sqlite`
- `labpilot_outputs/errors/error_records.jsonl`

Default hardware policy:

- GUI stays open.
- Real runmanager/BLACS/optimizer failures are marked `hardware_pause`.
- Supervised optimization pauses or stops at the next safe boundary.
- The user must decide whether to Resume, Stop, switch to Mock/Dry run, or fix the underlying hardware connection.

The page provides:

- error table
- traceback preview
- copy traceback
- save report
- clear resolved
- switch to Mock/Dry run
