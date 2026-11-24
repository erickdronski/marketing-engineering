"""Versioned review items and their recorded decisions."""

import json
import re
import unicodedata
from dataclasses import dataclass

from . import claims, feedback, frontmatter, ledger, permissions
from .decisions import actor, decision_flags, reviewer
from .errors import MktgError
from .workspace import scoped, text_hash, timestamp

PRIORITIES = ("high", "medium", "low")
STATES = {
    "submitted": "in_review",
    "resubmitted": "in_review",
    "approved": "approved",
    "sent_back": "sent_back",
    "went_live": "live",
    "withdrawn": "withdrawn",
}
DRAFT_FIELDS = ("title", "channel", "action", "priority", "claims", "depends_on", "batch", "notes")


@dataclass
class Item:
    path: str
    fields: dict
    body: str

    @property
    def id(self):
        return self.fields["id"]

    @property
    def status(self):
        return self.fields["status"]


def items(root):
    found = {}
    for path in sorted(scoped(root, "queue").glob("*.md")):
        if path.name.lower() == "readme.md":
            continue
        rel = path.relative_to(root.resolve()).as_posix()
        fields, body = frontmatter.read(scoped(root, rel))
        key = fields.get("id")
        if (
            not isinstance(key, str)
            or not re.fullmatch(r"Q-\d{4,}", key)
            or not path.name.startswith(key + "-")
            or key in found
        ):
            raise MktgError("missing, duplicate or inconsistent queue id", path=rel)
        if fields.get("status") not in STATES.values() or fields.get("priority") not in PRIORITIES:
            raise MktgError("invalid status or priority", path=rel)
        if type(fields.get("version")) is not int or fields["version"] < 1:
            raise MktgError("invalid version", path=rel)
        for field in ("title", "channel", "action"):
            if not isinstance(fields.get(field), str) or not fields[field].strip():
                raise MktgError("missing " + field, path=rel)
        for field in ("claims", "depends_on"):
            claims.string_list(fields, field, path=rel)
        found[key] = Item(rel, fields, body)
    return sorted(found.values(), key=lambda i: (PRIORITIES.index(i.fields["priority"]), i.id))


def get(root, ref):
    for item in items(root):
        if item.id == ref or item.path[6:-3] == ref:
            return item
    raise MktgError("unknown queue item " + ref)


def _slug(title):
    ascii_title = unicodedata.normalize("NFKD", title).encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[^a-z0-9]+", "-", ascii_title.lower()).strip("-")[:40].rstrip("-") or "draft"


def enabled_action(root, fields):
    """Check the current channel definition, including its allowed actions."""
    if not permissions.NAME.fullmatch(fields["channel"]):
        raise MktgError("invalid channel")
    channel = scoped(root, "agents/channels/" + fields["channel"] + ".md")
    if not channel.is_file():
        raise MktgError("unknown channel " + fields["channel"])
    channel_meta, _ = frontmatter.read(channel)
    if channel_meta.get("status", channel_meta.get("active")) not in ("active", True):
        raise MktgError(
            fields["channel"] + " is parked",
            fix=str(channel_meta.get("switch_on") or "Activate it before scheduling work."),
        )
    config = permissions.load(root)
    if fields["action"] not in {r["action"] for r in config["rules"]}:
        raise MktgError("unknown action " + fields["action"], fix="Register the action in permissions.json.")
    if fields["action"] not in claims.string_list(channel_meta, "actions"):
        raise MktgError(
            f"{fields['channel']} does not allow action {fields['action']}",
            fix="Use an action declared by this channel or select the correct channel.",
        )


def _validate_draft(root, fields, body, now, previous=None):
    required = ("title", "channel", "action", "priority")
    if any(not isinstance(fields.get(k), str) or not fields[k].strip() for k in required):
        raise MktgError("a draft needs a title, channel, action and priority")
    if not body.strip() or fields["priority"] not in PRIORITIES:
        raise MktgError("a draft needs body text and high, medium or low priority")
    enabled_action(root, fields)
    if previous and (fields["action"], fields["channel"]) != (
        previous.fields["action"],
        previous.fields["channel"],
    ):
        raise MktgError(
            "a revised item must keep its action and channel",
            fix="Submit a new item for the new destination.",
        )
    dependencies = claims.string_list(fields, "depends_on")
    all_items = {i.id: i for i in items(root)}
    visiting = set(dependencies)
    seen = set()
    while visiting:
        key = visiting.pop()
        if previous and key == previous.id:
            raise MktgError("dependency cycle involving " + key)
        if key not in all_items:
            raise MktgError("unknown dependency " + key)
        seen.add(key)
        visiting.update(set(claims.string_list(all_items[key].fields, "depends_on")) - seen)
    claims.validate(root, body, claims.string_list(fields, "claims"), now)


