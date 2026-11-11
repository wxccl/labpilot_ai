import json
from pathlib import Path
import subprocess
import sys

import pytest

from labpilot_ai.local_control.transport import LocalGateway


REQUEST_ID = "a" * 32


@pytest.fixture
def fake_gateway(tmp_path):
    gateway_path = tmp_path / "gateway with spaces.py"
    gateway_path.write_text(
        '''from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys
import time

envelope = json.load(sys.stdin)
request = envelope["request"]
with Path("calls.jsonl").open("a", encoding="utf-8") as calls:
    calls.write(json.dumps(envelope) + "\\n")
payload = request.get("payload", {})
mode = payload.get("mode")
if mode == "timeout":
    time.sleep(30)
if mode == "duplicate":
    print('RBBEC_JSON:{"state":"APPLIED","state":"OBSERVED"}')
    sys.exit(0)
if mode == "ambiguous":
    print('RBBEC_JSON:{"state":"UNKNOWN"}')
    sys.exit(0)
device = payload.get("device")
action = request["action"]
state = "APPLIED"
value = {"device": device, "after": {"ao0": 1.25}}
if action == "discover":
    state = "OBSERVED"
    value = {"devices": []}
elif action == "snapshot":
    state = "OBSERVED"
    value = {
        "host_generation": "a" * 32,
        "connection_sha256": "c" * 64,
        "device": device,
        "connection": "Dev1",
        "driver_class": "FakeNI",
        "family": "NI_DAQMX_OUTPUT",
        "channels": {"ao0": {"kind": "AO", "units": "V", "limits": [-10, 10]}},
        "front_panel": {"ao0": 0.0},
        "last_programmed_values": {"ao0": 0.0},
        "register_readback": None,
    }
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    value["snapshot_sha256"] = hashlib.sha256(encoded).hexdigest()
    value["observed_at_utc"] = datetime.now(timezone.utc).isoformat()
result = {
    "schema": "rbbec-unified-result/1",
    "request_id": request.get("request_id"),
    "action": action,
    "state": state,
    "value": value,
}
if mode == "wrong_id":
    result["request_id"] = "b" * 32
print("unstructured gateway log")
print("RBBEC_JSON:" + json.dumps(result))
''',
        encoding="utf-8",
    )
    return LocalGateway(gateway_path, sys.executable, tmp_path / "local receipts", timeout=5)


def write_request(**payload):
    return {
        "schema": "rbbec-unified/1",
        "request_id": REQUEST_ID,
        "action": "manual.apply",
        "payload": {"device": "simulated", "changes": {"ao0": {"kind": "AO", "value": 1.25}}, **payload},
    }


def invocations(gateway):
    trace = gateway.gateway_path.parent / "calls.jsonl"
    return [json.loads(line) for line in trace.read_text(encoding="utf-8").splitlines()]


def test_read_uses_process_without_creating_receipts(fake_gateway):
    result = fake_gateway.read_blacs("discover")

    assert result["state"] == "OBSERVED"
    assert result["value"] == {"devices": []}
    assert not fake_gateway.receipts.exists()
    observed, = invocations(fake_gateway)
    assert observed["target"] == "blacs"
    assert observed["request"]["action"] == "discover"
    assert observed["request"]["request_id"] == result["request_id"]


def test_write_once_caches_result_and_rejects_changed_payload(fake_gateway):
    request = write_request()

    result = fake_gateway.call("blacs", request)
    assert result["state"] == "APPLIED"
    assert fake_gateway.call("blacs", request) == result
    with pytest.raises(ValueError, match="different content"):
        fake_gateway.call("blacs", write_request(device="another"))

    assert invocations(fake_gateway) == [{"target": "blacs", "request": request}]
    assert (fake_gateway.receipts / f"{REQUEST_ID}.intent.json").is_file()
    result_path = fake_gateway.receipts / f"{REQUEST_ID}.result.json"
    assert json.loads(result_path.read_text(encoding="utf-8")) == result


