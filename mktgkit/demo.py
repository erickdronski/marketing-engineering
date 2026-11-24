"""Replay a labeled fictional review using the same CLI that serves a client."""

import io
import json
import tempfile
from pathlib import Path

from . import scaffold
from .errors import MktgError


class _ReviewerTerminal(io.StringIO):
    def isatty(self):
        return True


def replay(stdout):
    from .cli import main

    print(
        "Wrenfield • fictional company and data. Both roles are simulated; no person or model took part.",
        file=stdout,
    )
    with tempfile.TemporaryDirectory(prefix="mktgkit-demo-") as temporary:
        root = scaffold.init(Path(temporary) / "wrenfield", example=True)

        def run(role, label, args, expected=0):
            out, err = io.StringIO(), io.StringIO()
            agent = role == "Agent"
            status = main(
                ["--workspace", str(root), *args],
                env={"AI_AGENT": "1"} if agent else {},
                stdin=io.StringIO() if agent else _ReviewerTerminal(),
                stdout=out,
                stderr=err,
            )
            if status != expected:
                raise MktgError(f"demo step {label!r} exited {status}: {err.getvalue() or out.getvalue()}")
            if label:
                print(f"{role} · {label}\n{(err.getvalue() or out.getvalue()).strip()}", file=stdout)
            return out.getvalue()

        run("Operator", "", ["warehouse", "build"])
        run("Operator", "Inspect the client workspace", ["check"])
        run("Agent", "Read the review queue", ["queue", "list"])
        run(
            "Agent",
            "Submit an unsupported savings figure",
            ["queue", "submit", "drafts/unsupported-savings.md", "--by", "writer-fixture"],
            1,
        )
        run("Agent", "Try a reviewer decision", ["queue", "approve", "Q-0004"], 3)
        run(
            "Reviewer",
            "Return vague feedback",
            ["queue", "send-back", "Q-0004", "--feedback", "Make it better", "--by", "avery-fixture"],
            1,
        )
        run(
            "Reviewer",
            "Return an actionable edit",
            [
                "queue",
                "send-back",
                "Q-0004",
                "--feedback",
                "Replace the opening with the dispatcher’s first check.",
                "--by",
                "avery-fixture",
            ],
        )
        run(
            "Agent",
            "Revise the crew tips",
            ["queue", "resubmit", "Q-0004", "drafts/crew-tips-revised.md", "--by", "writer-fixture"],
        )
        run("Reviewer", "Approve the revised text", ["queue", "approve", "Q-0004", "--by", "avery-fixture"])
        run("Operator", "Check this exact version", ["gate", "check", "--item", "Q-0004"])
        run(
            "Reviewer",
            "Request unattended publishing",
            ["gate", "promote", "--action", "publish_post", "--channel", "content", "--by", "avery-fixture"],
            1,
        )
        run(
            "Operator",
            "Measure campaign attribution",
            ["warehouse", "query", "SELECT * FROM attribution_coverage"],
        )
        graph = json.loads(run("Operator", "", ["brain", "graph", "--format", "json"]))
        print(
            f"Knowledge base · {len(graph['nodes'])} linked or recorded notes; {len(graph['edges'])} connections.",
            file=stdout,
        )
    return 0
