import configparser
from types import SimpleNamespace

import pytest

from labpilot_ai.config.registry_editor import LYSE_FIELDS, build_lyse_registry, flatten_lyse_registry
from labpilot_ai.host.managed_runmanager import listener_port
from labpilot_ai.host.preflight import capability_report
from labpilot_ai.host.protocol import Refused


def test_editable_lyse_columns_preserve_reviewed_hash():
    pin = "a" * 64
    original = {"single_modules": {"site_camera": {"path": "a.py", "routine_sha256": pin}}, "multi_modules": {}}
    rows = [{key: row.get(key) for key in LYSE_FIELDS} for row in flatten_lyse_registry(original)]
    assert build_lyse_registry(rows)["single_modules"]["site_camera"]["routine_sha256"] == pin


def test_endpoint_uses_site_port_and_refuses_conflict():
    cfg = configparser.ConfigParser()
    cfg.read_dict({"ports": {"runmanager": "45001"}})
    assert listener_port(SimpleNamespace(runmanager={}), cfg, 42523) == 45001
    with pytest.raises(Refused):
        listener_port(SimpleNamespace(runmanager={"port": 45002}), cfg, 42523)


def test_unfamiliar_device_inventory_does_not_grant_writes():
    response = {"state":"OBSERVED", "value":{"targets":{"blacs":{"available":True,
                "devices":["custom_detector"], "actions":[]}}}}
    report = capability_report(response, ["blacs.set_manual"])
    assert report["state"] == "REFUSED"
    assert report["devices"][0]["device"] == "custom_detector"
    assert not report["devices"][0]["write_actions"]
