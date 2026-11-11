from datetime import datetime, timedelta, timezone
from importlib import metadata
import json
import os
from pathlib import Path
import subprocess
import sys
import time
from types import SimpleNamespace

import pytest

from labpilot_ai.host.blacs_plugin import Plugin
from labpilot_ai.host.compatibility import inspect_api
from labpilot_ai.host.device_actions import describe_device, read_device_action, require_typed_manual
from labpilot_ai.host.protocol import Refused


class FixtureTab:
    mode = 1
    error_message = None

    def program_device(self):
        pytest.fail("Compatibility inspection called a programming method")

    def queue_work(self, *_args):
        pytest.fail("Passive device diagnostics started a worker request")


def vendor_tab(module, name, **state):
    tab_type = type(name, (FixtureTab,), {"__module__": f"labscript_devices.{module}"})
    tab = tab_type()
    vars(tab).update(state)
    return tab


def test_typed_ni_and_novatech_descriptors_are_family_specific():
    ni = vendor_tab("NI_DAQmx.blacs_tabs", "NI_DAQmxTab")
    dds = vendor_tab("NovaTechDDS9M", "NovatechDDS9MTab")
    ao = {"kind": "AO", "unit": "V", "limits": [-10, 10]}
    freq = {"kind": "DDS.freq", "unit": "Hz", "limits": [0, 170_000_000]}
    require_typed_manual(ni, {"ao1": ao, "port1/line3": {"kind": "DO"}})
    require_typed_manual(dds, {"channel 1.freq": freq})
    for tab, channel, descriptor in (
        (ni, "channel 1.freq", freq), (dds, "ao1", ao), (ni, "ao1", {**ao, "unit": "mV"}),
        (dds, "channel 4.freq", freq), (dds, "channel 1.gate", {"kind": "DDS.gate"}),
        (ni, "ao1", {**ao, "limits": [0, float("inf")]}),
    ):
        with pytest.raises(Refused):
            require_typed_manual(tab, {channel: descriptor})
    assert describe_device(ni, manual_mode=1, write_channels=["ao1"])["write_actions"] == ["set_manual"]
    assert describe_device(FixtureTab(), manual_mode=1, write_channels=["ao1"])["write_actions"] == []


def test_novatech_register_cache_is_bounded_and_never_treated_as_fresh_hardware():
    dds = vendor_tab("NovaTechDDS9M", "NovatechDDS9MTab", _can_check_remote_values=True,
                     _last_remote_values={"channel 1": {"freq": 88e6, "amp": 0.1, "phase": 0},
                                          "channel 2": {"freq": float("nan"), "amp": 0.1, "phase": 0}})
    assert "dds_registers" in describe_device(dds, manual_mode=1)["read_actions"]
    result = read_device_action("dds_registers", dds, device="dds", manual_mode=1)
    assert result["evidence"] == "BLACS_NOVATECH_REGISTER_CACHE"
    assert result["new_hardware_query"] is False and result["physical_output_verified"] is False
    assert result["value"] == {"channel 1": {"frequency_hz": 88e6, "amplitude_arb": 0.1, "phase_deg": 0}}
    dds._last_remote_values = {}
    assert read_device_action("dds_registers", dds, device="dds", manual_mode=1)["available"] is False


def test_andor_cached_temperature_and_prawn_existing_status_labels():
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    camera = vendor_tab("AndorPylablib.blacs_tabs", "AndorPylablibTab", _andor_last_status={
        "settings": {"hsspeed_mhz": 0.1, "amplifier_mode": "conventional", "xbin": 4, "extra": 7},
        "temperature": {"value_C": -60, "sampled_at_utc": now.isoformat(), "stale": False},
    })
    value = read_device_action("camera_status", camera, device="andor", manual_mode=1, now=now)
    assert value["value"]["temperature"] == {
        "value_c": -60, "sampled_at_utc": now.isoformat(), "age_s": 0, "stale": False,
    }
    assert value["value"]["settings"] == {"hsspeed_mhz": 0.1, "amplifier_mode": "conventional", "xbin": 4}
    later = read_device_action("camera_status", camera, device="andor", manual_mode=1,
                               now=now + timedelta(seconds=31))
    assert later["value"]["temperature"]["stale"] is True
    assert camera._andor_last_status["temperature"]["stale"] is False
    generic_camera = vendor_tab("IMAQdxCamera.blacs_tabs", "IMAQdxCameraTab")
    assert describe_device(generic_camera, manual_mode=1)["unavailable_read_actions"] == ["camera_status"]
    with pytest.raises(Refused):
        read_device_action("camera_status", generic_camera, device="generic", manual_mode=1)

    clock = vendor_tab("PrawnBlaster.blacs_tabs", "PrawnBlasterTab",
                       status_label=SimpleNamespace(text=lambda: "Status: 0"),
                       clock_status_label=SimpleNamespace(text=lambda: "Clock status: 1"))
    result = read_device_action("pseudoclock_status", clock, device="prawn", manual_mode=1)
    assert result["value"] == {"run_status": 0, "clock_status": 1}
    assert result["new_hardware_query"] is False


