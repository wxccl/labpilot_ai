"""AI-assisted sequence variable discovery for LabPilot runmanager globals.

This module is intentionally conservative and dependency-light. It combines
static AST parsing with name/unit heuristics so the GUI can populate the
Runmanager global registry from labscript sequence code without executing the
sequence file.
"""

from __future__ import annotations

import ast
import os
import builtins
import keyword
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, MutableMapping, Sequence, Tuple


KNOWN_RUNTIME_NAMES = {
    # Python/runtime helpers
    "True", "False", "None", "__name__", "__file__",
    # Common scientific aliases
    "np", "numpy", "pd", "plt", "math", "time", "Path",
    # labscript symbols commonly imported or injected
    "start", "stop", "wait", "add_time_marker", "labscript_import", "compiler",
    "AnalogOut", "DigitalOut", "DDS", "StaticDDS", "ClockLine", "PseudoclockDevice",
    "Trigger", "Shutter", "Camera", "RemoteBLACS", "UnitConversion",
}

CONTROL_PREFIXES = (
    "do_", "lyse_do_", "enable_", "use_", "with_", "is_", "has_", "run_", "skip_",
)

HIGH_RISK_HINTS = (
    "mw", "microwave", "rf", "power", "current", "coil", "bias", "gradient", "shutter",
    "aom", "dds", "laser", "heat", "evap", "trap", "blast", "blow", "pump",
)

UNIT_SUFFIXES = [
    ("_ms", "ms"),
    ("_us", "us"),
    ("_ns", "ns"),
    ("_s", "s"),
    ("_hz", "Hz"),
    ("_khz", "kHz"),
    ("_mhz", "MHz"),
    ("_ghz", "GHz"),
    ("_v", "V"),
    ("_mv", "mV"),
    ("_w", "W"),
    ("_mw", "mW"),
    ("_uw", "uW"),
    ("_dbm", "dBm"),
    ("_g", "G"),
    ("_gauss", "G"),
    ("_cm", "cm"),
    ("_mm", "mm"),
    ("_um", "um"),
    ("_px", "px"),
    ("_deg", "deg"),
    ("_rad", "rad"),
]


@dataclass
class SequenceVariable:
    name: str
    value: Any = ""
    type: str = "str"
    unit: str = ""
    risk: str = "low"
    description: str = ""
    allow_array: bool = False
    require_confirm: bool = False
    ai_control: bool = True
    source_file: str = ""
    line: int = 0
    confidence: str = "medium"

    def to_registry_rule(self) -> Dict[str, Any]:
        rule: Dict[str, Any] = {
            "type": self.type,
            "unit": self.unit,
            "risk": self.risk,
            "description": self.description,
            "allow_array": self.allow_array,
            "require_confirm": self.require_confirm,
            "ai_control": self.ai_control,
        }
        if self.value != "":
            rule["default"] = self.value
        if self.source_file:
            rule["source"] = self.source_file
        if self.line:
            rule["line"] = self.line
        rule["confidence"] = self.confidence
        return rule


def discover_sequence_globals(
    project_settings: Mapping[str, Any] | None,
    existing_registry: Mapping[str, Any] | None = None,
    *,
    project_dir: str | Path | None = None,
    max_files: int = 200,
) -> Tuple[Dict[str, Dict[str, Any]], Dict[str, Any]]:
    """Return ``(merged_registry, report)`` after scanning sequence code.

    The function never executes user sequence code. It discovers candidate
    runmanager globals from two signals:
    1. explicit assignments to constants/arrays, and
    2. undefined names referenced by the sequence, which is how labscript files
       commonly receive runmanager globals.
    """

    existing: Dict[str, Dict[str, Any]] = {k: dict(v or {}) for k, v in (existing_registry or {}).items()}
    files = discover_sequence_files(project_settings or {}, project_dir=project_dir, max_files=max_files)
    discovered: Dict[str, SequenceVariable] = {}
    parse_errors: List[str] = []

    for path in files:
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            text = path.read_text(encoding="gbk", errors="replace")
        except Exception as exc:
            parse_errors.append(f"{path}: read failed: {exc}")
            continue
        try:
            tree = ast.parse(text, filename=str(path))
        except SyntaxError as exc:
            parse_errors.append(f"{path}: syntax error line {exc.lineno}: {exc.msg}")
            continue
        except Exception as exc:
            parse_errors.append(f"{path}: parse failed: {exc}")
            continue
        for variable in extract_sequence_variables(tree, path):
            if variable.name in discovered:
                # Keep higher confidence explicit/default records over inferred-only records.
                old = discovered[variable.name]
                rank = {"high": 3, "medium": 2, "low": 1}
                if rank.get(variable.confidence, 0) <= rank.get(old.confidence, 0):
                    continue
            discovered[variable.name] = variable

    merged = dict(existing)
    added: List[str] = []
    updated: List[str] = []
    for name, variable in sorted(discovered.items()):
        new_rule = variable.to_registry_rule()
        if name not in merged:
            merged[name] = new_rule
            added.append(name)
            continue
        current = dict(merged.get(name) or {})
        before = dict(current)
        # Preserve operator-edited safety fields; fill missing metadata from AI parser.
        for key in ["type", "unit", "risk", "description", "allow_array", "require_confirm", "ai_control"]:
            if current.get(key, "") in {"", None}:
                current[key] = new_rule.get(key)
        for key in ["source", "line", "confidence"]:
            current[key] = new_rule.get(key, current.get(key))
        if "default" not in current and "default" in new_rule:
            current["default"] = new_rule["default"]
        merged[name] = current
        if current != before:
            updated.append(name)

    report = {
        "files": [str(p) for p in files],
        "discovered": len(discovered),
        "added": added,
        "updated": updated,
        "parse_errors": parse_errors,
    }
    return merged, report


