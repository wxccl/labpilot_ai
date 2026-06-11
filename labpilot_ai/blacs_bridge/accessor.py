from __future__ import annotations

import json
import os
import threading
import traceback
from dataclasses import dataclass
from typing import Any, Callable

try:
    from qtutils import inmain as _qt_inmain
except Exception:  # pragma: no cover - absent outside BLACS
    _qt_inmain = None

try:
    from blacs.tab_base_classes import MODE_MANUAL
except Exception:  # pragma: no cover - absent outside BLACS
    MODE_MANUAL = 1


_SIMPLE_TYPES = (str, int, float, bool, type(None))


def safe_repr(value: Any, maxlen: int = 300) -> str:
    try:
        text = repr(value)
    except Exception:
        text = f"<{type(value).__name__}: repr failed>"
    if len(text) > maxlen:
        text = text[: maxlen - 3] + "..."
    return text


def json_safe(value: Any, max_depth: int = 5) -> Any:
    if max_depth <= 0:
        return safe_repr(value)
    if isinstance(value, _SIMPLE_TYPES):
        return value
    if isinstance(value, dict):
        return {str(k): json_safe(v, max_depth - 1) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [json_safe(v, max_depth - 1) for v in value]
    return safe_repr(value)


def _maybe_call(obj: Any, name: str, *args, **kwargs) -> Any:
    func = getattr(obj, name, None)
    if callable(func):
        return func(*args, **kwargs)
    return None


@dataclass
class ChannelRef:
    name: str
    device: str
    channel: str
    kind: str
    type: str
    value: Any = None
    subchannel: str | None = None
    labscript_name: str | None = None
    unit: str | None = None
    minimum: float | None = None
    maximum: float | None = None
    locked: bool | None = None
    tab: Any = None
    output: Any = None

    def as_dict(self) -> dict[str, Any]:
        out = {
            "name": self.name,
            "bridge_name": self.name,
            "device": self.device,
            "channel": self.channel,
            "kind": self.kind,
            "type": self.type,
            "current_value": json_safe(self.value),
            "risk": "medium",
            "require_confirm": True,
        }
        if self.subchannel:
            out["subchannel"] = self.subchannel
        if self.labscript_name:
            out["labscript_name"] = self.labscript_name
            out["aliases"] = [self.labscript_name]
        if self.unit:
            out["unit"] = self.unit
        if self.minimum is not None:
            out["min"] = self.minimum
        if self.maximum is not None:
            out["max"] = self.maximum
        if self.locked is not None:
            out["locked"] = self.locked
        return out


class BLACSAccessor:
    """Introspect and control the running BLACS process.

    The accessor must be constructed inside BLACS plugin_setup_complete(BLACS),
    where BLACS is the dictionary-like object passed by BLACS. Operations that
    touch Qt widgets or BLACS DeviceTabs are routed through qtutils.inmain when
    available.
    """

    def __init__(self, blacs_data: Any):
        self.blacs_data = blacs_data
        self._last_debug_error: str | None = None

    def _call_main(self, func: Callable, *args, **kwargs):
        if _qt_inmain is None:
            return func(*args, **kwargs)
        return _qt_inmain(func, *args, **kwargs)

    def _manager(self) -> Any:
        data = self.blacs_data
        # BLACS passes a dict containing experiment_queue, and the queue has a
        # .BLACS attribute pointing back to the main BLACS object. This is the
        # path used by the built-in connection_table plugin.
        if isinstance(data, dict):
            queue = data.get("experiment_queue")
            manager = getattr(queue, "BLACS", None)
            if manager is not None:
                return manager
            if "BLACS" in data:
                return data["BLACS"]
        return data

    def status(self) -> dict[str, Any]:
        manager = self._manager()
        return {
            "ok": True,
            "service": "labpilot-real-blacs-bridge",
            "has_blacs": self.blacs_data is not None,
            "has_manager": manager is not None,
            "thread": threading.current_thread().name,
            "allow_write_env": os.environ.get("LABPILOT_BLACS_ALLOW_WRITE", ""),
        }

    def debug(self) -> dict[str, Any]:
        manager = self._manager()
        data = self.blacs_data
        payload = {
            "ok": True,
            "service": "labpilot-real-blacs-bridge",
            "blacs_data_type": str(type(data)),
            "manager_type": str(type(manager)),
            "blacs_dict_keys": sorted(list(data.keys())) if isinstance(data, dict) else [],
            "manager_dict_keys": sorted(list(getattr(manager, "__dict__", {}).keys())),
            "manager_attrs": sorted([x for x in dir(manager) if not x.startswith("__")])[:400],
            "tab_names": [],
            "tab_debug": {},
            "last_debug_error": self._last_debug_error,
        }
        try:
            tabs = self._tabs()
            payload["tab_names"] = sorted(tabs.keys())
            for name_, tab in tabs.items():
                payload["tab_debug"][name_] = {
                    "type": str(type(tab)),
                    "attrs": sorted([x for x in dir(tab) if not x.startswith("__")])[:250],
                    "dict_keys": sorted(list(getattr(tab, "__dict__", {}).keys())),
                    "has_get_front_panel_values": callable(getattr(tab, "get_front_panel_values", None)),
                    "has_get_channel": callable(getattr(tab, "get_channel", None)),
                    "mode": safe_repr(getattr(tab, "mode", None)),
                    "state": safe_repr(getattr(tab, "state", None)),
                }
        except Exception:
            payload["debug_exception"] = traceback.format_exc()
        return payload

    def _tabs(self) -> dict[str, Any]:
        def discover():
            manager = self._manager()
            tabs: dict[str, Any] = {}

            # Preferred, exact BLACS path: BLACS object has tablist.
            for source in (manager, self.blacs_data):
                tablist = getattr(source, "tablist", None)
                if isinstance(tablist, dict):
                    for name_, tab in tablist.items():
                        if self._is_device_tab(tab):
                            tabs[str(name_)] = tab

            # Fallbacks for version/custom code: scan common attrs and dicts.
            if not tabs:
                for obj in (manager, self.blacs_data):
                    self._walk_for_tabs(obj, tabs, depth=0, seen=set())

            return tabs

        return self._call_main(discover)

    def _walk_for_tabs(self, obj: Any, tabs: dict[str, Any], depth: int, seen: set[int]) -> None:
        if obj is None or depth > 4:
            return
        oid = id(obj)
        if oid in seen:
            return
        seen.add(oid)
        if self._is_device_tab(obj):
            name_ = str(getattr(obj, "device_name", f"tab_{len(tabs)}"))
            tabs.setdefault(name_, obj)
            return
        if isinstance(obj, dict):
            iterable = obj.values()
        elif isinstance(obj, (list, tuple, set)):
            iterable = obj
        else:
            keys = [
                "tablist",
                "tabs",
                "device_tabs",
                "_tabs",
                "settings_dict",
                "blacs_data",
                "BLACS",
            ]
            iterable = [getattr(obj, key, None) for key in keys if hasattr(obj, key)]
        for child in iterable:
            self._walk_for_tabs(child, tabs, depth + 1, seen)

    @staticmethod
    def _is_device_tab(obj: Any) -> bool:
        return (
            hasattr(obj, "device_name")
            and callable(getattr(obj, "get_front_panel_values", None))
            and callable(getattr(obj, "get_channel", None))
            and any(hasattr(obj, attr) for attr in ("_AO", "_DO", "_DDS", "_EO", "_image"))
        )

    def discover_channels(self) -> list[dict[str, Any]]:
        def discover():
            refs = self._channel_refs()
            return [ref.as_dict() for ref in refs]

        return self._call_main(discover)

    def values(self) -> dict[str, Any]:
        def read():
            values: dict[str, Any] = {}
            for ref in self._channel_refs():
                values[ref.name] = json_safe(ref.value)
            return values

        return self._call_main(read)

    def _channel_refs(self) -> list[ChannelRef]:
        refs: list[ChannelRef] = []
        for device, tab in self._tabs().items():
            try:
                front_values = tab.get_front_panel_values() or {}
            except Exception:
                front_values = {}
            refs.extend(self._refs_from_outputs(device, tab, "AO", "_AO", "float", front_values))
            refs.extend(self._refs_from_outputs(device, tab, "DO", "_DO", "bool", front_values))
            refs.extend(self._refs_from_outputs(device, tab, "EO", "_EO", "enum", front_values))
            refs.extend(self._refs_from_outputs(device, tab, "Image", "_image", "object", front_values))
            refs.extend(self._dds_refs(device, tab, front_values))
        return refs

    def _refs_from_outputs(
        self,
        device: str,
        tab: Any,
        kind: str,
        attr: str,
        type_: str,
        front_values: dict[str, Any],
    ) -> list[ChannelRef]:
        refs = []
        outputs = getattr(tab, attr, {}) or {}
        for channel, output in outputs.items():
            value = front_values.get(channel, getattr(output, "value", None))
            refs.append(
                ChannelRef(
                    name=f"{device}.{channel}",
                    device=device,
                    channel=str(channel),
                    kind=kind,
                    type=type_,
                    value=value,
                    labscript_name=self._labscript_name(output),
                    unit=getattr(output, "_base_unit", None) or getattr(output, "_current_units", None),
                    minimum=self._limit(output, 0),
                    maximum=self._limit(output, 1),
                    locked=bool(getattr(output, "_locked", False)),
                    tab=tab,
                    output=output,
                )
            )
        return refs

    def _dds_refs(self, device: str, tab: Any, front_values: dict[str, Any]) -> list[ChannelRef]:
        refs = []
        outputs = getattr(tab, "_DDS", {}) or {}
        for channel, output in outputs.items():
            value = front_values.get(channel, getattr(output, "value", None))
            refs.append(
                ChannelRef(
                    name=f"{device}.{channel}",
                    device=device,
                    channel=str(channel),
                    kind="DDS",
                    type="dict",
                    value=value,
                    labscript_name=self._labscript_name(output),
                    locked=bool(getattr(output, "_locked", False)),
                    tab=tab,
                    output=output,
                )
            )
            if isinstance(value, dict):
                for sub, sub_value in value.items():
                    sub_output = getattr(output, sub, None)
                    refs.append(
                        ChannelRef(
                            name=f"{device}.{channel}.{sub}",
                            device=device,
                            channel=str(channel),
                            kind=f"DDS.{sub}",
                            type="bool" if sub == "gate" else "float",
                            value=sub_value,
                            subchannel=str(sub),
                            labscript_name=self._labscript_name(output),
                            unit=getattr(sub_output, "_base_unit", None) if sub_output is not None else None,
                            minimum=self._limit(sub_output, 0) if sub_output is not None else None,
                            maximum=self._limit(sub_output, 1) if sub_output is not None else None,
                            locked=bool(getattr(sub_output, "_locked", False)) if sub_output is not None else None,
                            tab=tab,
                            output=output,
                        )
                    )
        return refs

    @staticmethod
    def _labscript_name(output: Any) -> str | None:
        for attr in ("_connection_name", "connection_name", "name"):
            value = getattr(output, attr, None)
            if value and value != "-":
                return str(value)
        return None

    @staticmethod
    def _limit(output: Any, index: int) -> float | None:
        limits = getattr(output, "_limits", None)
        if isinstance(limits, (list, tuple)) and len(limits) > index:
            try:
                return float(limits[index])
            except Exception:
                return None
        return None

    def _find_ref(self, name: str | None = None, device: str | None = None, channel: str | None = None, subchannel: str | None = None) -> ChannelRef:
        refs = self._channel_refs()
        norm = str(name or "").strip()
        if device and channel:
            norm = f"{device}.{channel}" + (f".{subchannel}" if subchannel else "")
        aliases: dict[str, ChannelRef] = {}
        for ref in refs:
            aliases[ref.name] = ref
            aliases[ref.name.lower()] = ref
            aliases[f"{ref.device}.{ref.channel}".lower()] = ref
            if ref.subchannel:
                aliases[f"{ref.device}.{ref.channel}.{ref.subchannel}".lower()] = ref
            if ref.labscript_name:
                aliases[ref.labscript_name] = ref
                aliases[ref.labscript_name.lower()] = ref
        if norm in aliases:
            return aliases[norm]
        if norm.lower() in aliases:
            return aliases[norm.lower()]
        raise KeyError(f"BLACS manual channel not found: {norm!r}")

    def set_manual(self, payload: dict[str, Any], *, allow_write: bool = False) -> dict[str, Any]:
        if not allow_write:
            return {
                "ok": False,
                "error": "Real BLACS write is disabled. Set LABPILOT_BLACS_ALLOW_WRITE=1 or labpilot_bridge.allow_write=True only after verifying channels.",
            }

        def write():
            ref = self._find_ref(
                name=payload.get("name") or payload.get("bridge_name"),
                device=payload.get("device"),
                channel=payload.get("channel"),
                subchannel=payload.get("subchannel"),
            )
            tab = ref.tab
            output = ref.output
            if tab is None or output is None:
                raise RuntimeError("Resolved channel has no BLACS tab/output object")
            if getattr(tab, "mode", MODE_MANUAL) != MODE_MANUAL:
                raise RuntimeError(
                    f"Device {ref.device} is not in manual mode; current mode={safe_repr(getattr(tab, 'mode', None))}"
                )
            if getattr(output, "_locked", False):
                raise RuntimeError(f"BLACS channel is locked: {ref.name}")

            value = payload.get("value")
            unit = payload.get("unit")
            program = bool(payload.get("program", True))

            if ref.subchannel:
                # Prefer editing a DDS sub-output directly if it exists.
                sub_output = getattr(output, ref.subchannel, None)
                if sub_output is not None and callable(getattr(sub_output, "set_value", None)):
                    if unit is not None:
                        sub_output.set_value(value, unit=unit, program=False)
                    else:
                        sub_output.set_value(value, program=False)
                    if program:
                        tab.program_device()
                else:
                    current = dict(getattr(output, "value", {}) or {})
                    current[ref.subchannel] = value
                    output.set_value(current, program=program)
            else:
                if unit is not None:
                    output.set_value(value, unit=unit, program=program)
                else:
                    output.set_value(value, program=program)

            new_values = tab.get_front_panel_values()
            return {
                "ok": True,
                "service": "labpilot-real-blacs-bridge",
                "name": ref.name,
                "device": ref.device,
                "channel": ref.channel,
                "subchannel": ref.subchannel,
                "program": program,
                "front_panel_value": json_safe(new_values.get(ref.channel)),
                "note": "program=True queues BLACS DeviceTab.program_device() through the BLACS state machine.",
            }

        try:
            return self._call_main(write)
        except Exception as exc:
            return {"ok": False, "error": str(exc), "traceback": traceback.format_exc()}