def test_timeout_is_durable_and_never_replayed(fake_gateway):
    fake_gateway.timeout = 1.5
    request = write_request(mode="timeout")

    result = fake_gateway.call("blacs", request)

    assert result["state"] == "UNKNOWN"
    assert result["request_id"] == REQUEST_ID
    assert result["no_automatic_retry"] is True
    assert fake_gateway.call("blacs", request) == result
    assert len(invocations(fake_gateway)) == 1


@pytest.mark.parametrize("mode", ["duplicate", "wrong_id", "ambiguous"])
def test_untrusted_response_stays_unknown_without_replay(fake_gateway, mode):
    request = write_request(mode=mode)

    result = fake_gateway.call("blacs", request)

    assert result["state"] == "UNKNOWN"
    assert result["request_id"] == REQUEST_ID
    assert fake_gateway.call("blacs", request) == result
    assert len(invocations(fake_gateway)) == 1


@pytest.mark.parametrize(
    ("filename_suffix", "replacement"),
    [
        ("intent", "{"),
        ("intent", "[]"),
        ("result", "{"),
        ("result", "null"),
        ("result", '{"state":"APPLIED","request_id":"b"}'),
    ],
)
def test_damaged_receipt_is_unknown_without_replay(fake_gateway, filename_suffix, replacement):
    request = write_request()
    assert fake_gateway.call("blacs", request)["state"] == "APPLIED"
    damaged = fake_gateway.receipts / f"{REQUEST_ID}.{filename_suffix}.json"
    damaged.write_text(replacement, encoding="utf-8")

    result = fake_gateway.call("blacs", request)

    assert result["state"] == "UNKNOWN"
    assert result["request_id"] == REQUEST_ID
    assert result["no_automatic_retry"] is True
    assert len(invocations(fake_gateway)) == 1


def test_cli_prepares_then_applies_exact_plan_once(fake_gateway, tmp_path, monkeypatch):
    monkeypatch.setenv("LABPILOT_LOCAL_GATEWAY", str(fake_gateway.gateway_path))
    monkeypatch.setenv("LABPILOT_LABSCRIPT_PYTHON", str(fake_gateway.python_path))
    monkeypatch.setenv("LABPILOT_CONTROL_RECEIPTS", str(fake_gateway.receipts))
    monkeypatch.setenv("LABPILOT_CONTROL_MODE", "local_gateway")
    plan = tmp_path / "reviewed plan.json"
    cli = [sys.executable, "-m", "labpilot_ai.local_control.cli"]
    repo = Path(__file__).resolve().parents[1]

    prepared = subprocess.run([*cli, "prepare-manual", "simulated", "ao0", "1.25",
                               "--approver", "测试人员", "--instruction", "模拟通道设为 1.25 V",
                               "--output", str(plan)], cwd=repo, capture_output=True, timeout=10, check=True)
    assert json.loads(prepared.stdout)["state"] == "PREPARED"
    envelope = json.loads(plan.read_text(encoding="utf-8"))
    request = envelope["request"]
    assert request["approval_context"]["approver"] == "测试人员"
    assert request["payload"]["changes"] == {"ao0": {"kind": "AO", "value": 1.25}}
    snapshot_call, = invocations(fake_gateway)
    assert snapshot_call["request"]["action"] == "snapshot"
    assert not fake_gateway.receipts.exists()

    first = subprocess.run([*cli, "apply", str(plan)], cwd=repo, capture_output=True, timeout=10, check=True)
    second = subprocess.run([*cli, "apply", str(plan)], cwd=repo, capture_output=True, timeout=10, check=True)

    assert json.loads(first.stdout)["state"] == "APPLIED"
    assert json.loads(second.stdout) == json.loads(first.stdout)
    assert invocations(fake_gateway) == [snapshot_call, envelope]
