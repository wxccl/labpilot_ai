"""Small newline-delimited JSON-RPC MCP transport for the LabPilot catalog."""

from __future__ import annotations

from typing import TextIO

from labpilot_ai import __version__
from .catalog import ToolCatalog, ToolError, decode_json, encode_json

SUPPORTED_VERSIONS = ("2025-11-25", "2025-06-18", "2025-03-26", "2024-11-05")
MAX_LINE = 128 * 1024


def _response(request_id, *, result=None, code=None, message=None):
    message_data = {"jsonrpc": "2.0", "id": request_id}
    if code is None:
        message_data["result"] = result
    else:
        message_data["error"] = {"code": code, "message": message}
    return message_data


def _tool_result(catalog, params):
    name = params.get("name")
    arguments = params.get("arguments", {})
    if not isinstance(name, str) or not isinstance(arguments, dict):
        return None
    try:
        result = catalog.invoke(name, arguments)
    except ToolError as exc:
        return {"content": [{"type": "text", "text": str(exc)}], "isError": True}
    return {"content": [{"type": "text", "text": encode_json(result)}], "isError": False}


def _handle(request, catalog, initialized):
    request_id = request.get("id") if isinstance(request, dict) else None
    if (not isinstance(request, dict) or request.get("jsonrpc") != "2.0"
            or not isinstance(request.get("method"), str)
            or ("id" in request and type(request_id) not in (str, int))):
        return _response(None, code=-32600, message="Invalid request"), initialized
    if "id" not in request:
        return None, initialized
    method = request["method"]
    params = request.get("params", {})
    if not isinstance(params, dict):
        return _response(request_id, code=-32602, message="Invalid params"), initialized
    if method == "initialize":
        version = params.get("protocolVersion")
        if not isinstance(version, str) or initialized:
            return _response(request_id, code=-32602, message="Invalid initialization"), initialized
        if version not in SUPPORTED_VERSIONS:
            version = SUPPORTED_VERSIONS[0]
        return _response(request_id, result={
            "protocolVersion": version, "capabilities": {"tools": {}},
            "serverInfo": {"name": "labpilot", "version": __version__},
        }), True
    if method == "ping":
        return _response(request_id, result={}), initialized
    if not initialized:
        return _response(request_id, code=-32000, message="Initialize the MCP session first"), initialized
    if method == "tools/list":
        return _response(request_id, result={"tools": catalog.describe()}), initialized
    if method == "tools/call":
        result = _tool_result(catalog, params)
        if result is not None:
            return _response(request_id, result=result), initialized
        return _response(request_id, code=-32602, message="Invalid tool call params"), initialized
    return _response(request_id, code=-32601, message="Method not found"), initialized


def serve(catalog: ToolCatalog, stdin: TextIO, stdout: TextIO) -> int:
    """Process one UTF-8 text line per JSON-RPC message until input closes."""
    initialized = False
    while line := stdin.readline(MAX_LINE + 1):
        if len(line) > MAX_LINE:
            stdout.write(encode_json(_response(None, code=-32700, message="Message too large")) + "\n")
            stdout.flush()
            return 2
        try:
            request = decode_json(line)
        except (ValueError, RecursionError):
            response = _response(None, code=-32700, message="Invalid JSON")
        else:
            response, initialized = _handle(request, catalog, initialized)
        if response is not None:
            stdout.write(encode_json(response) + "\n")
            stdout.flush()
    return 0
