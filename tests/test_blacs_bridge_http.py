from email.message import Message
from io import BytesIO

import pytest

from labpilot_ai.blacs_bridge import plugin as bridge


def test_diagnostic_entrypoint_prints_readonly_guidance(capsys, monkeypatch):
    def unexpected_server(*args, **kwargs):
        pytest.fail("diagnostic entry point started a server")

    monkeypatch.setattr(bridge, "ThreadingHTTPServer", unexpected_server)
    monkeypatch.setenv("LABPILOT_BLACS_TOKEN", "example-private-value")
    assert bridge.diagnostic_main() == 0
    output = capsys.readouterr().out
    assert "--disable-write" in output
    assert "labpilot-control" in output
    assert "example-private-value" not in output


class FakeAccessor:
    def __init__(self):
        self.writes = []

    def status(self):
        return {"ok": True, "service": "labpilot-real-blacs-bridge"}

    def discover_channels(self):
        return [{"name": "Example.ao0"}]

    def values(self):
        return {"Example.ao0": 1.5}

    def set_manual(self, payload, *, allow_write):
        self.writes.append((payload, allow_write))
        return {"ok": True}


@pytest.fixture
def make_bridge(monkeypatch):
    class FakeServer:
        def __init__(self, address, handler):
            self.server_address = address
            self.RequestHandlerClass = handler

        def serve_forever(self):
            pass

    monkeypatch.setattr(bridge, "ThreadingHTTPServer", FakeServer)

    def make(host="localhost", token="", allow_write=False):
        instance = bridge.Plugin()
        instance.host = host
        instance.port = 8765
        instance.token = token
        instance.allow_write = allow_write
        instance.accessor = FakeAccessor()
        instance.start_server()
        return instance

    return make


def request(instance, method, path, headers=(), body=b""):
    handler = object.__new__(instance.server.RequestHandlerClass)
    handler.path = path
    handler.headers = Message()
    for key, value in headers:
        handler.headers[key] = value
    handler.rfile = BytesIO(body)
    response = []
    handler._send = lambda payload, status=200: response.append((status, payload))
    getattr(handler, f"do_{method}")()
    return response[0], handler.rfile.tell()


@pytest.mark.parametrize("host", ["0.0.0.0", "192.0.2.1", "example.com"])
def test_legacy_bridge_refuses_non_loopback_binding(make_bridge, host):
    with pytest.raises(ValueError, match="loopback"):
        make_bridge(host=host)


def test_missing_token_leaves_discovery_and_values_read_only(make_bridge):
    instance = make_bridge(token="  ", allow_write=True)
    assert instance.server.server_address == ("127.0.0.1", 8765)
    assert request(instance, "GET", "/status")[0][1]["allow_write"] is False
    assert request(instance, "GET", "/channels")[0][1]["channels"] == [{"name": "Example.ao0"}]
    assert request(instance, "GET", "/values")[0][1]["values"] == {"Example.ao0": 1.5}
    assert request(instance, "POST", "/set_manual")[0][0] == 403
    assert instance.accessor.writes == []


def test_only_an_exact_single_header_token_authenticates(make_bridge):
    instance = make_bridge(token="example-token", allow_write=True)
    token = ("X-LabPilot-Token", "example-token")
    assert request(instance, "GET", "/status?token=example-token")[0][0] == 401
    assert request(instance, "GET", "/status", [token, token])[0][0] == 401
    assert request(instance, "GET", "/status", [token])[0][0] == 200
    body = b'{"name":"Example.ao0","value":1.5}'
    headers = [token, ("Content-Length", str(len(body)))]
    assert request(instance, "POST", "/set_manual", headers, body)[0][0] == 200
    assert instance.accessor.writes == [({"name": "Example.ao0", "value": 1.5}, True)]


def test_oversize_body_is_rejected_before_reading(make_bridge):
    instance = make_bridge(token="example-token", allow_write=True)
    headers = [("X-LabPilot-Token", "example-token"), ("Content-Length", str(bridge.MAX_REQUEST_BYTES + 1))]
    (status, _), bytes_read = request(instance, "POST", "/set_manual", headers, b"unread")
    assert (status, bytes_read, instance.accessor.writes) == (413, 0, [])


@pytest.mark.parametrize("body", [b"[]", b"{", b'{"value":NaN}', b'{"value":1e999}'])
def test_invalid_manual_payload_never_reaches_accessor(make_bridge, body):
    instance = make_bridge(token="example-token", allow_write=True)
    headers = [("X-LabPilot-Token", "example-token"), ("Content-Length", str(len(body)))]
    assert request(instance, "POST", "/set_manual", headers, body)[0][0] == 400
    assert instance.accessor.writes == []
