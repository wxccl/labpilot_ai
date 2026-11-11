"""Read and update runmanager globals HDF5 files."""

from __future__ import annotations

import ast
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping

import numpy as np


@dataclass
class GlobalsH5Snapshot:
    path: str
    values: dict[str, Any] = field(default_factory=dict)
    units: dict[str, str] = field(default_factory=dict)
    notes: dict[str, str] = field(default_factory=dict)
    expansion: dict[str, str] = field(default_factory=dict)
    registry_rules: dict[str, dict[str, Any]] = field(default_factory=dict)
    report: dict[str, Any] = field(default_factory=dict)


@dataclass
class GlobalsH5WriteReport:
    path: str
    group: str
    written: dict[str, Any] = field(default_factory=dict)
    missing: dict[str, Any] = field(default_factory=dict)
    expressions: dict[str, str] = field(default_factory=dict)


def read_runmanager_globals_h5(path: str | Path) -> GlobalsH5Snapshot:
    """Read a runmanager globals H5 file.

    Supported layout:
        /globals/<group_name>.attrs[name] = value
        /globals/<group_name>/units.attrs[name] = unit
        /globals/<group_name>/notes.attrs[name] = description
        /globals/<group_name>/expansion.attrs[name] = scan expansion

    The file is opened read-only. LabPilot applies value changes through
    runmanager.remote.set_globals(), not by writing this H5 file.
    """

    h5_path = Path(path).expanduser()
    if not h5_path.exists():
        raise FileNotFoundError(f"runmanager globals H5 does not exist: {h5_path}")
    if h5_path.suffix.lower() not in {".h5", ".hdf5"}:
        raise ValueError(f"runmanager globals path must be .h5 or .hdf5: {h5_path}")

    from labpilot_ai.bootstrap_labscript import install_h5_lock

    install_h5_lock(verbose=False)
    import h5py

    values: dict[str, Any] = {}
    units: dict[str, str] = {}
    notes: dict[str, str] = {}
    expansion: dict[str, str] = {}
    groups: list[str] = []
    warnings: list[str] = []

    with h5py.File(h5_path, "r") as handle:
        if "globals" not in handle:
            raise ValueError(f"runmanager globals H5 is missing /globals group: {h5_path}")
        globals_group = handle["globals"]
        for group_name, group in globals_group.items():
            if not isinstance(group, h5py.Group):
                continue
            groups.append(str(group_name))
            for name, raw in group.attrs.items():
                values[str(name)] = _coerce_attr_value(raw)
            for sub_name, target in [("units", units), ("notes", notes), ("expansion", expansion)]:
                if sub_name not in group:
                    continue
                sub = group[sub_name]
                if not isinstance(sub, h5py.Group):
                    warnings.append(f"{group_name}/{sub_name} is not a group")
                    continue
                for name, raw in sub.attrs.items():
                    target[str(name)] = str(_coerce_attr_value(raw))

    snapshot = GlobalsH5Snapshot(
        path=str(h5_path),
        values=values,
        units=units,
        notes=notes,
        expansion=expansion,
        report={
            "path": str(h5_path),
            "groups": groups,
            "count": len(values),
            "warnings": warnings,
        },
    )
    snapshot.registry_rules = _build_registry_rules(snapshot)
    return snapshot


def registry_from_globals_h5(
    snapshot: GlobalsH5Snapshot,
    existing_registry: Mapping[str, Mapping[str, Any]] | None = None,
) -> dict[str, dict[str, Any]]:
    """Merge H5-derived rules into an existing registry without overwriting edits."""

    merged: dict[str, dict[str, Any]] = {
        str(name): dict(rule or {}) for name, rule in (existing_registry or {}).items()
    }
    for name, rule in snapshot.registry_rules.items():
        if name not in merged:
            merged[name] = dict(rule)
            continue
        current = dict(merged[name])
        for key, value in rule.items():
            if _missing(current.get(key)):
                current[key] = value
        merged[name] = current
    return merged


