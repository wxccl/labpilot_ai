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


def test_legacy_client_never_posts_to_existing_older_bridges(monkeypatch):
    import pytest

    monkeypatch.delenv("LABPILOT_CONTROL_MODE", raising=False)
    client = BlacsManualClient(mock=False)
    with pytest.raises(PermissionError, match="read-only"):
        client.set_manual("channel", 1, program=True)
    with pytest.raises(ValueError):
        BlacsManualClient(mock=False, host="192.0.2.1")


def test_client_can_read_server_token_from_environment(monkeypatch):
    monkeypatch.setenv("LABPILOT_BLACS_TOKEN", "example-only")
    assert BlacsManualClient(mock=False)._headers()["X-LabPilot-Token"] == "example-only"
