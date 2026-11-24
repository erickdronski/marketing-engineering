"""Hand-editable file validation must return a usable, structured diagnostic."""

import io
import json
import tempfile
import unittest
from pathlib import Path

from mktgkit import cli, frontmatter, scaffold


class MalformedWorkspaceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = scaffold.init(Path(self.temp.name).resolve() / "Client", example=True)

    def run_check(self, *command):
        out = io.StringIO()
        err = io.StringIO()
        status = cli.main(
            ["--workspace", str(self.root), "--format", "json", *command],
            stdout=out,
            stderr=err,
            stdin=io.StringIO(),
            env={},
        )
        self.assertEqual(status, 1, (out.getvalue(), err.getvalue()))
        return "\n".join(json.loads(out.getvalue())["errors"])

    def test_list_valued_note_type_and_kind(self):
        p = self.root / "brain/offers/route-planning-release.md"
        original, body = frontmatter.read(p)
        for field, malformed in (("type", ["offer"]), ("kind", ["fact"])):
            with self.subTest(field=field):
                frontmatter.write(p, dict(original, **{field: malformed}), body)
                for command in (("brain", "check"), ("check",)):
                    errors = self.run_check(*command)
                    self.assertIn("brain/offers/route-planning-release.md", errors)
                    self.assertIn(field, errors)

    def test_invalid_claim_figure_members_are_reported_at_the_note(self):
        p = self.root / "brain/claims/C-001-route-building-time.md"
        fields, body = frontmatter.read(p)
        frontmatter.write(p, dict(fields, figures=[3]), body)
        self.assertIn("brain/claims/C-001-route-building-time.md", self.run_check("brain", "check"))
        self.assertIn("figures", self.run_check("check"))

    def test_malformed_item_reference_in_ledger(self):
        with (self.root / "log/ledger.jsonl").open("a", encoding="utf-8") as log:
            log.write(json.dumps({"event": "submitted", "item": ["Q-0001"]}) + "\n")
        errors = self.run_check("check")
        self.assertIn("log/ledger.jsonl", errors)
        self.assertIn("item", errors)

    def test_invalid_nested_permission_mapping_names_its_field(self):
        path = self.root / "permissions.json"
        policy = json.loads(path.read_text(encoding="utf-8"))
        policy["tools"] = {
            "example_publish": {"action": ["publish_post"], "channel": "content", "content_field": "text"}
        }
        path.write_text(json.dumps(policy), encoding="utf-8")
        errors = self.run_check("check")
        self.assertIn("permissions.json", errors)
        self.assertIn("example_publish", errors)

    def test_malformed_queue_claims_list_names_its_file(self):
        path = next((self.root / "queue").glob("Q-0001-*.md"))
        fields, body = frontmatter.read(path)
        frontmatter.write(path, dict(fields, claims=[10]), body)
        errors = self.run_check("check")
        self.assertIn(path.name, errors)
        self.assertIn("claims", errors)
