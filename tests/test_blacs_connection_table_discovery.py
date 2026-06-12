from pathlib import Path

from labpilot_ai.ai.llm_client import LLMClient
from labpilot_ai.blacs_ctrl.connection_table_discovery import (
    discover_blacs_channels_from_connection_table,
    merge_blacs_registry_from_connection_table,
)
from labpilot_ai.safety.validator import SafetyValidator


def test_connection_table_discovery_from_virtual_project():
    root = Path(__file__).resolve().parents[2]
    path = root / "virtual_real_labscript_project" / "connection_table.py"
    registry, report = discover_blacs_channels_from_connection_table(path)

    assert report["count"] >= 3
    assert registry["camera_trigger"]["type"] == "bool"
    assert registry["camera_trigger"]["channel"] == "port0/line2"
    assert registry["bias_voltage"]["type"] == "float"
    assert registry["probe_intensity_voltage"]["channel"] == "ao4"
    assert "LabPilotVirtualDevice.port0/line2" in registry["camera_trigger"]["aliases"]


def test_blacs_alias_resolution_and_mock_parser():
    parsed = {
        "camera_trigger": {
            "type": "bool",
            "device": "LabPilotVirtualDevice",
            "channel": "port0/line2",
            "aliases": ["camera trigger", "LabPilotVirtualDevice.port0/line2"],
            "risk": "low",
        }
    }
    registry = merge_blacs_registry_from_connection_table(parsed, {})
    validator = SafetyValidator({}, registry)

    safe = validator.validate_command(
        {"actions": [{"type": "set_blacs_manual", "name": "LabPilotVirtualDevice.port0/line2", "value": "关闭"}]}
    )
    assert safe["actions"][0]["name"] == "camera_trigger"
    assert safe["blacs_manual"]["camera_trigger"] is False

    command = LLMClient(mock=True)._mock_parse("关闭 blacs 的 camera trigger", {}, registry)
    assert command["actions"] == [{"type": "set_blacs_manual", "name": "camera_trigger", "value": False}]


def test_connection_table_merge_deduplicates_bridge_channel():
    existing = {
        "LabPilotVirtualDevice.port0/line2": {
            "type": "bool",
            "device": "LabPilotVirtualDevice",
            "channel": "port0/line2",
            "bridge_name": "LabPilotVirtualDevice.port0/line2",
            "aliases": ["port0/line2"],
        }
    }
    parsed = {
        "camera_trigger": {
            "type": "bool",
            "device": "LabPilotVirtualDevice",
            "channel": "port0/line2",
            "aliases": ["camera trigger"],
            "risk": "low",
        }
    }
    registry = merge_blacs_registry_from_connection_table(parsed, existing)
    assert "camera_trigger" in registry
    assert "LabPilotVirtualDevice.port0/line2" not in registry
    assert "LabPilotVirtualDevice.port0/line2" in registry["camera_trigger"]["aliases"]
    assert registry["camera_trigger"]["bridge_name"] == "LabPilotVirtualDevice.port0/line2"


def test_mock_parser_routes_runmanager_global():
    command = LLMClient(mock=True)._mock_parse(
        "设置 ct_probe_voltage_min_V 为 1V",
        {"ct_probe_voltage_min_V": {"type": "float"}},
        {},
    )
    assert command["actions"] == [{"type": "set_global", "name": "ct_probe_voltage_min_V", "value": 1.0}]
