import json
import subprocess
import sys

from labpilot_ai.automation import Automation


def invoke(profile, *args):
    completed = subprocess.run(
        [sys.executable, "-m", "labpilot_ai.automation_cli", "--profile", str(profile), *args],
        text=True, capture_output=True, timeout=30,
    )
    assert completed.returncode == 0, (completed.stdout, completed.stderr)
    return json.loads(completed.stdout)


def test_simulated_batch_survives_separate_cli_processes(tmp_path):
    profile = tmp_path / "two processes 站点.json"
    invoke(profile, "init")
    doctor = invoke(profile, "doctor")
    assert doctor["capabilities"]["value"]["targets"]["blacs"]["available"]
    plan = tmp_path / "batch.json"
    plan.write_text('{"target":"runmanager","action":"engage","expected_n_shots":1}', encoding="utf-8")
    prepared = invoke(profile, "prepare", str(plan))
    task = prepared["task_id"]
    assert prepared["status"] == "PENDING_APPROVAL"
    invoke(profile, "approve", task, prepared["plan_digest"], "--operator", "local")
    dispatched = invoke(profile, "run-next")
    assert dispatched["status"] == "OBSERVING"
    result = invoke(profile, "observe", task)
    assert result["status"] == "COMPLETED"
    assert result["evidence"]["simulated"] is True
    assert result["evidence"]["executed_count"] == 1


def test_changed_profile_cannot_adopt_existing_plans(tmp_path):
    profile = tmp_path / "station.json"
    original = {"schema_version": 1, "simulate": True, "host": {"state_db": "host.sqlite3"}}
    profile.write_text(json.dumps(original), encoding="utf-8")
    automation = Automation(profile)
    automation.dispatch("prepare", {"target": "runmanager", "action": "engage", "expected_n_shots": 1})
    assert len(automation.store.list()) == 1
    original["host"]["runmanager"] = {"max_shots": 4}
    profile.write_text(json.dumps(original), encoding="utf-8")
    assert Automation(profile).store.list() == []
