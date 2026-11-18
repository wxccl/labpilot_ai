from __future__ import annotations

import json
import os
from ipaddress import IPv4Address
from urllib import error, request

from labpilot_ai.local_control.transport import local_gateway_enabled

from .local_gateway import LocalBlacs


class _NoRedirect(request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class BlacsBridgeConnectionError(ConnectionError):
    pass


class BlacsManualClient:
    """Client for LabPilot BLACS manual bridges.

    mock=True keeps all values local. mock=False talks to a localhost bridge.
    A real BLACS bridge reports service='labpilot-real-blacs-bridge'.
    The legacy placeholder bridge reports service='labpilot-blacs-manual-bridge'.
    """

    def __init__(self, host="127.0.0.1", port=8765, mock=True, token=None, *, local_gateway=None):
        if not mock and str(host).lower() != "localhost" and not IPv4Address(host).is_loopback:
            raise ValueError("Legacy BLACS HTTP requires IPv4 loopback")
        self.host = "127.0.0.1" if str(host).lower() == "localhost" else host
        self.port = int(port)
        self.mock = bool(mock)
        self.token = os.getenv("LABPILOT_BLACS_TOKEN", "") if token is None else token
        self.values = {}
        self.local = None
        if not self.mock and (local_gateway is not None or local_gateway_enabled()):
            self.local = LocalBlacs(local_gateway)

    @property
    def base_url(self) -> str:
        if self.local is not None:
            return "local BLACS gateway"
        return f"http://{self.host}:{self.port}"

    @property
    def uses_local_gateway(self):
        return self.local is not None

    def prepare_local_manual(self, name, value, *, approver, instruction, **extra):
        if self.local is None:
            raise ValueError("Local BLACS gateway mode is required to prepare a manual request")
        fields = ("device", "channel", "unit", "subchannel")
        return self.local.prepare_selected_manual(name, value, approver=approver, instruction=instruction,
                                                  **{key: extra[key] for key in fields if key in extra})

    def apply_local_manual(self, request):
        if self.local is None:
            raise ValueError("Local BLACS gateway mode is required to apply a prepared manual request")
        return self.local.apply_selected_manual(request)

    def _headers(self):
        headers = {"Content-Type": "application/json"}
        if self.token:
            headers["X-LabPilot-Token"] = self.token
        return headers

    def _get_json(self, path: str, timeout=10):
        try:
            req = request.Request(f"{self.base_url}{path}", headers=self._headers(), method="GET")
            with request.build_opener(request.ProxyHandler({}), _NoRedirect()).open(req, timeout=timeout) as resp:
                text = resp.read().decode("utf-8")
        except error.URLError as exc:
            raise BlacsBridgeConnectionError(f"Cannot connect to BLACS bridge at {self.base_url}: {exc}") from exc
        try:
            return json.loads(text)
        except Exception:
            return {"ok": True, "raw": text}

    def status(self):
        if self.mock:
            return {"ok": True, "service": "mock-blacs-bridge", "mock": True}
        if self.local is not None:
            return self.local.status()
        return self._get_json("/status", timeout=5)

    def test(self):
        payload = self.status()
        service = payload.get("service", "unknown")
        if payload.get("backend") == "local_gateway":
            return "connected to running BLACS via the local gateway"
        if service == "mock-blacs-bridge":
            return "mock-blacs-bridge: ok"
        if service == "labpilot-real-blacs-bridge":
            return "connected to real running BLACS bridge"
        if service == "labpilot-blacs-manual-bridge":
            return "connected to placeholder bridge only; not real BLACS hardware"
        return json.dumps(payload, ensure_ascii=False)

    def is_real_bridge(self) -> bool:
        return self.status().get("service") == "labpilot-real-blacs-bridge"

    def debug(self):
        if self.mock:
            return {"ok": True, "mock": True, "values": dict(self.values)}
        if self.local is not None:
            return self.local.status()
        return self._get_json("/debug", timeout=10)

    def discover_channels(self):
        if self.mock:
            return [
                {
                    "name": name,
                    "bridge_name": name,
                    "kind": "manual",
                    "device": "mock",
                    "channel": name,
                    "type": "float" if not isinstance(value, bool) else "bool",
                    "current_value": value,
                    "risk": "low",
                    "require_confirm": False,
                }
                for name, value in sorted(self.values.items())
            ]
        if self.local is not None:
            return self.local.discover_channels()
        payload = self._get_json("/channels", timeout=10)
        if isinstance(payload, dict) and payload.get("ok") is False:
            raise RuntimeError(payload.get("error") or "BLACS bridge channel discovery failed")
        return payload.get("channels", payload if isinstance(payload, list) else [])

    def get_values(self):
        if self.mock:
            return dict(self.values)
        if self.local is not None:
            return self.local.get_values()
        payload = self._get_json("/values", timeout=10)
        if isinstance(payload, dict) and payload.get("ok") is False:
            raise RuntimeError(payload.get("error") or "BLACS bridge value readback failed")
        return payload.get("values", payload if isinstance(payload, dict) else {})

    def set_manual(self, name, value, program=False, **extra):
        if self.mock:
            self.values[name] = value
            for alias in _manual_name_candidates(name, extra):
                self.values.setdefault(alias, value)
            return {"mock": True, "ok": True, "name": name, "value": value, "program": program}

        if self.local is not None:
            fields = ("device", "channel", "unit", "subchannel", "approver", "instruction")
            return self.local.set_manual(name, value, program=program,
                                         **{key: extra[key] for key in fields if key in extra})

        raise PermissionError("Legacy HTTP is read-only; use a managed labpilot A2/A3 task")


def _manual_name_candidates(name, extra):
    candidates = []

    def add(value):
        text = str(value or "").strip()
        if text and text not in candidates:
            candidates.append(text)

    add(name)
    device = extra.get("device")
    channel = extra.get("channel")
    if device and name and "." not in str(name):
        add(f"{device}.{name}")
    add(extra.get("bridge_name"))
    if device and channel:
        add(f"{device}.{channel}")
    add(channel)
    for alias in extra.get("aliases", []) or []:
        add(alias)
        if device and alias and "." not in str(alias):
            add(f"{device}.{alias}")
    return candidates or [str(name)]
