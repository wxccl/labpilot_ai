from pathlib import Path


GLOBAL_TYPES = {"float", "int", "bool", "str", "float_array"}
BLACS_TYPES = {"float", "int", "bool", "str"}
RISK_LEVELS = {"low", "medium", "high"}

GLOBAL_FIELDS = [
    "name",
    "type",
    "unit",
    "default",
    "min",
    "max",
    "allow_array",
    "max_points",
    "risk",
    "require_confirm",
    "aliases",
    "description",
]

BLACS_FIELDS = [
    "name",
    "kind",
    "backend",
    "device",
    "channel",
    "type",
    "unit",
    "min",
    "max",
    "risk",
    "require_confirm",
    "ai_control",
    "description",
    "aliases",
]

LYSE_FIELDS = [
    "group",
    "name",
    "path",
    "mode",
    "enabled_by_default",
    "order",
    "description",
    "params",
    "outputs",
]

PROJECT_PATH_FIELDS = [
    "sequence_dir",
    "active_sequence_file",
    "connection_table",
    "active_connection_table",
    "runmanager_globals_path",
    "blacs_connection_context_path",
    "h5_output_dir",
    "lyse_results_dir",
    "single_modules_dir",
    "multi_modules_dir",
    "labscript_source_dir",
    "manual_dir",
    "paper_dir",
    "knowledge_db_path",
    "co_sequence_log_dir",
    "experiment_log_dir",
    "command_log_dir",
    "knowledge_context_enabled",
    "shot_naming_rule",
]

TRUE_STRINGS = {
    "true",
    "1",
    "yes",
    "y",
    "on",
    "open",
    "enable",
    "enabled",
    "打开",
    "开启",
    "启用",
    "开",
    "是",
    "真",
}
FALSE_STRINGS = {
    "false",
    "0",
    "no",
    "n",
    "off",
    "close",
    "closed",
    "disable",
    "disabled",
    "关闭",
    "关",
    "禁用",
    "否",
    "假",
}


def parse_bool(value):
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    text = str(value).strip().lower()
    if text in TRUE_STRINGS:
        return True
    if text in FALSE_STRINGS:
        return False
    return False


def parse_list(value):
    if value is None:
        return []
    if isinstance(value, list):
        return [str(v).strip() for v in value if str(v).strip()]
    return [v.strip() for v in str(value).replace("\n", ",").split(",") if v.strip()]


def parse_scalar(value, typ=None):
    if value is None:
        return None
    if isinstance(value, str) and not value.strip():
        return None
    if typ == "bool":
        return parse_bool(value)
    if typ == "int":
        return int(value)
    if typ == "float":
        return float(value)
    return value


def _has_value(value):
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    return True


def _maybe_number(rule, key):
    if key in rule and _has_value(rule[key]):
        rule[key] = float(rule[key])


def normalize_global_entry(entry):
    name = str(entry.get("name", "")).strip()
    rule = {k: v for k, v in entry.items() if k != "name" and _has_value(v)}
    typ = str(rule.get("type", "float")).strip()
    rule["type"] = typ
    for key in ["min", "max"]:
        _maybe_number(rule, key)
    if "max_points" in rule and _has_value(rule["max_points"]):
        rule["max_points"] = int(rule["max_points"])
    if "allow_array" in rule:
        rule["allow_array"] = parse_bool(rule["allow_array"])
    if "require_confirm" in rule:
        rule["require_confirm"] = parse_bool(rule["require_confirm"])
    if "aliases" in rule:
        rule["aliases"] = parse_list(rule["aliases"])
    if "default" in rule:
        scalar_type = typ if typ in {"float", "int", "bool"} else None
        rule["default"] = parse_scalar(rule["default"], scalar_type)
    return name, rule


def normalize_blacs_entry(entry):
    name = str(entry.get("name", "")).strip()
    rule = {k: v for k, v in entry.items() if k != "name" and _has_value(v)}
    typ = str(rule.get("type", "float")).strip()
    rule["type"] = typ
    for key in ["min", "max"]:
        _maybe_number(rule, key)
    for key in ["require_confirm", "ai_control"]:
        if key in rule:
            rule[key] = parse_bool(rule[key])
    if "aliases" in rule:
        rule["aliases"] = parse_list(rule["aliases"])
    return name, rule


