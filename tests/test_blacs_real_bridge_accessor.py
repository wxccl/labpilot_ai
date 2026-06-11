from labpilot_ai.blacs_bridge.accessor import BLACSAccessor


class FakeOutput:
    def __init__(self, value=0.0, name="chan", unit="V"):
        self._current_value = value
        self._connection_name = name
        self._base_unit = unit
        self._current_units = unit
        self._limits = [-10.0, 10.0]
        self._locked = False
        self.calls = []

    @property
    def value(self):
        return self._current_value

    def set_value(self, value, unit=None, program=True):
        self.calls.append((value, unit, program))
        self._current_value = value


class FakeTab:
    device_name = "FakeDevice"
    mode = 1
    state = "idle"

    def __init__(self):
        self._AO = {"ao0": FakeOutput(0.1, "BiasAO")}
        self._DO = {"port0/line0": FakeOutput(False, "ShutterDO", "")}
        self._DDS = {}
        self._EO = {}
        self._image = {}
        self.programmed = False

    def get_front_panel_values(self):
        return {"ao0": self._AO["ao0"].value, "port0/line0": self._DO["port0/line0"].value}

    def get_channel(self, channel):
        return self._AO.get(channel) or self._DO.get(channel)

    def program_device(self):
        self.programmed = True


class FakeManager:
    def __init__(self):
        self.tablist = {"FakeDevice": FakeTab()}


class FakeQueue:
    def __init__(self):
        self.BLACS = FakeManager()


def test_discover_and_values():
    accessor = BLACSAccessor({"experiment_queue": FakeQueue()})
    channels = accessor.discover_channels()
    names = {ch["name"] for ch in channels}
    assert "FakeDevice.ao0" in names
    assert "FakeDevice.port0/line0" in names
    values = accessor.values()
    assert values["FakeDevice.ao0"] == 0.1
    assert values["FakeDevice.port0/line0"] is False


def test_write_manual_requires_allow_write():
    accessor = BLACSAccessor({"experiment_queue": FakeQueue()})
    result = accessor.set_manual({"name": "FakeDevice.ao0", "value": 0.2, "program": True}, allow_write=False)
    assert result["ok"] is False


def test_write_manual_enabled():
    accessor = BLACSAccessor({"experiment_queue": FakeQueue()})
    result = accessor.set_manual({"name": "FakeDevice.ao0", "value": 0.2, "program": True}, allow_write=True)
    assert result["ok"] is True
    assert result["front_panel_value"] == 0.2
