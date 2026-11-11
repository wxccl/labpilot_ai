"""Typed native manual devices and passive status from existing BLACS tabs."""

from datetime import datetime, timezone
import math
import re

from .protocol import Refused


_FAMILIES = {
    ("labscript_devices.NI_DAQmx.blacs_tabs", "NI_DAQmxTab"): "ni_daqmx",
    ("labscript_devices.NovaTechDDS9M", "NovatechDDS9MTab"): "novatech_dds9m",
    ("labscript_devices.AndorPylablib.blacs_tabs", "AndorPylablibTab"): "andor_pylablib",
    ("labscript_devices.IMAQdxCamera.blacs_tabs", "IMAQdxCameraTab"): "imaqdx_camera",
    ("labscript_devices.PrawnBlaster.blacs_tabs", "PrawnBlasterTab"): "prawnblaster",
}
_MANUAL = {
    "ni_daqmx": {
        "AO": (r"ao\d+", "v"),
        "DO": (r"port\d+/line\d+", None),
    },
    "novatech_dds9m": {
        "DDS.freq": (r"channel [0-3]\.freq", "hz"),
        "DDS.amp": (r"channel [0-3]\.amp", "arb"),
        "DDS.phase": (r"channel [0-3]\.phase", "degrees"),
    },
}
_CAMERA_SETTINGS = (
    "hsspeed_mhz", "vsspeed_us", "amplifier_mode", "preamp_gain", "emccd_gain",
    "em_gain_applied_command", "xbin", "ybin", "left_start", "bottom_start",
    "width", "height", "exposure_time",
)
_TEMPERATURE_MAX_AGE = 30.0
DEVICE_READ_ACTIONS = frozenset({"device_status", "dds_registers", "camera_status", "pseudoclock_status"})


def device_family(tab):
    for cls in type(tab).__mro__:
        family = _FAMILIES.get((cls.__module__, cls.__name__))
        if family is not None:
            return family
    return "unknown"


def _finite(value):
    return ((type(value) is int and value.bit_length() <= 53)
            or (type(value) is float and math.isfinite(value)))


def _manual_state(tab, manual_mode):
    return getattr(tab, "mode", None) == manual_mode and not bool(getattr(tab, "error_message", False))


def _read_support(tab, family):
    actions = {"device_status": True}
    if family == "novatech_dds9m":
        actions["dds_registers"] = (getattr(tab, "_can_check_remote_values", False) is True
                                    and isinstance(getattr(tab, "_last_remote_values", None), dict))
    if family in {"andor_pylablib", "imaqdx_camera"}:
        actions["camera_status"] = family == "andor_pylablib" and hasattr(tab, "_andor_last_status")
    if family == "prawnblaster":
        actions["pseudoclock_status"] = all(
            callable(getattr(getattr(tab, label, None), "text", None))
            for label in ("status_label", "clock_status_label")
        )
    return actions


def describe_device(tab, *, manual_mode, write_channels=()):
    family = device_family(tab)
    reads = _read_support(tab, family)
    can_write = bool(write_channels) and family in _MANUAL and callable(getattr(tab, "program_device", None))
    return {
        "family": family,
        "manual_healthy": _manual_state(tab, manual_mode),
        "read_actions": sorted(name for name, available in reads.items() if available),
        "unavailable_read_actions": sorted(name for name, available in reads.items() if not available),
        "write_actions": ["set_manual"] if can_write else [],
        "manual_channel_kinds": sorted(_MANUAL.get(family, {})),
    }


def require_typed_manual(tab, channels):
    allowed = _MANUAL.get(device_family(tab))
    if not allowed or not channels or not callable(getattr(tab, "program_device", None)):
        raise Refused("This BLACS tab has no supported typed manual driver")
    for name, descriptor in channels.items():
        kind = descriptor.get("kind")
        rule = allowed.get(kind)
        if rule is None:
            raise Refused(f"{name} is not a supported channel kind for this BLACS device")
        pattern, unit = rule
        if re.fullmatch(pattern, name) is None:
            raise Refused(f"{name} does not match the native BLACS channel format")
        if unit is not None:
            reported_unit = descriptor.get("unit")
            limits = descriptor.get("limits")
            if (type(reported_unit) is not str or reported_unit.strip().lower() != unit
                    or not isinstance(limits, (list, tuple)) or len(limits) != 2
                    or not all(_finite(limit) for limit in limits) or limits[0] > limits[1]):
                raise Refused(f"{name} has incompatible native units or numeric limits")