def normalize_lyse_entry(entry):
    group = str(entry.get("group", "single")).strip()
    name = str(entry.get("name", "")).strip()
    cfg = {k: v for k, v in entry.items() if k not in {"group", "name"} and _has_value(v)}
    if "enabled_by_default" in cfg:
        cfg["enabled_by_default"] = parse_bool(cfg["enabled_by_default"])
    if "order" in cfg:
        cfg["order"] = int(cfg["order"])
    if "outputs" in cfg:
        cfg["outputs"] = parse_list(cfg["outputs"])
    if "params" in cfg and isinstance(cfg["params"], str):
        import yaml

        cfg["params"] = yaml.safe_load(cfg["params"]) or {}
    return group, name, cfg


def build_global_registry(rows):
    out = {}
    for row in rows:
        name, rule = normalize_global_entry(row)
        if name:
            out[name] = rule
    return out


def build_blacs_registry(rows):
    out = {}
    for row in rows:
        name, rule = normalize_blacs_entry(row)
        if name:
            out[name] = rule
    return out


def validate_global_registry(registry):
    errors = []
    for name, rule in (registry or {}).items():
        if not str(name).strip():
            errors.append("global name is required")
        typ = rule.get("type")
        if typ not in GLOBAL_TYPES:
            errors.append(f"{name}: unknown type {typ!r}")
        try:
            if "min" in rule and "max" in rule and float(rule["min"]) > float(rule["max"]):
                errors.append(f"{name}: min is greater than max")
        except Exception:
            errors.append(f"{name}: min and max must be numeric")
        if "max_points" in rule:
            try:
                if int(rule["max_points"]) <= 0:
                    errors.append(f"{name}: max_points must be positive")
            except Exception:
                errors.append(f"{name}: max_points must be an integer")
        if "aliases" in rule and not isinstance(rule["aliases"], list):
            errors.append(f"{name}: aliases must be a list")
        if rule.get("risk", "low") not in RISK_LEVELS:
            errors.append(f"{name}: risk must be one of {sorted(RISK_LEVELS)}")
    return errors


def validate_blacs_registry(registry):
    errors = []
    for name, rule in (registry or {}).items():
        if not str(name).strip():
            errors.append("BLACS channel name is required")
        typ = rule.get("type")
        if typ not in BLACS_TYPES:
            errors.append(f"{name}: unknown type {typ!r}")
        try:
            if "min" in rule and "max" in rule and float(rule["min"]) > float(rule["max"]):
                errors.append(f"{name}: min is greater than max")
        except Exception:
            errors.append(f"{name}: min and max must be numeric")
        if not rule.get("device") or not rule.get("channel"):
            errors.append(f"{name}: device and channel are required")
        if rule.get("risk", "low") not in RISK_LEVELS:
            errors.append(f"{name}: risk must be one of {sorted(RISK_LEVELS)}")
    return errors


def validate_lyse_registry(registry, base_dir=None):
    errors = []
    base = Path(base_dir or Path.cwd())
    for group in ["single_modules", "multi_modules"]:
        for name, cfg in ((registry or {}).get(group, {}) or {}).items():
            if not str(name).strip():
                errors.append(f"{group}: module name is required")
            try:
                int(cfg.get("order", 1000))
            except Exception:
                errors.append(f"{group}.{name}: order must be an integer")
            path = cfg.get("path")
            if not path:
                errors.append(f"{group}.{name}: path is required")
                continue
            candidate = Path(path)
            if not candidate.is_absolute():
                candidate = base / candidate
            if not candidate.exists():
                errors.append(f"{group}.{name}: module path does not exist: {path}")
    return errors


def flatten_lyse_registry(registry):
    rows = []
    for group in ["single_modules", "multi_modules"]:
        label = "single" if group == "single_modules" else "multi"
        for name, cfg in ((registry or {}).get(group, {}) or {}).items():
            row = {"group": label, "name": name}
            row.update(cfg or {})
            row["outputs"] = ", ".join(row.get("outputs", []) or [])
            rows.append(row)
    return rows


def build_lyse_registry(rows):
    out = {"single_modules": {}, "multi_modules": {}}
    for row in rows:
        group, name, cfg = normalize_lyse_entry(row)
        if not name:
            continue
        key = "single_modules" if group == "single" else "multi_modules"
        out[key][name] = cfg
    return out
