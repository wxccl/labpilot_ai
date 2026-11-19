import sys
from types import SimpleNamespace

import pytest

from labpilot_ai.shot_analysis import LyseBatchAnalysis
from labpilot_ai.shot_analysis.worker import _run_routine


def test_trusted_helper_scope_is_bound_and_restored(tmp_path):
    helper = tmp_path / "trusted"
    helper.mkdir()
    (helper / "test_labpilot_site_calibration.py").write_text("GAIN = 19", encoding="utf8")
    config = {"routine": "routine.py", "routine_sha256": "a"*64,
              "quality_rules": [{"result": "gain", "type": "integer", "min": 1}]}
    bare = LyseBatchAnalysis(sys.executable, config, base_dir=tmp_path)
    reviewed = LyseBatchAnalysis(sys.executable, {**config, "sys_path": ["trusted"]}, base_dir=tmp_path)
    assert bare.profile_sha256 != reviewed.profile_sha256
    previous = sys.path[:]
    source = "from test_labpilot_site_calibration import GAIN\nassert GAIN == 19\n"
    try:
        _run_routine(SimpleNamespace(path=None), reviewed.routine, source, tmp_path / "shot.h5", reviewed.import_dirs)
        assert sys.path == previous
    finally:
        sys.modules.pop("test_labpilot_site_calibration", None)
    for bad in ["trusted", ["missing"], ["trusted", "trusted"], [str(tmp_path.anchor)]]:
        with pytest.raises(ValueError):
            LyseBatchAnalysis(sys.executable, {**config, "sys_path": bad}, base_dir=tmp_path)
