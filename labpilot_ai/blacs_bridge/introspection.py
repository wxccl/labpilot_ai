from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class ChannelCandidate:
    name: str
    kind: str
    device: str
    channel: str
    type: str
    current_value: Any
    object_path: str
    class_name: str
    object_ref: Any

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "kind": self.kind,
            "device": self.device,
            "channel": self.channel,
            "type": self.type,
            "current_value": self.current_value,
            "object_path": self.object_path,
            "class_name": self.class_name,
            "risk": "unknown",
            "bridge_type": "real_blacs_candidate",
        }


def _safe_call(obj: Any, method_name: str, default=None):
    try:
        meth = getattr(obj, method_name, None)
        if callable(meth):
            return meth()
    except Exception:
        return default
    return default


def _simple_value(obj: Any):
    for meth in ("value", "isChecked", "currentText", "text"):
        value = _safe_call(obj, meth, default=None)
        if value is not None:
            try:
                if hasattr(value, "item"):
                    value = value.item()
            except Exception:
                pass
            return value
    return None


def _infer_type(obj: Any, value: Any) -> str:
    cls = type(obj).__name__.lower()
    if isinstance(value, bool) or "checkbox" in cls or "button" in cls:
        return "bool"
    if isinstance(value, int) and not isinstance(value, bool):
        return "int"
    if isinstance(value, float):
        return "float"
    return "str"


def _is_candidate_widget(obj: Any) -> bool:
    setters = ("setValue", "setChecked", "setText", "setCurrentText")
    readers = ("value", "isChecked", "text", "currentText")
    return any(callable(getattr(obj, s, None)) for s in setters) and any(callable(getattr(obj, r, None)) for r in readers)


def _object_name(obj: Any, fallback: str) -> str:
    name = _safe_call(obj, "objectName", default="")
    if name:
        return str(name)
    return fallback


def discover_blacs_manual_candidates(blacs: Any, max_depth: int = 5, max_items: int = 5000) -> list[ChannelCandidate]:
    """Best-effort discovery of Qt/manual-like controls inside BLACS.

    This is deliberately conservative and read-only. It does not assume a fixed BLACS
    internal API, because labscript-suite versions and device tabs may differ.
    """
    out: list[ChannelCandidate] = []
    seen: set[int] = set()

    def visit(obj: Any, path: str, depth: int):
        if obj is None or depth > max_depth or len(seen) > max_items:
            return
        ident = id(obj)
        if ident in seen:
            return
        seen.add(ident)

        if _is_candidate_widget(obj):
            value = _simple_value(obj)
            name = _object_name(obj, path.split(".")[-1])
            cls_name = type(obj).__name__
            out.append(
                ChannelCandidate(
                    name=name or path,
                    kind="manual_widget_candidate",
                    device="unknown",
                    channel=name or path,
                    type=_infer_type(obj, value),
                    current_value=value,
                    object_path=path,
                    class_name=cls_name,
                    object_ref=obj,
                )
            )

        if depth >= max_depth:
            return

        # Traverse dictionaries and sequences.
        if isinstance(obj, dict):
            for key, value in list(obj.items())[:200]:
                if isinstance(key, str) and key.startswith("__"):
                    continue
                visit(value, f"{path}.{key}", depth + 1)
            return

        if isinstance(obj, (list, tuple, set)):
            for i, value in enumerate(list(obj)[:200]):
                visit(value, f"{path}[{i}]", depth + 1)
            return

        # Traverse selected __dict__ attributes. Avoid calling arbitrary properties.
        dct = getattr(obj, "__dict__", None)
        if isinstance(dct, dict):
            for key, value in list(dct.items())[:300]:
                if key.startswith("__"):
                    continue
                if key.startswith("_") and key not in {"_notebook", "_tab", "_tabs"}:
                    continue
                lower = key.lower()
                if any(marker in lower for marker in ("tab", "manual", "widget", "control", "output", "channel", "device", "notebook")):
                    visit(value, f"{path}.{key}", depth + 1)

    visit(blacs, "BLACS", 0)

    # Deduplicate by object id/name.
    unique: list[ChannelCandidate] = []
    names: set[str] = set()
    for item in out:
        key = f"{item.name}|{item.object_path}"
        if key in names:
            continue
        names.add(key)
        unique.append(item)
    return unique


def candidates_to_json(candidates: list[ChannelCandidate]) -> list[dict[str, Any]]:
    return [item.to_dict() for item in candidates]


def values_from_candidates(candidates: list[ChannelCandidate]) -> dict[str, Any]:
    values = {}
    for item in candidates:
        values[item.name] = _simple_value(item.object_ref)
    return values


def set_candidate_value(candidate: ChannelCandidate, value: Any) -> dict[str, Any]:
    obj = candidate.object_ref
    typ = candidate.type
    if typ == "bool":
        if hasattr(obj, "setChecked"):
            obj.setChecked(bool(value))
            return {"ok": True, "name": candidate.name, "value": bool(value), "method": "setChecked"}
    if typ in {"float", "int"} and hasattr(obj, "setValue"):
        obj.setValue(float(value) if typ == "float" else int(value))
        return {"ok": True, "name": candidate.name, "value": value, "method": "setValue"}
    if hasattr(obj, "setText"):
        obj.setText(str(value))
        return {"ok": True, "name": candidate.name, "value": str(value), "method": "setText"}
    if hasattr(obj, "setCurrentText"):
        obj.setCurrentText(str(value))
        return {"ok": True, "name": candidate.name, "value": str(value), "method": "setCurrentText"}
    return {"ok": False, "error": f"No supported setter for {candidate.name} ({candidate.class_name})"}
