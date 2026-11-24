"""A local, stdio-only MCP server for read-only warehouse analytics."""

import json
import os
import sqlite3
import sys
from dataclasses import asdict

from . import __version__, warehouse
from .errors import MktgError
from .workspace import config

LATEST = "2026-07-28"
LEGACY = ("2025-11-25", "2025-06-18", "2025-03-26", "2024-11-05")
VERSION = "io.modelcontextprotocol/protocolVersion"
CLIENT_CAPS = "io.modelcontextprotocol/clientCapabilities"
SERVER_INFO = {"name": "mktgkit-warehouse", "title": "mktgkit warehouse", "version": __version__}
SUPPORTED = [LATEST] + list(LEGACY)
TOOL_NAMES = ("list_tables", "describe_table", "query", "freshness")
_NAMES = {"type": "string", "enum": list(warehouse.TABLES + warehouse.VIEWS)}
_DEFS = {
    "list_tables": ("List the available warehouse tables and views.", {}, []),
    "describe_table": ("List column names and types for one table or view.", {"name": _NAMES}, ["name"]),
    "query": (
        "Read one SQL query and report the age of every input table.",
        {
            "sql": {"type": "string"},
            "limit": {"type": "integer", "minimum": 1, "maximum": 1000},
        },
        ["sql"],
    ),
    "freshness": (
        "Report the last recorded load, age and limit for each source.",
        {
            "tables": {"type": "array", "items": {"type": "string", "enum": list(warehouse.TABLES)}},
        },
        [],
    ),
}


def _tools(version):
    out = []
    for name, (description, props, required) in _DEFS.items():
        item = {
            "name": name,
            "description": description,
            "inputSchema": {
                "type": "object",
                "properties": props,
                "required": required,
                "additionalProperties": False,
            },
        }
        if version != "2024-11-05":
            item["annotations"] = {"readOnlyHint": True, "openWorldHint": False}
        out.append(item)
    return out


def _error(reqid, code, message, data=None):
    error = {"code": code, "message": message}
    if data is not None:
        error["data"] = data
    return {"jsonrpc": "2.0", "id": reqid, "error": error}


