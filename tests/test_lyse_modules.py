import pandas as pd

from labpilot_ai.lyse_ctrl.multi_runner import run_multi_module


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
