from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import sys
from uuid import uuid4

import h5py
import pytest

from labpilot_ai.shot_analysis import LyseBatchAnalysis
from labpilot_ai.shot_analysis.worker import _copy_shot, _prepare_copy
from labpilot_ai.tasks import TaskService, TaskStore


CONFIG = "a" * 64


def fixture_manifest(tmp_path, count=2):
    batch_root = tmp_path / "batch"
    batch_root.mkdir()
    shots = [{"index": index, "path": str(batch_root / f"shot{index}.h5"), "sha256": f"{index:064x}"}
             for index in range(count)]
    return {"batch_id": uuid4().hex, "config_digest": CONFIG, "batch_root": str(batch_root),
            "expected_n_shots": count, "shots": shots}


def run(analyzer, manifest, **fields):
    return analyzer.analyze(manifest, **{"request_id": manifest["batch_id"], "config_digest": CONFIG,
                                        "expected_n_shots": manifest["expected_n_shots"], **fields})


@pytest.fixture
def analyzer(tmp_path, monkeypatch):
    routine = tmp_path / "analysis_signal.py"
    source = b"import lyse\nlyse.Run(lyse.path).save_result('signal', 1.0)\n"
    routine.write_bytes(source)
    engine = LyseBatchAnalysis(sys.executable, {
        "routine": str(routine), "routine_sha256": hashlib.sha256(source).hexdigest(), "shots_per_observation": 1,
        "quality_rules": [{"result": "signal", "type": "number", "min": 0.9, "max": 1.1}],
    }, base_dir=tmp_path)
    calls = []

    def analyze_shot(manifest, shot, binding):
        calls.append(binding)
        return {**binding, "status": "COMPLETE", "results": {"signal": 1.0},
                "sequence_id": "sequence_01", "lyse_version": "fixture"}

    monkeypatch.setattr(engine, "_run_shot", analyze_shot)
    return engine, calls


def test_analysis_progress_and_reports_are_bound_and_resumable(analyzer, tmp_path):
    engine, calls = analyzer
    manifest = fixture_manifest(tmp_path)
    first = run(engine, manifest)
    assert (first["analysis_state"], first["analyzed_count"], first["quality"]) == ("PENDING", 1, "UNKNOWN"), first.get("reason")
    second = run(engine, manifest, prior_manifest_sha256=first["manifest_sha256"])
    assert (second["analysis_state"], second["analyzed_count"], second["quality"]) == ("COMPLETE", 2, "PASS")
    directory = Path(second["report_dir"])
    report = json.loads((directory / "shot_000000.json").read_text(encoding="utf-8"))
    assert report["routine_sha256"] == engine.routine_sha256
    assert report["source_sha256"] == manifest["shots"][0]["sha256"]
    assert report["results"] == {"signal": 1.0}
    assert report["request_id"] == manifest["batch_id"]
    assert json.loads((directory / "manifest.json").read_text(encoding="utf-8")) == manifest
    assert run(engine, manifest)["quality"] == "PASS"
    assert len(calls) == 2


@pytest.mark.parametrize("case", ["outside", "duplicate", "wrong_request", "partial", "wrong_config"])
def test_refuses_unbound_or_malformed_manifests(analyzer, tmp_path, case):
    engine, calls = analyzer
    manifest = fixture_manifest(tmp_path)
    fields = {}
    if case == "outside":
        manifest["shots"][0]["path"] = str(tmp_path / "unrelated.h5")
    elif case == "duplicate":
        manifest["shots"][1]["index"] = 0
    elif case == "wrong_request":
        fields["request_id"] = uuid4().hex
    elif case == "partial":
        manifest["shots"].pop()
    else:
        manifest["config_digest"] = "b" * 64
    result = run(engine, manifest, **fields)
    assert result["analysis_state"] == "FAILED"
    assert result["quality"] == "UNKNOWN"
    assert not calls


def test_new_manifest_does_not_mix_previously_verified_reports(analyzer, tmp_path):
    engine, calls = analyzer
    manifest = fixture_manifest(tmp_path)
    first = run(engine, manifest)
    manifest["shots"][1]["sha256"] = "b" * 64
    result = run(engine, manifest, prior_manifest_sha256=first["manifest_sha256"])
    assert result["analysis_state"] == "FAILED"
    assert "manifest changed" in result["reason"]
    assert len(calls) == 1