def discover_sequence_files(
    project_settings: Mapping[str, Any],
    *,
    project_dir: str | Path | None = None,
    max_files: int = 200,
) -> List[Path]:
    base = Path(project_dir or Path.cwd()).resolve()
    candidates: List[Path] = []

    def add_path(value: Any) -> None:
        if value is None:
            return
        if isinstance(value, str):
            if not value.strip():
                return
            value = value.strip()
        elif not isinstance(value, (Path, os.PathLike)):
            # Project settings also contain nested sections such as
            # co_sequence/voice/experiment_log. They are not paths and must not
            # be tested for set membership, otherwise dict values can raise
            # "unhashable type: 'dict'".
            return
        path = Path(str(value)).expanduser()
        if not path.is_absolute():
            path = base / path
        if path.is_file() and path.suffix.lower() == ".py":
            candidates.append(path.resolve())
        elif path.is_dir():
            for child in sorted(path.rglob("*.py")):
                if len(candidates) >= max_files:
                    break
                if "__pycache__" in child.parts or child.name.startswith("."):
                    continue
                candidates.append(child.resolve())

    preferred_keys = [
        "active_sequence_file", "sequence_file", "sequence_path", "main_sequence_file",
        "sequence_folder", "sequence_dir", "sequence_code_dir", "sequence_modules_dir",
    ]
    for key in preferred_keys:
        add_path(project_settings.get(key))
    for key, value in sorted(project_settings.items()):
        if "sequence" in str(key).lower() and key not in preferred_keys:
            add_path(value)

    # De-duplicate while preserving order.
    out: List[Path] = []
    seen = set()
    for path in candidates:
        if path in seen:
            continue
        seen.add(path)
        out.append(path)
        if len(out) >= max_files:
            break
    return out


def extract_sequence_variables(tree: ast.AST, source_path: str | Path) -> List[SequenceVariable]:
    assigned: Dict[str, ast.AST] = {}
    assignment_line: Dict[str, int] = {}
    imported: set[str] = set()
    used: Dict[str, int] = {}

    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            for alias in node.names:
                imported.add(alias.asname or alias.name.split(".")[0])
        elif isinstance(node, ast.Assign):
            for target in node.targets:
                for name in _target_names(target):
                    assigned.setdefault(name, node.value)
                    assignment_line.setdefault(name, getattr(node, "lineno", 0))
        elif isinstance(node, ast.AnnAssign):
            for name in _target_names(node.target):
                assigned.setdefault(name, node.value or ast.Constant(value=""))
                assignment_line.setdefault(name, getattr(node, "lineno", 0))
        elif isinstance(node, ast.AugAssign):
            for name in _target_names(node.target):
                assigned.setdefault(name, ast.Constant(value=""))
                assignment_line.setdefault(name, getattr(node, "lineno", 0))
        elif isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load):
            used.setdefault(node.id, getattr(node, "lineno", 0))

    builtin_names = set(dir(builtins))
    variables: Dict[str, SequenceVariable] = {}

    for name, value_node in assigned.items():
        if not _is_candidate_name(name) or name in imported:
            continue
        if _looks_like_internal_temporary(name):
            continue
        value, confidence = _literal_or_source(value_node)
        var_type = infer_type(name, value, value_node)
        unit = infer_unit(name)
        risk = infer_risk(name)
        variables[name] = SequenceVariable(
            name=name,
            value=value,
            type=var_type,
            unit=unit,
            risk=risk,
            description=f"AI parsed from sequence assignment: {Path(source_path).name}:{assignment_line.get(name, 0)}",
            allow_array=var_type == "float_array",
            require_confirm=risk == "high",
            ai_control=risk != "high",
            source_file=str(source_path),
            line=assignment_line.get(name, 0),
            confidence=confidence,
        )

    undefined = sorted(set(used) - set(assigned) - imported - builtin_names - KNOWN_RUNTIME_NAMES)
    for name in undefined:
        if not _is_candidate_name(name):
            continue
        var_type = infer_type(name, "", None)
        unit = infer_unit(name)
        risk = infer_risk(name)
        if name not in variables:
            variables[name] = SequenceVariable(
                name=name,
                value=False if var_type == "bool" else "",
                type=var_type,
                unit=unit,
                risk=risk,
                description=f"AI inferred runmanager global from sequence use: {Path(source_path).name}:{used.get(name, 0)}",
                allow_array=var_type == "float_array",
                require_confirm=risk == "high",
                ai_control=risk != "high",
                source_file=str(source_path),
                line=used.get(name, 0),
                confidence="medium" if name.startswith(CONTROL_PREFIXES) or unit else "low",
            )

    return list(variables.values())