def write_runmanager_globals_h5(
    path: str | Path,
    values: Mapping[str, Any],
    *,
    group_name: str = "",
) -> GlobalsH5WriteReport:
    """Write existing globals in a runmanager globals H5 file.

    This is a direct fallback for cases where runmanager.remote has no active
    group. Unknown globals are reported as missing and are not created.
    """

    h5_path = Path(path).expanduser()
    if not h5_path.exists():
        raise FileNotFoundError(f"runmanager globals H5 does not exist: {h5_path}")
    if h5_path.suffix.lower() not in {".h5", ".hdf5"}:
        raise ValueError(f"runmanager globals path must be .h5 or .hdf5: {h5_path}")
    if not values:
        return GlobalsH5WriteReport(path=str(h5_path), group=str(group_name or ""))

    from labpilot_ai.bootstrap_labscript import install_h5_lock

    install_h5_lock(verbose=False)
    import h5py

    report = GlobalsH5WriteReport(path=str(h5_path), group=str(group_name or ""))
    with h5py.File(h5_path, "a") as handle:
        if "globals" not in handle:
            raise ValueError(f"runmanager globals H5 is missing /globals group: {h5_path}")
        groups = handle["globals"]
        for name, value in values.items():
            target_group_name = _find_group_for_global(groups, str(name), group_name=group_name)
            if not target_group_name:
                report.missing[str(name)] = value
                continue
            group = groups[target_group_name]
            previous = group.attrs.get(str(name), "")
            expr = _format_runmanager_value(value)
            comment = _trailing_comment(str(previous))
            if comment and "#" not in expr:
                expr += comment
            group.attrs[str(name)] = expr
            report.group = target_group_name
            report.written[str(name)] = value
            report.expressions[str(name)] = expr
    return report


def _find_group_for_global(groups, name: str, *, group_name: str = "") -> str:
    if group_name:
        if group_name in groups and name in groups[group_name].attrs:
            return str(group_name)
        return ""
    found: list[str] = []
    for candidate, group in groups.items():
        if name in group.attrs:
            found.append(str(candidate))
    return found[0] if len(found) == 1 else ""


def _format_runmanager_value(value: Any) -> str:
    if isinstance(value, np.ndarray):
        return f"np.array({value.tolist()!r})"
    if isinstance(value, (list, tuple)):
        return repr(list(value))
    if isinstance(value, np.generic):
        return repr(value.item())
    return repr(value)


def _trailing_comment(expr: str) -> str:
    in_single = False
    in_double = False
    escaped = False
    for index, char in enumerate(expr):
        if escaped:
            escaped = False
            continue
        if char == "\\":
            escaped = True
            continue
        if char == "'" and not in_double:
            in_single = not in_single
            continue
        if char == '"' and not in_single:
            in_double = not in_double
            continue
        if char == "#" and not in_single and not in_double:
            return expr[index:]
    return ""


def _build_registry_rules(snapshot: GlobalsH5Snapshot) -> dict[str, dict[str, Any]]:
    rules: dict[str, dict[str, Any]] = {}
    for name, value in sorted(snapshot.values.items()):
        typ = _infer_type(value)
        risk = _infer_risk(name)
        rule: dict[str, Any] = {
            "type": typ,
            "unit": snapshot.units.get(name, ""),
            "default": value,
            "risk": risk,
            "require_confirm": risk == "high",
            "allow_array": typ == "float_array",
            "ai_control": risk != "high",
            "description": snapshot.notes.get(name) or f"Imported from runmanager globals H5: {Path(snapshot.path).name}",
            "source": snapshot.path,
            "confidence": "high",
        }
        if typ == "float_array" and isinstance(value, (list, tuple)):
            rule["max_points"] = max(1, len(value))
        if snapshot.expansion.get(name):
            rule["expansion"] = snapshot.expansion[name]
        rules[name] = rule
    return rules


def _coerce_attr_value(value: Any) -> Any:
    if isinstance(value, bytes):
        value = value.decode("utf-8", errors="replace")
    if hasattr(value, "item") and not isinstance(value, (str, bytes)):
        try:
            value = value.item()
        except Exception:
            pass
    if hasattr(value, "tolist") and not isinstance(value, (str, bytes)):
        try:
            value = value.tolist()
        except Exception:
            pass
    if isinstance(value, list):
        return [_coerce_attr_value(item) for item in value]
    if isinstance(value, tuple):
        return [_coerce_attr_value(item) for item in value]
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return ""
        lower = text.lower()
        if lower in {"true", "false"}:
            return lower == "true"
        try:
            return ast.literal_eval(text)
        except Exception:
            return text
    return value


def _infer_type(value: Any) -> str:
    if isinstance(value, bool):
        return "bool"
    if isinstance(value, int) and not isinstance(value, bool):
        return "int"
    if isinstance(value, float):
        return "float"
    if isinstance(value, (list, tuple)):
        if all(isinstance(item, (int, float)) and not isinstance(item, bool) for item in value):
            return "float_array"
    return "str"


def _infer_risk(name: str) -> str:
    lower = str(name).lower()
    high_hints = (
        "mw",
        "microwave",
        "rf",
        "power",
        "current",
        "coil",
        "bias",
        "gradient",
        "shutter",
        "aom",
        "dds",
        "laser",
        "heat",
        "evap",
        "trap",
        "blast",
        "blow",
        "pump",
    )
    if any(hint in lower for hint in high_hints):
        return "high"
    if any(hint in lower for hint in ("duration", "time", "delay", "tof")):
        return "medium"
    return "low"


def _missing(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, str):
        return not value.strip()
    if isinstance(value, (list, tuple, dict, set)):
        return len(value) == 0
    return False