def test_plugin_snapshot_dispatches_specialized_cache_without_full_channel_scan(tmp_path, monkeypatch):
    tab = vendor_tab("NovaTechDDS9M", "NovatechDDS9MTab",
                     _can_check_remote_values=True, _last_remote_values={})
    plugin = Plugin()
    plugin.manual_mode = 1
    plugin.accessor = SimpleNamespace(_tabs=lambda: {"dds": tab})
    plugin.profile = SimpleNamespace(blacs={"allow": {"dds": ["channel 1.freq"]}})
    replies = []
    monkeypatch.setattr(plugin, "_reply", lambda message, state, **data: replies.append((state, data)))
    monkeypatch.setattr(plugin, "_capture", lambda *_: pytest.fail("Specialized query scanned all channels"))
    for index, (method, params) in enumerate((
        ("discover", {}), ("snapshot", {"device": "dds", "action": "dds_registers"}),
        ("snapshot", {"device": "dds", "action": "snap"}),
    )):
        path = tmp_path / f"{index}.json"
        path.write_text(json.dumps({"generation": plugin.generation, "mail_id": path.stem,
                                    "expires": time.time() + 2, "method": method, "params": params}), encoding="utf-8")
        plugin._read_one(path)
    assert replies[0][1]["value"]["device_capabilities"]["dds"]["read_actions"] == ["dds_registers", "device_status"]
    assert replies[1][1]["value"]["available"] is False
    assert replies[2][0] == "REFUSED"


class Distribution:
    version = "9.0.0"

    def __init__(self, root):
        self.root = root

    def locate_file(self, path):
        return self.root / path


def write(root, name, text):
    path = root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def test_static_compatibility_detects_missing_renamed_and_unreadable_apis(tmp_path):
    def installed(name):
        if name not in {"blacs", "runmanager"}:
            raise metadata.PackageNotFoundError(name)
        return Distribution(tmp_path)

    write(tmp_path, "runmanager/remote.py", "raise RuntimeError('never import fixture')\nclass Client:\n"
          "    def get_globals(self, *, raw=False): ...\n    engage = 3\n")
    write(tmp_path, "blacs/tab_base_classes.py", "this file cannot be parsed !\n")
    result = inspect_api(installed)
    features = result["features"]
    assert features["lyse_h5_surface"]["state"] == "PACKAGE_MISSING"
    assert features["blacs_manual_tab"]["state"] == "SOURCE_UNAVAILABLE"
    assert features["runmanager_remote_client"]["state"] == "API_MISMATCH"
    assert "runmanager/remote.py:Client.engage" in features["runmanager_remote_client"]["missing_members"]
    assert "runmanager/remote.py:Client.get_globals" not in features["runmanager_remote_client"]["missing_members"]
    assert result["runtime_or_hardware_verified"] is False


def test_native_host_cli_installs_and_checks_shim_in_isolated_pythonpath(tmp_path):
    isolated = tmp_path / "isolated"
    write(isolated, "blacs/__init__.py", "raise RuntimeError('do not import fixture BLACS')\n")
    write(isolated, "blacs/plugins/__init__.py", "def get_callbacks(name): ...\n")
    write(isolated, "blacs/tab_base_classes.py", "MODE_MANUAL = 1\n"
          "def define_state(*args): ...\nclass Tab:\n    def queue_work(self, *args): ...\n")
    write(isolated, "blacs/device_base_class.py", "class DeviceTab:\n"
          "    def get_front_panel_values(self): ...\n    def program_device(self): ...\n")
    write(isolated, "blacs-9.0.0.dist-info/METADATA", "Name: blacs\nVersion: 9.0.0\n")
    profile = write(tmp_path, "profile.json", '{"host":{"blacs":{"enabled":true}}}')
    config = write(tmp_path, "labconfig.ini", "[BLACS/plugins]\nother = True\n")
    original = config.read_bytes()
    script = Path(__file__).resolve().parents[1] / "labpilot_ai" / "host" / "__main__.py"
    env = {**os.environ, "PYTHONPATH": str(isolated), "PYTHONNOUSERSITE": "1"}

    def host(command, *options):
        result = subprocess.run([sys.executable, str(script), command, "--profile", str(profile),
                                 "--labconfig", str(config), *options], cwd=tmp_path, env=env,
                                capture_output=True, check=True, text=True, encoding="utf-8", timeout=30)
        message, = (line for line in result.stdout.splitlines() if line.startswith("LABPILOT_HOST_JSON:"))
        return json.loads(message.split(":", 1)[1])["value"]

    assert host("doctor")["shim_state"] == "MISSING"
    assert host("install", "--apply")["applied"] is True
    result = host("doctor")
    shim = isolated / "blacs" / "plugins" / "labpilot_host" / "__init__.py"
    assert Path(result["shim_path"]) == shim
    assert result["shim_state"] == "MATCHES_PACKAGE"
    assert result["labconfig_blacs_plugin_enabled"] is True
    assert result["api_compatibility"]["features"]["blacs_manual_tab"]["state"] == "API_SURFACE_PRESENT"
    host("uninstall", "--apply")
    assert not shim.exists() and config.read_bytes() == original
