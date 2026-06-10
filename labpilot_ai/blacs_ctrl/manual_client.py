import json
from urllib import request


class BlacsManualClient:
    """Placeholder client for BLACS localhost bridge."""
    def __init__(self, host="127.0.0.1", port=8765, mock=True):
        self.host = host
        self.port = port
        self.mock = mock
        self.values = {}

    def test(self):
        if self.mock:
            return "mock-blacs-bridge: ok"
        with request.urlopen(f"http://{self.host}:{self.port}/status", timeout=5) as resp:
            return resp.read().decode("utf-8")

    def discover_channels(self):
        if self.mock:
            return [
                {
                    "name": name,
                    "kind": "manual",
                    "device": "mock",
                    "channel": name,
                    "type": "float" if not isinstance(value, bool) else "bool",
                    "current_value": value,
                    "risk": "low",
                }
                for name, value in sorted(self.values.items())
            ]
        with request.urlopen(f"http://{self.host}:{self.port}/channels", timeout=10) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
        if isinstance(payload, dict) and payload.get("ok") is False:
            raise RuntimeError(payload.get("error") or "BLACS bridge channel discovery failed")
        return payload.get("channels", payload if isinstance(payload, list) else [])

    def get_values(self):
        if self.mock:
            return dict(self.values)
        with request.urlopen(f"http://{self.host}:{self.port}/values", timeout=10) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
        if isinstance(payload, dict) and payload.get("ok") is False:
            raise RuntimeError(payload.get("error") or "BLACS bridge value readback failed")
        return payload.get("values", payload if isinstance(payload, dict) else {})

    def set_manual(self, name, value, program=False):
        if self.mock:
            self.values[name] = value
            return {"mock": True, "name": name, "value": value, "program": program}
        payload = json.dumps({"name": name, "value": value, "program": bool(program)}).encode("utf-8")
        req = request.Request(
            f"http://{self.host}:{self.port}/set_manual",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with request.urlopen(req, timeout=10) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
        if isinstance(payload, dict) and payload.get("ok") is False:
            raise RuntimeError(payload.get("error") or "BLACS bridge manual write failed")
        return payload
