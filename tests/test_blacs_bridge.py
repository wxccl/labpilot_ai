from labpilot_ai.blacs_ctrl.manual_client import BlacsManualClient


def test_blacs_mock_readonly_discovery_and_values():
    client = BlacsManualClient(mock=True)
    client.set_manual("ao0", 1.5)
    client.set_manual("shutter", True)

    channels = {item["name"]: item for item in client.discover_channels()}
    assert channels["ao0"]["kind"] == "manual"
    assert channels["ao0"]["current_value"] == 1.5
    assert channels["shutter"]["type"] == "bool"

    values = client.get_values()
    assert values["ao0"] == 1.5
    assert values["shutter"] is True
