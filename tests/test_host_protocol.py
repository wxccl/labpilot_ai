import json
from hashlib import sha256
from pathlib import Path
import subprocess
import sys

import pytest

from labpilot_ai.host import install
from labpilot_ai.host.adapters import Runmanager
from labpilot_ai.host.protocol import Profile, Refused


SCRIPT = Path(__file__).resolve().parents[1] / "labpilot_ai" / "host" / "__main__.py"


@pytest.fixture
def simulated(tmp_path):
    path = tmp_path / "test profile.json"
    path.write_text(json.dumps({"schema_version": 1, "simulate": True, "host": {"state_db": "sim.db"}}),
                    encoding="utf-8")

    def request(method, **params):
        envelope = {"method": method, "params": params}
        proc = subprocess.run([sys.executable, str(SCRIPT), "--profile", str(path)], cwd=tmp_path,
                              input=json.dumps(envelope), text=True, capture_output=True, timeout=8, check=True)
        line, = [line for line in proc.stdout.splitlines() if line.startswith("LABPILOT_HOST_JSON:")]
        return json.loads(line.split(":", 1)[1])

    return request


def test_simulation_persists_cross_process_and_observes_exact_batch(simulated):
    discovery = simulated("discover")
    assert discovery["value"]["targets"]["runmanager"]["available"] is True
    before = simulated("snapshot", target="runmanager")["value"]
    assert before["n_shots"] == 1
    changes = {"target": "runmanager", "action": "set_globals", "request_id": "set-001",
               "values": {"dummy": [1, 2, 3]}, "expected_snapshot_sha256": before["snapshot_sha256"]}
    applied = simulated("execute", **changes)
    assert applied["state"] == "APPLIED"
    assert simulated("execute", **changes) == applied
    assert simulated("execute", **{**changes, "values": {"dummy": 9}})["state"] == "REFUSED"
    after = simulated("snapshot", target="runmanager")["value"]
    assert after == applied["value"]["after"]
    assert after["n_shots"] == 3
    engage = {"target": "runmanager", "action": "engage", "expected_n_shots": 3,
              "expected_snapshot_sha256": after["snapshot_sha256"], "request_id": "batch-001"}
    assert simulated("execute", **engage)["state"] == "APPLIED"
    observed = simulated("observe", target="runmanager", request_id="batch-001")
    assert observed["value"]["evidence"] == {
        "simulated": True, "config_digest": after["snapshot_sha256"], "compiled_count": 3,
        "queued_count": 3, "executed_count": 3, "analyzed_count": 3, "quality": "UNKNOWN", "terminal": "COMPLETED",
    }


def test_simulation_rejects_stale_or_untyped_blacs_changes(simulated):
    before = simulated("snapshot", target="blacs", device="sim_daq")["value"]
    params = {"target": "blacs", "action": "set_manual", "device": "sim_daq",
              "expected_snapshot_sha256": before["snapshot_sha256"]}
    rejected = simulated("execute", request_id="bad-bool", values={"port0/line0": 1}, **params)
    assert rejected["state"] == "REFUSED"
    assert simulated("execute", request_id="valid", values={"port0/line0": True}, **params)["state"] == "APPLIED"
    stale = simulated("execute", request_id="stale", values={"ao0": 1.25}, **params)
    assert stale["state"] == "REFUSED"
    assert simulated("snapshot", target="blacs", device="sim_daq")["value"]["values"] == {
        "ao0": 0.0, "port0/line0": True,
    }


