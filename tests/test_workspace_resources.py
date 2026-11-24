"""The installed starter and its worked example should be usable side by side."""

import io
import json
import re
import tempfile
import unittest
from pathlib import Path

from mktgkit import brain, cli, frontmatter, permissions, scaffold
from mktgkit.workspace import parse_time

ROOT = Path(__file__).resolve().parents[1]
EXAMPLE = ROOT / "examples" / "wrenfield"
TEMPLATE = ROOT / "mktgkit" / "template"


class WorkspaceResourcesTest(unittest.TestCase):
    def test_all_role_wrappers_point_to_the_matching_canonical_definition(self):
        roles = sorted((EXAMPLE / "agents").rglob("*.md"))
        self.assertEqual(len(roles), 9)
        for path in roles:
            with self.subTest(role=path.stem):
                relative_name = path.relative_to(EXAMPLE)
                fields, _ = frontmatter.read(path)
                self.assertEqual(fields["name"], path.stem)
                self.assertEqual((TEMPLATE / relative_name).read_bytes(), path.read_bytes())
                wrapper = EXAMPLE / ".claude" / "agents" / path.name
                metadata, body = frontmatter.read(wrapper)
                self.assertEqual(fields["name"], metadata["name"])
                self.assertIn(relative_name.as_posix(), body)
                self.assertEqual(
                    wrapper.read_bytes(),
                    (TEMPLATE / "_dot_claude" / "agents" / path.name).read_bytes(),
                )

    def test_policy_covers_every_published_channel_and_parked_channel_has_criteria(self):
        config = permissions.load(EXAMPLE)
        self.assertEqual(config, permissions.load(TEMPLATE))
        self.assertEqual(config["default_mode"], "draft_only")
        self.assertEqual(config["tools"], {})
        pairs = {(rule["channel"], rule["action"]) for rule in config["rules"]}
        channels = {}
        for path in (EXAMPLE / "agents" / "channels").glob("*.md"):
            fields, _ = frontmatter.read(path)
            channels[path.stem] = fields["status"]
            for action in fields["actions"]:
                self.assertIn((path.stem, action), pairs)
            if fields["status"] == "parked":
                self.assertTrue(fields["switch_on"].strip())
        self.assertEqual(
            channels, {"content": "active", "seo-aeo": "active", "ads": "parked", "partnerships": "parked"}
        )

    def test_starter_has_a_formatted_first_submission_and_no_sample_outcomes(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = scaffold.init(Path(temporary) / "Client Name")
            config = json.loads((root / "mktgkit.json").read_text(encoding="utf-8"))
            self.assertEqual(config["name"], "Client Name")
            self.assertNotIn("now", config)
            self.assertEqual((root / "log" / "ledger.jsonl").read_bytes(), b"")
            self.assertEqual(list((root / "queue").glob("Q-*.md")), [])
            self.assertEqual(list((root / "brain" / "claims").glob("*.md")), [])
            readme = (root / "README.md").read_text(encoding="utf-8")
            draft = re.search(r"```markdown\n(.*?)\n```", readme, re.DOTALL)
            self.assertIsNotNone(draft)
            fields, body = frontmatter.parse(draft.group(1))
            self.assertEqual(fields["channel"], "content")
            self.assertIn("action", fields)
            self.assertTrue(body.strip())
            (root / "drafts" / "first-post.md").write_text(draft.group(1) + "\n", encoding="utf-8")
            output = io.StringIO()
            result = cli.main(
                ["--workspace", str(root), "queue", "submit", "drafts/first-post.md"],
                stdout=output,
                stderr=output,
                env={},
            )
            self.assertEqual(result, 0, output.getvalue())
            self.assertIn("in_review", output.getvalue())
            self.assertTrue((root / ".mcp.json").is_file())
            self.assertTrue((root / ".claude" / "settings.json").is_file())

    def test_example_evidence_graph_resolves_and_identifies_the_dated_source(self):
        now = parse_time("2026-11-20T15:00:00Z")
        errors, warnings, _, _ = brain.inspect(EXAMPLE, now)
        self.assertEqual(errors, [])
        self.assertTrue(any("competitor-route-pricing" in warning for warning in warnings))
        self.assertFalse(any("isolated note" in warning for warning in warnings))
        claims = {}
        for path in (EXAMPLE / "brain" / "claims").glob("*.md"):
            fields, _ = frontmatter.read(path)
            claims[fields["id"]] = fields["kind"], fields["figures"]
        self.assertEqual(
            claims,
            {
                "C-001": ("fact", ["38 minutes"]),
                "C-002": ("inference", ["3 hours"]),
                "C-003": ("assumption", ["50%"]),
            },
        )
