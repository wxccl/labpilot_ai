from labpilot_ai.blacs_ctrl.manual_client import BlacsManualClient


def test_mock_blacs_client_status():
    client = BlacsManualClient(mock=True)
    assert "mock" in client.test()
    assert client.status()["service"] == "mock-blacs-bridge"


def test_mock_blacs_set_and_discover():
    client = BlacsManualClient(mock=True)
    result = client.set_manual("dummy", 0.1)
    assert result["ok"] is True
    channels = client.discover_channels()
    assert channels[0]["name"] == "dummy"
    assert client.get_values()["dummy"] == 0.1


def test_real_blacs_client_retries_device_channel_alias(monkeypatch):
    client = BlacsManualClient(mock=False)
    calls = []

    def fake_post(path, payload, timeout=10):
        calls.append(dict(payload))
        if payload["name"] in {"camera_trigger", "LabPilotVirtualDevice.camera_trigger"}:
            raise RuntimeError("BLACS manual channel not found: 'camera_trigger'")
        return {"ok": True, "name": payload["name"], "value": payload["value"]}

    monkeypatch.setattr(client, "_post_json", fake_post)
    result = client.set_manual(
        "camera_trigger",
        False,
        program=True,
        device="LabPilotVirtualDevice",
        channel="port0/line2",
        aliases=["camera trigger"],
    )
    assert result["ok"] is True
    assert result["name"] == "LabPilotVirtualDevice.port0/line2"
    assert [payload["name"] for payload in calls[:3]] == [
        "camera_trigger",
        "LabPilotVirtualDevice.camera_trigger",
        "LabPilotVirtualDevice.port0/line2",
    ]


def test_real_blacs_client_tries_device_labscript_name_without_connection_channel(monkeypatch):
    client = BlacsManualClient(mock=False)
    calls = []

    def fake_post(path, payload, timeout=10):
        calls.append(dict(payload))
        if payload["name"] != "LabPilotVirtualDevice.rf_switch":
            raise RuntimeError(f"BLACS manual channel not found: {payload['name']!r}")
        return {"ok": True, "name": payload["name"], "value": payload["value"]}

    monkeypatch.setattr(client, "_post_json", fake_post)
    result = client.set_manual(
        "rf_switch",
        True,
        device="LabPilotVirtualDevice",
        channel="port0/line0",
        unit="",
        aliases=["rf switch"],
    )
    assert result["ok"] is True
    device_name_payload = calls[-1]
    assert device_name_payload["name"] == "LabPilotVirtualDevice.rf_switch"
    assert "channel" not in device_name_payload
    assert "device" not in device_name_payload
    assert "unit" not in device_name_payload


def test_real_blacs_client_drops_wrong_device_for_bare_channel(monkeypatch):
    client = BlacsManualClient(mock=False)
    calls = []

    def fake_post(path, payload, timeout=10):
        calls.append(dict(payload))
        if payload["name"] != "port0/line0":
            raise RuntimeError(f"BLACS manual channel not found: {payload['name']!r}")
        return {"ok": True, "name": payload["name"], "value": payload["value"]}

    monkeypatch.setattr(client, "_post_json", fake_post)
    result = client.set_manual(
        "rf_switch",
        True,
        device="WrongDevice",
        channel="port0/line0",
        aliases=["port0/line0"],
    )
    assert result["ok"] is True
    bare_payload = calls[-1]
    assert bare_payload["name"] == "port0/line0"
    assert "device" not in bare_payload