class Server:
    def __init__(self, root, now=None):
        self.root = root
        self.now = now
        self.legacy = None

    def _call(self, name, args, version):
        try:
            _, properties, required = _DEFS[name]
            if not isinstance(args, dict):
                raise MktgError("arguments must be an object")
            for key in required:
                if key not in args:
                    raise MktgError("missing required argument: " + key)
            if set(args) - set(properties):
                raise MktgError("unknown arguments: " + ", ".join(sorted(set(args) - set(properties))))
            if name == "query":
                result = warehouse.query(self.root, args["sql"], limit=args.get("limit", 200), now=self.now)
                data, text = asdict(result), warehouse.render_query(result)
            elif name == "freshness":
                tables = args.get("tables")
                if "tables" in args and (
                    not isinstance(tables, list) or any(not isinstance(t, str) for t in tables)
                ):
                    raise MktgError("tables must be an array of source table names")
                ages = warehouse.freshness(self.root, tables, now=self.now)
                data, text = {"freshness": [asdict(x) for x in ages]}, warehouse.footer(ages)
            elif name == "list_tables":
                rows = warehouse.list_tables(self.root)
                data = {"tables": rows}
                text = warehouse.render_table(["Name", "Type"], [[r["name"], r["type"]] for r in rows])
            else:
                rows = warehouse.describe(self.root, args["name"])
                data = {"name": args["name"], "columns": rows}
                text = warehouse.render_table(["Column", "Type"], [[r["name"], r["type"]] for r in rows])
        except (MktgError, sqlite3.Error, OSError) as exc:
            text = exc.format() if isinstance(exc, MktgError) else "Cannot read warehouse: " + str(exc)
            return {"isError": True, "content": [{"type": "text", "text": text}]}
        result = {"isError": False, "content": [{"type": "text", "text": text}]}
        if version not in ("2025-03-26", "2024-11-05"):
            result["structuredContent"] = data
        return result

    def handle(self, message):
        if isinstance(message, list):
            if not message or self.legacy != "2025-03-26":
                return _error(None, -32600, "A batch requires the 2025-03-26 handshake.")
            responses = [
                self.handle(x) if isinstance(x, dict) else _error(None, -32600, "Invalid request")
                for x in message
            ]
            return [x for x in responses if x is not None] or None
        if (
            not isinstance(message, dict)
            or message.get("jsonrpc") != "2.0"
            or not isinstance(message.get("method"), str)
        ):
            return _error(None, -32600, "Invalid JSON-RPC request")
        if "id" not in message:
            return None
        rid, method, params = message["id"], message["method"], message.get("params", {})
        if type(rid) not in (int, str):
            return _error(None, -32600, "Request id must be an integer or string")
        if not isinstance(params, dict) or not isinstance(params.get("_meta", {}), dict):
            return _error(rid, -32602, "Request parameters and metadata must be objects")
        meta = params.get("_meta", {})
        modern = VERSION in meta
        if modern:
            if meta[VERSION] != LATEST:
                return _error(
                    rid,
                    -32022,
                    "Unsupported protocol version",
                    {"requested": meta[VERSION], "supported": SUPPORTED},
                )
            if not isinstance(meta.get(CLIENT_CAPS), dict):
                return _error(rid, -32602, "Request metadata must include client capabilities")
        if method == "initialize" and not modern:
            requested = params.get("protocolVersion")
            if not isinstance(requested, str):
                return _error(rid, -32602, "initialize requires a protocolVersion")
            self.legacy = requested if requested in LEGACY else LEGACY[0]
            result = {
                "protocolVersion": self.legacy,
                "serverInfo": SERVER_INFO,
                "capabilities": {"tools": {}},
            }
        elif not modern and not self.legacy:
            return _error(
                rid,
                -32600,
                "Send a protocol version or a legacy initialize request.",
                {"supported": SUPPORTED},
            )
        elif modern and method == "server/discover":
            result = {"supportedVersions": [LATEST], "capabilities": {"tools": {}}}
        elif not modern and method == "ping":
            result = {}
        elif method == "tools/list":
            result = {"tools": _tools(LATEST if modern else self.legacy)}
        elif method == "tools/call":
            name = params.get("name")
            if name not in TOOL_NAMES:
                return _error(rid, -32602, "Unknown tool: " + str(name))
            result = self._call(name, params.get("arguments", {}), LATEST if modern else self.legacy)
        else:
            return _error(rid, -32601, "Unknown method: " + method)
        if modern:
            result.update(
                {"resultType": "complete", "_meta": {"io.modelcontextprotocol/serverInfo": SERVER_INFO}}
            )
            if method in ("server/discover", "tools/list"):
                result.update({"ttlMs": 3600000, "cacheScope": "public"})
        return {"jsonrpc": "2.0", "id": rid, "result": result}


def _reject_nonfinite(value):
    raise ValueError("Non-finite number in JSON message")


def serve(root, stdin, stdout, stderr=None, *, now=None):
    """Read and write one UTF-8 JSON object per line; stdout carries only protocol messages."""
    server = Server(root, now=now)
    for line in stdin:
        if not line.strip():
            continue
        try:
            request = json.loads(
                line.decode("utf-8") if isinstance(line, bytes) else line, parse_constant=_reject_nonfinite
            )
            response = server.handle(request)
        except (ValueError, RecursionError):
            response = _error(None, -32700, "Invalid JSON message")
        if response is not None:
            wire = json.dumps(response, ensure_ascii=True, separators=(",", ":"), allow_nan=False) + "\n"
            try:
                stdout.write(wire.encode("utf-8"))
            except TypeError:
                stdout.write(wire)
            stdout.flush()
    return 0


def _command(args, root, now, stdout, stdin):
    # An unpinned production workspace takes a fresh clock reading on each request.

    pinned = getattr(args, "now", None) or os.environ.get("MKTGKIT_NOW") or config(root).get("now")
    return serve(
        root,
        getattr(stdin, "buffer", stdin),
        getattr(stdout, "buffer", stdout),
        sys.stderr,
        now=now if pinned else None,
    )


def register(subparsers):
    parser = subparsers.add_parser("mcp", help="Serve the workspace warehouse over MCP on stdio")
    parser.set_defaults(handler=_command)
