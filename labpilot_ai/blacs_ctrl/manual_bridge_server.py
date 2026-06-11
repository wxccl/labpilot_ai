from __future__ import annotations

import argparse
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any


class ManualBridgeState:
    """
    Placeholder bridge state.

    This server is for UI/HTTP testing only. It does not control real BLACS hardware.
    The real bridge must run inside the BLACS process as a BLACS plugin.
    """

    def __init__(self):
        self.values: dict[str, Any] = {}
        self.channels: list[dict[str, Any]] = []

    def set_manual(self, name: str, value: Any, program: bool = False) -> dict[str, Any]:
        if not name:
            return {"ok": False, "error": "missing manual channel name"}
        self.values[name] = value
        if not any(item.get("name") == name for item in self.channels):
            self.channels.append(
                {
                    "name": name,
                    "kind": "manual",
                    "device": "placeholder",
                    "channel": name,
                    "type": "bool" if isinstance(value, bool) else "float",
                    "current_value": value,
                    "risk": "low",
                    "bridge_type": "placeholder",
                }
            )
        else:
            for item in self.channels:
                if item.get("name") == name:
                    item["current_value"] = value
        return {"ok": True, "name": name, "value": value, "program": bool(program), "placeholder": True}


def make_handler(state: ManualBridgeState):
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            if self.path == "/status":
                self._send(
                    {
                        "ok": True,
                        "service": "labpilot-blacs-manual-bridge",
                        "bridge_type": "placeholder",
                        "is_real_blacs": False,
                        "warning": "This is a placeholder bridge. It does not control real BLACS hardware.",
                        "values": state.values,
                    }
                )
                return
            if self.path == "/channels":
                self._send({"ok": True, "channels": state.channels})
                return
            if self.path == "/values":
                self._send({"ok": True, "values": state.values})
                return
            self.send_error(404)

        def do_POST(self):
            if self.path != "/set_manual":
                self.send_error(404)
                return
            try:
                length = int(self.headers.get("Content-Length", "0"))
                payload = json.loads(self.rfile.read(length).decode("utf-8") or "{}")
                result = state.set_manual(payload.get("name"), payload.get("value"), payload.get("program", False))
                self._send(result, status=200 if result.get("ok") else 400)
            except Exception as exc:
                self._send({"ok": False, "error": repr(exc)}, status=500)

        def log_message(self, fmt, *args):
            return

        def _send(self, payload: dict[str, Any], status: int = 200):
            data = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

    return Handler


def serve(host: str = "127.0.0.1", port: int = 8765):
    state = ManualBridgeState()
    server = ThreadingHTTPServer((host, int(port)), make_handler(state))
    print(f"LabPilot placeholder BLACS bridge listening at http://{host}:{port}/status")
    print("WARNING: placeholder bridge only stores values in memory; it does NOT control real BLACS hardware.")
    server.serve_forever()


def main():
    parser = argparse.ArgumentParser(description="Start LabPilot placeholder BLACS manual bridge.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()
    serve(args.host, args.port)


if __name__ == "__main__":
    main()
