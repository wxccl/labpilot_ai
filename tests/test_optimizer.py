import os

import pandas as pd

from labpilot_ai.optimizer.experiment_loop import OptimizerLoop
from labpilot_ai.optimizer.lyse_feedback import latest_row_position, objective_values_from_row, tell_optimizer_from_dataframe


def test_grid_optimizer_loop():
    loop = OptimizerLoop(
        {
            "method": "grid",
            "mode": "maximize",
            "objective": "signal",
            "parameters": {"x": {"min": 0, "max": 1, "points": 3}},
        }
    )
    params = loop.ask()
    assert params == {"x": 0.0}
    value = loop.tell(params, {"signal": 2.0})
    assert value == 2.0
    assert loop.best()["value"] == 2.0


def test_bayesian_optimizer_loop_midpoint_first():
    loop = OptimizerLoop(
        {
            "method": "bayesian",
            "mode": "maximize",
            "objective": "signal",
            "parameters": {"x": {"min": 0, "max": 10, "points": 5}},
        }
    )
    params = loop.ask()
    assert "x" in params
    assert 0 <= params["x"] <= 10


def test_latest_row_position_uses_h5_file_mtime(tmp_path):
    older = tmp_path / "older.h5"
    newer = tmp_path / "newer.h5"
    older.write_text("old", encoding="utf-8")
    newer.write_text("new", encoding="utf-8")
    os.utime(older, (100, 100))
    os.utime(newer, (200, 200))
    df = pd.DataFrame({"filepath": [str(newer), str(older)]})
    assert latest_row_position(df) == 0


def test_objective_values_from_row_adds_short_result_names():
    values = objective_values_from_row({"results.N_total": 2.5, "filename": "shot.h5"})
    assert values["results.N_total"] == 2.5
    assert values["N_total"] == 2.5
    assert "filename" not in values


def test_tell_optimizer_from_dataframe_uses_latest_lyse_values():
    loop = OptimizerLoop(
        {
            "method": "grid",
            "mode": "maximize",
            "objective": "N_total / temperature_uK",
            "parameters": {"x": {"min": 0, "max": 1, "points": 2}},
            "max_iterations": 2,
        }
    )
    assert loop.ask() == {"x": 0.0}
    df = pd.DataFrame({"results.N_total": [10.0], "temperature_uK": [2.0]})
    feedback = tell_optimizer_from_dataframe(loop, df)
    assert feedback["objective_value"] == 5.0
    assert loop.best()["value"] == 5.0
