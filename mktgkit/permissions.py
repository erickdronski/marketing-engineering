"""Read a conservative permission policy for a single workspace."""

import json
import re

from .errors import MktgError
from .workspace import atomic_write, scoped

MODES = ("draft_only", "approve_each", "auto")
NAME = re.compile(r"^[a-zA-Z0-9][\w.-]*$")
DEFAULT_PROMOTION = {
    "to_approve_each": {"live_items": 3},
    "to_auto": {"clean_approvals": 10, "window_days": 30},
}


def load(root):
    path = scoped(root, "permissions.json")
    try:
        config = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(config, dict) or config.get("default_mode") != "draft_only":
            raise ValueError("unlisted pairs must default to draft_only")
        seen = set()
        rules = config["rules"]
        if not isinstance(rules, list):
            raise TypeError("rules must be a list")
        for r in rules:
            pair = (r["action"], r["channel"])
            if not all(isinstance(k, str) and NAME.fullmatch(k) for k in pair) or pair in seen:
                raise ValueError("invalid or duplicate action/channel pair")
            seen.add(pair)
            if type(r.get("spend", False)) is not bool or r["mode"] not in MODES:
                raise ValueError("invalid mode or spend flag")
            if r["mode"] == "auto" and r.get("spend"):
                raise ValueError("spend actions cannot be automatic")
        promotion = config.setdefault("promotion", DEFAULT_PROMOTION)
        for target, defaults in DEFAULT_PROMOTION.items():
            for field in defaults:
                value = promotion[target][field]
                if type(value) is not int or value < 1:
                    raise ValueError(field + " must be a positive integer")
        tools = config.setdefault("tools", {})
        if not isinstance(tools, dict):
            raise TypeError("tools must be an object")
        for name, mapping in tools.items():
            if not NAME.fullmatch(name) or (mapping["action"], mapping["channel"]) not in seen:
                raise ValueError("tool must map to a configured action and channel")
            if not isinstance(mapping["content_field"], str) or not all(
                NAME.fullmatch(k) for k in mapping["content_field"].split(".")
            ):
                raise ValueError("invalid tool content_field")
        return config
    except (OSError, KeyError, TypeError, ValueError) as exc:
        raise MktgError("invalid permissions: " + str(exc), path="permissions.json") from exc


def rule(config, action, channel):
    return next(
        (r for r in config["rules"] if (r["action"], r["channel"]) == (action, channel)),
        {"action": action, "channel": channel, "mode": "draft_only"},
    )


def save(root, config):
    atomic_write(scoped(root, "permissions.json"), json.dumps(config, indent=2, ensure_ascii=False) + "\n")
