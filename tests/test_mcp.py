import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from io import BytesIO
from pathlib import Path

from mktgkit import mcp, warehouse

ROOT = Path(__file__).resolve().parents[1]
META = {mcp.VERSION: mcp.LATEST, mcp.CLIENT_CAPS: {}}


def req(method, params=None, rid=1):
    return {"jsonrpc": "2.0", "method": method, "params": params or {}, "id": rid}


class MCPTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory(prefix="example client ")
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        shutil.copytree(ROOT / "examples/wrenfield/warehouse", self.root / "warehouse")
        (self.root / "mktgkit.json").write_text(
            '{"name":"Client","now":"2026-11-20T15:00:00Z"}', encoding="utf-8"
        )
        warehouse.build(self.root)
        self.server = mcp.Server(self.root)

    def test_stateless_discovery_and_tools(self):
        found = self.server.handle(req("server/discover", {"_meta": META}))["result"]
        self.assertEqual(found["supportedVersions"], [mcp.LATEST])
        self.assertEqual(found["resultType"], "complete")
        self.assertEqual(found["cacheScope"], "public")
        self.assertEqual(found["_meta"]["io.modelcontextprotocol/serverInfo"]["name"], "mktgkit-warehouse")
        listed = self.server.handle(req("tools/list", {"_meta": META}))["result"]["tools"]
        self.assertEqual([x["name"] for x in listed], list(mcp.TOOL_NAMES))
        for tool in listed:
            self.assertTrue(tool["annotations"]["readOnlyHint"])
            self.assertFalse(tool["inputSchema"]["additionalProperties"])

    def test_all_legacy_handshakes_and_version_fallback(self):
        for version in mcp.LEGACY + ("2000-01-01",):
            server = mcp.Server(self.root)
            init = server.handle(req("initialize", {"protocolVersion": version}))["result"]
            self.assertEqual(init["protocolVersion"], version if version in mcp.LEGACY else mcp.LEGACY[0])
            self.assertIsNone(server.handle({"jsonrpc": "2.0", "method": "notifications/initialized"}))
            self.assertEqual(server.handle(req("ping"))["result"], {})
            self.assertNotIn("resultType", server.handle(req("tools/list"))["result"])

    def test_version_and_transport_errors(self):
        self.assertEqual(self.server.handle(req("tools/list"))["error"]["code"], -32600)
        reply = self.server.handle(req("tools/list", {"_meta": {mcp.VERSION: "1900-01-01"}}))
        self.assertEqual(reply["error"]["code"], -32022)
        self.assertIn(mcp.LATEST, reply["error"]["data"]["supported"])
        reply = self.server.handle(req("ping", {"_meta": META}))
        self.assertEqual(reply["error"]["code"], -32601)
        self.assertEqual(
            self.server.handle(req("tools/list", {"_meta": {mcp.VERSION: mcp.LATEST}}))["error"]["code"],
            -32602,
        )

    def test_only_march_2025_accepts_batches(self):
        for version in ("2025-03-26", "2025-11-25", "2024-11-05"):
            self.server.handle(req("initialize", {"protocolVersion": version}))
            res = self.server.handle([req("ping"), {"jsonrpc": "2.0", "method": "notifications/initialized"}])
            if version == "2025-03-26":
                self.assertEqual(res, [{"jsonrpc": "2.0", "id": 1, "result": {}}])
            else:
                self.assertEqual(res["error"]["code"], -32600)

    def call(self, name, **args):
        return self.server.handle(req("tools/call", {"name": name, "arguments": args, "_meta": META}))

    def test_tool_results_report_freshness_and_normal_failures(self):
        data = self.call("query", sql="SELECT count(*) AS n FROM signups")["result"]
        self.assertEqual(data["structuredContent"]["tables"], ["signups"])
        self.assertIn("9 h old", data["content"][0]["text"])
        self.assertFalse(data["isError"])
        self.assertEqual(len(self.call("list_tables")["result"]["structuredContent"]["tables"]), 8)
        self.assertEqual(self.call("describe_table", name_renamed="x")["result"]["isError"], True)
        self.assertTrue(self.call("query", sql="DROP TABLE signups")["result"]["isError"])
        self.assertTrue(self.call("query")["result"]["isError"])
        self.assertTrue(self.call("freshness", tables="signups")["result"]["isError"])
        self.assertFalse(self.call("freshness", tables=["signups"])["result"]["isError"])
        self.assertEqual(self.call("unknown")["error"]["code"], -32602)
        warehouse.db_path(self.root).unlink()
        self.assertIn(
            "mktgkit warehouse build", self.call("query", sql="SELECT 1")["result"]["content"][0]["text"]
        )

    def test_binary_stdio_newlines_invalid_message_and_unicode(self):
        data = req(
            "tools/call", {"_meta": META, "name": "query", "arguments": {"sql": "SELECT 'Café ✓' AS label"}}
        )
        payload = b"\xff\n\n" + json.dumps(data).encode("utf-8") + b"\n"
        output = BytesIO()
        self.assertEqual(mcp.serve(self.root, BytesIO(payload), output), 0)
        parsed = [json.loads(line) for line in output.getvalue().splitlines()]
        self.assertEqual(parsed[0]["error"]["code"], -32700)
        self.assertIn("Café ✓", parsed[1]["result"]["content"][0]["text"])

    def test_public_cli_stdio_process_for_modern_and_legacy(self):
        for version in (mcp.LATEST, mcp.LEGACY[0]):
            if version == mcp.LATEST:
                msgs = [req("server/discover", {"_meta": META})]
                meta = {"_meta": META}
            else:
                msgs = [
                    req("initialize", {"protocolVersion": version}),
                    {"jsonrpc": "2.0", "method": "notifications/initialized"},
                ]
                meta = {}
            msgs.append(
                req(
                    "tools/call",
                    dict(meta, name="query", arguments={"sql": "SELECT * FROM attribution_coverage"}),
                    rid=2,
                )
            )
            proc = subprocess.run(
                [sys.executable, "-m", "mktgkit", "mcp", "-w", str(self.root)],
                input="".join(json.dumps(m) + "\n" for m in msgs),
                encoding="utf-8",
                capture_output=True,
                check=False,
                timeout=10,
                cwd=ROOT,
            )
            self.assertEqual(proc.returncode, 0, proc.stderr)
            parsed = [json.loads(line) for line in proc.stdout.splitlines()]
            self.assertEqual(len(parsed), 2)
            self.assertEqual(parsed[-1]["result"]["structuredContent"]["rows"], [[125, 76, 0.608]])
