"""Detached owner grants for packaged live host requests."""
import argparse
import base64
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path

from .host.protocol import Refused, canonical, digest, read_json, request_id


def trust_key():
    if os.name == "nt":
        import ctypes
        buffer = ctypes.create_unicode_buffer(260)
        if ctypes.windll.shell32.SHGetFolderPathW(None, 35, None, 0, buffer):
            raise Refused("Cannot resolve the system application data directory")
        return Path(buffer.value) / "LabPilot" / "trust" / "owner.pub"
    return Path("/etc/labpilot/trust/owner.pub")


def task_request(task):
    params = {**task["params"], "action": task["action"], "request_id": task["request_id"],
              "expected_snapshot_sha256": task["expected_config_digest"]}
    if task["kind"] == "batch":
        params["expected_n_shots"] = task["expected_shots"]
    return params


def grant_path(profile_path, params):
    return Path(profile_path).parent / "owner-grants" / (request_id(params) + ".json")


def verify(profile, params):
    try:
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

        grant = read_json(grant_path(profile.path, params))
        body = grant["body"]
        key = Ed25519PublicKey.from_public_bytes(bytes.fromhex(trust_key().read_text().strip()))
        key.verify(base64.b64decode(grant["signature"], validate=True), canonical(body).encode("ascii"))
        now = datetime.now(timezone.utc)
        expiry = datetime.fromisoformat(body["expires"])
        issued = datetime.fromisoformat(body["issued"])
        if (body["schema"] != "labpilot-owner-grant/1" or body["profile"] != profile.sha256
                or body["site_path"] != str(profile.path.resolve())
                or canonical(body["request"]) != canonical(params) or not issued <= now < expiry
                or expiry - issued > timedelta(minutes=15)):
            raise ValueError("Binding or expiry mismatch")
        return digest(body)
    except Exception as exc:
        raise Refused("Live action requires a valid, unexpired detached owner grant") from exc


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    export = sub.add_parser("export")
    export.add_argument("--profile", required=True)
    export.add_argument("task")
    export.add_argument("output", type=Path)
    sign = sub.add_parser("sign")
    sign.add_argument("proposal", type=Path)
    sign.add_argument("key", type=Path)
    sign.add_argument("output", type=Path)
    args = parser.parse_args()
    if args.command == "export":
        from .automation import Automation
        app = Automation(args.profile)
        task = app.store.get(args.task)
        value = {"site_path": str(app.profile), "profile": app.host.profile_sha256, "request": task_request(task)}
    else:
        from getpass import getpass
        from cryptography.hazmat.primitives.serialization import load_pem_private_key
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
        proposal = read_json(args.proposal)
        now = datetime.now(timezone.utc)
        body = {"schema": "labpilot-owner-grant/1", "profile": proposal["profile"], "site_path": proposal["site_path"],
                "request": proposal["request"], "issued": now.isoformat(),
                "expires": (now + timedelta(minutes=15)).isoformat()}
        print(json.dumps(body, indent=2, ensure_ascii=True))
        if input("Confirm by typing the full request ID: ").strip() != request_id(body["request"]):
            parser.error("Confirmation did not match")
        key = load_pem_private_key(args.key.read_bytes(), password=getpass("Owner key passphrase: ").encode())
        if not isinstance(key, Ed25519PrivateKey):
            parser.error("Expected an encrypted Ed25519 private key")
        value = {"body": body, "signature": base64.b64encode(key.sign(canonical(body).encode("ascii"))).decode()}
    with args.output.open("x", encoding="utf8") as stream:
        json.dump(value, stream, indent=2)
