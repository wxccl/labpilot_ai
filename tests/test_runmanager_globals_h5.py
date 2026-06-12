from labpilot_ai.bootstrap_labscript import install_h5_lock
from labpilot_ai.runmanager_ctrl.globals_h5 import (
    read_runmanager_globals_h5,
    registry_from_globals_h5,
    write_runmanager_globals_h5,
)
from labpilot_ai.runmanager_ctrl.write_router import write_runmanager_globals
from labpilot_ai.safety.validator import SafetyValidator, normalize_bool


def test_runmanager_globals_h5_reader_and_registry_merge(tmp_path):
    install_h5_lock(verbose=False)
    import h5py

    path = tmp_path / "globals.h5"
    with h5py.File(path, "w") as handle:
        group = handle.create_group("globals").create_group("virtual_globals")
        group.attrs["duration_tof_ms"] = "17.0"
        group.attrs["do_Rabi"] = "False"
        group.attrs["ct_bias_voltage_connection"] = "'ao0'"
        group.attrs["scan_values"] = "[1, 2, 3]"
        units = group.create_group("units")
        units.attrs["duration_tof_ms"] = "ms"
        notes = group.create_group("notes")
        notes.attrs["duration_tof_ms"] = "Time of flight"
        expansion = group.create_group("expansion")
        expansion.attrs["scan_values"] = "outer"

    snapshot = read_runmanager_globals_h5(path)

    assert snapshot.values["duration_tof_ms"] == 17.0
    assert snapshot.values["do_Rabi"] is False
    assert snapshot.values["ct_bias_voltage_connection"] == "ao0"
    assert snapshot.values["scan_values"] == [1, 2, 3]
    assert snapshot.units["duration_tof_ms"] == "ms"
    assert snapshot.notes["duration_tof_ms"] == "Time of flight"
    assert snapshot.report["count"] == 4

    merged = registry_from_globals_h5(
        snapshot,
        {"duration_tof_ms": {"type": "float", "unit": "custom", "description": "human edited"}},
    )
    assert merged["duration_tof_ms"]["unit"] == "custom"
    assert merged["duration_tof_ms"]["description"] == "human edited"
    assert merged["do_Rabi"]["type"] == "bool"
    assert merged["scan_values"]["type"] == "float_array"
    assert merged["scan_values"]["expansion"] == "outer"

    safe = SafetyValidator(merged).validate_command(
        {"actions": [{"type": "set_global", "name": "duration_tof_ms", "value": "18.5"}]}
    )
    assert safe["globals"]["duration_tof_ms"] == 18.5


def test_chinese_bool_terms_are_supported():
    for value in ["打开", "开启", "启用", "是", "真"]:
        assert normalize_bool(value) is True
    for value in ["关闭", "关", "禁用", "否", "假"]:
        assert normalize_bool(value) is False


def test_runmanager_globals_h5_direct_writer(tmp_path):
    install_h5_lock(verbose=False)
    import h5py

    path = tmp_path / "globals.h5"
    with h5py.File(path, "w") as handle:
        group = handle.create_group("globals").create_group("virtual_globals")
        group.attrs["ct_probe_voltage_min_V"] = "0.0"
        group.attrs["do_camera"] = "True"
        group.create_group("units")
        group.create_group("notes")
        group.create_group("expansion")

    report = write_runmanager_globals_h5(path, {"ct_probe_voltage_min_V": 1.0, "do_camera": False, "missing": 2})
    assert set(report.written) == {"ct_probe_voltage_min_V", "do_camera"}
    assert set(report.missing) == {"missing"}

    snapshot = read_runmanager_globals_h5(path)
    assert snapshot.values["ct_probe_voltage_min_V"] == 1.0
    assert snapshot.values["do_camera"] is False


class _FakeRunmanager:
    def __init__(self, current):
        self.current = dict(current)
        self.writes = []

    def get_globals(self):
        return dict(self.current)

    def set_globals(self, values):
        self.writes.append(dict(values))
        self.current.update(values)


def test_runmanager_write_router_remote_then_h5(tmp_path):
    install_h5_lock(verbose=False)
    import h5py

    path = tmp_path / "globals.h5"
    with h5py.File(path, "w") as handle:
        group = handle.create_group("globals").create_group("virtual_globals")
        group.attrs["do_camera"] = "True"
        group.attrs["ct_probe_voltage_min_V"] = "0.0"
        group.create_group("units")
        group.create_group("notes")
        group.create_group("expansion")

    backend = _FakeRunmanager({"do_camera": True})
    report = write_runmanager_globals(
        backend,
        {"do_camera": False, "ct_probe_voltage_min_V": 1.0},
        globals_h5_path=path,
        direct_h5_write=True,
    )

    assert report.remote_written == {"do_camera": False}
    assert report.h5_written == {"ct_probe_voltage_min_V": 1.0}
    assert not report.missing
    assert backend.writes == [{"do_camera": False}]
    assert read_runmanager_globals_h5(path).values["ct_probe_voltage_min_V"] == 1.0