def infer_type(name: str, value: Any, value_node: ast.AST | None = None) -> str:
    lower = name.lower()
    if lower.startswith(CONTROL_PREFIXES):
        return "bool"
    if isinstance(value, bool):
        return "bool"
    if isinstance(value, int) and not isinstance(value, bool):
        return "int"
    if isinstance(value, float):
        return "float"

    # Important: non-literal array constructors such as np.linspace(...) are
    # returned by _literal_or_source as a source string. Check the AST call
    # before treating any non-empty source string as a plain string.
    if isinstance(value_node, ast.Call):
        fn = _call_name(value_node.func).lower()
        if fn.endswith("linspace") or fn.endswith("arange") or fn.endswith("array"):
            return "float_array"

    if isinstance(value, (list, tuple)):
        if all(isinstance(v, (int, float)) and not isinstance(v, bool) for v in value):
            return "float_array"
        return "str"
    if isinstance(value, str) and value != "":
        return "str"
    numeric_hints = ["duration", "time", "delay", "freq", "frequency", "power", "voltage", "amp", "amplitude", "bias", "field", "current", "tof", "detuning", "phase", "ramp", "hold"]
    if infer_unit(name) or any(h in lower for h in numeric_hints):
        return "float"
    return "str"


def infer_unit(name: str) -> str:
    lower = name.lower()
    for suffix, unit in UNIT_SUFFIXES:
        if lower.endswith(suffix):
            return unit
    if "duration" in lower or "delay" in lower or "hold" in lower or "tof" in lower:
        return "ms"
    if "freq" in lower or "detuning" in lower:
        return "MHz"
    if "power" in lower:
        return "W"
    if "voltage" in lower:
        return "V"
    if "phase" in lower:
        return "deg"
    return ""


def infer_risk(name: str) -> str:
    lower = name.lower()
    if any(hint in lower for hint in HIGH_RISK_HINTS):
        return "high"
    if "duration" in lower or "time" in lower or "delay" in lower or "tof" in lower:
        return "medium"
    return "low"


def _target_names(target: ast.AST) -> Iterable[str]:
    if isinstance(target, ast.Name):
        yield target.id
    elif isinstance(target, (ast.Tuple, ast.List)):
        for item in target.elts:
            yield from _target_names(item)


def _literal_or_source(node: ast.AST | None) -> Tuple[Any, str]:
    if node is None:
        return "", "low"
    try:
        return ast.literal_eval(node), "high"
    except Exception:
        try:
            return ast.unparse(node), "medium"
        except Exception:
            return "", "low"


def _call_name(func: ast.AST) -> str:
    if isinstance(func, ast.Name):
        return func.id
    if isinstance(func, ast.Attribute):
        parent = _call_name(func.value)
        return f"{parent}.{func.attr}" if parent else func.attr
    return ""


def _is_candidate_name(name: str) -> bool:
    if not name or keyword.iskeyword(name):
        return False
    if name.startswith("_"):
        return False
    if not name.isidentifier():
        return False
    if name in KNOWN_RUNTIME_NAMES:
        return False
    return True


def _looks_like_internal_temporary(name: str) -> bool:
    lower = name.lower()
    if lower in {"i", "j", "k", "x", "y", "z", "row", "col", "idx", "index", "fig", "ax", "axes"}:
        return True
    if lower.startswith(("tmp", "temp_", "local_")):
        return True
    return False
