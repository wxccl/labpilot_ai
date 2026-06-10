import json
import numbers
from pathlib import Path
from datetime import datetime, timezone

from labpilot_ai.utils.json_utils import to_jsonable


SCALAR_TYPES = (str, bool, type(None), numbers.Number)


def default_result_store_path(base_dir=None):
    base = Path(base_dir) if base_dir else Path.cwd() / "labpilot_outputs" / "lyse_results"
    return base / "analysis_results.jsonl"


def merge_result_columns(dataframe, row_index: int, result: dict):
    """Merge single-shot analysis outputs into the loaded H5 table."""
    if not isinstance(result, dict):
        return dataframe
    for key, value in result.items():
        if isinstance(value, SCALAR_TYPES):
            dataframe.loc[dataframe.index[row_index], key] = value
        else:
            dataframe.loc[dataframe.index[row_index], key] = json.dumps(to_jsonable(value), ensure_ascii=False)
    return dataframe


class JsonlResultStore:
    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def append(self, kind: str, name: str, result: dict, metadata=None):
        row = {
            "created_at": datetime.now(timezone.utc).isoformat(),
            "kind": kind,
            "name": name,
            "result": to_jsonable(result),
            "metadata": to_jsonable(metadata or {}),
        }
        with self.path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
        return row

    def read_all(self):
        if not self.path.exists():
            return []
        rows = []
        with self.path.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    rows.append(json.loads(line))
        return rows