def _registers(tab):
    result = {}
    for channel, sample in tab._last_remote_values.items():
        if (type(channel) is str and re.fullmatch(r"channel [0-3]", channel)
                and isinstance(sample, dict) and all(_finite(sample.get(key)) for key in ("freq", "amp", "phase"))):
            result[channel] = {"frequency_hz": sample["freq"], "amplitude_arb": sample["amp"],
                               "phase_deg": sample["phase"]}
    return result


def _camera(tab, now):
    sample = tab._andor_last_status
    if not isinstance(sample, dict):
        return {}, False
    settings = sample.get("settings")
    temperature = sample.get("temperature")
    settings = settings if isinstance(settings, dict) else {}
    temperature = temperature if isinstance(temperature, dict) else {}
    filtered_settings = {}
    for key in _CAMERA_SETTINGS:
        value = settings.get(key)
        if _finite(value) or (key == "amplifier_mode" and type(value) is str and len(value) <= 64):
            filtered_settings[key] = value
    sampled = temperature.get("sampled_at_utc")
    age = None
    if isinstance(sampled, str) and len(sampled) <= 64:
        try:
            instant = datetime.fromisoformat(sampled.replace("Z", "+00:00"))
            if instant.tzinfo is not None:
                age = (now - instant).total_seconds()
        except (ValueError, OverflowError):
            pass
    value = temperature.get("value_C")
    if not _finite(value):
        value = None
    quarantined = sample.get("quarantined") is True
    stale = (temperature.get("stale") is not False or age is None or not 0 <= age <= _TEMPERATURE_MAX_AGE
             or value is None or quarantined)
    return {"settings": filtered_settings,
            "temperature": {"value_c": value, "sampled_at_utc": sampled if age is not None else None,
                            "age_s": age, "stale": stale},
            "quarantined": quarantined}, bool(filtered_settings or value is not None)


def _prawn(tab):
    result = {}
    for key, label, prefix in (
        ("run_status", "status_label", "Status"),
        ("clock_status", "clock_status_label", "Clock status"),
    ):
        text = getattr(tab, label).text()
        match = re.fullmatch(rf"{prefix}:\s*(\d{{1,2}})", text) if isinstance(text, str) else None
        if match is not None:
            result[key] = int(match[1])
    return result


def read_device_action(action, tab, *, device, manual_mode, now=None):
    family = device_family(tab)
    if type(action) is not str or not _read_support(tab, family).get(action, False):
        raise Refused("This BLACS tab does not expose the requested read capability")
    now = now or datetime.now(timezone.utc)
    if action == "dds_registers":
        data = _registers(tab)
        evidence, sampled = "BLACS_NOVATECH_REGISTER_CACHE", bool(data)
    elif action == "camera_status":
        data, sampled = _camera(tab, now)
        evidence = "BLACS_ANDOR_STATUS_CACHE"
    elif action == "pseudoclock_status":
        data = _prawn(tab)
        evidence, sampled = "BLACS_PRAWN_STATUS_LABELS", bool(data)
    else:
        mode = getattr(tab, "mode", None)
        data = {"mode": mode if type(mode) is int else None,
                "manual_healthy": _manual_state(tab, manual_mode),
                "error_present": bool(getattr(tab, "error_message", False))}
        evidence, sampled = "BLACS_TAB_STATE", True
    return {"device": device, "family": family, "action": action, "available": sampled,
            "observed_at_utc": now.isoformat(), "value": data, "evidence": evidence,
            "manual_healthy": _manual_state(tab, manual_mode), "new_hardware_query": False,
            "physical_output_verified": False}
