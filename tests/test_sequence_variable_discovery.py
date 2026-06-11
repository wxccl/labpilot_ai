from pathlib import Path

from labpilot_ai.runmanager_ctrl.sequence_variable_discovery import discover_sequence_globals


def test_sequence_variable_discovery_from_file(tmp_path):
    seq = tmp_path / "sequence.py"
    seq.write_text(
        """
import numpy as np
from labscript import start, stop

duration_tof_ms = 17.0
do_Rabi = False
MW_power_W = 0.01
scan_values = np.linspace(1, 3, 5)

start()
if do_SG:
    x = duration_probe_us
stop(1)
""".strip(),
        encoding="utf-8",
    )
    registry, report = discover_sequence_globals({"active_sequence_file": str(seq)}, {}, project_dir=tmp_path)
    assert report["files"]
    assert registry["duration_tof_ms"]["type"] == "float"
    assert registry["duration_tof_ms"]["unit"] == "ms"
    assert registry["do_Rabi"]["type"] == "bool"
    assert registry["MW_power_W"]["risk"] == "high"
    assert registry["scan_values"]["type"] == "float_array"
    assert registry["do_SG"]["type"] == "bool"
    assert registry["duration_probe_us"]["unit"] == "us"
