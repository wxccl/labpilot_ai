import json

import numpy as np
import pandas as pd
import pytest

from labpilot_ai.analysis.fit_models import gaussian2d, fit_xyz
from labpilot_ai.analysis.plot_specs import default_plot_columns, numeric_varying_columns, valid_fit_models
from labpilot_ai.analysis.plotting import heatmap2d, histogram, mean_errorbar, scatter_line, scatter2d, surface3d
from labpilot_ai.analysis.report_generator import generate_markdown_report
from labpilot_ai.lyse_ctrl.result_store import JsonlResultStore, merge_result_columns


def test_jsonl_result_store_roundtrip(tmp_path):
    store = JsonlResultStore(tmp_path / "analysis_results.jsonl")
    row = store.append("fit", "linear", {"status": "ok", "params": {"a": np.float64(2.0)}}, metadata={"x": "tof"})
    assert row["kind"] == "fit"
    rows = store.read_all()
    assert rows[0]["result"]["params"]["a"] == 2.0
    assert rows[0]["metadata"]["x"] == "tof"


def test_merge_result_columns_updates_single_row():
    df = pd.DataFrame({"filepath": ["a.h5", "b.h5"], "x": [1, 2]})
    merge_result_columns(df, 1, {"N_total": 42.5, "roi": {"x": 1}})
    assert df.loc[1, "N_total"] == 42.5
    assert json.loads(df.loc[1, "roi"]) == {"x": 1}


def test_report_includes_analysis_records():
    text = generate_markdown_report(
        "report",
        pd.DataFrame({"x": [1]}),
        analysis_records=[{"kind": "single", "name": "atom_number", "result": {"status": "ok"}}],
    )
    assert "single/atom_number" in text


def test_fit_xyz_gaussian2d():
    pytest.importorskip("scipy")
    xs = np.linspace(-2, 2, 5)
    ys = np.linspace(-2, 2, 5)
    xx, yy = np.meshgrid(xs, ys)
    zz = gaussian2d((xx.ravel(), yy.ravel()), 5.0, 0.2, -0.1, 1.0, 1.3, 0.5)
    result = fit_xyz(xx.ravel(), yy.ravel(), zz, model="gaussian2d")
    assert result["status"] == "ok"
    assert result["r2"] > 0.95


def test_plot_specs_only_offer_numeric_varying_columns():
    df = pd.DataFrame(
        {
            "filepath": ["a.h5", "b.h5", "c.h5"],
            "constant": [1, 1, 1],
            "x": [0, 1, 2],
            "y": ["1.0", "2.0", "bad"],
            "label": ["a", "b", "c"],
        }
    )

    columns = numeric_varying_columns(df)

    assert columns == ["x", "y"]
    assert valid_fit_models("histogram") == ["none", "gaussian", "lorentzian"]
    assert "linear" in valid_fit_models("scatter_line")
    assert default_plot_columns("heatmap2d", ["x", "y", "z"]) == {"x": "x", "y": "y", "z": "z"}


def test_plotting_functions_coerce_numeric_columns(tmp_path):
    df = pd.DataFrame(
        {
            "x": [0, 0, 1, 1, 2, 2],
            "y": [1, 2, 2, 3, 3, 4],
            "z": ["1", "2", "3", "4", "5", "6"],
            "bad": ["skip", None, "7", "8", "9", "10"],
        }
    )

    figures = [
        scatter_line(df, "x", "y", out_path=tmp_path / "scatter.png"),
        mean_errorbar(df, "x", "y", out_path=tmp_path / "errorbar.png"),
        histogram(df, "z", out_path=tmp_path / "hist.png"),
        scatter2d(df, "x", "y", "z", out_path=tmp_path / "scatter2d.png"),
        heatmap2d(df, "x", "y", "z", out_path=tmp_path / "heatmap.png"),
        surface3d(df, "x", "y", "z", out_path=tmp_path / "surface.png"),
    ]

    for figure in figures:
        assert figure is not None
    assert (tmp_path / "surface.png").exists()
