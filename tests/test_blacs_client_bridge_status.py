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
        calls.append(payload["name"])
        if payload["name"] == "camera_trigger":
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
    assert calls[:2] == ["camera_trigger", "LabPilotVirtualDevice.port0/line2"]
