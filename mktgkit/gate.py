"""Evaluate action permissions locally. No connector is invoked."""

import json
import re
from datetime import timedelta
from urllib.parse import urlsplit

from . import claims, ledger, permissions, queue
from .decisions import actor, decision_flags, reviewer
from .errors import MktgError
from .workspace import parse_time, text_hash, timestamp


def _check(root, item, now, manual=False):
    config = permissions.load(root)
    mode = permissions.rule(config, item.fields["action"], item.fields["channel"])["mode"]
    entries = ledger.read(root)
    error = queue.integrity(item, entries)
    if error:
        raise MktgError(error)
    if item.status in ("live", "sent_back", "withdrawn") or item.fields.get("flagged"):
        raise MktgError(item.id + " is " + item.status + " or flagged; action unavailable")
    if any(
        e.get("item") == item.id
        and e.get("version") == item.fields["version"]
        and e.get("event") == "incident"
        for e in entries
    ):
        raise MktgError(item.id + " has a recorded incident")
    if mode == "draft_only" and not manual:
        raise MktgError("draft_only: a person performs this action", exit_code=4)
    if mode != "auto" and item.status != "approved":
        raise MktgError(item.id + " needs a reviewer decision", exit_code=3)
    queue.enabled_action(root, item.fields)
    queue.dependency_check(root, item, entries)
    claims.validate(root, item.body, claims.string_list(item.fields, "claims"), now)
    return {"allowed": True, "item": item.id, "mode": mode}


def check_content(root, action, channel, content, now):
    if not isinstance(content, str) or not content.strip():
        raise MktgError("provide the exact nonempty draft text", exit_code=3)
    digest = text_hash(content)
    matches = [
        i
        for i in queue.items(root)
        if (i.fields["action"], i.fields["channel"]) == (action, channel)
        and text_hash(i.body) == digest
        and i.status not in ("live", "withdrawn")
    ]
    if len(matches) != 1:
        raise MktgError("no unique reviewed item matches this action, channel and text", exit_code=3)
    return _check(root, matches[0], now)


def progress(root, rule, config, now):
    action, channel, mode = rule["action"], rule["channel"], rule["mode"]
    events = [e for e in ledger.read(root) if (e.get("action"), e.get("channel")) == (action, channel)]
    if mode == "draft_only":
        needed = config["promotion"]["to_approve_each"]["live_items"]
        approved = set()
        live = set()
        for event in events:
            key = (event.get("item"), event.get("version"), event.get("sha256"))
            if event.get("event") == "approved":
                approved.add(key)
            if event.get("event") == "went_live" and key in approved:
                live.add(event["item"])
        return ("approve_each", len(live), needed, "approved items recorded live")
    if mode == "auto":
        return (None, 0, 0, "already at highest mode")
    if rule.get("spend"):
        return (None, 0, 0, "this action spends money; auto is unavailable")
    limits = config["promotion"]["to_auto"]
    since = now - timedelta(days=limits["window_days"])
    clean = set()
    for event in reversed(events):
        if event.get("event") not in ("incident", "approved", "sent_back"):
            continue
        when = parse_time(event["ts"])
        if when < since or when > now:
            continue
        if event["event"] != "approved" or event.get("attended") is not True or event.get("version") != 1:
            break
        clean.add(event["item"])
    return (
        "auto",
        len(clean),
        limits["clean_approvals"],
        "consecutive attended first-version approvals in the window",
    )


def _change(root, config, rule, mode, now, person, reason):
    previous = rule["mode"]
    rule["mode"] = mode
    permissions.save(root, config)
    ledger.append(
        root,
        dict(
            person,
            ts=timestamp(now),
            event="permission_changed",
            action=rule["action"],
            channel=rule["channel"],
            previous=previous,
            mode=mode,
            reason=reason,
        ),
    )


def mark_live(root, item, url, person, now):
    try:
        target = urlsplit(url)
        valid = (
            target.scheme in ("http", "https")
            and bool(target.hostname)
            and not target.username
            and not target.password
        )
    except ValueError:
        valid = False
    if not valid:
        raise MktgError("supply a public HTTP(S) receipt URL without credentials")
    verdict = _check(root, item, now, manual=True)
    queue.record(root, item, now, "went_live", person, mode=verdict["mode"], url=url)


