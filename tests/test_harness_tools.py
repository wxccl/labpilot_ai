from hashlib import sha256
from io import BytesIO, StringIO
import json

import pytest

from labpilot_ai.harness import ToolError, build_catalog
from labpilot_ai.harness.deepseek import DeepSeekHTTP, DeepSeekProvider, ProviderError
from labpilot_ai.harness.mcp_stdio import serve


@pytest.fixture
def dispatcher():
    calls = []

    def task(operation, arguments):
        calls.append((operation, arguments))
        return {"operation": operation, "arguments": arguments}

    return task, calls


def test_catalog_validates_and_exposes_only_read_and_prepare(dispatcher):
    task, calls = dispatcher
    catalog = build_catalog(task)
    names = [tool["name"] for tool in catalog.describe()]
    assert names == [
        "experiment_discover", "experiment_snapshot", "experiment_status", "experiment_prepare",
    ]
    with pytest.raises(ToolError, match="Unknown tool"):
        catalog.invoke("experiment_execute", {})
    with pytest.raises(ToolError, match="unknown field"):
        catalog.invoke("experiment_status", {"task_id": "a", "execute": True})
    with pytest.raises(ToolError, match="JSON integer"):
        catalog.invoke("experiment_prepare", {
            "target": "runmanager", "action": "engage_once", "values": {}, "expected_n_shots": True,
        })
    assert not calls
    result = catalog.invoke("experiment_prepare", {
        "target": "runmanager", "action": "set_globals", "values": {"example": [1, 2]},
    })
    assert result["operation"] == "prepare"
    assert result["arguments"]["values"] == {"example": [1, 2]}
    assert calls == [("prepare", result["arguments"])]


def test_catalog_does_not_expose_exception_details():
    def failed(_operation, _arguments):
        raise KeyError("private detail")

    with pytest.raises(ToolError, match=r"^Tool operation failed"):
        build_catalog(failed).invoke("experiment_status", {"task_id": "a"})


def test_opt_in_source_excerpt_is_bounded_and_filters_private_files(tmp_path, dispatcher):
    project = tmp_path / "project"
    project.mkdir()
    inside = project / "sequence.py"
    raw = b"first\nsecond\nthird\n"
    inside.write_bytes(raw)
    (project / "secret.txt").write_text("private filename", encoding="utf-8")
    (project / "other.py").write_text('password = "synthetic-example-value"', encoding="utf-8")
    (tmp_path / "outside.py").write_text("outside", encoding="utf-8")
    (project / ".env").write_text("outside catalog", encoding="utf-8")
    catalog = build_catalog(dispatcher[0], source_root=project)
    index = catalog.invoke("experiment_sources", {})
    assert index == {"paths": ["other.py", "sequence.py"], "truncated": False}
    assert catalog.invoke("experiment_source_read", {
        "path": "sequence.py", "start_line": 2, "max_lines": 1,
    }) == {
        "path": "sequence.py", "sha256": sha256(raw).hexdigest(),
        "start_line": 2, "text": "second\n", "truncated": True,
    }
    for path in ("../outside.py", "secret.txt", "other.py", ".env", "C:/outside.py", "..\\outside.py"):
        with pytest.raises(ToolError):
            catalog.invoke("experiment_source_read", {"path": path})


def test_source_excludes_symlink_targets(tmp_path, dispatcher):
    project = tmp_path / "project"
    project.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "sequence.py").write_text("outside", encoding="utf-8")
    try:
        (project / "linked").symlink_to(outside, target_is_directory=True)
    except OSError:
        pytest.skip("Creating symbolic links requires permission on this host")
    catalog = build_catalog(dispatcher[0], source_root=project)
    assert catalog.invoke("experiment_sources", {})["paths"] == []
    with pytest.raises(ToolError, match="links"):
        catalog.invoke("experiment_source_read", {"path": "linked/sequence.py"})


def _rpc(method, params=None, request_id=None):
    body = {"jsonrpc": "2.0", "method": method}
    if params is not None:
        body["params"] = params
    if request_id is not None:
        body["id"] = request_id
    return json.dumps(body) + "\n"


