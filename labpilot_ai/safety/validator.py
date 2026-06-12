from pathlib import Path

import numpy as np


class SafetyError(ValueError):
    pass


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


def normalize_bool(value):
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        text = value.strip().lower()
        if text in TRUE_STRINGS:
            return True
        if text in FALSE_STRINGS:
            return False
    raise SafetyError(f"Cannot convert value to bool / 无法转换为布尔值: {value!r}")


def _optional_bool(value, default=False):
    if value is None:
        return default
    return normalize_bool(value)


class SafetyValidator:
    def __init__(self, global_registry: dict, blacs_registry: dict | None = None, lyse_registry: dict | None = None):
        self.global_registry = global_registry or {}
        self.blacs_registry = blacs_registry or {}
        self.lyse_registry = lyse_registry or {}

    def reload(self, global_registry: dict | None = None, blacs_registry: dict | None = None, lyse_registry: dict | None = None):
        if global_registry is not None:
            self.global_registry = global_registry or {}
        if blacs_registry is not None:
            self.blacs_registry = blacs_registry or {}
        if lyse_registry is not None:
            self.lyse_registry = lyse_registry or {}

    def validate_command(self, command: dict) -> dict:
        actions = command.get("actions", [])
        if not isinstance(actions, list):
            raise SafetyError("actions must be a list")

        safe = {
            "actions": [],
            "globals": {},
            "blacs_manual": {},
            "engage": False,
            "get_globals": False,
            "load_h5": [],
            "single_modules": [],
            "multi_modules": [],
            "plots": [],
            "fits": [],
            "optimization": None,
            "optimization_feedback": [],
            "protocol_requests": [],
            "report_requests": [],
            "confirmations": [],
            "other_actions": [],
            "comment": command.get("comment", ""),
        }
        for action in actions:
            if not isinstance(action, dict):
                raise SafetyError("each action must be an object")
            typ = action.get("type")
            if typ == "set_global":
                name = action.get("name")
                value = action.get("value")
                safe["globals"][name] = self.validate_value(name, value, self.global_registry)
                normalized = {"type": typ, "name": name, "value": safe["globals"][name]}
                safe["actions"].append(normalized)
                self._maybe_require_confirmation(name, self.global_registry, safe)
            elif typ == "set_blacs_manual":
                requested_name = action.get("name")
                name = self.resolve_registry_name(requested_name, self.blacs_registry)
                value = action.get("value")
                safe["blacs_manual"][name] = self.validate_value(name, value, self.blacs_registry)
                normalized = {"type": typ, "name": name, "value": safe["blacs_manual"][name]}
                if requested_name != name:
                    normalized["requested_name"] = requested_name
                safe["actions"].append(normalized)
                self._maybe_require_confirmation(name, self.blacs_registry, safe)
            elif typ == "engage":
                safe["engage"] = True
                safe["actions"].append({"type": "engage"})
            elif typ == "get_globals":
                safe["get_globals"] = True
                safe["actions"].append({"type": "get_globals"})
            elif typ in {"load_h5", "load_h5_folder"}:
                item = self.validate_load_h5(action)
                safe["load_h5"].append(item)
                safe["actions"].append(item)
            elif typ == "run_single_lyse":
                item = self.validate_lyse_module(action, "single_modules")
                safe["single_modules"].append(item)
                safe["actions"].append(item)
            elif typ == "run_multi_lyse":
                item = self.validate_lyse_module(action, "multi_modules")
                safe["multi_modules"].append(item)
                safe["actions"].append(item)
            elif typ == "plot":
                item = self.validate_plot(action)
                safe["plots"].append(item)
                safe["actions"].append(item)
            elif typ == "fit":
                item = self.validate_fit(action)
                safe["fits"].append(item)
                safe["actions"].append(item)
            elif typ == "start_optimization":
                item = self.validate_optimization(action)
                safe["optimization"] = item
                safe["actions"].append(item)
            elif typ == "stop_optimization":
                item = {"type": "stop_optimization"}
                safe["optimization"] = item
                safe["actions"].append(item)
            elif typ in {"tell_optimization_result", "evaluate_optimization_result"}:
                item = self.validate_optimization_feedback(action)
                safe["optimization_feedback"].append(item)
                safe["actions"].append(item)
            elif typ == "generate_protocol":
                item = {"type": typ, "prompt": str(action.get("prompt", "")).strip()}
                safe["protocol_requests"].append(item)
                safe["actions"].append(item)
            elif typ == "generate_report":
                item = {
                    "type": typ,
                    "title": str(action.get("title", "LabPilot report")).strip(),
                    "include_errors": _optional_bool(action.get("include_errors"), True),
                    "include_knowledge_context": _optional_bool(action.get("include_knowledge_context"), True),
                    "include_optimizer_history": _optional_bool(action.get("include_optimizer_history"), True),
                }
                safe["report_requests"].append(item)
                safe["actions"].append(item)
            else:
                safe["other_actions"].append(action)
        return safe

    def validate_value(self, name: str, value, registry: dict):
        if name not in registry:
            raise SafetyError(
                f"Variable or channel {name!r} is not registered in the whitelist / 未在白名单中登记"
            )
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
        raise SafetyError(f"Unknown parameter type {typ!r} for {name!r}")

    def resolve_registry_name(self, name, registry: dict) -> str:
        text = str(name or "").strip()
        if text in registry:
            return text
        norm = self._norm_name(text)
        aliases: dict[str, str] = {}
        for registered, rule in (registry or {}).items():
            aliases[self._norm_name(registered)] = registered
            aliases[self._norm_name(str(rule.get("bridge_name", "")))] = registered
            aliases[self._norm_name(str(rule.get("channel", "")))] = registered
            device = str(rule.get("device", "")).strip()
            channel = str(rule.get("channel", "")).strip()
            if device and channel:
                aliases[self._norm_name(f"{device}.{channel}")] = registered
            for alias in rule.get("aliases", []) or []:
                aliases[self._norm_name(str(alias))] = registered
        return aliases.get(norm, text)

    @staticmethod
    def _norm_name(value: str) -> str:
        return "".join(ch for ch in str(value).lower().replace("_", " ") if ch.isalnum())

    def validate_load_h5(self, action: dict) -> dict:
        path = action.get("path") or action.get("folder")
        if not path:
            raise SafetyError("load_h5 requires path")
        return {
            "type": "load_h5",
            "path": str(Path(str(path))),
            "recursive": _optional_bool(action.get("recursive"), False),
        }

    def validate_lyse_module(self, action: dict, group: str) -> dict:
        modules = self.lyse_registry.get(group, {})
        name = action.get("name")
        if not name:
            raise SafetyError(f"{group}: module name is required")
        if name not in modules:
            raise SafetyError(f"{group}: module {name!r} is not registered")
        params = action.get("params", {})
        if params is None:
            params = {}
        if not isinstance(params, dict):
            raise SafetyError(f"{group}: params must be an object")
        return {"type": action.get("type"), "name": str(name), "params": params}

    def validate_plot(self, action: dict) -> dict:
        plot_type = str(action.get("plot_type", "scatter_line"))
        allowed = {"scatter_line", "mean_errorbar", "histogram", "scatter2d", "heatmap2d", "surface3d"}
        if plot_type not in allowed:
            raise SafetyError(f"plot_type {plot_type!r} is not allowed")
        item = {"type": "plot", "plot_type": plot_type}
        for key in ["x", "y", "z", "value", "group_by", "out_path"]:
            if key in action and action[key] is not None:
                item[key] = str(action[key])
        return item

    def validate_fit(self, action: dict) -> dict:
        model = str(action.get("model", "linear"))
        allowed = {"linear", "gaussian", "logarithmic", "exponential", "lorentzian", "gaussian2d", "double_gaussian2d"}
        if model not in allowed:
            raise SafetyError(f"fit model {model!r} is not allowed")
        item = {"type": "fit", "model": model}
        for key in ["x", "y", "z", "value"]:
            if key in action and action[key] is not None:
                item[key] = str(action[key])
        return item

    def validate_optimization(self, action: dict) -> dict:
        method = str(action.get("method", "grid")).lower()
        if method not in {"grid", "bayesian"}:
            raise SafetyError("optimization method must be grid or bayesian")
        mode = str(action.get("mode", "maximize")).lower()
        if mode not in {"maximize", "minimize"}:
            raise SafetyError("optimization mode must be maximize or minimize")
        objective = str(action.get("objective", "")).strip()
        if not objective:
            raise SafetyError("optimization objective is required")
        try:
            from labpilot_ai.optimizer.objective import SafeObjective

            SafeObjective(objective)
        except Exception as exc:
            raise SafetyError(f"unsafe optimization objective: {exc}") from exc
        params = action.get("parameters", action.get("params", {}))
        parameters = self._normalize_optimization_parameters(params)
        max_iterations = int(action.get("max_iterations", len(parameters) or 1))
        repeats = int(action.get("repeats", 1))
        if max_iterations < 1 or repeats < 1:
            raise SafetyError("max_iterations and repeats must be positive")
        poll_interval_s = float(action.get("poll_interval_s", 1.0))
        h5_timeout_s = float(action.get("h5_timeout_s", 120.0))
        if poll_interval_s < 0.05:
            raise SafetyError("poll_interval_s must be >= 0.05")
        if h5_timeout_s < 0.1:
            raise SafetyError("h5_timeout_s must be >= 0.1")
        return {
            "type": "start_optimization",
            "method": method,
            "mode": mode,
            "objective": objective,
            "parameters": parameters,
            "max_iterations": max_iterations,
            "repeats": repeats,
            "auto_loop": _optional_bool(action.get("auto_loop"), False),
            "run_checked_modules": _optional_bool(action.get("run_checked_modules"), True),
            "poll_interval_s": poll_interval_s,
            "h5_timeout_s": h5_timeout_s,
            "generate_report_on_complete": _optional_bool(action.get("generate_report_on_complete"), False),
        }

    def validate_optimization_feedback(self, action: dict) -> dict:
        values = action.get("values")
        if values is not None:
            if not isinstance(values, dict):
                raise SafetyError("optimization feedback values must be an object")
            return {"type": "tell_optimization_result", "source": "manual_values", "values": values}
        source = str(action.get("source", "latest_h5"))
        if source != "latest_h5":
            raise SafetyError("optimization feedback source must be latest_h5 or values")
        return {
            "type": "tell_optimization_result",
            "source": "latest_h5",
            "run_checked_modules": _optional_bool(action.get("run_checked_modules"), True),
            "reload_h5": _optional_bool(action.get("reload_h5"), True),
        }

    def _normalize_optimization_parameters(self, params) -> dict:
        if isinstance(params, list):
            raw = {p.get("name"): p for p in params if isinstance(p, dict)}
        elif isinstance(params, dict):
            raw = params
        else:
            raise SafetyError("optimization parameters must be an object or list")
        out = {}
        for name, spec in raw.items():
            if name not in self.global_registry:
                raise SafetyError(f"optimization parameter {name!r} is not in global whitelist")
            rule = self.global_registry[name]
            if not isinstance(spec, dict):
                raise SafetyError(f"optimization parameter {name}: spec must be an object")
            pmin = float(spec.get("min", spec.get("low", rule.get("min", 0.0))))
            pmax = float(spec.get("max", spec.get("high", rule.get("max", pmin))))
            self._check_range(name, pmin, rule)
            self._check_range(name, pmax, rule)
            if pmax < pmin:
                raise SafetyError(f"optimization parameter {name}: max below min")
            points = int(spec.get("points", spec.get("num", 5)))
            if points < 1:
                raise SafetyError(f"optimization parameter {name}: points must be positive")
            max_points = int(rule.get("max_points", 100))
            if points > max_points:
                raise SafetyError(f"optimization parameter {name}: points exceeds max_points={max_points}")
            out[name] = {
                "min": pmin,
                "max": pmax,
                "points": points,
                "type": rule.get("type", "float"),
                "unit": rule.get("unit", ""),
            }
        if not out:
            raise SafetyError("at least one optimization parameter is required")
        return out

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

    def _maybe_require_confirmation(self, name: str, registry: dict, safe: dict):
        rule = registry.get(name, {})
        if rule.get("require_confirm") or str(rule.get("risk", "")).lower() == "high":
            safe["confirmations"].append(
                {
                    "name": name,
                    "risk": rule.get("risk", "high"),
                    "description": rule.get("description", ""),
                }
            )
