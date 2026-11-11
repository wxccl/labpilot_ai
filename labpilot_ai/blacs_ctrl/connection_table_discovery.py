"""Static BLACS manual channel discovery from connection_table.py."""

from __future__ import annotations

import ast
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping


@dataclass
class DiscoveredBlacsChannel:
    name: str
    kind: str
    device: str = ""
    channel: str = ""
    type: str = "float"
    unit: str = ""
    min: Any = ""
    max: Any = ""
    current_value: Any = ""
    risk: str = "medium"
    aliases: list[str] = field(default_factory=list)
    source: str = ""
    line: int = 0

    def registry_rule(self) -> dict[str, Any]:
        rule: dict[str, Any] = {
            "kind": self.kind,
            "backend": "blacs_manual",
            "device": self.device,
            "channel": self.channel,
            "type": self.type,
            "unit": self.unit,
            "risk": self.risk,
            "require_confirm": self.risk == "high",
            "ai_control": self.risk != "high",
            "description": f"Parsed from connection table: {Path(self.source).name}:{self.line}",
            "aliases": sorted({alias for alias in self.aliases if alias}),
            "source": self.source,
        }
        if self.min != "":
            rule["min"] = self.min
        if self.max != "":
            rule["max"] = self.max
        if self.current_value != "":
            rule["default"] = self.current_value
        return rule


def discover_blacs_channels_from_connection_table(path: str | Path) -> tuple[dict[str, dict[str, Any]], dict[str, Any]]:
    source_path = Path(path).expanduser()
    if not source_path.exists():
        raise FileNotFoundError(f"connection table does not exist: {source_path}")
    text = source_path.read_text(encoding="utf-8")
    tree = ast.parse(text, filename=str(source_path))
    env = _collect_simple_assignments(tree)
    device_instances = _collect_device_instances(tree, env)
    channels: dict[str, DiscoveredBlacsChannel] = {}

    mock_channels = env.get("mock_channels")
    if isinstance(mock_channels, dict):
        for name, cfg in mock_channels.items():
            if not isinstance(cfg, dict):
                continue
            channel = DiscoveredBlacsChannel(
                name=str(name),
                kind=str(cfg.get("kind", "manual")),
                device=str(cfg.get("device", "")),
                channel=str(cfg.get("channel", name)),
                type=_type_from_kind_and_value(str(cfg.get("kind", "")), cfg.get("value", "")),
                unit=str(cfg.get("unit", "")),
                min=cfg.get("min", ""),
                max=cfg.get("max", ""),
                current_value=cfg.get("value", ""),
                risk=str(cfg.get("risk", _risk_from_name(str(name)))),
                aliases=_aliases(str(name), str(cfg.get("device", "")), str(cfg.get("channel", ""))),
                source=str(source_path),
                line=_assignment_line(tree, "mock_channels"),
            )
            channels[channel.name] = channel

    constructors = {
        "AnalogOut": ("AO", "float"),
        "DigitalOut": ("DO", "bool"),
        "StaticAnalogOut": ("StaticAO", "float"),
        "StaticDigitalOut": ("StaticDO", "bool"),
        "DDS": ("DDS", "str"),
        "StaticDDS": ("StaticDDS", "str"),
    }
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign) or not isinstance(node.value, ast.Call):
            continue
        ctor = _call_name(node.value.func)
        if ctor not in constructors:
            continue
        target_names = [target.id for target in node.targets if isinstance(target, ast.Name)]
        if not target_names:
            continue
        labscript_name = _eval_arg(node.value, 0, env, default=target_names[0])
        parent_var = _eval_raw_arg(node.value, 1)
        connection = _eval_arg(node.value, 2, env, default="")
        device = device_instances.get(str(parent_var), str(parent_var or ""))
        kind, typ = constructors[ctor]
        name = str(labscript_name or target_names[0])
        existing = channels.get(name)
        if existing is None:
            channels[name] = DiscoveredBlacsChannel(
                name=name,
                kind=kind,
                device=device,
                channel=str(connection),
                type=typ,
                unit="",
                risk=_risk_from_name(name),
                aliases=_aliases(name, device, str(connection)),
                source=str(source_path),
                line=getattr(node, "lineno", 0),
            )
        else:
            existing.kind = existing.kind or kind
            existing.device = existing.device or device
            existing.channel = existing.channel or str(connection)
            existing.type = existing.type or typ
            existing.aliases = sorted(set(existing.aliases) | set(_aliases(name, device, str(connection))))
            existing.line = existing.line or getattr(node, "lineno", 0)

    registry = {name: channel.registry_rule() for name, channel in sorted(channels.items())}
    report = {"path": str(source_path), "count": len(registry), "names": sorted(registry)}
    return registry, report


