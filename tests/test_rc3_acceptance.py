from datetime import datetime, timedelta, timezone
import base64
import json
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

from labpilot_ai import owner_grant as owner
from labpilot_ai.host.adapters import restore_record
from labpilot_ai.host.protocol import Refused, canonical, snapshot


@pytest.mark.parametrize("change", ["none", "absent", "forged", "expired", "future", "long", "profile",
                                    "path", "shots", "id", "digest", "values"])
def test_owner_authorization(tmp_path, monkeypatch, change):
    profile = SimpleNamespace(path=tmp_path / "site.json", sha256="a"*64)
    params = {"request_id": "req1", "target": "runmanager", "action": "engage", "expected_n_shots": 1,
              "expected_snapshot_sha256": "b"*64}
    key = Ed25519PrivateKey.generate()
    public = tmp_path / "owner.pub"
    public.write_text(key.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw).hex())
    monkeypatch.setattr(owner, "trust_key", lambda: public)
    now = datetime.now(timezone.utc)
    body = {"schema": "labpilot-owner-grant/1", "profile": profile.sha256, "site_path": str(profile.path),
            "issued": (now-timedelta(seconds=1)).isoformat(), "expires": (now+timedelta(minutes=4)).isoformat(),
            "request": dict(params)}
    if change == "forged":
        key = Ed25519PrivateKey.generate()
    if change in {"expired", "future", "long"}:
        field, minutes = {"expired": ("expires",-1), "future": ("issued",1), "long": ("expires",20)}[change]
        body[field] = (now+timedelta(minutes=minutes)).isoformat()
    if change in {"profile", "path"}:
        body["profile" if change == "profile" else "site_path"] += "x"
    if change in {"shots","id","digest","values"}:
        field = {"shots":"expected_n_shots","id":"request_id","digest":"expected_snapshot_sha256","values":"values"}[change]
        body["request"][field] = "different"
    grant = owner.grant_path(profile.path, params)
    grant.parent.mkdir()
    if change != "absent":
        grant.write_text(json.dumps({"body":body,"signature":base64.b64encode(key.sign(canonical(body).encode())).decode()}))
    if change == "none":
        assert len(owner.verify(profile, params)) == 64
    else:
        with pytest.raises(Refused):
            owner.verify(profile, params)


def test_restore_only_reviewed_numeric_successor(tmp_path):
    old = snapshot({"output":str(tmp_path/"0010"),"globals_raw":{"a":"1 # original"}})
    written = snapshot({"output":old["output"],"globals_raw":{"a":"2 # original"}})
    successor = str(tmp_path/"0011")
    current = snapshot({"output":successor,"globals_raw":written["globals_raw"]})
    journal = Mock()
    journal.observe.return_value = {"state":"APPLIED","request_id":"src","value":{"after":written,"restore_baseline":old}}
    spec = {"original_request_id":"src","preserve_output":successor}
    assert restore_record(journal,spec,current)["globals_raw"] == old["globals_raw"]
    assert restore_record(journal,spec,current)["output"] == successor
    for changed in [snapshot({"output":successor,"globals_raw":{"a":"3"}}),snapshot({"output":str(tmp_path/"0012"),"globals_raw":written["globals_raw"]})]:
        with pytest.raises(Refused):
            restore_record(journal,spec,changed)


def test_unsigned_live_host_request_has_no_effect(tmp_path, monkeypatch):
    from labpilot_ai.host import __main__ as host
    from labpilot_ai.host.protocol import Profile

    path = tmp_path / "profile.json"
    path.write_text(json.dumps({"schema_version":1}))
    profile = Profile(path)
    effect = Mock(side_effect=AssertionError("unexpected live dispatch"))
    monkeypatch.setattr(host.Runmanager, "execute", effect)
    response = host.dispatch({"method":"execute","params":{"request_id":"test","target":"runmanager",
                                                          "action":"engage","expected_n_shots":1}}, profile)
    assert response["state"] == "REFUSED"
    effect.assert_not_called()
    assert not profile.state_db.exists()
