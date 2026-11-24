import io
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from mktgkit import brain, cli, frontmatter, ledger, scaffold, workspace
from mktgkit.errors import MktgError


class HeaderTests(unittest.TestCase):
    def test_headers_round_trip_and_keep_editor_body(self):
        fields = {
            "title": "Café: #2",
            "claims": ["C-001", "C-002"],
            "fields": ["q, x", '"', "01"],
            "enabled": False,
            "version": 2,
            "cancelled": None,
        }
        body = "  The actual copy.\n\nLine two.\n"
        self.assertEqual(
            frontmatter.parse(frontmatter.dump(fields, body).replace("\n", "\r\n")), (fields, body)
        )
        self.assertEqual(frontmatter.parse("No header"), ({}, "No header"))

    def test_readable_fields_and_line_diagnostics(self):
        text = "---\ntitle: Dispatch # fixture\nclaims: [A, B]\nroles:\n - 'the owner'\n - writer\n---\nBody"
        fields, _ = frontmatter.parse(text)
        self.assertEqual(
            fields, {"title": "Dispatch", "claims": ["A", "B"], "roles": ["the owner", "writer"]}
        )
        for source in (
            "---\nk: a\nk: b\n---",
            "---\nk: 1\n  thing: x\n---",
            "---\nk: [unfinished\n---",
            "---\nk: 4",
        ):
            with self.assertRaises(MktgError) as err:
                frontmatter.parse(source, path="draft.md")
            self.assertIn("draft.md", err.exception.format())


class WorkspaceTests(unittest.TestCase):
    def setUp(self):
        self.scratch = tempfile.TemporaryDirectory()
        self.addCleanup(self.scratch.cleanup)
        self.parent = Path(self.scratch.name).resolve()
        self.root = scaffold.init(self.parent / "Client A")

    def test_real_clock_and_empty_install(self):
        self.assertEqual(workspace.config(self.root)["name"], "Client A")
        self.assertNotIn("now", workspace.config(self.root))
        self.assertEqual(ledger.read(self.root), [])
        self.assertTrue((self.root / ".mcp.json").is_file())
        with self.assertRaises(MktgError):
            scaffold.init(self.root)
        self.assertEqual(
            workspace.resolve_root("Client A", {"CLAUDE_PROJECT_DIR": str(self.parent)}), self.root
        )
        self.assertEqual(
            workspace.clock({"now": "2001-01-01"}, "2003-01-01", {"MKTGKIT_NOW": "2002-01-01"}).year, 2003
        )
        self.assertEqual(workspace.text_hash(" \nhello  \r\n\r\n"), workspace.text_hash("hello"))
        with self.assertRaises(MktgError):
            workspace.scoped(self.root, "../outside")

    def test_failed_batch_restores_existing_and_new_files(self):
        a = self.root / "goals.md"
        original = a.read_bytes()
        with self.assertRaises(RuntimeError), workspace.locked(self.root, mutate=True):
            workspace.atomic_write(a, "modified")
            workspace.atomic_write(self.root / "queue/item.md", "new")
            ledger.append(self.root, {"event": "submitted"})
            raise RuntimeError("simulated interruption")
        self.assertEqual(a.read_bytes(), original)
        self.assertFalse((self.root / "queue/item.md").exists())
        self.assertEqual(ledger.read(self.root), [])

    def test_abandoned_process_is_recovered_on_next_command(self):
        path = self.root / "goals.md"
        previous = path.read_bytes()
        code = (
            "from pathlib import Path\nimport sys,os\nfrom mktgkit import workspace\n"
            "root=Path(sys.argv[1]); guard=workspace.locked(root,mutate=True); guard.__enter__()\n"
            "workspace.atomic_write(root/'goals.md','partial'); os._exit(9)"
        )
        self.assertEqual(
            subprocess.run([sys.executable, "-c", code, str(self.root)], check=False).returncode, 9
        )
        self.assertEqual(path.read_bytes(), b"partial")
        with workspace.locked(self.root):
            self.assertEqual(path.read_bytes(), previous)

    def test_handoff_names_override_reasons_and_missing_operating_roles(self):
        from mktgkit import checks

        ledger.append(
            self.root,
            {
                "event": "approved",
                "item": "Q-0001",
                "attended": "overridden",
                "override_reason": "accessible review session",
            },
        )
        (self.root / "agents/orchestrator.md").unlink()
        with (self.root / "goals.md").open("a", encoding="utf-8") as stream:
            stream.write("| G1 | Inquiries | Unique accepted IDs | missing_data | one | 2026-12-01 |\n")
        result = checks.inspect(self.root, workspace.parse_time("2026-11-24"))
        self.assertTrue(any("accessible review session" in value for value in result["warnings"]))
        self.assertTrue(any("orchestrator" in value for value in result["errors"]))
        self.assertTrue(any("missing_data" in value for value in result["errors"]))

    def test_malformed_ledger_is_reported(self):
        (self.root / "log/ledger.jsonl").write_text('{"event":"submitted"}\n42\n', encoding="utf-8")
        with self.assertRaisesRegex(MktgError, "line 2"):
            ledger.read(self.root)

    def test_flags_work_before_and_after_nested_commands(self):
        for cmd in (
            ["--workspace", str(self.root), "--format", "json", "queue", "list"],
            ["queue", "list", "--format", "json", "-w", str(self.root)],
        ):
            out, err = io.StringIO(), io.StringIO()
            self.assertEqual(cli.main(cmd, stdout=out, stderr=err, env={}), 0, err.getvalue())
            self.assertEqual(json.loads(out.getvalue()), [])

    def test_error_exits_cleanly_for_malformed_or_missing_workspace(self):
        for root in (self.parent, self.root):
            if root == self.root:
                (root / "mktgkit.json").write_text("{", encoding="utf-8")
            err = io.StringIO()
            self.assertEqual(cli.main(["check", "-w", str(root)], stderr=err, env={}), 1)
            self.assertNotIn("Traceback", err.getvalue())

    def test_brain_detects_unsupported_inference_broken_link_and_stale_date(self):
        folder = self.root / "brain/research"
        frontmatter.write(
            folder / "sample.md",
            {
                "title": "Sample",
                "type": "research",
                "kind": "inference",
                "as_of": "2020-01-01",
                "derivation": "Estimate from the intake",
            },
            "See [[missing]] and \x60[[ignored]]\x60.",
        )
        errors, warnings, _, _ = brain.inspect(self.root, workspace.parse_time("2026-11-20"))
        self.assertTrue(any("missing" in message for message in errors))
        self.assertTrue(any("supporting fact" in message for message in errors))
        self.assertTrue(any("90 days" in message for message in warnings))
        self.assertFalse(any("ignored" in message for message in errors))


if __name__ == "__main__":
    unittest.main()
