from __future__ import annotations

import json
from urllib import error, request


class BlacsBridgeConnectionError(ConnectionError):
    pass


class BlacsManualClient:
    """Client for LabPilot BLACS manual bridges.

    mock=True keeps all values local. mock=False talks to a localhost bridge.
    A real BLACS bridge reports service='labpilot-real-blacs-bridge'.
    The legacy placeholder bridge reports service='labpilot-blacs-manual-bridge'.
    """

    def __init__(self, host="127.0.0.1", port=8765, mock=True, token=None):
        self.host = host
        self.port = int(port)
        self.mock = bool(mock)
        self.token = token
        self.values = {}

    @property
    def base_url(self) -> str:
        return f"http://{self.host}:{self.port}"

    def _headers(self):
        headers = {"Content-Type": "application/json"}
        if self.token:
            headers["X-LabPilot-Token"] = self.token
        return headers

    def _get_json(self, path: str, timeout=10):
        try:
            req = request.Request(f"{self.base_url}{path}", headers=self._headers(), method="GET")
            with request.urlopen(req, timeout=timeout) as resp:
                text = resp.read().decode("utf-8")
        except error.URLError as exc:
            raise BlacsBridgeConnectionError(f"Cannot connect to BLACS bridge at {self.base_url}: {exc}") from exc
        try:
            return json.loads(text)
        except Exception:
            return {"ok": True, "raw": text}

    def _post_json(self, path: str, payload: dict, timeout=10):
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        try:
            req = request.Request(f"{self.base_url}{path}", data=data, headers=self._headers(), method="POST")
            with request.urlopen(req, timeout=timeout) as resp:
                text = resp.read().decode("utf-8")
        except error.HTTPError as exc:
            try:
                body = exc.read().decode("utf-8")
                payload = json.loads(body)
                raise RuntimeError(payload.get("error") or body) from exc
            except RuntimeError:
                raise
            except Exception:
                raise RuntimeError(str(exc)) from exc
        except error.URLError as exc:
            raise BlacsBridgeConnectionError(f"Cannot connect to BLACS bridge at {self.base_url}: {exc}") from exc
        return json.loads(text)

    def status(self):
        if self.mock:
            return {"ok": True, "service": "mock-blacs-bridge", "mock": True}
        return self._get_json("/status", timeout=5)

    def test(self):
        payload = self.status()
        service = payload.get("service", "unknown")
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
        payload = self._get_json("/channels", timeout=10)
        if isinstance(payload, dict) and payload.get("ok") is False:
            raise RuntimeError(payload.get("error") or "BLACS bridge channel discovery failed")
        return payload.get("channels", payload if isinstance(payload, list) else [])

    def get_values(self):
        if self.mock:
            return dict(self.values)
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

        last_error = None
        attempted = []
        for candidate in _manual_name_candidates(name, extra):
            payload = _manual_payload_for_candidate(candidate, value, program, extra)
            attempted.append(candidate)
            try:
                result = self._post_json("/set_manual", payload, timeout=10)
            except RuntimeError as exc:
                last_error = exc
                if "not found" in str(exc).lower():
                    continue
                raise
            if isinstance(result, dict) and result.get("ok") is False:
                message = result.get("error") or "BLACS bridge manual write failed"
                last_error = RuntimeError(message)
                if "not found" in message.lower():
                    continue
                raise last_error
            if isinstance(result, dict):
                result.setdefault("attempted_names", attempted)
                result.setdefault("requested_name", name)
            return result
        if last_error is not None:
            available = self._available_channel_names_for_error()
            raise RuntimeError(f"{last_error}; attempted BLACS names: {attempted}; available BLACS names: {available}") from last_error
        payload = {"name": name, "value": value, "program": bool(program)}
        payload.update(extra)
        result = self._post_json("/set_manual", payload, timeout=10)
        if isinstance(result, dict) and result.get("ok") is False:
            raise RuntimeError(result.get("error") or "BLACS bridge manual write failed")
        return result


    def _available_channel_names_for_error(self):
        try:
            channels = self.discover_channels()
        except Exception as exc:
            return f"unavailable ({exc})"
        names = []
        for channel in channels:
            if isinstance(channel, dict):
                for key in ("name", "labscript_name", "channel"):
                    value = channel.get(key)
                    if value and str(value) not in names:
                        names.append(str(value))
        return names[:50]


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


def _manual_payload_for_candidate(candidate, value, program, extra):
    payload = {"name": candidate, "value": value, "program": bool(program)}
    payload.update(extra)
    payload["name"] = candidate
    if payload.get("unit") in {None, ""}:
        payload.pop("unit", None)

    device = str(extra.get("device", "") or "").strip()
    channel = str(extra.get("channel", "") or "").strip()
    device_channel = f"{device}.{channel}" if device and channel else ""

    # Older bridge versions prioritise device/channel over name. When trying a
    # labscript object name such as rf_switch or LabPilotVirtualDevice.rf_switch,
    # remove the stale connection-string fields so the candidate name is used.
    if candidate != device_channel:
        payload.pop("device", None)
        payload.pop("channel", None)
        payload.pop("subchannel", None)
    elif candidate == channel:
        payload.pop("device", None)
    return payload
