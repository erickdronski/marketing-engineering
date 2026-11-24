"""Exercise the public review commands against disposable client files."""

import argparse
import io
import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from mktgkit import claims, frontmatter, gate, ledger, permissions, queue, workspace
from mktgkit.errors import MktgError


class Terminal(io.StringIO):
    def isatty(self):
        return True


class ReviewWorkflow(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.now = datetime(2026, 11, 20, 15, tzinfo=timezone.utc)
        self.parser = argparse.ArgumentParser()
        sub = self.parser.add_subparsers(required=True)
        for module in (queue, claims, gate):
            module.register(sub)
        for path in (
            "agents/channels",
            "brain/claims",
            "brain/edits",
            "brain/brand",
            "drafts",
            "queue",
            "log",
        ):
            (self.root / path).mkdir(parents=True)
        (self.root / "mktgkit.json").write_text('{"name":"Example"}', encoding="utf-8")
        self.cfg = {
            "default_mode": "draft_only",
            "rules": [
                {"action": "publish_post", "channel": "content", "mode": "approve_each"},
                {"action": "buy", "channel": "ads", "mode": "draft_only", "spend": True},
            ],
            "promotion": {
                "to_approve_each": {"live_items": 1},
                "to_auto": {"clean_approvals": 2, "window_days": 30},
            },
            "tools": {
                "demo_publish": {"action": "publish_post", "channel": "content", "content_field": "post.text"}
            },
        }
        self.policy()
        self.md(
            "agents/channels/content.md", {"status": "active", "actions": ["publish_post"]}, "Content drafts"
        )
        self.md("agents/channels/ads.md", {"status": "parked", "switch_on": "Get attribution first."}, "Ads")
        self.md("brain/brand/voice.md", {"banned_phrases": ["game-changing", "seamless"]}, "Voice")
        self.c = {
            "id": "C-001",
            "type": "claim",
            "kind": "fact",
            "source": "Dispatch time sheets, export 2026-11-01",
            "figures": ["38 minutes"],
            "review_by": "2026-12-01",
        }
        self.md("brain/claims/c.md", self.c, "Pilot")
        self.df = {"title": "Crew tips", "channel": "content", "action": "publish_post", "priority": "high"}
        self.draft()

    def md(self, path, fields, body):
        frontmatter.write(self.root / path, fields, body)

    def draft(self, body="Keep the route plan nearby.", **fields):
        self.md("drafts/item.md", dict(self.df, **fields), body)

    def policy(self):
        (self.root / "permissions.json").write_text(json.dumps(self.cfg), encoding="utf-8")

    def run_cmd(self, *argv, stdin=None, env=None):
        args = self.parser.parse_args(list(argv))
        args.format = "text"
        args.review_env = {} if env is None else env
        output = io.StringIO()
        with workspace.locked(self.root, mutate=True):
            result = args.handler(
                args, self.root, self.now, output, stdin if stdin is not None else Terminal()
            )
            self.assertEqual(result, 0)
        return output.getvalue()

    def submit(self):
        return self.run_cmd("queue", "submit", "drafts/item.md", "--by", "planner").split()[0]

    def sign(self):
        self.run_cmd("claims", "approve", "C-001", "--by", "Avery")

    def approve(self, key):
        self.run_cmd("queue", "approve", key, "--by", "Avery")

    def denied(self, code, *args, **kwargs):
        with self.assertRaises(MktgError) as c:
            self.run_cmd(*args, **kwargs)
        self.assertEqual(c.exception.exit_code, code, c.exception)
        return str(c.exception)

    def test_figure_units_and_boundaries(self):
        source = (
            "38 minutes, 27 percent, $1,200, 3x, 1.50 hours. In 2019 with 14 people. https://w.example/a?x=5x"
        )
        self.assertEqual(
            [n for _, n in claims.extract_figures(source)], ["38min", "27%", "$1200", "3x", "1.5h"]
        )
        self.assertEqual(
            [n for _, n in claims.extract_figures("€5k, 5 months, 5 monthly, 5 hrs")], ["€5k", "5mo", "5h"]
        )

    def test_claim_requires_evidence_and_signoff(self):
        self.draft("Save 38 minutes in dispatch.", claims=["C-001"])
        self.assertIn("not signed off", self.denied(1, "queue", "submit", "drafts/item.md"))
        self.sign()
        item = self.submit()
        self.md("brain/claims/c.md", self.c, "Edited evidence")
        self.assertIn("changed after sign-off", self.denied(1, "queue", "approve", item))
        self.assertEqual(queue.get(self.root, item).status, "in_review")

    def test_signoff_refuses_placeholder_source(self):
        self.md("brain/claims/c.md", dict(self.c, source="internal data"), "Details missing")
        self.assertIn("source", self.denied(1, "claims", "approve", "C-001"))
        self.assertEqual(ledger.read(self.root), [])

    def test_assumption_cannot_be_signed(self):
        self.md("brain/claims/c.md", dict(self.c, kind="assumption"), "Projection")
        self.assertIn("assumption", self.denied(1, "claims", "approve", "C-001"))

    def test_expiry_rechecked_on_action(self):
        self.sign()
        self.draft("It saved 38 minutes.", claims=["C-001"])
        key = self.submit()
        self.approve(key)
        self.now = datetime(2027, 1, 1, tzinfo=timezone.utc)
        self.assertIn("review_by", self.denied(1, "gate", "check", "--item", key))

    def test_uncited_unknown_claim_banned_phrase(self):
        self.sign()
        self.draft("Our game-changing release saves 38 minutes seamlessly.", claims=["C-999"])
        message = self.denied(1, "queue", "submit", "drafts/item.md")
        for text in ("game-changing", "38 minutes", "C-999"):
            self.assertIn(text, message)
        self.assertNotIn("seamless", message)
        self.assertEqual(queue.items(self.root), [])

    def test_agent_and_pipe_refused_override_persisted(self):
        key = self.submit()
        for env, stream in (({"CLAUDECODE": "1"}, Terminal()), ({}, io.StringIO())):
            self.denied(3, "queue", "approve", key, env=env, stdin=stream)
        self.run_cmd(
            "queue",
            "approve",
            key,
            "--override-attendance",
            "Reviewer is present on video",
            stdin=io.StringIO(),
        )
        event = ledger.read(self.root)[-1]
        self.assertEqual(event["attended"], "overridden")
        self.assertEqual(event["override_reason"], "Reviewer is present on video")
        self.assertIn(
            "0 of 2", self.denied(1, "gate", "promote", "--action", "publish_post", "--channel", "content")
        )

    def test_blank_override_and_unset_markers(self):
        key = self.submit()
        self.denied(2, "queue", "approve", key, "--override-attendance", " ")
        self.run_cmd("queue", "approve", key, env={"AI_AGENT": "false", "CLAUDECODE": "0"})

    def test_parked_channels_and_unknown_actions(self):
        self.draft(channel="ads", action="buy")
        self.assertIn("parked", self.denied(1, "queue", "submit", "drafts/item.md"))
        self.draft(action="misspelled")
        self.assertIn("unknown action", self.denied(1, "queue", "submit", "drafts/item.md"))

    def test_misbound_channel_or_reassigned_action(self):
        self.draft(action="buy")
        self.assertIn("does not allow", self.denied(1, "queue", "submit", "drafts/item.md"))
        self.draft()
        key = self.submit()
        self.approve(key)
        self.md("agents/channels/content.md", {"status": "parked", "actions": ["publish_post"]}, "Paused")
        self.assertIn("parked", self.denied(1, "gate", "check", "--item", key))
        self.md("agents/channels/content.md", {"status": "active", "actions": ["buy"]}, "Reassigned")
        self.assertIn(
            "does not allow", self.denied(1, "queue", "mark-live", key, "--url", "https://example.test/post")
        )
        self.assertEqual(queue.get(self.root, key).status, "approved")

    def test_draft_read_error_names_relative_path(self):
        self.assertIn("draft file does not exist", self.denied(1, "queue", "submit", "drafts/gone.md"))

    def test_queue_lifecycle_unicode_and_dependencies(self):
        self.draft("Crème brûlée — “good” ✓")
        one = self.submit()
        self.draft("Publish the page.", depends_on=[one], priority="medium")
        two = self.submit()
        self.assertIn(one, self.denied(3, "queue", "approve", two))
        self.approve(one)
        self.approve(two)
        self.assertEqual(self.run_cmd("gate", "check", "--item", two).split()[0], "Allowed")
        self.run_cmd("queue", "mark-live", one, "--url", "https://example.test/page")
        self.denied(1, "queue", "mark-live", one, "--url", "https://example.test/page")
        self.assertEqual(queue.audit(self.root, self.now), [])

    def test_body_and_metadata_bound_to_grant(self):
        key = self.submit()
        self.approve(key)
        i = queue.get(self.root, key)
        self.md(i.path, i.fields, "Unexpected new text")
        self.assertIn("changed", self.denied(1, "gate", "check", "--item", key))
        self.md(i.path, dict(i.fields, claims=["C-001"]), i.body)
        self.assertIn("metadata", self.denied(1, "gate", "check", "--item", key))

    def test_specific_feedback_and_version_boundary(self):
        key = self.submit()
        self.denied(1, "queue", "send-back", key, "--feedback", "Make it better")
        self.run_cmd(
            "queue",
            "send-back",
            key,
            "--feedback",
            "Lead with the dispatcher's morning routine.",
            "--because",
            "Owners read on mobile.",
            "--applies-to",
            "voice",
        )
        (edit,) = (self.root / "brain/edits").glob("*.md")
        self.assertIn("[[brain/brand/voice]]", edit.read_text(encoding="utf-8"))
        self.draft("Start with the dispatcher's plan.")
        self.run_cmd("queue", "resubmit", key, "drafts/item.md")
        self.assertEqual(queue.get(self.root, key).fields["version"], 2)
        self.denied(3, "gate", "check", "--item", key)
        self.approve(key)
        self.run_cmd("queue", "resubmit", key, "drafts/item.md")
        self.denied(3, "gate", "check", "--item", key)

    def test_draft_only_manual_receipt_and_promotion(self):
        self.cfg["rules"][0]["mode"] = "draft_only"
        self.policy()
        key = self.submit()
        self.approve(key)
        self.denied(4, "gate", "check", "--item", key)
        self.denied(1, "gate", "promote", "--action", "publish_post", "--channel", "content")
        self.run_cmd("queue", "mark-live", key, "--url", "https://example.test/p")
        self.run_cmd("gate", "promote", "--action", "publish_post", "--channel", "content")
        self.assertEqual(permissions.load(self.root)["rules"][0]["mode"], "approve_each")

    def test_auto_promotion_and_incident_demotion(self):
        self.approve(self.submit())
        self.approve(self.submit())
        self.run_cmd("gate", "promote", "--action", "publish_post", "--channel", "content")
        self.draft("Publish this new post.")
        key = self.submit()
        self.run_cmd("gate", "check", "--item", key)
        i = queue.get(self.root, key)
        self.md(i.path, i.fields, "Edited: publish something else.")
        self.denied(1, "gate", "check", "--item", key)
        self.md(i.path, i.fields, i.body)
        self.run_cmd("queue", "mark-live", key, "--url", "https://example.test/p")
        self.run_cmd("queue", "incident", key, "--note", "Link went to an expired offer.")
        self.assertEqual(permissions.load(self.root)["rules"][0]["mode"], "approve_each")
        self.assertIn(
            "0 of 2", self.denied(1, "gate", "promote", "--action", "publish_post", "--channel", "content")
        )

    def test_feedback_and_time_window_break_promotion(self):
        one = self.submit()
        self.approve(one)
        two = self.submit()
        self.run_cmd("queue", "send-back", two, "--feedback", "Remove the last paragraph about discounts.")
        self.approve(self.submit())
        self.assertIn(
            "1 of 2", self.denied(1, "gate", "promote", "--action", "publish_post", "--channel", "content")
        )
        self.now = datetime(2027, 4, 1, tzinfo=timezone.utc)
        self.assertIn(
            "0 of 2", self.denied(1, "gate", "promote", "--action", "publish_post", "--channel", "content")
        )

    def test_spend_policy_or_promotion_never_auto(self):
        self.cfg["rules"][1]["mode"] = "auto"
        self.policy()
        self.assertIn("spend", self.denied(1, "gate", "status"))
        self.cfg["rules"][1]["mode"] = "approve_each"
        self.policy()
        self.assertIn("money", self.denied(1, "gate", "promote", "--action", "buy", "--channel", "ads"))

    def test_hook_matches_only_exact_tool_and_content(self):
        key = self.submit()
        self.approve(key)

        def event(text):
            return io.StringIO(
                json.dumps({"tool_name": "demo_publish", "tool_input": {"post": {"text": text}}})
            )

        self.run_cmd("gate", "hook", stdin=event("Keep the route plan nearby.\n"))
        self.denied(2, "gate", "hook", stdin=event("Publish my changed content."))
        self.denied(
            2, "gate", "hook", stdin=io.StringIO('{"tool_name":"demo_publish","tool_input":{"other":"body"}}')
        )
        self.denied(2, "gate", "hook", stdin=io.StringIO("{oops"))
        self.run_cmd("gate", "hook", stdin=io.StringIO('{"tool_name":"read_local"}'))
        self.assertIn("demo_publish", self.run_cmd("gate", "hook", "--print-settings"))

    def test_ambiguous_matching_and_early_dependency_rejection(self):
        self.approve(self.submit())
        self.approve(self.submit())
        self.assertIn(
            "unique",
            self.denied(
                3,
                "gate",
                "check",
                "--action",
                "publish_post",
                "--channel",
                "content",
                stdin=io.StringIO("Keep the route plan nearby."),
            ),
        )
        self.draft(depends_on=["Q-9999"])
        self.assertIn("dependency", self.denied(1, "queue", "submit", "drafts/item.md"))

    def test_render_escapes_and_protects_existing_files(self):
        self.draft("<script>test</script>", title="Treat <markup> as text")
        self.approve(self.submit())
        self.run_cmd("queue", "render", "--out", "out/queue.html")
        html = (self.root / "out/queue.html").read_text(encoding="utf-8")
        self.assertNotIn("<script", html)
        self.assertIn("&lt;markup&gt;", html)
        self.assertIn("approved by Avery", html)
        (self.root / "out/queue.html").write_text("A hand-written page.", encoding="utf-8")
        self.denied(1, "queue", "render", "--out", "out/queue.html")

    def test_partial_ledger_failure_rolls_back(self):
        key = self.submit()
        with patch.object(ledger, "append", side_effect=OSError("disk full")), self.assertRaises(OSError):
            self.run_cmd("queue", "send-back", key, "--feedback", "Cut the sentence about the schedule.")
        self.assertEqual(list((self.root / "brain/edits").glob("*.md")), [])
        self.assertEqual(queue.get(self.root, key).status, "in_review")

    def test_withdrawn_item_cannot_progress(self):
        key = self.submit()
        self.run_cmd("queue", "withdraw", key, "--reason", "Campaign cancelled.")
        self.denied(1, "queue", "approve", key)
        self.denied(1, "queue", "resubmit", key, "drafts/item.md")
