import numpy as np


class SafetyError(ValueError):
    pass


TRUE_STRINGS = {"true", "1", "yes", "on", "open", "enable", "enabled", "打开", "开启", "是"}
FALSE_STRINGS = {"false", "0", "no", "off", "close", "disable", "disabled", "关闭", "否"}


def normalize_bool(value):
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        s = value.strip().lower()
        if s in TRUE_STRINGS:
            return True
        if s in FALSE_STRINGS:
            return False
    raise SafetyError(f"无法转换为 bool: {value!r}")


class SafetyValidator:
    def __init__(self, global_registry: dict, blacs_registry: dict | None = None):
        self.global_registry = global_registry or {}
        self.blacs_registry = blacs_registry or {}

    def validate_command(self, command: dict) -> dict:
        actions = command.get("actions", [])
        if not isinstance(actions, list):
            raise SafetyError("actions must be a list")

        safe = {
            "globals": {},
            "blacs_manual": {},
            "engage": False,
            "get_globals": False,
            "other_actions": [],
            "comment": command.get("comment", ""),
        }
        for action in actions:
            typ = action.get("type")
            if typ == "set_global":
                name = action.get("name")
                value = action.get("value")
                safe["globals"][name] = self.validate_value(name, value, self.global_registry)
            elif typ == "set_blacs_manual":
                name = action.get("name")
                value = action.get("value")
                safe["blacs_manual"][name] = self.validate_value(name, value, self.blacs_registry)
            elif typ == "engage":
                safe["engage"] = True
            elif typ == "get_globals":
                safe["get_globals"] = True
            else:
                # Keep placeholders for future pages, but do not execute them yet.
                safe["other_actions"].append(action)
        return safe

    def validate_value(self, name: str, value, registry: dict):
        if name not in registry:
            raise SafetyError(f"变量 {name!r} 不在白名单中")
        rule = registry[name]
        typ = rule.get("type")

        if typ == "float":
            if rule.get("allow_array", False) and self._is_array_like(value):
                return self._convert_float_array(name, value, rule)
            converted = float(value)
            self._check_range(name, converted, rule)
            return converted
        if typ == "float_array":
            return self._convert_float_array(name, value, rule)
        if typ == "int":
            converted = int(value)
            self._check_range(name, converted, rule)
            return converted
        if typ == "bool":
            return normalize_bool(value)
        if typ == "str":
            return str(value)
        raise SafetyError(f"未知参数类型: {typ!r} for {name}")

    def _is_array_like(self, value) -> bool:
        return isinstance(value, (list, tuple, np.ndarray, dict))

    def _convert_float_array(self, name: str, value, rule: dict):
        if isinstance(value, dict):
            if "linspace" in value:
                start, stop, num = value["linspace"]
                arr = np.linspace(float(start), float(stop), int(num))
            elif "arange" in value:
                start, stop, step = value["arange"]
                arr = np.arange(float(start), float(stop), float(step))
            else:
                raise SafetyError(f"{name}: array dict must contain linspace or arange")
        else:
            arr = np.asarray(value, dtype=float)
        if arr.ndim != 1:
            raise SafetyError(f"{name}: only 1D arrays are allowed")
        max_points = int(rule.get("max_points", 1000))
        if len(arr) > max_points:
            raise SafetyError(f"{name}: array length {len(arr)} exceeds max_points={max_points}")
        for x in arr:
            self._check_range(name, float(x), rule)
        return arr

    def _check_range(self, name: str, value: float, rule: dict):
        if "min" in rule and value < float(rule["min"]):
            raise SafetyError(f"{name}={value} below min={rule['min']}")
        if "max" in rule and value > float(rule["max"]):
            raise SafetyError(f"{name}={value} above max={rule['max']}")
