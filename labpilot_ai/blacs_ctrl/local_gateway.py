"""Same-machine client for the installed, guarded BLACS gateway contract."""

from datetime import datetime, timedelta, timezone
import hashlib
import json
import math
import os
import re
import uuid


_SNAPSHOT_FIELDS = (
    "host_generation", "connection_sha256", "device", "connection", "driver_class",
    "family", "channels", "front_panel", "last_programmed_values", "register_readback",
)
_MANUAL_FAMILIES = {"NI_DAQMX_OUTPUT", "NOVATECH_DDS9M"}


def _check_operator(approver):
    expected = os.getenv("LABPILOT_SITE_APPROVER")
    if expected and expected != approver:
        raise ValueError("OWNER_INSTRUCTION_REFERENCE_REQUIRED: approver differs from local site setting")


def _digest(value):
    encoded = json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":"),
                         allow_nan=False).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _timestamp(value):
    if not isinstance(value, str):
        raise ValueError("BLACS snapshot requires a timestamp")
    result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if result.tzinfo is None:
        raise ValueError("BLACS timestamp requires a timezone")
    return result.astimezone(timezone.utc)


def _observed(result, action):
    if (result.get("schema") != "rbbec-unified-result/1" or
            result.get("state") != "OBSERVED" or result.get("action") != action or
            not isinstance(result.get("value"), dict)):
        reason = result.get("error") or result.get("reason") or "invalid receipt"
        raise RuntimeError(f"BLACS {action}: {result.get('state', 'UNKNOWN')} ({reason})")
    return result["value"]


def _base_value(value, descriptor):
    kind = descriptor.get("kind")
    if kind == "DO":
        if type(value) is not bool:
            raise ValueError("Digital outputs require a JSON boolean")
        return value
    if kind != "AO" or type(value) not in (int, float) or not math.isfinite(value):
        raise ValueError("Analog outputs require a finite number in the device's base unit")
    limits = descriptor.get("limits")
    if (not isinstance(limits, (list, tuple)) or len(limits) != 2 or
            any(type(limit) not in (int, float) or not math.isfinite(limit) for limit in limits) or
            not limits[0] <= value <= limits[1]):
        raise ValueError("Value is outside the limits reported by BLACS")
    return float(value)


def _channel_rows(device, channels, values=None):
    values = values or {}
    for channel, descriptor in channels.items():
        kind = descriptor["kind"]
        name = f"{device}.{channel}"
        value = values.get(channel)
        if kind == "DDS":
            for subchannel, sub in descriptor["subchannels"].items():
                sub_value = value.get(subchannel) if isinstance(value, dict) else None
                yield _row(device, channel, f"{name}.{subchannel}", sub, sub_value,
                           subchannel=subchannel)
        else:
            yield _row(device, channel, name, descriptor, value)


def _row(device, channel, name, descriptor, value, subchannel=None):
    kind = descriptor["kind"]
    row = {
        "name": name, "bridge_name": name, "device": device, "channel": channel,
        "kind": f"DDS.{subchannel}" if subchannel else kind,
        "type": "bool" if kind == "DO" else "float", "unit": descriptor.get("units", ""),
        "current_value": value, "risk": "unknown", "require_confirm": True,
    }
    if subchannel is not None:
        row["subchannel"] = subchannel
    if "limits" in descriptor:
        row["min"], row["max"] = descriptor["limits"]
    return row