def test_rejects_changed_report_and_preserves_input_manifest(analyzer, tmp_path):
    engine, calls = analyzer
    manifest = fixture_manifest(tmp_path, count=1)
    report = run(engine, manifest)
    path = Path(report["report_dir"]) / "shot_000000.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    data["results"]["signal"] = 99.0
    path.write_text(json.dumps(data), encoding="utf-8")
    result = run(engine, manifest)
    assert result["analysis_state"] == "FAILED"
    assert "provenance" in result["reason"]
    assert len(calls) == 1


@pytest.mark.parametrize("value,analysis_state,quality", [
    (True, "FAILED", "UNKNOWN"), (float("nan"), "FAILED", "UNKNOWN"),
    (0.2, "COMPLETE", "FAIL"), (0.9, "COMPLETE", "PASS"),
])
def test_typed_inclusive_quality_gate(analyzer, tmp_path, monkeypatch, value, analysis_state, quality):
    engine, _ = analyzer
    original = engine._run_shot

    def result(*args):
        return {**original(*args), "results": {"signal": value}}

    monkeypatch.setattr(engine, "_run_shot", result)
    report = run(engine, fixture_manifest(tmp_path, count=1))
    assert (report["analysis_state"], report["quality"]) == (analysis_state, quality)


def test_worker_checks_hdf5_identity_and_removes_old_results_from_copy_only(tmp_path):
    manifest = fixture_manifest(tmp_path, count=1)
    shot = manifest["shots"][0]
    original = Path(shot["path"])
    with h5py.File(original, "w") as file:
        file.attrs.update({"sequence_id": "sequence_01", "run number": 0, "n_runs": 1})
        file.create_group("results/analysis_signal").attrs["signal"] = 1.0
    shot["sha256"] = hashlib.sha256(original.read_bytes()).hexdigest()
    staged = tmp_path / "staged.h5"
    params = {"shot": shot, "batch_root": manifest["batch_root"], "max_shot_bytes": 1024 * 1024,
              "expected_n_shots": 1, "binding": {"result_group": "analysis_signal"}}
    _copy_shot(h5py, params, staged)
    assert _prepare_copy(h5py, params, staged) == "sequence_01"
    with h5py.File(staged, "r") as file:
        assert "analysis_signal" not in file["results"]
    assert hashlib.sha256(original.read_bytes()).hexdigest() == shot["sha256"]
    with pytest.raises(ValueError, match="index or count"):
        _prepare_copy(h5py, {**params, "expected_n_shots": 2}, staged)
    with pytest.raises(ValueError, match="differ"):
        _copy_shot(h5py, {**params, "shot": {**shot, "sha256": "b" * 64}}, tmp_path / "wrong.h5")


def test_native_task_waits_for_quality_before_completing(analyzer, tmp_path):
    engine, calls = analyzer
    manifest = fixture_manifest(tmp_path)
    request_id = manifest["batch_id"]
    store = TaskStore(tmp_path / "tasks.sqlite3")
    task = store.submit({"kind": "batch", "action": "engage", "request_id": request_id,
                         "expected_config_digest": CONFIG, "expected_shots": 2, "params": {"target": "runmanager"}})
    store.approve(task["task_id"], task["plan_digest"], "owner", datetime.now(timezone.utc) + timedelta(minutes=5))

    class Host:
        complete = False

        def execute(self, params):
            return {"schema": "labpilot-host-result/1", "state": "APPLIED", "request_id": request_id}

        def observe(self, params):
            evidence = {"config_digest": CONFIG, "compiled_count": 2, "queued_count": 2, "executed_count": 2}
            if self.complete:
                evidence.update(batch_execution_complete=True, shot_manifest=manifest)
            else:
                evidence.update(terminal="COMPLETED", quality="PASS")
            return {"schema": "labpilot-host-result/1", "state": "OBSERVED", "request_id": request_id,
                    "value": {"evidence": evidence}}

    host = Host()
    service = TaskService(store, host, analysis=engine)
    assert service.run_next()["status"] == "OBSERVING"
    assert service.observe(task["task_id"])["status"] == "OBSERVING"
    assert not calls
    host.complete = True
    pending = service.observe(task["task_id"])
    assert pending["status"] == "OBSERVING"
    assert pending["evidence"]["analyzed_count"] == 1
    finished = service.observe(task["task_id"])
    assert finished["status"] == "COMPLETED"
    assert finished["evidence"]["batch_execution_complete"] is True
    assert finished["evidence"]["quality"] == "PASS"
    assert len(calls) == 2
