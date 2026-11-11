from datetime import datetime, timedelta, timezone
import hashlib
import json

import pytest

from labpilot_ai.blacs_ctrl.local_gateway import LocalBlacs
from labpilot_ai.blacs_ctrl.manual_client import BlacsManualClient


def snapshot():
    data = {
        "host_generation": "1" * 32,
        "connection_sha256": "2" * 64,
        "device": "TestDDS",
        "connection": "COM1",
        "driver_class": "labscript_devices.NovaTechDDS9M.NovatechDDS9MTab",
        "family": "NOVATECH_DDS9M",
        "channels": {
            "channel 1": {"kind": "DDS", "subchannels": {
                "freq": {"kind": "AO", "limits": [0, 100_000_000], "units": "Hz"},
                "amp": {"kind": "AO", "limits": [0, 1], "units": "Arb"},
                "gate": {"kind": "DO", "units": "logical boolean"},
            }},
        },
        "front_panel": {"channel 1": {"freq": 10, "amp": 0.1, "gate": False}},
        "last_programmed_values": {"channel 1": {"freq": 10, "amp": 0.1, "gate": False}},
        "register_readback": {"channel 1": {"freq": 10, "amp": 0.10068, "gate": False}},
    }
    raw = json.dumps(data, ensure_ascii=True, sort_keys=True, separators=(",", ":")).encode()
    data["snapshot_sha256"] = hashlib.sha256(raw).hexdigest()
    data["observed_at_utc"] = datetime.now(timezone.utc).isoformat()
    return data


class FakeGateway:
    def __init__(self, write_state="APPLIED"):
        self.write_state = write_state
        self.reads = []
        self.writes = []

    def read_blacs(self, action, device=None):
        self.reads.append((action, device))
        device_snapshot = snapshot()
        if action == "discover":
            value = {"queue": {"status": "Idle"}, "devices": [{
                "device": device_snapshot["device"], "channels": device_snapshot["channels"],
                "mode": "MANUAL", "error_present": False,
            }]}
        elif action == "queue.status":
            value = {"status": "Idle"}
        else:
            value = device_snapshot
        return {"schema": "rbbec-unified-result/1", "state": "OBSERVED", "action": action, "value": value}

    def call(self, target, request):
        self.writes.append((target, request))
        return {"schema": "rbbec-unified-result/1", "state": self.write_state, "action": request["action"],
                "request_id": request["request_id"], "value": {
                    "device": "TestDDS",
                    "after": {"channel 1": {"freq": 10, "amp": 0.1994, "gate": False}},
                    "evidence": "NOVATECH_QUE_REGISTER_READBACK",
                }}


def test_local_bridge_discovery_and_register_readback():
    gateway = FakeGateway()
    client = BlacsManualClient(mock=False, local_gateway=gateway)
    assert client.status()["backend"] == "local_gateway"
    rows = {row["name"]: row for row in client.discover_channels()}
    assert rows["TestDDS.channel 1.gate"]["type"] == "bool"
    assert rows["TestDDS.channel 1.freq"]["unit"] == "Hz"
    assert client.get_values()["TestDDS.channel 1.amp"] == {
        "value": 0.10068, "evidence": "device_register_readback",
    }
    assert gateway.writes == []


def test_prepare_sparse_change_reuses_snapshot_binding_without_io():
    gateway = FakeGateway()
    adapter = LocalBlacs(gateway)
    saved = snapshot()
    request = adapter.prepare_manual(saved, "channel 1", 0.2, subchannel="amp",
                                     approver="operator", instruction="Set channel 1 amplitude to 0.2")
    assert request["payload"] == {
        "device": "TestDDS", "expected_snapshot_sha256": saved["snapshot_sha256"],
        "changes": {"channel 1": {"kind": "DDS", "value": {"amp": 0.2}}},
    }
    assert request["expected_host_generation"] == saved["host_generation"]
    assert request["connection_sha256"] == saved["connection_sha256"]
    assert gateway.reads == gateway.writes == []


@pytest.mark.parametrize("value,subchannel", [(1.1, "amp"), (float("nan"), "freq"), (1, "gate"), (0.2, "alias")])
def test_prepare_refuses_wrong_units_range_or_subchannel(value, subchannel):
    with pytest.raises(ValueError):
        LocalBlacs.prepare_manual(snapshot(), "channel 1", value, subchannel=subchannel,
                                  approver="operator", instruction="approved")


