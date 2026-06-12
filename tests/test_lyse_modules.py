import pandas as pd

from labpilot_ai.lyse_ctrl.single_runner import run_single_module
from labpilot_ai.lyse_ctrl.multi_runner import run_multi_module
from labpilot_ai.lyse_ctrl.registry_autoscan import merge_autoscanned_lyse_modules


def test_multi_module_runner_loads_example():
    registry = {
        "multi_modules": {
            "example_multi": {
                "path": "plugins/multi_modules/example_multi.py",
                "enabled_by_default": True,
                "order": 10,
                "params": {},
            }
        }
    }
    result = run_multi_module(registry, "example_multi", pd.DataFrame({"x": [1, 2]}))
    assert result["n_rows"] == 2


def test_lyse_script_single_runner_writes_and_reads_h5_results(tmp_path):
    h5_path = tmp_path / "shot.h5"
    script = tmp_path / "single_script.py"
    script.write_text(
        "from lyse import Run, path\n"
        "run = Run(path)\n"
        "run.save_result('N_total', 42)\n",
        encoding="utf-8",
    )
    registry = {
        "single_modules": {
            "native_single": {
                "path": str(script),
                "mode": "lyse_script",
                "enabled_by_default": True,
                "order": 1,
                "params": {},
            }
        }
    }
    result = run_single_module(registry, "native_single", h5_path)
    assert result["N_total"] == 42


def test_lyse_script_multi_runner_uses_dataframe(tmp_path):
    script = tmp_path / "multi_script.py"
    script.write_text(
        "import lyse\n"
        "df = lyse.data()\n"
        "lyse.save_result('n_rows', len(df))\n"
        "lyse.save_result('sum_x', int(df['x'].sum()))\n",
        encoding="utf-8",
    )
    registry = {
        "multi_modules": {
            "native_multi": {
                "path": str(script),
                "mode": "lyse_script",
                "enabled_by_default": True,
                "order": 1,
                "params": {},
            }
        }
    }
    result = run_multi_module(registry, "native_multi", pd.DataFrame({"x": [1, 2, 3]}))
    assert result["n_rows"] == 3
    assert result["sum_x"] == 6


def test_lyse_script_multi_runner_exposes_lyse_style_columns(tmp_path):
    script = tmp_path / "multi_script.py"
    script.write_text(
        "import lyse\n"
        "df = lyse.data()\n"
        "lyse.save_result('n_atoms', int(df[('analysis', 'N_atom', '', '')].iloc[0]))\n"
        "lyse.save_result('scan', int(df['scan_time_ms'].iloc[0]))\n",
        encoding="utf-8",
    )
    registry = {
        "multi_modules": {
            "native_multi": {
                "path": str(script),
                "mode": "lyse_script",
                "enabled_by_default": True,
                "order": 1,
                "params": {},
            }
        }
    }
    dataframe = pd.DataFrame(
        {
            "results.analysis.N_atom": [5, 6],
            "globals.scan_time_ms": [10, 20],
        }
    )

    result = run_multi_module(registry, "native_multi", dataframe)

    assert result["n_atoms"] == 5
    assert result["scan"] == 10


def test_autoscan_skips_helper_modules_that_only_import_lyse(tmp_path):
    single_dir = tmp_path / "single"
    single_dir.mkdir()
    (single_dir / "utils.py").write_text("from lyse import *\n\ndef helper():\n    return 1\n", encoding="utf-8")
    (single_dir / "analysis.py").write_text("from lyse import Run, path\nrun = Run(path)\n", encoding="utf-8")

    registry, report = merge_autoscanned_lyse_modules(
        {"single_modules": {}, "multi_modules": {}},
        single_dir=single_dir,
        multi_dir=None,
        project_root=tmp_path,
    )

    assert report["single_scanned"] == 1
    assert sorted(registry["single_modules"]) == ["analysis"]