@pytest.mark.parametrize("raw", [b"[main]\r\nkey=1", b"[BLACS/plugins]\r\nold = True\r\n[main]\r\nkey=1\r\n"])
def test_installer_preview_apply_idempotency_and_exact_uninstall(tmp_path, monkeypatch, raw):
    config = tmp_path / "labconfig.ini"
    config.write_bytes(raw)
    profile_path = tmp_path / "native.json"
    profile_path.write_text('{"host":{"blacs":{"enabled":true}}}', encoding="utf-8")
    profile = Profile(profile_path)
    plugins = tmp_path / "blacs" / "plugins"
    plugins.mkdir(parents=True)
    shim = plugins / "labpilot_host" / "__init__.py"
    monkeypatch.setattr(install, "_shim_path", lambda: shim)

    assert install.configure(profile, config)["applied"] is False
    assert config.read_bytes() == raw and not shim.exists()
    assert install.configure(profile, config, apply=True)["applied"] is True
    assert shim.read_bytes() == install.SHIM
    assert install.doctor(profile, config)["labconfig_blacs_plugin_enabled"] is True
    assert install.configure(profile, config, apply=True)["changes_labconfig"] is False
    install.configure(profile, config, apply=True, uninstall=True)
    assert config.read_bytes() == raw and not shim.exists()


class FakeRunmanager:
    def __init__(self, directory):
        self.sequence = directory / "test.py"
        self.sequence.write_text("# mock sequence", encoding="utf-8")
        self.output = directory
        self.engage_count = 0
        self.values = {"dummy": 0, "other": 1}

    def get_globals(self, raw=False):
        return {name: repr(value) + " # preserved comment" for name, value in self.values.items()} if raw else dict(self.values)

    def set_globals(self, values, raw=False):
        assert raw is False
        self.values.update(values)

    def get_labscript_file(self):
        return str(self.sequence)

    def get_shot_output_folder(self):
        return str(self.output)

    def n_shots(self):
        return 1

    def get_run_shots(self):
        return True

    def get_view_shots(self):
        return False

    def get_shuffle(self):
        return False

    def error_in_globals(self):
        return False

    def engage(self):
        self.engage_count += 1


def test_official_runmanager_api_shape_and_ack_boundary(tmp_path):
    path = tmp_path / "profile.json"
    path.write_text(json.dumps({"host": {"runmanager": {"enabled": True,
                                "allow": ["set_globals", "engage"], "sequence_root": ".", "output_root": "."}}}),
                    encoding="utf-8")
    fake = FakeRunmanager(tmp_path)
    rm = Runmanager(Profile(path), client=fake)
    before = rm.snapshot({})
    result = rm.execute({"action": "set_globals", "expected_snapshot_sha256": before["snapshot_sha256"],
                         "values": {"dummy": "1 + 1"}})
    assert result["after"]["globals_raw"]["dummy"] == "'1 + 1' # preserved comment"
    fresh = result["after"]["snapshot_sha256"]
    with pytest.raises(Refused, match="positive shot count"):
        rm.execute({"action": "engage", "expected_snapshot_sha256": fresh, "expected_n_shots": 2})
    assert fake.engage_count == 0
    evidence = rm.execute({"action": "engage", "expected_snapshot_sha256": fresh,
                           "expected_n_shots": 1})["evidence"]
    assert evidence == {"config_digest": fresh, "native_acknowledged": True, "physical_execution_verified": False}
    assert fake.engage_count == 1
    fake.engage = lambda: RuntimeError("Remote handler refused")
    with pytest.raises(RuntimeError, match="returned RuntimeError"):
        rm.execute({"action": "engage", "expected_snapshot_sha256": fresh, "expected_n_shots": 1})


def test_profile_pin_refuses_bytes_changed_before_subprocess(tmp_path):
    profile = tmp_path / "profile.json"
    original = b'{"schema_version":1,"simulate":true}'
    profile.write_bytes(original + b"\n")
    payload = '{"method":"discover","params":{}}'
    proc = subprocess.run([sys.executable, str(SCRIPT), "--profile", str(profile),
                           "--expect-profile-sha256", sha256(original).hexdigest()],
                          input=payload, text=True, capture_output=True, check=True, timeout=8)
    assert json.loads(proc.stdout.split(":", 1)[1])["state"] == "REFUSED"