def last_state(entries, key):
    return next((e for e in reversed(entries) if e.get("item") == key and e.get("event") in STATES), None)


def integrity(item, entries):
    event = last_state(entries, item.id)
    if not event or item.status != STATES[event["event"]] or item.fields["version"] != event.get("version"):
        return item.id + " state/version disagrees with the ledger"
    fields = item.fields
    if any(event.get(key) != fields[key] for key in ("channel", "action")):
        return item.id + " action/channel disagrees with the ledger"
    if text_hash(item.body) != event.get("sha256"):
        return (
            item.id
            + " text changed after "
            + ("approval" if item.status == "approved" else "recording")
            + (
                "; resubmit the draft or restore the recorded text"
                if item.status in ("approved", "sent_back")
                else "; restore the recorded text before proceeding"
            )
        )
    if review_hash(item) != event.get("review_sha256"):
        return item.id + " review metadata changed; restore the recorded metadata before proceeding"
    return ""


def review_hash(item):
    keys = {k: item.fields[k] for k in DRAFT_FIELDS if k in item.fields}
    return text_hash(json.dumps(keys, sort_keys=True, ensure_ascii=False))


def audit(root, now):
    entries = ledger.read(root)
    result = []
    current = items(root)
    ids = {i.id for i in current}
    for item in current:
        error = integrity(item, entries)
        if error:
            result.append(error)
        for dep in claims.string_list(item.fields, "depends_on"):
            if dep not in ids:
                result.append(item.id + " has missing dependency " + dep)
        if item.status in ("approved", "in_review"):
            try:
                enabled_action(root, item.fields)
                claims.validate(root, item.body, claims.string_list(item.fields, "claims"), now)
            except MktgError as exc:
                result.append(item.id + ": " + str(exc))
    for orphan in sorted({e["item"] for e in entries if e.get("event") in STATES and "item" in e} - ids):
        result.append(orphan + " is in the ledger but missing from queue/")
    return result


def dependency_check(root, item, entries):
    for key in claims.string_list(item.fields, "depends_on"):
        dep = get(root, key)
        if dep.status not in ("approved", "live") or integrity(dep, entries):
            raise MktgError("dependency " + key + " needs a valid approval", exit_code=3)


def record(root, item, now, event, person, **extra):
    if event in STATES:
        item.fields["status"] = STATES[event]
    frontmatter.write(scoped(root, item.path), item.fields, item.body)
    row = dict(
        person,
        ts=timestamp(now),
        event=event,
        item=item.id,
        version=item.fields["version"],
        sha256=text_hash(item.body),
        review_sha256=review_hash(item),
        channel=item.fields["channel"],
        action=item.fields["action"],
        **extra,
    )
    ledger.append(root, row)


def _submit(root, now, draft, person, previous=None):
    path = scoped(root, draft)
    if not path.is_file():
        raise MktgError(
            "draft file does not exist", path=draft, fix="Provide the Markdown path inside this workspace."
        )
    fields, body = frontmatter.read(path, rel=draft)
    _validate_draft(root, fields, body, now, previous)
    cleaned = {k: fields[k] for k in DRAFT_FIELDS if k in fields}
    if previous:
        cleaned.update(
            id=previous.id, created=previous.fields["created"], version=previous.fields["version"] + 1
        )
        item = Item(previous.path, cleaned, body)
    else:
        seen = [int(i.id[2:]) for i in items(root)]
        seen += [
            int(e["item"][2:]) for e in ledger.read(root) if re.fullmatch(r"Q-\d{4,}", str(e.get("item", "")))
        ]
        key = f"Q-{max(seen, default=0) + 1:04d}"
        cleaned.update(id=key, created=timestamp(now), version=1)
        item = Item("queue/" + key + "-" + _slug(fields["title"]) + ".md", cleaned, body)
    record(root, item, now, "resubmitted" if previous else "submitted", person)
    return item


def _require(item, statuses):
    if item.status not in statuses:
        raise MktgError(item.id + " is " + item.status + "; expected " + " or ".join(statuses))


