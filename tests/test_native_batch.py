from hashlib import sha256
from pathlib import Path
from queue import Queue
from types import SimpleNamespace
import json

import h5py
import pytest

from labpilot_ai.host.adapters import Runmanager
from labpilot_ai.host.managed_runmanager import NativeView, manage_engage
from labpilot_ai.host import native_batch
from labpilot_ai.host.native_batch import NativeBatches
from labpilot_ai.host.protocol import Journal, Profile, Refused


class Editor:
    def __init__(self, text, callback=lambda _: None):
        self.value = text
        self.callback = callback

    def text(self):
        return self.value

    def setText(self, value):
        self.value = value
        self.callback(value)


class Button:
    enabled = False

    def setEnabled(self, enabled):
        self.enabled = enabled

    def isEnabled(self):
        return self.enabled


class FakeApp:
    n_shots = 2

    def __init__(self, sequence, original):
        self.sequence = sequence
        self.original = original
        self.non_default_folder = False
        self.compile_queue = Queue()
        self.ui = SimpleNamespace(lineEdit_shot_output_folder=Editor(str(original), self._changed),
                                  lineEdit_BLACS_hostname=Editor("localhost"), pushButton_abort=Button())

    def _changed(self, path):
        self.non_default_folder = path != str(self.original)

    def get_default_output_folder(self):
        return str(self.original)

    def on_reset_shot_output_folder_clicked(self, _):
        self.ui.lineEdit_shot_output_folder.setText(self.get_default_output_folder())

    def on_engage_clicked(self):
        output = Path(self.ui.lineEdit_shot_output_folder.text())

        def generated():
            for index in range(self.n_shots):
                shot = output / f"shot_{index}.h5"
                with h5py.File(shot, "w") as h5:
                    h5.attrs.update({"script_basename": self.sequence.stem, "sequence_id": "native-sequence",
                                     "sequence_date": "2026-11-11", "sequence_index": 3,
                                     "run number": index, "n_runs": self.n_shots})
                    h5.create_group("globals").create_group("example").attrs["dummy"] = "[1, 2]"
                yield str(shot)

        self.ui.pushButton_abort.setEnabled(True)
        self.compile_queue.put([str(self.sequence), generated(), self.n_shots, True, "localhost", False])


class FakeRemote:
    def __init__(self, app):
        self.app = app

    def handle_get_globals(self, raw=False):
        return {"dummy": "[1, 2]" if raw else [1, 2]}

    def handle_get_labscript_file(self):
        return str(self.app.sequence)

    def handle_get_shot_output_folder(self):
        return self.app.ui.lineEdit_shot_output_folder.text()

    def handle_get_run_shots(self):
        return True

    def handle_get_view_shots(self):
        return False

    def handle_get_shuffle(self):
        return False

    def handle_error_in_globals(self):
        return False


@pytest.fixture
def managed(tmp_path, monkeypatch):
    monkeypatch.setattr(native_batch, "_h5", lambda: h5py)
    (tmp_path / "batches").mkdir()
    profile_path = tmp_path / "profile.json"
    profile_path.write_text(json.dumps({"host": {"state_db": "host.db", "runmanager": {
        "enabled": True, "allow": ["engage"], "sequence_root": ".", "output_root": ".", "batch_root": "batches",
    }}}), encoding="utf-8")
    profile = Profile(profile_path)
    sequence = tmp_path / "sequence.py"
    sequence.write_text("# sequence source\n", encoding="utf-8")
    app = FakeApp(sequence, tmp_path / "original")
    server = FakeRemote(app)
    before = Runmanager(profile, NativeView(server)).snapshot({})
    params = {"target": "runmanager", "action": "engage", "request_id": "test-batch",
              "expected_n_shots": 2, "expected_snapshot_sha256": before["snapshot_sha256"]}
    journal = Journal(profile.state_db)
    journal.reserve(params["request_id"], "runmanager", params)
    return profile, server, params


def compile_shot(path, sequence):
    with h5py.File(path, "r+") as h5:
        script = h5.create_dataset("script", data=sequence.read_text())
        script.attrs["name"] = sequence.name
        h5.create_group("devices")
        h5.create_dataset("connection table", data=[])


def complete_shot(path):
    with h5py.File(path, "r+") as h5:
        h5.attrs["run time"] = "20261111T010203.123456+0800"
        h5.create_group("data")


def test_native_managed_output_is_restored_before_compile_payload(managed):
    profile, server, params = managed
    accepted = manage_engage(server, profile, params)
    assert accepted["configuration_restored"] is True
    assert server.app.ui.lineEdit_shot_output_folder.text() == server.app.get_default_output_folder()
    _, outputs, count, *_ = server.app.compile_queue.get_nowait()
    assert count == 2
    batch = NativeBatches(profile)
    paths = list(outputs)
    assert len(paths) == 2
    assert all(Path(name).parent == Path(accepted["batch_root"]) for name in paths)
    assert batch.observe(params["request_id"])["executed_count"] == 0
    for path in paths:
        compile_shot(path, server.app.sequence)
        batch.record(path, "compiled")
        batch.record(path, "queued")
        complete_shot(path)
        batch.record(path, "executed")
    evidence = batch.observe(params["request_id"])
    assert evidence["batch_execution_complete"] is True
    assert evidence["executed_count"] == 2
    assert "terminal" not in evidence
    manifest = evidence["shot_manifest"]
    assert manifest["config_digest"] == params["expected_snapshot_sha256"]
    assert [shot["sha256"] for shot in manifest["shots"]] == [sha256(Path(path).read_bytes()).hexdigest() for path in paths]
    with pytest.raises(Refused, match="already reserved"):
        manage_engage(server, profile, params)
    assert server.app.compile_queue.empty()


def test_restore_failure_never_enqueues_native_payload(managed, monkeypatch):
    profile, server, params = managed
    monkeypatch.setattr(server.app, "on_reset_shot_output_folder_clicked", lambda _: None)
    with pytest.raises(RuntimeError, match="restoration"):
        manage_engage(server, profile, params)
    assert server.app.compile_queue.empty()
    evidence = NativeBatches(profile).observe(params["request_id"])
    assert evidence["native_batch_phase"] == "CAPTURE_OR_RESTORE_FAILED"
    assert "batch_execution_complete" not in evidence


def test_repeated_or_requeued_shot_blocks_completion(managed):
    profile, server, params = managed
    manage_engage(server, profile, params)
    _, outputs, *_ = server.app.compile_queue.get_nowait()
    first, _ = list(outputs)
    batch = NativeBatches(profile)
    compile_shot(first, server.app.sequence)
    batch.record(first, "compiled")
    batch.record(first, "queued")
    with pytest.raises(ValueError, match="Duplicate"):
        batch.record(first, "queued")
    assert "Duplicate" in batch.observe(params["request_id"])["batch_ambiguity"]
    assert "shot_manifest" not in batch.observe(params["request_id"])


def test_completed_h5_without_bound_callback_cannot_close_batch(managed):
    profile, server, params = managed
    manage_engage(server, profile, params)
    _, outputs, *_ = server.app.compile_queue.get_nowait()
    batch = NativeBatches(profile)
    for path in outputs:
        compile_shot(path, server.app.sequence)
        complete_shot(path)
    evidence = batch.observe(params["request_id"])
    assert evidence["executed_count"] == 0
    assert "shot_manifest" not in evidence
