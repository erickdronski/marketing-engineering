"""Match public figures to unchanged, approved evidence."""

import json
import re
from datetime import date

from . import brain, frontmatter, ledger
from .decisions import decision_flags, reviewer
from .errors import MktgError
from .workspace import scoped, text_hash, timestamp

UNITS = {
    "%": "%",
    "percent": "%",
    "x": "x",
    "×": "x",
    "k": "k",
    "thousand": "k",
    "m": "m",
    "million": "m",
    "bn": "bn",
    "billion": "bn",
    "min": "min",
    "minute": "min",
    "hr": "h",
    "hour": "h",
    "day": "d",
    "week": "w",
    "month": "mo",
    "year": "y",
}
NUMBER = r"[-+−]?(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?"
UNIT = r"(?:percent|thousands?|millions?|billions?|mins?|minutes?|hrs?|hours?|days?|weeks?|months?|years?|bn|[xkm])(?!\w)|[%×]"
FIGURE = re.compile(
    r"(?<![\w.,])(?:(?P<currency>[$€£])\s*(?P<money>" + NUMBER + r")(?:\s*(?P<scale>" + UNIT + r"))?"
    r"|(?P<number>" + NUMBER + r")\s*(?P<unit>" + UNIT + r"))",
    re.IGNORECASE,
)


def extract_figures(text):
    text = re.sub(r"https?://\S+", "", text)
    figures = {}
    for match in FIGURE.finditer(text):
        number = (match["number"] or match["money"]).replace(",", "").replace("−", "-")
        if "." in number:
            number = number.rstrip("0").rstrip(".")
        unit = (match["unit"] or match["scale"] or "").lower()
        normalized = (match["currency"] or "") + number + UNITS.get(unit, UNITS.get(unit.rstrip("s"), unit))
        figures.setdefault(normalized, match.group().strip())
    return [(raw, key) for key, raw in figures.items()]


def string_list(fields, key, *, path=None):
    value = fields.get(key) if fields.get(key) is not None else []
    if not isinstance(value, list) or any(not isinstance(i, str) or not i.strip() for i in value):
        raise MktgError(key + " must be a list of nonempty strings", path=path)
    return value


def load_claims(root):
    claims = {}
    for path in sorted(scoped(root, "brain/claims").glob("*.md")):
        if path.name.lower() == "readme.md":
            continue
        rel = path.relative_to(root.resolve())
        path = scoped(root, str(rel))
        fields, _ = frontmatter.read(path)
        key = fields.get("id")
        if not isinstance(key, str) or not key or key in claims:
            raise MktgError("missing or duplicate claim id", path=str(rel))
        figs = set()
        for raw in string_list(fields, "figures", path=rel.as_posix()):
            matches = extract_figures(raw)
            if len(matches) != 1 or matches[0][0] != raw.strip():
                raise MktgError("expected a single measurable figure: " + raw, path=str(rel))
            figs.add(matches[0][1])
        claims[key] = (fields, figs, text_hash(path.read_text(encoding="utf-8")))
    return claims


def _evidence(fields, now):
    if fields.get("type") != "claim" or not fields.get("figures"):
        return "claim notes need type claim and at least one measurable figure"
    if fields.get("kind") not in ("fact", "inference"):
        return "assumptions cannot support public figures"
    field = "source" if fields["kind"] == "fact" else "derivation"
    if (
        not isinstance(fields.get(field), str)
        or not fields[field].strip()
        or fields[field].strip().casefold() in brain.VAGUE
    ):
        return "missing " + field
    if fields.get("review_by"):
        try:
            expired = date.fromisoformat(str(fields["review_by"])) < now.date()
        except ValueError:
            return "invalid review_by date"
        if expired:
            return "review_by date has passed"
    return ""


def _status(key, claim, entries, now):
    fields, _, digest = claim
    problem = _evidence(fields, now)
    if problem:
        return problem
    entry = next(
        (e for e in reversed(entries) if e.get("event") == "claim_approved" and e.get("claim") == key), {}
    )
    if not entry:
        return "not signed off; run mktgkit claims approve " + key
    if entry.get("sha256") != digest:
        return "changed after sign-off"
    return "approved"


def list_claims(root, now):
    entries = ledger.read(root)
    return [{"id": k, "standing": _status(k, c, entries, now)} for k, c in load_claims(root).items()]


def validate(root, body, cited, now):
    catalog = load_claims(root)
    entries = ledger.read(root)
    problems = []
    accepted = set()
    for key in cited:
        if key not in catalog:
            problems.append("unknown cited claim " + key)
            continue
        status = _status(key, catalog[key], entries, now)
        if status != "approved":
            problems.append(key + ": " + status)
        else:
            accepted.update(catalog[key][1])
    for raw, value in extract_figures(body):
        if value not in accepted:
            problems.append(raw + " has no current signed-off claim among those cited")
    voice = scoped(root, "brain/brand/voice.md")
    if voice.exists():
        settings, _ = frontmatter.read(voice)
        for phrase in string_list(settings, "banned_phrases"):
            if re.search(r"(?<!\w)" + re.escape(phrase) + r"(?!\w)", body, re.IGNORECASE):
                problems.append("banned phrase: " + phrase)
    if problems:
        raise MktgError("; ".join(problems), fix="Revise the draft or cite an eligible signed-off claim.")


def _handle(args, root, now, stdout, stdin):
    if args.claim_command == "list":
        rows = list_claims(root, now)
        print(
            json.dumps(rows)
            if args.format == "json"
            else "\n".join(r["id"] + "  " + r["standing"] for r in rows) or "No claims.",
            file=stdout,
        )
    elif args.claim_command == "approve":
        person = reviewer(root, args, stdin)
        claims = load_claims(root)
        if args.id not in claims:
            raise MktgError("unknown claim: " + args.id)
        fields, _, digest = claims[args.id]
        problem = _evidence(fields, now)
        if problem:
            raise MktgError(args.id + ": " + problem)
        ledger.append(
            root, dict(person, ts=timestamp(now), event="claim_approved", claim=args.id, sha256=digest)
        )
        print("Signed off " + args.id, file=stdout)
    else:
        fields, body = frontmatter.read(scoped(root, args.file))
        cited = args.claims.split(",") if args.claims else string_list(fields, "claims")
        validate(root, body, cited, now)
        print("Claims check passed.", file=stdout)
    return 0


def register(subparsers):
    group = subparsers.add_parser("claims").add_subparsers(dest="claim_command", required=True)
    for name in ("list", "check", "approve"):
        parser = group.add_parser(name)
        parser.set_defaults(handler=_handle)
        if name == "check":
            parser.add_argument("file")
            parser.add_argument("--claims")
        elif name == "approve":
            parser.add_argument("id")
            decision_flags(parser)
