from pathlib import Path
from datetime import datetime
import json
from labpilot_ai.utils.json_utils import to_jsonable


class AuditLog:
    def __init__(self, path="labpilot_audit.log"):
        self.path = Path(path)

    def write(self, event: str, data=None):
        row = {"time": datetime.now().isoformat(timespec="seconds"), "event": event, "data": to_jsonable(data or {})}
        with open(self.path, "a", encoding="utf-8") as f:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
