"""Reviewer attendance is a recorded signal, not authentication."""

import getpass
import json
import os

from .errors import MktgError
from .workspace import scoped


def decision_flags(parser):
    parser.add_argument("--by", help="Name to record in the ledger")
    parser.add_argument("--override-attendance", metavar="REASON")


def reviewer(root, args, stdin):
    env = getattr(args, "review_env", os.environ)
    config = json.loads(scoped(root, "mktgkit.json").read_text(encoding="utf-8"))
    markers = config.get("agent_markers", ["CLAUDECODE", "AI_AGENT"])
    if not isinstance(markers, list) or not all(isinstance(m, str) and m for m in markers):
        raise MktgError("agent_markers must be a list of variable names", path="mktgkit.json")
    name = (getattr(args, "by", None) or env.get("MKTGKIT_REVIEWER") or getpass.getuser()).strip()
    if not name:
        raise MktgError("supply a reviewer name", exit_code=2)
    reasons = [m for m in markers if env.get(m, "").strip().lower() not in ("", "0", "false")]
    if not stdin.isatty():
        reasons.append("standard input is not a terminal")
    override = getattr(args, "override_attendance", None)
    if override is not None:
        if not override.strip():
            raise MktgError("attendance override needs a reason", exit_code=2)
        return {"by": name, "attended": "overridden", "override_reason": override.strip()}
    if reasons:
        raise MktgError(
            "reviewer decision refused: " + ", ".join(reasons),
            fix="Review from your own terminal. An intentional --override-attendance REASON is recorded.",
            exit_code=3,
        )
    return {"by": name, "attended": True}


def actor(args):
    return {"by": getattr(args, "by", None) or getpass.getuser()}