def incident(root, item, note, person, now):
    if item.status not in ("approved", "live") or not note.strip():
        raise MktgError("an incident needs an approved or live item and a note")
    cfg = permissions.load(root)
    rule = permissions.rule(cfg, item.fields["action"], item.fields["channel"])
    item.fields["flagged"] = True
    queue.record(root, item, now, "incident", person, note=note.strip())
    if rule["mode"] == "auto":
        _change(root, cfg, rule, "approve_each", now, person, "Incident on " + item.id)


def _hook(args, root, now, stdout, stdin):
    try:
        mappings = permissions.load(root)["tools"]
        if args.print_settings:
            hooks = []
            if mappings:
                matcher = "|".join(re.escape(name) for name in sorted(mappings))
                hooks.append(
                    {
                        "matcher": "^(" + matcher + ")$",
                        "hooks": [{"type": "command", "command": "mktgkit gate hook"}],
                    }
                )
            print(json.dumps({"hooks": {"PreToolUse": hooks}}, indent=2), file=stdout)
            return 0
        payload = json.load(stdin)
        if (
            not isinstance(payload, dict)
            or not isinstance(payload.get("tool_name"), str)
            or not payload["tool_name"].strip()
        ):
            raise ValueError("expected tool_name")
        mapping = mappings.get(payload["tool_name"])
        if mapping is None:
            return 0
        content = payload["tool_input"]
        for field in mapping["content_field"].split("."):
            content = content[field]
        check_content(root, mapping["action"], mapping["channel"], content, now)
    except (ValueError, KeyError, TypeError, MktgError) as exc:
        raise MktgError("gate hook blocked: " + str(exc), exit_code=2) from exc
    return 0


def _handle(args, root, now, stdout, stdin):
    cmd = args.gate_command
    if cmd == "hook":
        return _hook(args, root, now, stdout, stdin)
    cfg = permissions.load(root)
    if cmd == "check":
        if args.item:
            if args.channel:
                raise MktgError("--item does not take --channel", exit_code=2)
            result = _check(root, queue.get(root, args.item), now)
        else:
            if not args.channel:
                raise MktgError("--action requires --channel", exit_code=2)
            result = check_content(root, args.action, args.channel, stdin.read(), now)
        print(
            json.dumps(result)
            if args.format == "json"
            else "Allowed " + result["item"] + " (" + result["mode"] + ").",
            file=stdout,
        )
    elif cmd == "status":
        rows = cfg["rules"]
        print(
            json.dumps(cfg, ensure_ascii=False)
            if args.format == "json"
            else "\n".join(r["action"] + " / " + r["channel"] + "  " + r["mode"] for r in rows)
            or "Default: draft_only",
            file=stdout,
        )
    else:
        rules = [r for r in cfg["rules"] if (r["action"], r["channel"]) == (args.action, args.channel)]
        if not rules:
            raise MktgError("configure this action/channel pair in permissions.json first")
        rule = rules[0]
        if cmd == "promote":
            person = reviewer(root, args, stdin)
            target, found, needed, reason = progress(root, rule, cfg, now)
            if not target or found < needed:
                raise MktgError(f"{reason}: {found} of {needed}" if target else reason)
        else:
            if rule["mode"] == "draft_only" or not args.reason.strip():
                raise MktgError("demotion needs a reason and a mode above draft_only")
            target = permissions.MODES[permissions.MODES.index(rule["mode"]) - 1]
            reason, person = args.reason.strip(), actor(args)
        _change(root, cfg, rule, target, now, person, reason)
        print(rule["action"] + " / " + rule["channel"] + "  " + target, file=stdout)
    return 0


def register(subparsers):
    group = subparsers.add_parser("gate").add_subparsers(dest="gate_command", required=True)
    for cmd in ("status", "check", "promote", "demote", "hook"):
        parser = group.add_parser(cmd)
        parser.set_defaults(handler=_handle)
        if cmd == "check":
            selector = parser.add_mutually_exclusive_group(required=True)
            selector.add_argument("--item")
            selector.add_argument("--action")
            parser.add_argument("--channel")
        if cmd in ("promote", "demote"):
            parser.add_argument("--action", required=True)
            parser.add_argument("--channel", required=True)
        if cmd == "promote":
            decision_flags(parser)
        if cmd == "demote":
            parser.add_argument("--reason", required=True)
            parser.add_argument("--by")
        if cmd == "hook":
            parser.add_argument("--print-settings", action="store_true")