def _edit(root, item, args, person, now):
    feedback.validate(args.feedback)
    refs = []
    for ref in args.applies_to or []:
        matches = [
            p
            for p in scoped(root, "brain").rglob("*.md")
            if p.stem == ref or p.relative_to(root.resolve()).with_suffix("").as_posix() == ref
        ]
        if len(matches) != 1:
            raise MktgError("unknown or ambiguous note " + ref)
        refs.append(matches[0].relative_to(root.resolve()).with_suffix("").as_posix())
    directory = scoped(root, "brain/edits")
    nums = [int(m.group(1)) for p in directory.glob("*.md") for m in [re.match(r"E-(\d+)-", p.name)] if m]
    slug = item.path[6:-3]
    path = f"brain/edits/E-{max(nums, default=0) + 1:04d}-{_slug(item.fields['title'])}.md"
    links = [slug, "agents/channels/" + item.fields["channel"]] + refs
    body = args.feedback.strip()
    if args.because:
        body += "\n\nReason: " + args.because.strip()
    body += "\n\n" + " · ".join("[[" + link + "]]" for link in links)
    fields = {
        "title": "Revision of " + item.fields["title"],
        "type": "edit",
        "kind": "fact",
        "source": "Send-back of "
        + item.id
        + " version "
        + str(item.fields["version"])
        + " (log/ledger.jsonl)",
        "as_of": now.date().isoformat(),
        "item": item.id,
        "version": item.fields["version"],
    }
    frontmatter.write(scoped(root, path), fields, body)
    record(root, item, now, "sent_back", person, feedback=args.feedback.strip(), edit=path)


def _handle(args, root, now, stdout, stdin):
    from . import board, gate

    cmd = args.queue_command
    if cmd in ("list", "show", "render"):
        if cmd == "render":
            board.write(root, args.out, items(root), ledger.read(root))
            print("Wrote " + args.out, file=stdout)
        elif cmd == "show":
            item = get(root, args.id)
            print(
                json.dumps(dict(item.fields, body=item.body), ensure_ascii=False)
                if args.format == "json"
                else item.id + "  " + item.status + "\n" + item.body,
                file=stdout,
            )
        else:
            rows = [i.fields for i in items(root) if not args.status or i.status == args.status]
            print(
                json.dumps(rows, ensure_ascii=False)
                if args.format == "json"
                else "\n".join(i["id"] + "  " + i["status"] + "  " + i["title"] for i in rows)
                or "Queue is empty.",
                file=stdout,
            )
        return 0
    person = reviewer(root, args, stdin) if cmd in ("approve", "send-back") else actor(args)
    if cmd == "submit":
        item = _submit(root, now, args.file, person)
    else:
        item = get(root, args.id)
        entries = ledger.read(root)
        error = integrity(item, entries)
        # An edited body can be recovered by withdrawing or explicitly resubmitting.
        if error and (cmd not in ("withdraw", "resubmit") or "text changed after" not in error):
            raise MktgError(error)
        if cmd == "approve":
            _require(item, ("in_review",))
            enabled_action(root, item.fields)
            dependency_check(root, item, entries)
            claims.validate(root, item.body, claims.string_list(item.fields, "claims"), now)
            record(root, item, now, "approved", person)
        elif cmd == "send-back":
            _require(item, ("in_review",))
            _edit(root, item, args, person, now)
        elif cmd == "resubmit":
            _require(item, ("sent_back", "approved"))
            item = _submit(root, now, args.file, person, item)
        elif cmd == "withdraw":
            _require(item, ("in_review", "sent_back", "approved"))
            if not args.reason.strip():
                raise MktgError("supply a withdrawal reason")
            record(root, item, now, "withdrawn", person, reason=args.reason.strip())
        elif cmd == "incident":
            gate.incident(root, item, args.note, person, now)
        elif cmd == "mark-live":
            gate.mark_live(root, item, args.url, person, now)
    print(item.id + "  " + item.status + "  v" + str(item.fields["version"]), file=stdout)
    return 0


def register(subparsers):
    group = subparsers.add_parser("queue").add_subparsers(dest="queue_command", required=True)
    for cmd in (
        "list",
        "show",
        "render",
        "submit",
        "resubmit",
        "approve",
        "send-back",
        "withdraw",
        "mark-live",
        "incident",
    ):
        parser = group.add_parser(cmd)
        parser.set_defaults(handler=_handle)
        if cmd not in ("list", "render", "submit"):
            parser.add_argument("id")
        if cmd in ("submit", "resubmit"):
            parser.add_argument("file")
        if cmd in ("approve", "send-back"):
            decision_flags(parser)
        elif cmd not in ("list", "show", "render"):
            parser.add_argument("--by")
        if cmd == "list":
            parser.add_argument("--status", choices=sorted(set(STATES.values())))
        if cmd == "render":
            parser.add_argument("--out", default="out/queue.html")
        if cmd == "send-back":
            parser.add_argument("--feedback", required=True)
            parser.add_argument("--because")
            parser.add_argument("--applies-to", nargs="+")
        if cmd in ("withdraw", "mark-live", "incident"):
            parser.add_argument(
                {"withdraw": "--reason", "mark-live": "--url", "incident": "--note"}[cmd], required=True
            )
