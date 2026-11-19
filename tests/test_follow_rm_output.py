import json
from pathlib import Path

import pytest

from labpilot_ai.host.native_batch import NativeBatches
from labpilot_ai.host.protocol import Journal, Profile, Refused


def test_follow_reviewed_output_and_ignore_sibling_callbacks(tmp_path):
    config = tmp_path / "profile.json"
    approved = tmp_path / "data"
    approved.mkdir()
    selected = approved / "selected"
    selected.mkdir()
    config.write_text(json.dumps({"host": {"state_db": "host.db", "runmanager": {
        "enabled": True, "allow": ["engage"], "output_root": str(approved),
        "batch_root": "@runmanager_output"}}}), encoding="utf8")
    profile = Profile(config)
    batches = NativeBatches(profile)
    params = {"request_id": "batch123"}
    Journal(profile.state_db).reserve(params["request_id"], "runmanager", params)
    before = {"sequence": str(config), "snapshot_sha256": "abc", "globals_raw": {}, "n_shots": 1}
    for location in (str(tmp_path), "relative", str(approved / "absent")):
        with pytest.raises(Refused):
            batches.reserve(params, {**before, "output": location})
    batch = batches.reserve(params, {**before, "output": str(selected)})
    assert Path(batch["batch_root"]) == selected / "batch123"
    assert batches.manages_path(selected / "batch123" / "managed.h5")
    other = approved / "other" / "batch123" / "unrelated.h5"
    assert not batches.manages_path(other)
    batches.record(other, "executed")
    observed = batches.observe("batch123")
    assert observed["executed_count"] == 0 and not observed.get("batch_ambiguity")