class LocalBlacs:
    """Use the current BLACS process through its existing local gateway."""

    def __init__(self, gateway=None):
        self._gateway = gateway

    @property
    def gateway(self):
        if self._gateway is None:
            from labpilot_ai.local_control.transport import LocalGateway

            self._gateway = LocalGateway.from_env()
        return self._gateway

    def discover(self):
        return _observed(self.gateway.read_blacs("discover"), "discover")

    def queue_status(self):
        return _observed(self.gateway.read_blacs("queue.status"), "queue.status")

    @staticmethod
    def _queue_digest(queue):
        fields = ("host_generation", "queue_generation", "status", "paused", "repeat", "queued_count", "running_shot")
        if not isinstance(queue, dict) or not all(key in queue for key in fields):
            raise ValueError("Incomplete site queue snapshot")
        if (type(queue["queued_count"]) is not int or queue["queued_count"] < 0 or
                type(queue["paused"]) is not bool or type(queue["repeat"]) is not bool or
                queue.get("queue_sha256") != _digest({key: queue[key] for key in fields})):
            raise ValueError("Invalid queue state or digest")
        return queue["queue_sha256"]

    def preflight(self):
        site = self.discover()
        queue = site.get("queue")
        self._queue_digest(queue)
        now = datetime.now(timezone.utc)
        if not -5 <= (now - _timestamp(queue.get("observed_at_utc"))).total_seconds() <= 60:
            raise ValueError("Queue snapshot expired")
        if (not re.fullmatch(r"[0-9a-f]{32}", str(site.get("host_generation"))) or
                site["host_generation"] != queue["host_generation"] or
                not re.fullmatch(r"[0-9a-f]{64}", str(site.get("connection_sha256")))):
            raise ValueError("Queue snapshot is not bound to this host and connection table")
        idle = (queue["queued_count"] == 0 and queue["running_shot"] == "" and
                queue["status"] in (("Idle", "Queue paused") if queue["paused"] else ("Idle",)))
        return {"queue": queue, "connection_sha256": site["connection_sha256"], "idle_empty": idle,
                "static_queue_ready": idle and queue["paused"] and not queue["repeat"],
                "local_approver_check_configured": bool(os.getenv("LABPILOT_SITE_APPROVER")),
                "identity_check": "site-enforced at apply; supplied name is not authentication"}

    def prepare_queue(self, setting, value, *, approver, instruction):
        if setting not in ("pause", "repeat") or type(value) is not bool:
            raise ValueError("Queue plan needs pause/repeat and a JSON boolean")
        if any(not isinstance(item, str) or not item.strip() for item in (approver, instruction)):
            raise ValueError("Site approver and operator instruction required")
        state = self.preflight()
        _check_operator(approver)
        queue = state["queue"]
        key = "paused" if setting == "pause" else "repeat"
        if not state["idle_empty"] or queue[key] == value:
            raise ValueError("Queue change requires an idle empty queue and an actual change")
        now = datetime.now(timezone.utc)
        return {"schema": "rbbec-unified/1", "action": "queue." + setting, "request_id": uuid.uuid4().hex,
                "issued_at_utc": now.isoformat(), "expires_at_utc": (now + timedelta(seconds=60)).isoformat(),
                "expected_host_generation": queue["host_generation"], "connection_sha256": state["connection_sha256"],
                "approval_context": {"approver": approver, "instruction": instruction},
                "payload": {"expected_queue_sha256": queue["queue_sha256"], "expected": queue[key], "value": value}}

    def apply_queue(self, request):
        action = request.get("action")
        if action not in ("queue.pause", "queue.repeat") or request.get("schema") != "rbbec-unified/1":
            raise ValueError("Expected a prepared queue change")
        payload = request["payload"]
        _check_operator(request["approval_context"]["approver"])
        if type(payload.get("value")) is not bool or type(payload.get("expected")) is not bool or payload["expected"] == payload["value"]:
            raise ValueError("Invalid prepared queue transition")
        result = self.gateway.call("blacs", request)
        if result.get("state") == "APPLIED":
            key = "paused" if action == "queue.pause" else "repeat"
            after = result.get("value")
            try:
                self._queue_digest(after)
                valid = (result.get("schema") == "rbbec-unified-result/1" and result.get("action") == action and
                         result.get("request_id") == request["request_id"] and result.get("request_sha256") == _digest(request) and
                         after["host_generation"] == request["expected_host_generation"] and after[key] is payload["value"])
            except ValueError:
                valid = False
            if not valid:
                return {"state": "UNKNOWN", "reason": "Queue receipt does not bind the plan and readback",
                        "request_id": request["request_id"], "no_automatic_retry": True}
        return result

    def snapshot(self, device):
        if type(device) is not str or not device.strip():
            raise ValueError("An exact BLACS device name is required")
        value = _observed(self.gateway.read_blacs("snapshot", device=device), "snapshot")
        if value.get("device") != device:
            raise RuntimeError("The BLACS snapshot describes a different device")
        return value

    def status(self):
        value = self.discover()
        return {"ok": True, "service": "labpilot-real-blacs-bridge", "backend": "local_gateway",
                "queue": value["queue"], "devices": value["devices"]}

    def discover_channels(self):
        return [row for device in self.discover()["devices"]
                for row in _channel_rows(device["device"], device["channels"])]

    def get_values(self):
        values = {}
        devices = [device for device in self.discover()["devices"] if device["channels"]]
        for device in devices:
            if device.get("mode") != "MANUAL" or device.get("error_present") is not False:
                raise RuntimeError(f"BLACS readback requires a ready manual device: {device['device']}")
        for device in devices:
            snapshot = self.snapshot(device["device"])
            registers = snapshot.get("register_readback")
            evidence = "device_register_readback" if isinstance(registers, dict) else "front_panel"
            for row in _channel_rows(snapshot["device"], snapshot["channels"],
                                     registers if isinstance(registers, dict) else snapshot["front_panel"]):
                values[row["name"]] = {"value": row["current_value"], "evidence": evidence}
        return values

    @staticmethod
    def prepare_manual(snapshot, channel, value, *, approver, instruction, subchannel=None,
                       ttl_seconds=90):
        """Prepare one request from a fresh exact snapshot without contacting BLACS."""
        if any(type(text) is not str or not text.strip() for text in (approver, instruction)):
            raise ValueError("An explicit approver and actual operator instruction are required")
        _check_operator(approver)
        if type(ttl_seconds) is not int or not 1 <= ttl_seconds <= 120:
            raise ValueError("BLACS request lifetime must be 1 to 120 seconds")
        if type(snapshot) is not dict or not set(_SNAPSHOT_FIELDS).issubset(snapshot):
            raise ValueError("A full BLACS device snapshot is required")
        if snapshot["family"] not in _MANUAL_FAMILIES:
            raise ValueError("This BLACS device does not support the reviewed manual write profile")
        fields = {key: snapshot[key] for key in _SNAPSHOT_FIELDS}
        if "special" in snapshot:
            fields["special"] = snapshot["special"]
        if snapshot.get("snapshot_sha256") != _digest(fields):
            raise ValueError("BLACS snapshot digest mismatch")
        now = datetime.now(timezone.utc)
        if not -5 <= (now - _timestamp(snapshot.get("observed_at_utc"))).total_seconds() <= 120:
            raise ValueError("BLACS snapshot expired or dated in the future")
        if (not re.fullmatch(r"[0-9a-f]{32}", str(snapshot["host_generation"])) or
                not re.fullmatch(r"[0-9a-f]{64}", str(snapshot["connection_sha256"]))):
            raise ValueError("BLACS snapshot has no valid generation or connection table binding")
        if type(channel) is not str or channel not in snapshot["channels"] or channel not in snapshot["front_panel"]:
            raise ValueError("An exact channel in the live BLACS snapshot is required")
        descriptor = snapshot["channels"][channel]
        kind = descriptor.get("kind")
        if kind == "DDS":
            proposed = {subchannel: value} if subchannel is not None else value
            subs = descriptor["subchannels"]
            if type(proposed) is not dict or not proposed or not set(proposed).issubset(subs):
                raise ValueError("DDS changes require exact subchannel names")
            proposed = {key: _base_value(item, subs[key]) for key, item in proposed.items()}
        else:
            if subchannel is not None:
                raise ValueError("Only DDS channels support subchannel changes")
            proposed = _base_value(value, descriptor)
        return {
            "schema": "rbbec-unified/1", "request_id": uuid.uuid4().hex, "action": "manual.apply",
            "issued_at_utc": now.isoformat(),
            "expires_at_utc": (now + timedelta(seconds=ttl_seconds)).isoformat(),
            "expected_host_generation": snapshot["host_generation"],
            "connection_sha256": snapshot["connection_sha256"],
            "approval_context": {"approver": approver, "instruction": instruction},
            "payload": {"device": snapshot["device"],
                        "expected_snapshot_sha256": snapshot["snapshot_sha256"],
                        "changes": {channel: {"kind": kind, "value": proposed}}},
        }

    def apply_manual(self, request):
        """Submit the same approved request once and return its actual receipt."""
        if (not isinstance(request, dict) or request.get("schema") != "rbbec-unified/1" or
                request.get("action") != "manual.apply"):
            raise ValueError("A prepared BLACS manual.apply request is required")
        _check_operator(request["approval_context"]["approver"])
        result = self.gateway.call("blacs", request)
        if result.get("state") == "APPLIED":
            payload = request["payload"]
            value = result.get("value")
            if (result.get("schema") != "rbbec-unified-result/1" or
                    result.get("request_id") != request["request_id"] or result.get("action") != request["action"] or
                    not isinstance(value, dict) or value.get("device") != payload["device"] or
                    not isinstance(value.get("after"), dict) or not set(payload["changes"]).issubset(value["after"])):
                return {"state": "UNKNOWN", "request_id": request["request_id"],
                        "reason": "BLACS write receipt does not bind the submitted request and channels",
                        "no_automatic_retry": True}
        return result

    def prepare_selected_manual(self, name, value, *, device=None, channel=None, unit=None,
                                subchannel=None, approver=None, instruction=None):
        """Read the exact registered device and prepare its reviewed change."""
        if any(type(text) is not str or not text.strip() for text in (device, channel, approver, instruction)):
            raise ValueError("Local BLACS writes require exact device and channel plus explicit operator approval")
        snapshot = self.snapshot(device)
        descriptor = snapshot["channels"].get(channel, {})
        if subchannel is None and descriptor.get("kind") == "DDS":
            for sub in descriptor.get("subchannels", {}):
                if name == f"{device}.{channel}.{sub}":
                    subchannel = sub
                    break
        unit_descriptor = descriptor.get("subchannels", {}).get(subchannel, {}) if subchannel else descriptor
        if unit and unit != unit_descriptor.get("units"):
            raise ValueError("Use the exact base unit reported by the live BLACS snapshot")
        return self.prepare_manual(snapshot, channel, value, approver=approver,
                                   instruction=instruction, subchannel=subchannel)

    def apply_selected_manual(self, request):
        """Translate the native receipt to the existing LabPilot UI format."""
        changes = request.get("payload", {}).get("changes", {})
        if not isinstance(changes, dict) or len(changes) != 1:
            raise ValueError("The LabPilot manual panel accepts exactly one output per request")
        channel, change = next(iter(changes.items()))
        subchannel = None
        if change.get("kind") == "DDS" and isinstance(change.get("value"), dict) and len(change["value"]) == 1:
            subchannel = next(iter(change["value"]))
        result = self.apply_manual(request)
        state = result.get("state")
        if state != "APPLIED":
            reason = result.get("error") or result.get("reason") or "invalid receipt"
            raise RuntimeError(f"BLACS manual request {request['request_id']} returned {state or 'UNKNOWN'}: {reason}")
        outcome = result.get("value", {})
        after = outcome.get("after", {}).get(channel)
        if subchannel is not None and isinstance(after, dict):
            after = after.get(subchannel)
        return {**result, "ok": True, "front_panel_value": after, "evidence": outcome.get("evidence")}

    def set_manual(self, name, value, *, program, **extra):
        if program is not True:
            raise ValueError("Local BLACS writes require explicit hardware programming")
        return self.apply_selected_manual(self.prepare_selected_manual(name, value, **extra))