def test_prepare_refuses_expired_or_altered_snapshot():
    saved = snapshot()
    saved["observed_at_utc"] = (datetime.now(timezone.utc) - timedelta(minutes=3)).isoformat()
    with pytest.raises(ValueError, match="expired"):
        LocalBlacs.prepare_manual(saved, "channel 1", {"amp": 0.2}, approver="operator", instruction="approved")
    saved = snapshot()
    saved["front_panel"]["channel 1"]["freq"] = 30
    with pytest.raises(ValueError, match="digest mismatch"):
        LocalBlacs.prepare_manual(saved, "channel 1", {"amp": 0.2}, approver="operator", instruction="approved")


def test_ui_edit_without_approval_cannot_dispatch():
    gateway = FakeGateway()
    client = BlacsManualClient(mock=False, local_gateway=gateway)
    with pytest.raises(ValueError, match="explicit operator approval"):
        client.set_manual("TestDDS.channel 1.amp", 0.2, program=True, device="TestDDS", channel="channel 1")
    assert gateway.reads == gateway.writes == []


def test_unknown_receipt_does_not_retry_other_names():
    gateway = FakeGateway(write_state="UNKNOWN")
    client = BlacsManualClient(mock=False, local_gateway=gateway)
    with pytest.raises(RuntimeError, match="UNKNOWN"):
        client.set_manual("TestDDS.channel 1.amp", 0.2, program=True, device="TestDDS", channel="channel 1",
                          approver="operator", instruction="approved", aliases=["other_device"])
    assert len(gateway.writes) == 1
    assert gateway.writes[0][1]["payload"]["device"] == "TestDDS"


def test_write_reports_quantized_readback():
    client = BlacsManualClient(mock=False, local_gateway=FakeGateway())
    result = client.set_manual("TestDDS.channel 1.amp", 0.2, program=True, device="TestDDS", channel="channel 1",
                               approver="operator", instruction="approved", unit="Arb")
    assert result["front_panel_value"] == 0.1994
    assert result["evidence"] == "NOVATECH_QUE_REGISTER_READBACK"


def test_panel_can_review_and_apply_the_same_exact_request():
    gateway = FakeGateway()
    client = BlacsManualClient(mock=False, local_gateway=gateway)
    assert client.uses_local_gateway
    request = client.prepare_local_manual("TestDDS.channel 1.amp", 0.2, device="TestDDS", channel="channel 1",
                                          approver="operator", instruction="Set amplitude to 0.2", unit="Arb")
    assert gateway.writes == []
    assert client.apply_local_manual(request)["front_panel_value"] == 0.1994
    assert gateway.writes == [("blacs", request)]


def test_mismatched_applied_receipt_is_unknown_without_resending(monkeypatch):
    gateway = FakeGateway()
    submit = gateway.call

    def corrupt(target, request):
        result = submit(target, request)
        result["value"]["device"] = "other"
        return result

    monkeypatch.setattr(gateway, "call", corrupt)
    adapter = LocalBlacs(gateway)
    request = adapter.prepare_manual(snapshot(), "channel 1", {"amp": 0.2},
                                     approver="operator", instruction="approved")
    assert adapter.apply_manual(request)["state"] == "UNKNOWN"
    assert gateway.writes == [("blacs", request)]


def test_legacy_transport_fault_stops_without_alias_replay(monkeypatch):
    monkeypatch.delenv("LABPILOT_CONTROL_MODE", raising=False)
    client = BlacsManualClient(mock=False)
    calls = []

    def fault(*args, **kwargs):
        calls.append(args)
        raise RuntimeError("Serial response not found after write")

    monkeypatch.setattr(client, "_post_json", fault)
    with pytest.raises(RuntimeError, match="Serial response not found"):
        client.set_manual("channel", 1.2, device="device", channel="ao0")
    assert len(calls) == 1


def test_mock_precedes_explicit_local_mode(monkeypatch):
    monkeypatch.setenv("LABPILOT_CONTROL_MODE", "local_gateway")
    assert BlacsManualClient(mock=True).local is None
    assert isinstance(BlacsManualClient(mock=False).local, LocalBlacs)
