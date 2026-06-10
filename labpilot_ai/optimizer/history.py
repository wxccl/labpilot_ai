import json
from pathlib import Path

from labpilot_ai.utils.json_utils import to_jsonable


def save_history(path, session_dict: dict):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(to_jsonable(session_dict), ensure_ascii=False, indent=2), encoding="utf-8")


def load_history(path) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def save_optimization_history(path, session):
    if hasattr(session, "as_dict"):
        payload = session.as_dict()
    else:
        payload = session
    save_history(path, payload)
    return Path(path)


def load_optimization_history(path) -> dict:
    return load_history(path)