def merge_blacs_registry_from_connection_table(
    parsed_registry: Mapping[str, Mapping[str, Any]],
    existing_registry: Mapping[str, Mapping[str, Any]] | None = None,
) -> dict[str, dict[str, Any]]:
    merged = {str(name): dict(rule or {}) for name, rule in (existing_registry or {}).items()}
    by_device_channel: dict[tuple[str, str], str] = {}
    for existing_name, existing_rule in merged.items():
        device = str(existing_rule.get("device", "") or "").strip()
        channel = str(existing_rule.get("channel", "") or "").strip()
        if device and channel:
            by_device_channel[(device, channel)] = existing_name

    for name, rule in parsed_registry.items():
        parsed_name = str(name)
        parsed_rule = dict(rule or {})
        device = str(parsed_rule.get("device", "") or "").strip()
        channel = str(parsed_rule.get("channel", "") or "").strip()
        existing_name = by_device_channel.get((device, channel)) if device and channel else None
        if existing_name and existing_name != parsed_name and parsed_name not in merged:
            existing_rule = dict(merged.pop(existing_name))
            current = dict(parsed_rule)
            for key, value in existing_rule.items():
                if _missing(current.get(key)):
                    current[key] = value
                elif key == "aliases":
                    current[key] = sorted(set(current.get(key) or []) | set(value or []))
            aliases = set(current.get("aliases") or [])
            aliases.add(existing_name)
            if existing_rule.get("bridge_name"):
                aliases.add(str(existing_rule.get("bridge_name")))
            current["aliases"] = sorted(alias for alias in aliases if alias)
            current.setdefault("bridge_name", existing_rule.get("bridge_name", existing_name))
            merged[parsed_name] = current
            by_device_channel[(device, channel)] = parsed_name
            continue

        if parsed_name not in merged:
            merged[parsed_name] = parsed_rule
            if device and channel:
                by_device_channel[(device, channel)] = parsed_name
            continue

        current = dict(merged[parsed_name])
        for key, value in parsed_rule.items():
            if _missing(current.get(key)):
                current[key] = value
            elif key == "aliases":
                current[key] = sorted(set(current.get(key) or []) | set(value or []))
        merged[parsed_name] = current
        if device and channel:
            by_device_channel[(device, channel)] = parsed_name
    return merged


def _collect_simple_assignments(tree: ast.AST) -> dict[str, Any]:
    env: dict[str, Any] = {}
    for node in tree.body if isinstance(tree, ast.Module) else []:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    env[target.id] = _eval_node(node.value, env)
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            env[node.target.id] = _eval_node(node.value, env)
    return env


def _collect_device_instances(tree: ast.AST, env: Mapping[str, Any]) -> dict[str, str]:
    devices: dict[str, str] = {}
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign) or not isinstance(node.value, ast.Call):
            continue
        ctor = _call_name(node.value.func)
        if not ctor.endswith("Device") and ctor not in {"DummyPseudoclock", "ClockLine"}:
            continue
        name = _keyword_value(node.value, "name", env) or _eval_arg(node.value, 0, env, default="")
        for target in node.targets:
            if isinstance(target, ast.Name):
                devices[target.id] = str(name or target.id)
    return devices


def _eval_arg(call: ast.Call, index: int, env: Mapping[str, Any], default: Any = "") -> Any:
    if len(call.args) <= index:
        return default
    return _eval_node(call.args[index], env)


def _eval_raw_arg(call: ast.Call, index: int) -> str:
    if len(call.args) <= index:
        return ""
    arg = call.args[index]
    if isinstance(arg, ast.Name):
        return arg.id
    return ""


def _keyword_value(call: ast.Call, key: str, env: Mapping[str, Any]) -> Any:
    for keyword in call.keywords:
        if keyword.arg == key:
            return _eval_node(keyword.value, env)
    return ""


def _eval_node(node: ast.AST | None, env: Mapping[str, Any]) -> Any:
    if node is None:
        return ""
    try:
        return ast.literal_eval(node)
    except Exception:
        pass
    if isinstance(node, ast.Name):
        return env.get(node.id, node.id)
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.USub):
        value = _eval_node(node.operand, env)
        return -value if isinstance(value, (int, float)) else value
    if isinstance(node, ast.Call):
        name = _call_name(node.func)
        if name in {"_s", "_f", "_g"} and len(node.args) >= 2:
            return _eval_node(node.args[1], env)
        if name in {"float", "int", "str", "bool"} and node.args:
            value = _eval_node(node.args[0], env)
            try:
                return {"float": float, "int": int, "str": str, "bool": bool}[name](value)
            except Exception:
                return value
    if isinstance(node, ast.Dict):
        return {_eval_node(k, env): _eval_node(v, env) for k, v in zip(node.keys, node.values)}
    if isinstance(node, ast.List):
        return [_eval_node(item, env) for item in node.elts]
    if isinstance(node, ast.Tuple):
        return tuple(_eval_node(item, env) for item in node.elts)
    return ""


def _call_name(node: ast.AST) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    return ""


def _assignment_line(tree: ast.AST, name: str) -> int:
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            if any(isinstance(target, ast.Name) and target.id == name for target in node.targets):
                return getattr(node, "lineno", 0)
    return 0


def _type_from_kind_and_value(kind: str, value: Any) -> str:
    low = kind.lower()
    if "do" in low or "digital" in low or isinstance(value, bool):
        return "bool"
    if "dds" in low:
        return "str"
    return "float"


def _risk_from_name(name: str) -> str:
    low = name.lower()
    if any(token in low for token in ("mw", "rf", "interlock", "laser", "shutter")):
        return "high" if "mw" in low or "interlock" in low else "medium"
    return "low"


def _aliases(name: str, device: str, channel: str) -> list[str]:
    aliases = {name, name.replace("_", " "), channel}
    if device and channel:
        aliases.add(f"{device}.{channel}")
    return sorted(alias for alias in aliases if alias)


def _missing(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, str):
        return not value.strip()
    if isinstance(value, (list, tuple, dict, set)):
        return len(value) == 0
    return False
