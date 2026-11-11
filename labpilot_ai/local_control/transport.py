"""Send JSON to an installed local gateway under the Labscript interpreter."""
import hashlib
import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
import re
import subprocess
import sys
import uuid


MODE = "local_gateway"
MAX_BYTES = 4 * 1024 * 1024
READ_ACTIONS = {
    "blacs": {"discover", "snapshot", "queue.status", "camera.attributes.read", "prawn.status.read"},
    "runmanager": {"read_all", "snapshot", "plan"},
}


def local_gateway_enabled():
    return os.getenv("LABPILOT_CONTROL_MODE", "").strip().lower() == MODE


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"Duplicate JSON field: {key}")
        result[key] = value
    return result


def reject_constant(value):
    raise ValueError(f"Invalid JSON number: {value}")


def load_json(raw):
    return json.loads(raw, object_pairs_hook=unique_object, parse_constant=reject_constant)


class LocalGateway:
    def __init__(self, gateway_path, python_path=None, receipts=None, timeout=55, *, runner=None):
        self.gateway_path = Path(gateway_path).expanduser().resolve()
        self.python_path = Path(python_path or sys.executable).expanduser().resolve()
        local_data = Path(os.environ.get("LOCALAPPDATA") or Path.home() / ".local" / "state")
        self.receipts = Path(receipts or local_data / "LabPilot" / "control_receipts")
        self.timeout = timeout
        self.runner = runner or subprocess.run

    @classmethod
    def from_env(cls):
        program_data = Path(os.environ.get("ProgramData", r"C:\ProgramData"))
        default_gateway = program_data / "RbBEC" / "unified_control" / "gateway.py"
        return cls(os.getenv("LABPILOT_LOCAL_GATEWAY") or default_gateway,
                   os.getenv("LABPILOT_LABSCRIPT_PYTHON"), os.getenv("LABPILOT_CONTROL_RECEIPTS"))

    def read_blacs(self, action, device=None):
        if action not in READ_ACTIONS["blacs"]:
            raise ValueError("Unsupported BLACS read")
        now = datetime.now(timezone.utc)
        payload = {"device": device} if device else {}
        if action == "camera.attributes.read":
            payload["visibility"] = "Simple"
        request = {"schema": "rbbec-unified/1", "action": action, "payload": payload,
                   "request_id": uuid.uuid4().hex, "issued_at_utc": now.isoformat(),
                   "expires_at_utc": (now + timedelta(seconds=90)).isoformat()}
        return self.call("blacs", request)

    def call(self, target, request):
        if target not in READ_ACTIONS or not isinstance(request, dict):
            raise ValueError("Invalid gateway request")
        if not self.gateway_path.is_file() or not self.python_path.is_file():
            raise FileNotFoundError("Local gateway or Labscript Python missing. Check LABPILOT_LOCAL_GATEWAY and LABPILOT_LABSCRIPT_PYTHON.")
        raw = json.dumps({"target": target, "request": request}, ensure_ascii=True,
                         sort_keys=True, allow_nan=False).encode("utf-8")
        if len(raw) > MAX_BYTES:
            raise ValueError("Gateway request too large")
        request_id = request.get("request_id")
        if request.get("action") in READ_ACTIONS[target]:
            return self._exchange(raw, request_id)
        if not isinstance(request_id, str) or not re.fullmatch(r"[0-9a-f]{32}", request_id):
            raise ValueError("A prepared write needs a 32-character hexadecimal request ID")
        return self._write_once(raw, request_id)

    def _write_once(self, raw, request_id):
        self.receipts.mkdir(parents=True, exist_ok=True)
        intent = self.receipts / f"{request_id}.intent.json"
        result_path = self.receipts / f"{request_id}.result.json"
        checksum = hashlib.sha256(raw).hexdigest()
        try:
            with intent.open("x", encoding="utf-8") as stream:
                json.dump({"request_id": request_id, "sha256": checksum}, stream)
                stream.flush()
                os.fsync(stream.fileno())
        except FileExistsError:
            try:
                previous = load_json(intent.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                return self._unknown(request_id, "Intent is unreadable. Reconcile the original operation.")
            if (not isinstance(previous, dict) or previous.get("request_id") != request_id
                    or not isinstance(previous.get("sha256"), str)):
                return self._unknown(request_id, "Intent is invalid. Reconcile the original operation.")
            if previous["sha256"] != checksum:
                raise ValueError("Request ID was already used for different content")
            try:
                previous_result = load_json(result_path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                return self._unknown(request_id, "Prior intent has no readable result. Reconcile the original operation.")
            if not isinstance(previous_result, dict) or previous_result.get("request_id") != request_id:
                return self._unknown(request_id, "Prior result does not match the request. Reconcile the original operation.")
            return previous_result
        result = self._exchange(raw, request_id)
        if result.get("request_id") != request_id:
            result = self._unknown(request_id, "Gateway did not bind its response to the write. Reconcile before retrying.")
        try:
            with result_path.open("x", encoding="utf-8") as stream:
                json.dump(result, stream, ensure_ascii=True, allow_nan=False)
                stream.flush()
                os.fsync(stream.fileno())
        except OSError:
            return self._unknown(request_id, "Could not save the gateway result. Reconcile the original operation.")
        return result

    @staticmethod
    def _unknown(request_id, reason):
        return {"state": "UNKNOWN", "request_id": request_id, "reason": reason, "no_automatic_retry": True}

    def _exchange(self, raw, request_id):
        try:
            completed = self.runner([str(self.python_path), "-X", "utf8", str(self.gateway_path)],
                                    input=raw, capture_output=True, timeout=self.timeout,
                                    check=False, shell=False, cwd=str(self.gateway_path.parent),
                                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            prefix = b"RBBEC_JSON:"
            if completed.returncode != 0 or len(completed.stdout) > MAX_BYTES:
                return self._unknown(request_id, "Gateway process or response size error")
            responses = [line[len(prefix):] for line in completed.stdout.splitlines() if line.startswith(prefix)]
            if len(responses) != 1:
                return self._unknown(request_id, "Expected one gateway response")
            result = load_json(responses[0].decode("utf-8"))
            if not isinstance(result, dict):
                return self._unknown(request_id, "Invalid gateway response")
            if request_id and result.get("request_id", request_id) != request_id:
                return self._unknown(request_id, "Gateway returned a different request ID")
            return result
        except (OSError, subprocess.TimeoutExpired, ValueError) as exc:
            return self._unknown(request_id, type(exc).__name__)
