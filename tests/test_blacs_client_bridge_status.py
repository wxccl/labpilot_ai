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
