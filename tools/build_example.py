"""Recreate the fictional queue history into an empty destination.

Run from a source checkout with python -m tools.build_example NEW_DIRECTORY.
"""

import argparse
import io
import shutil
from pathlib import Path

from mktgkit import cli, frontmatter, scaffold


class FixtureTerminal(io.StringIO):
    def isatty(self):
        return True


def build(destination):
    root = Path(destination).absolute()
    if root.exists():
        raise ValueError("choose a new directory")
    shutil.copytree(
        scaffold.EXAMPLE,
        root,
        ignore=shutil.ignore_patterns(
            "queue", "log", "edits", "drafts", "warehouse.db", ".mktgkit-state", "out"
        ),
    )
    for path in ("drafts", "queue", "log", "brain/edits"):
        (root / path).mkdir(parents=True, exist_ok=True)
    (root / "log/ledger.jsonl").touch()

    def act(date, role, *args):
        out = io.StringIO()
        status = cli.main(
            ["--workspace", str(root), "--now", date, *args, "--by", role],
            env={},
            stdin=FixtureTerminal(),
            stdout=out,
            stderr=out,
        )
        if status:
            raise RuntimeError(out.getvalue())

    def draft(filename, title, channel, priority, body, claims=(), dependencies=()):
        frontmatter.write(
            root / "drafts" / filename,
            {
                "title": title,
                "channel": channel,
                "action": "publish_post" if channel == "content" else "update_page",
                "priority": priority,
                "claims": list(claims),
                "depends_on": list(dependencies),
                "batch": "B-001",
            },
            body + "\n",
        )
        return "drafts/" + filename

    feature = draft(
        "route-page.md",
        "Route-planning feature page",
        "seo-aeo",
        "high",
        "Dispatchers can compare the proposed route with the jobs on their board. In the fictional time study, the dispatcher saved 38 minutes on one planning exercise.",
        ["C-001"],
    )
    launch = draft(
        "launch-first.md",
        "Route-planning launch post",
        "content",
        "high",
        "Route planning is ready for dispatch. Open the feature page to see the route comparison and the dispatcher's controls.",
        ["C-001", "C-002"],
        ["Q-0001"],
    )
    revised = draft(
        "launch-revised.md",
        "Route-planning launch post",
        "content",
        "high",
        "Monday morning starts with a full board and a crew waiting for its first stop. Compare Wrenfield’s suggested order with your board, then confirm which route the crew should take.",
        ["C-001", "C-002"],
        ["Q-0001"],
    )
    faq = draft(
        "dispatcher-faq.md",
        "Dispatcher FAQ",
        "seo-aeo",
        "medium",
        "Who chooses the final route? The dispatcher can review the suggested order and adjust it before confirming the route.",
    )
    tips = draft(
        "crew-tips.md",
        "Crew tips post",
        "content",
        "low",
        "Before leaving the yard, ask dispatch which stop comes first and where the latest job notes live.",
    )
    draft(
        "unsupported-savings.md",
        "Savings headline",
        "content",
        "medium",
        "Our product saves every team 90 hours each week.",
    )
    draft(
        "crew-tips-revised.md",
        "Crew tips post",
        "content",
        "low",
        "Before leaving the yard, open the first job on the dispatch board and confirm the access notes with the dispatcher.",
    )
    act("2026-11-09T09:00:00Z", "avery-fixture", "claims", "approve", "C-001")
    act("2026-11-09T09:05:00Z", "avery-fixture", "claims", "approve", "C-002")
    act("2026-11-10T09:00:00Z", "seo-fixture", "queue", "submit", feature)
    act("2026-11-11T14:00:00Z", "avery-fixture", "queue", "approve", "Q-0001")
    act("2026-11-12T09:00:00Z", "content-fixture", "queue", "submit", launch)
    act(
        "2026-11-12T17:30:00Z",
        "avery-fixture",
        "queue",
        "send-back",
        "Q-0002",
        "--feedback",
        "Lead with the dispatcher’s Monday morning and cut the feature list.",
        "--because",
        "An owner checks the opening on a phone.",
        "--applies-to",
        "voice",
    )
    act("2026-11-13T11:00:00Z", "content-fixture", "queue", "resubmit", "Q-0002", revised)
    act("2026-11-13T15:00:00Z", "avery-fixture", "queue", "approve", "Q-0002")
    act("2026-11-18T10:00:00Z", "seo-fixture", "queue", "submit", faq)
    act("2026-11-19T10:00:00Z", "content-fixture", "queue", "submit", tips)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("destination")
    build(parser.parse_args().destination)
