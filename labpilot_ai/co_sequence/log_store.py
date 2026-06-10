import json
from datetime import datetime
from pathlib import Path

from labpilot_ai.utils.json_utils import to_jsonable


class CodeChangeLogStore:
    def __init__(self, base_dir):
        self.base_dir = Path(base_dir or "labpilot_outputs/co_sequence_logs")

    def _day_dir(self, created_at=None):
        created_at = created_at or datetime.now()
        path = self.base_dir / created_at.strftime("%Y-%m-%d")
        path.mkdir(parents=True, exist_ok=True)
        return path

    def append(self, record):
        created_at = datetime.now()
        day_dir = self._day_dir(created_at)
        record = dict(record or {})
        record.setdefault("created_at", created_at.isoformat(timespec="seconds"))
        record.setdefault("kind", "co_sequence_change")
        record.setdefault("color_tags", [])
        jsonl_path = day_dir / "code_changes.jsonl"
        with jsonl_path.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(to_jsonable(record), ensure_ascii=False) + "\n")
        index = len(jsonl_path.read_text(encoding="utf-8").splitlines())
        summary_path = day_dir / f"{index:04d}_summary.md"
        summary_path.write_text(self._summary_markdown(record), encoding="utf-8")
        for item_index, item in enumerate(record.get("applied", []) or record.get("files", []) or [], start=1):
            diff_text = item.get("unified_diff", "")
            if diff_text:
                patch_path = day_dir / f"{index:04d}_{item_index}_{Path(item.get('path', 'file')).name}.patch"
                patch_path.write_text(diff_text, encoding="utf-8")
        return {
            "jsonl_path": str(jsonl_path),
            "summary_path": str(summary_path),
            "record": record,
        }

    def add_manual_note(self, note, color_tags=None, files=None):
        return self.append(
            {
                "kind": "manual_code_note",
                "summary": str(note or "").strip(),
                "color_tags": list(color_tags or []),
                "files": list(files or []),
                "status": "note",
            }
        )

    def records_for_date(self, date_text):
        path = self.base_dir / str(date_text) / "code_changes.jsonl"
        if not path.exists():
            return []
        rows = []
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                rows.append(json.loads(line))
        return rows

    def _summary_markdown(self, record):
        lines = [
            f"# {record.get('summary') or record.get('kind', 'Code change')}",
            "",
            f"- Time: {record.get('created_at', '')}",
            f"- Status: {record.get('status', '')}",
            f"- Risk: {record.get('risk_level', '')}",
        ]
        tags = record.get("color_tags") or []
        if tags:
            lines.append("- Color tags: " + ", ".join(str(tag) for tag in tags))
        if record.get("warnings"):
            lines.append("")
            lines.append("## Warnings")
            for warning in record.get("warnings", []):
                lines.append(f"- {warning}")
        files = record.get("applied") or record.get("files") or []
        if files:
            lines.append("")
            lines.append("## Files")
            for item in files:
                line = f"- {item.get('path', '')}"
                if item.get("backup_path"):
                    line += f" (backup: {item.get('backup_path')})"
                lines.append(line)
        if record.get("operator_note"):
            lines.extend(["", "## Operator note", str(record.get("operator_note"))])
        return "\n".join(lines) + "\n"
