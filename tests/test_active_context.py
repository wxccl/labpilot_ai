import json
from types import SimpleNamespace

from labpilot_ai.automation import Automation
from labpilot_ai.automation_cli import dispatch, parser
from labpilot_ai.harness import build_catalog
from labpilot_ai.host.preflight import capability_report


def test_sim_cli_and_mcp_show_same_snapshot(tmp_path):
    profile = tmp_path / "station.json"
    profile.write_text(json.dumps({"schema_version": 1, "simulate": True, "host": {
        "runmanager": {"batch_root": "managed"}}}), encoding="utf-8")
    app = Automation(profile)
    catalog = build_catalog(app.dispatch)
    result = catalog.invoke("experiment_context", {})
    cli_result = dispatch(parser().parse_args(["--profile", str(profile), "context"]))
    assert result == cli_result
    assert result["simulated"] is True and result["runmanager"]["n_shots"] == 1
    assert result["runmanager"]["output"] != result["configured_batch_root"]
    assert result["analysis"]["native_gui_state"] == "NOT_OBSERVED"
    assert catalog.invoke("experiment_preflight", {"require": "runmanager.managed_binding"})["state"] == "REFUSED"
    assert catalog.invoke("experiment_preflight", {"require": "analysis.quality_rules"})["state"] == "REFUSED"
    app.batch_root = "@runmanager_output"
    follow_context = catalog.invoke("experiment_context", {})
    assert follow_context["selected_batch_parent"] == result["runmanager"]["output"]
    assert follow_context["batch_output_policy"] == "runmanager_output"
    assert not app.store.list()
    task = app.prepare_engage(1)
    assert catalog.invoke("experiment_events", {"task_id": task["task_id"]}) == app.store.events(task["task_id"])


def test_failed_runtime_has_no_invented_path():
    app = object.__new__(Automation)
    calls = []
    def unavailable(op, args):
        calls.append(op)
        return {"state": "UNKNOWN", "reason": "offline"}
    app.host = SimpleNamespace(call=unavailable, profile_sha256="fake")
    app.simulate, app.batch_root = False, None
    app.service = SimpleNamespace(analysis=None)
    result = app.dispatch("context", {})
    assert calls == ["discover", "snapshot"]
    assert result["state"] == "UNKNOWN" and result["runmanager"]["sequence"] is None
    assert result["analysis"]["backend"] == "none"


def test_binding_is_a_predicate_not_a_writable_action():
    reply = {"state": "OBSERVED", "value": {"simulated": False, "targets": {
        "runmanager": {"available": True, "managed_batches": True}}}}
    report = capability_report(reply, ["runmanager.managed_binding"])
    assert report["state"] == "OBSERVED" and "runmanager.managed_binding" not in report["advertised_actions"]
