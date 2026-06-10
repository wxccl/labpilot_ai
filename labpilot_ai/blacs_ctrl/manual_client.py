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
            return json.loads(resp.read().decode("utf-8"))
