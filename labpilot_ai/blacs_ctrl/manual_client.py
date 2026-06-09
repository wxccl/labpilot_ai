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
        raise NotImplementedError("HTTP bridge client not implemented in starter. Add requests/httpx later.")

    def set_manual(self, name, value, program=False):
        if self.mock:
            self.values[name] = value
            return {"mock": True, "name": name, "value": value, "program": program}
        raise NotImplementedError("BLACS bridge is a later milestone.")