def test_codex_mcp_stdio_handshake_listing_and_injected_tool(dispatcher):
    task, calls = dispatcher
    catalog = build_catalog(task)
    stdin = StringIO("".join([
        _rpc("initialize", {"protocolVersion": "2025-06-18"}, 1),
        _rpc("notifications/initialized"),
        _rpc("tools/list", request_id=2),
        _rpc("tools/call", {"name": "experiment_status", "arguments": {"task_id": "实验-1"}}, 3),
        _rpc("tools/call", {"name": "experiment_approve", "arguments": {"task_id": "实验-1"}}, 4),
    ]))
    stdout = StringIO()
    assert serve(catalog, stdin, stdout) == 0
    messages = [json.loads(line) for line in stdout.getvalue().splitlines()]
    assert [message["id"] for message in messages] == [1, 2, 3, 4]
    assert messages[0]["result"]["protocolVersion"] == "2025-06-18"
    assert messages[1]["result"]["tools"] == catalog.describe()
    result = json.loads(messages[2]["result"]["content"][0]["text"])
    assert result["arguments"] == {"task_id": "实验-1"}
    assert messages[3]["result"]["isError"] is True
    assert calls == [("status", {"task_id": "实验-1"})]


def test_mcp_rejects_malformed_or_duplicate_json_fields(dispatcher):
    catalog = build_catalog(dispatcher[0])
    stdin = StringIO('{"jsonrpc":"2.0","id":1,"id":2,"method":"ping"}\nnot-json\n')
    stdout = StringIO()
    serve(catalog, stdin, stdout)
    assert [json.loads(line)["error"]["code"] for line in stdout.getvalue().splitlines()] == [-32700, -32700]


def _reply(**kwargs):
    return {"choices": [{"message": {"role": "assistant", **kwargs}}]}


def _call(name, arguments, call_id="call_1"):
    return {"id": call_id, "type": "function", "function": {"name": name, "arguments": arguments}}


def test_deepseek_provider_forwards_only_catalog_tool_calls(dispatcher):
    task, calls = dispatcher
    requests = []
    responses = iter([
        _reply(content=None, reasoning_content="example", tool_calls=[
            _call("experiment_status", '{"task_id":"abc"}'),
            _call("experiment_execute", "{}", "call_2"),
        ]),
        _reply(content="review needed"),
    ])

    def complete(payload):
        requests.append(payload)
        return next(responses)

    result = DeepSeekProvider(complete, model="example-model").run("Read the task status", build_catalog(task))
    assert result == {
        "content": "review needed", "rounds": 2,
        "tool_calls": [{"name": "experiment_status", "ok": True}, {"name": "experiment_execute", "ok": False}],
    }
    assert calls == [("status", {"task_id": "abc"})]
    assert all(tool["function"]["name"] != "experiment_execute" for tool in requests[0]["tools"])
    assistant, status, failure = requests[1]["messages"][-3:]
    assert assistant["reasoning_content"] == "example"
    assert status["tool_call_id"] == "call_1"
    assert json.loads(status["content"])["operation"] == "status"
    assert "Unknown tool" in failure["content"]


def test_deepseek_rejects_reused_call_id_without_dispatching_again(dispatcher):
    task, calls = dispatcher
    reply = _reply(content=None, tool_calls=[_call("experiment_status", '{"task_id":"abc"}')])
    with pytest.raises(ProviderError, match="repeated"):
        DeepSeekProvider(lambda _: reply).run("Check the task", build_catalog(task))
    assert calls == [("status", {"task_id": "abc"})]


def test_deepseek_official_transport_with_injected_opener():
    def opener(request, *, timeout):
        assert request.get_method() == "POST"
        assert request.full_url == "https://api.deepseek.com/chat/completions"
        assert request.get_header("Authorization") == "Bearer fake-test-key"
        assert timeout == 30
        assert json.loads(request.data)["model"] == "example"
        return BytesIO(b'{"choices":[]}')

    assert DeepSeekHTTP("fake-test-key", timeout=30, opener=opener)({"model": "example"}) == {"choices": []}
