"""Local filesystem mailbox to the packaged plugin inside BLACS."""

import os
from pathlib import Path
import time
import uuid

from .protocol import Refused, canonical, read_json


def atomic_json(path, value):
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        with temporary.open("x", encoding="ascii") as stream:
            stream.write(canonical(value))
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def mailbox(profile):
    spool = profile.spool
    if str(spool).startswith(("\\\\", "//")):
        raise Refused("BLACS plugin mailbox must be on the local machine")
    return spool


class Blacs:
    def __init__(self, profile):
        self.profile = profile

    def _contact(self, method, params):
        if not self.profile.blacs.get("enabled"):
            raise Refused("BLACS is disabled in the host profile")
        spool = mailbox(self.profile)
        try:
            ready = read_json(spool / "ready.json")
            generation = ready["generation"]
            if not 0 <= time.time() - ready["updated"] <= 5:
                raise ValueError("stale heartbeat")
        except (OSError, ValueError, TypeError, KeyError) as exc:
            raise Refused("Packaged BLACS plugin is unavailable; inspect doctor and normal startup") from exc
        key = uuid.uuid4().hex
        request_path = spool / "inbox" / f"{key}.json"
        result_path = spool / "outbox" / f"{key}.json"
        expires = time.time() + 6
        atomic_json(request_path, {"method": method, "params": params, "mail_id": key,
                                   "generation": generation, "expires": expires})
        try:
            while time.time() < expires + 2:
                if result_path.is_file():
                    result = read_json(result_path)
                    if result.get("mail_id") != key or result.get("generation") != generation:
                        raise RuntimeError("Invalid BLACS plugin receipt binding")
                    if result["state"] == "REFUSED":
                        raise Refused(result["reason"])
                    if result["state"] != "OK":
                        raise RuntimeError(result.get("reason", "Unresolved BLACS operation"))
                    return result["value"]
                time.sleep(0.08)
        finally:
            request_path.unlink(missing_ok=True)
            result_path.unlink(missing_ok=True)
        raise RuntimeError("No BLACS plugin response; reconcile the original request")

    def discover(self):
        if not self.profile.blacs.get("enabled"):
            return {"available": False, "actions": []}
        return self._contact("discover", {})

    def snapshot(self, params):
        return self._contact("snapshot", params)

    def execute(self, params):
        if params.get("action") != "set_manual":
            raise Refused("Only set_manual is supported by the packaged BLACS adapter")
        return self._contact("execute", params)
