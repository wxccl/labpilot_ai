from __future__ import annotations

import json
import math
import os
import threading
from hmac import compare_digest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from ipaddress import IPv4Address
from urllib.parse import urlparse

from .accessor import BLACSAccessor, json_safe

name = "LabPilot Bridge"
module = "labpilot_bridge"
MAX_REQUEST_BYTES = 64 * 1024
READ_TIMEOUT_SECONDS = 5


def _finite_float(value: str) -> float:
    number = float(value)
    if not math.isfinite(number):
        raise ValueError("Non-finite JSON number")
    return number


def _env_truthy(name_: str, default: bool = False) -> bool:
    value = os.environ.get(name_)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


class Plugin(object):
    """BLACS plugin exposing real front-panel manual controls to LabPilot AI.

    This plugin must run inside BLACS. It starts a localhost HTTP server and
    uses BLACS DeviceTab.get_front_panel_values(), DeviceTab.get_channel(), and
    output.set_value(..., program=True) so writes go through the normal BLACS
    front-panel/program_manual state-machine path.
    """

    def __init__(self, initial_settings=None):
        self.initial_settings = initial_settings or {}
        self.BLACS = None
        self.accessor = None
        self.server = None
        self.thread = None
        self.host = os.environ.get("LABPILOT_BLACS_BRIDGE_HOST", "127.0.0.1")
        self.port = int(os.environ.get("LABPILOT_BLACS_BRIDGE_PORT", "8765"))
        self.allow_write = _env_truthy("LABPILOT_BLACS_ALLOW_WRITE", False)
        self.token = os.environ.get("LABPILOT_BLACS_TOKEN", "")

    def get_menu_class(self):
        return None

    def get_notification_classes(self):
        return []

    def get_setting_classes(self):
        return []

    def get_callbacks(self):
        return {}

    def set_menu_instance(self, menu):
        pass

    def set_notification_instances(self, notifications):
        pass

    def get_save_data(self):
        return {}

    def plugin_setup_complete(self, BLACS):
        self.BLACS = BLACS
        self._read_labconfig_options(BLACS)
        self.accessor = BLACSAccessor(BLACS)
        self.start_server()

    def _read_labconfig_options(self, BLACS):
        try:
            exp_config = BLACS.get("exp_config") if isinstance(BLACS, dict) else None
            if exp_config is None:
                return
            self.host = exp_config.get("BLACS/plugins", "labpilot_bridge.host") if exp_config.has_option("BLACS/plugins", "labpilot_bridge.host") else self.host
            self.port = exp_config.getint("BLACS/plugins", "labpilot_bridge.port") if exp_config.has_option("BLACS/plugins", "labpilot_bridge.port") else self.port
            if exp_config.has_option("BLACS/plugins", "labpilot_bridge.allow_write"):
                self.allow_write = exp_config.getboolean("BLACS/plugins", "labpilot_bridge.allow_write")
            if exp_config.has_option("BLACS/plugins", "labpilot_bridge.token"):
                self.token = exp_config.get("BLACS/plugins", "labpilot_bridge.token")
        except Exception:
            # Never prevent BLACS startup due to LabPilot plugin config parsing.
            pass

    def close(self):
        if self.server:
            try:
                self.server.shutdown()
                self.server.server_close()
            except Exception:
                pass
            self.server = None

    def start_server(self):
        host = self.host.strip()
        if host.lower() == "localhost":
            host = "127.0.0.1"
        try:
            address = IPv4Address(host)
        except ValueError as exc:
            raise ValueError("BLACS bridge requires a local IPv4 loopback address") from exc
        if not address.is_loopback:
            raise ValueError("BLACS bridge requires a local IPv4 loopback address")
        self.host = str(address)
        plugin = self
        token = self.token.strip().encode("utf-8")
        writes_enabled = self.allow_write and bool(token)

        class Handler(BaseHTTPRequestHandler):
            timeout = READ_TIMEOUT_SECONDS

            def _authorised(self) -> bool:
                if not token:
                    return True
                headers = self.headers.get_all("X-LabPilot-Token", [])
                return len(headers) == 1 and compare_digest(headers[0].encode("utf-8"), token)

            def do_GET(self):
                if not self._authorised():
                    self._send({"ok": False, "error": "unauthorised"}, status=401)
                    return
                path = urlparse(self.path).path
                try:
                    if path == "/status":
                        payload = plugin.accessor.status()
                        payload.update({"allow_write": writes_enabled, "token_required": bool(token)})
                        self._send(payload)
                    elif path == "/debug":
                        self._send(plugin.accessor.debug())
                    elif path == "/channels":
                        self._send({"ok": True, "service": "labpilot-real-blacs-bridge", "channels": plugin.accessor.discover_channels()})
                    elif path == "/values":
                        self._send({"ok": True, "service": "labpilot-real-blacs-bridge", "values": plugin.accessor.values()})
                    else:
                        self.send_error(404)
                except Exception as exc:
                    self._send({"ok": False, "error": str(exc)}, status=500)

            def do_POST(self):
                if not self._authorised():
                    self._send({"ok": False, "error": "unauthorised"}, status=401)
                    return
                path = urlparse(self.path).path
                if path != "/set_manual":
                    self.send_error(404)
                    return
                if not writes_enabled:
                    self._send({"ok": False, "error": "BLACS bridge writes require explicit enablement and a header token"}, status=403)
                    return
                lengths = self.headers.get_all("Content-Length", [])
                if self.headers.get("Transfer-Encoding") or len(lengths) != 1:
                    self._send({"ok": False, "error": "A single Content-Length is required"}, status=400)
                    return
                length_text = lengths[0]
                if len(length_text) > 10 or not length_text.isascii() or not length_text.isdecimal():
                    self._send({"ok": False, "error": "Invalid Content-Length"}, status=400)
                    return
                length = int(length_text)
                if length < 1:
                    self._send({"ok": False, "error": "Invalid Content-Length"}, status=400)
                    return
                if length > MAX_REQUEST_BYTES:
                    self._send({"ok": False, "error": "Request body exceeds the bridge limit"}, status=413)
                    return
                try:
                    raw = self.rfile.read(length)
                except TimeoutError:
                    self._send({"ok": False, "error": "Request body timed out"}, status=408)
                    return
                if len(raw) != length:
                    self._send({"ok": False, "error": "Incomplete request body"}, status=400)
                    return
                try:
                    payload = json.loads(raw.decode("utf-8"), parse_float=_finite_float, parse_constant=_finite_float)
                except (ValueError, RecursionError):
                    self._send({"ok": False, "error": "Invalid JSON request body"}, status=400)
                    return
                if not isinstance(payload, dict):
                    self._send({"ok": False, "error": "Request body must be a JSON object"}, status=400)
                    return
                try:
                    result = plugin.accessor.set_manual(payload, allow_write=writes_enabled)
                    self._send(result, status=200 if result.get("ok") else 400)
                except Exception as exc:
                    self._send({"ok": False, "error": str(exc)}, status=500)

            def log_message(self, fmt, *args):
                return

            def _send(self, payload, status=200):
                data = json.dumps(json_safe(payload), ensure_ascii=False, indent=2).encode("utf-8")
                self.send_response(status)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

        self.server = ThreadingHTTPServer((self.host, self.port), Handler)
        self.server.daemon_threads = True
        self.thread = threading.Thread(target=self.server.serve_forever, name="LabPilotRealBLACSBridge", daemon=True)
        self.thread.start()
        print(f"LabPilot real BLACS bridge listening at http://{self.host}:{self.port}/status")


def diagnostic_main() -> int:
    """Print installation and readback guidance without starting a server."""
    print("BLACS loads labpilot_ai.blacs_bridge.plugin.Plugin in its own process.")
    print("For legacy readback, run tools/install_real_blacs_bridge.py --disable-write in the Labscript environment.")
    print("After a normal BLACS restart, GET http://127.0.0.1:8765/status.")
    print("Expected service: labpilot-real-blacs-bridge; expected allow_write: false.")
    print("For guarded same-machine control, configure the local gateway and use labpilot-control.")
    return 0
