import json
from http.server import BaseHTTPRequestHandler, HTTPServer


class ManualBridgeState:
    def __init__(self):
        self.values = {}

    def set_manual(self, name, value, program=False):
        self.values[name] = {"value": value, "program": bool(program)}
        return {"ok": True, "name": name, "value": value, "program": bool(program)}


def make_handler(state: ManualBridgeState):
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            if self.path == "/status":
                self._send({"ok": True, "service": "labpilot-blacs-manual-bridge", "values": state.values})
            else:
                self.send_error(404)

        def do_POST(self):
            if self.path != "/set_manual":
                self.send_error(404)
                return
            length = int(self.headers.get("Content-Length", "0"))
            payload = json.loads(self.rfile.read(length).decode("utf-8"))
            self._send(state.set_manual(payload.get("name"), payload.get("value"), payload.get("program", False)))

        def log_message(self, fmt, *args):
            return

        def _send(self, payload):
            data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

    return Handler


def serve(host="127.0.0.1", port=8765):
    state = ManualBridgeState()
    server = HTTPServer((host, port), make_handler(state))
    server.serve_forever()
