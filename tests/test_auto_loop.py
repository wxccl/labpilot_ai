import os

import pandas as pd
import pytest

from labpilot_ai.optimizer.auto_loop import (
    AutoLoopConfig,
    SupervisedOptimizerAutoLoop,
    find_new_or_updated_h5,
    h5_snapshot,
    wait_for_new_or_updated_h5,
)
from labpilot_ai.optimizer.lyse_feedback import tell_optimizer_from_dataframe
from labpilot_ai.runmanager_ctrl.backend import RunmanagerBackend
from labpilot_ai.safety.validator import SafetyValidator
from labpilot_ai.storage.database import LabPilotDatabase


def test_auto_loop_config_defaults_from_spec():
    cfg = AutoLoopConfig.from_spec({"objective": "signal", "parameters": {}})
    assert cfg.run_checked_modules is True
    assert cfg.poll_interval_s == 1.0
    assert cfg.h5_timeout_s == 120.0
    assert cfg.session_id


def test_h5_wait_detects_new_and_updated_file(tmp_path):
    before = h5_snapshot(tmp_path)
    first = tmp_path / "shot_1.h5"
    first.write_text("new", encoding="utf-8")
    assert find_new_or_updated_h5(tmp_path, before) == first.resolve()

    before = h5_snapshot(tmp_path)
    os.utime(first, (before[str(first.resolve())] + 5, before[str(first.resolve())] + 5))
    assert wait_for_new_or_updated_h5(tmp_path, before, timeout_s=0.2, poll_interval_s=0.05) == first.resolve()


def test_h5_wait_timeout_on_empty_folder(tmp_path):
    with pytest.raises(TimeoutError):
        wait_for_new_or_updated_h5(tmp_path, {}, timeout_s=0.1, poll_interval_s=0.05)


def test_auto_loop_pause_and_stop_states():
    spec = {
        "method": "grid",
        "mode": "maximize",
        "objective": "signal",
        "parameters": {"x": {"min": 0, "max": 1, "points": 2}},
        "max_iterations": 2,
    }
    runner = SupervisedOptimizerAutoLoop(
        spec,
        lambda params: {"params": params},
        lambda: {"engaged": True},
        lambda path: pd.DataFrame({"signal": [1.0]}),
        lambda loop, df, path, iteration: {"objective_value": loop.tell(loop.session.pending_params, {"signal": 1.0})},
        config=AutoLoopConfig.from_spec(spec, dry_run=True),
    )
    runner.request_pause()
    assert runner.step()["status"] == "paused"
    runner.resume()
    assert runner.step()["status"] == "dry_run_preview"

    runner = SupervisedOptimizerAutoLoop(
        spec,
        lambda params: {"params": params},
        lambda: {"engaged": True},
        lambda path: pd.DataFrame({"signal": [1.0]}),
        lambda loop, df, path, iteration: {"objective_value": loop.tell(loop.session.pending_params, {"signal": 1.0})},
        config=AutoLoopConfig.from_spec(spec),
    )
    runner.request_stop()
    assert runner.step()["status"] == "stopped"


def test_auto_loop_mock_runmanager_temp_h5(tmp_path):
    h5_dir = tmp_path / "shots"
    h5_dir.mkdir()
    rm = RunmanagerBackend(mock=True)
    registry = {"x": {"type": "float", "min": 0, "max": 1, "max_points": 3}}
    validator = SafetyValidator(registry)
    spec = {
        "method": "grid",
        "mode": "maximize",
        "objective": "signal",
        "parameters": {"x": {"min": 0, "max": 1, "points": 2}},
        "max_iterations": 2,
    }
    written = []

    def apply_params(params):
        safe = validator.validate_command({"actions": [{"type": "set_global", "name": name, "value": value} for name, value in params.items()]})
        rm.set_globals(safe["globals"])
        return safe

    def engage():
        idx = len(written)
        path = h5_dir / f"shot_{idx}.h5"
        path.write_text("mock", encoding="utf-8")
        os.utime(path, (100 + idx, 100 + idx))
        written.append(path)
        return rm.engage()

    def load_dataframe(path):
        x = rm.get_globals()["x"]
        return pd.DataFrame({"filepath": [str(path)], "signal": [x]})

    def evaluate_feedback(loop, dataframe, h5_path, iteration):
        return tell_optimizer_from_dataframe(loop, dataframe, row_position=0)

    points = []
    runner = SupervisedOptimizerAutoLoop(
        spec,
        apply_params,
        engage,
        load_dataframe,
        evaluate_feedback,
        h5_folder=h5_dir,
        config=AutoLoopConfig.from_spec(spec, poll_interval_s=0.05, h5_timeout_s=1.0),
        record_point=points.append,
    )
    results = list(runner.run_until_terminal())
    assert [r["status"] for r in results] == ["point_complete", "point_complete", "complete"]
    assert runner.optimizer.best()["value"] == 1.0
    assert len(points) >= 2


def test_database_optimization_point_roundtrip(tmp_path):
    db = LabPilotDatabase(tmp_path / "labpilot.sqlite")
    db.upsert_optimization_session("s1", "running", {"status": "running"})
    db.log_optimization_point("s1", 1, "point_complete", {"x": 1.0}, 2.0, {"objective_value": 2.0})
    rows = db.list_optimization_points("s1")
    db.close()
    assert rows[0]["params"] == {"x": 1.0}
    assert rows[0]["objective_value"] == 2.0
