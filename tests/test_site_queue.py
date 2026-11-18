from datetime import datetime, timezone

import pytest

from labpilot_ai.blacs_ctrl.local_gateway import LocalBlacs, _digest
from labpilot_ai.local_control.cli import dispatch, parser


class Site:
    def __init__(self):
        self.queue = dict(host_generation="a"*32, queue_generation="b"*32, status="Idle", paused=False,
                          repeat=False, queued_count=0, running_shot="")
        self.bad = False
        self.calls = 0

    def snapshot(self):
        return dict(self.queue, queue_sha256=_digest(self.queue), observed_at_utc=datetime.now(timezone.utc).isoformat())

    def read_blacs(self, action):
        return dict(schema="rbbec-unified-result/1", state="OBSERVED", action=action, value=dict(
            host_generation=self.queue["host_generation"], connection_sha256="c"*64, queue=self.snapshot()))

    def call(self, target, request):
        self.calls += 1
        assert request["payload"]["expected_queue_sha256"] == self.snapshot()["queue_sha256"]
        self.queue["paused" if request["action"] == "queue.pause" else "repeat"] = request["payload"]["value"]
        return dict(schema="rbbec-unified-result/1", action=request["action"], request_id=request["request_id"],
                    request_sha256="" if self.bad else _digest(request), state="APPLIED", value=self.snapshot())


@pytest.mark.parametrize("setting", ["pause", "repeat"])
def test_queue_review_apply_and_restore(tmp_path, monkeypatch, setting):
    monkeypatch.setenv("LABPILOT_SITE_APPROVER", "the operator")
    site = Site()
    for desired in ["true", "false"]:
        plan = str(tmp_path / (desired + ".json"))
        args = ["prepare-queue", setting, desired, "--approver", "the operator", "--instruction", "operator request", "--output", plan]
        count = site.calls
        assert dispatch(parser().parse_args(args), site)["state"] == "PREPARED"
        assert site.calls == count
        assert dispatch(parser().parse_args(["apply", plan]), site)["state"] == "APPLIED"
    assert not site.queue["paused"] and not site.queue["repeat"]


def test_refuse_nonempty_and_mismatched_operator_and_receipt(monkeypatch):
    site = Site()
    client = LocalBlacs(site)
    params = dict(approver="operator", instruction="pause request")
    site.queue["queued_count"] = 1
    with pytest.raises(ValueError, match="idle empty"):
        client.prepare_queue("pause", True, **params)
    site.queue["queued_count"] = 0
    monkeypatch.setenv("LABPILOT_SITE_APPROVER", "different operator")
    with pytest.raises(ValueError, match="OWNER_INSTRUCTION"):
        client.prepare_queue("pause", True, **params)
    assert site.calls == 0
    monkeypatch.delenv("LABPILOT_SITE_APPROVER")
    site.bad = True
    assert client.apply_queue(client.prepare_queue("pause", True, **params))["state"] == "UNKNOWN"
    assert site.calls == 1
