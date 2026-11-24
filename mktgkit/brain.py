"""Check the workspace knowledge base and expose the links behind a brief."""

import json
import re
from datetime import date
from pathlib import PurePosixPath

from . import frontmatter
from .errors import MktgError
from .workspace import scoped

TYPES = {"offer", "customer", "brand", "claim", "result", "edit", "skill", "research"}
MAX_AGE = {"research": 90, "offer": 180, "customer": 180, "claim": 180, "result": 180}
VAGUE = {"internal data", "tbd", "industry standard", "research shows", "unknown"}
LINK = re.compile(r"\[\[([^\]\n]+)\]\]")


def links(text):
    fence = ""
    for line in text.splitlines():
        stripped = line.lstrip()
        if fence:
            if stripped.startswith(fence) and not stripped.strip(fence[0]).strip():
                fence = ""
            continue
        marker = re.match(r"^(\x60{3,}|~{3,})", stripped)
        if marker:
            fence = marker[1]
            continue
        for name in LINK.findall(re.sub(r"\x60[^\x60]*\x60", "", line)):
            name = name.split("|")[0].split("#")[0].strip().removesuffix(".md")
            if name:
                yield name


def _notes(root):
    notes, errors = {}, []
    for path in sorted(scoped(root, "brain").rglob("*.md")):
        if path.name.lower() == "readme.md":
            continue
        rel = path.relative_to(root).as_posix()
        try:
            fields, body = frontmatter.read(scoped(root, rel), rel=rel)
        except (MktgError, ValueError, OSError) as exc:
            errors.append(f"{rel}: {exc}")
            continue
        notes[rel[6:-3]] = fields, body
    return notes, errors


def inspect(root, now):
    notes, errors = _notes(root)
    warnings, edges = [], set()
    targets = set(notes)
    for folder in ("agents", "batches", "queue"):
        targets.update(
            p.relative_to(root).as_posix()[:-3]
            for p in scoped(root, folder).rglob("*.md")
            if p.name.lower() != "readme.md"
        )
    by_name = {}
    for name in sorted(targets):
        by_name.setdefault(PurePosixPath(name).name, []).append(name)
    claims = {}
    for name, (fields, body) in notes.items():

        def issue(message, note=name):
            errors.append(f"brain/{note}.md: {message}")

        kind = fields.get("kind")
        note_type = fields.get("type")
        if not isinstance(fields.get("title"), str) or not fields["title"].strip():
            issue("give the note a title")
        if not isinstance(note_type, str) or note_type not in TYPES:
            issue("type must be a supported note type, written as a single word")
            note_type = None
        if kind not in ("fact", "inference", "assumption"):
            issue("kind must be fact, inference or assumption, written as a single word")
            kind = None
        try:
            as_of = date.fromisoformat(str(fields.get("as_of")))
            if fields.get("review_by") and date.fromisoformat(str(fields["review_by"])) < now.date():
                warnings.append(f"brain/{name}.md: review_by date has passed")
            elif note_type in MAX_AGE and (now.date() - as_of).days > MAX_AGE[note_type]:
                warnings.append(f"brain/{name}.md: older than {MAX_AGE[note_type]} days")
        except ValueError:
            issue("dates must use YYYY-MM-DD")
        field = {"fact": "source", "inference": "derivation", "assumption": "rationale"}.get(kind)
        if field:
            value = fields.get(field)
            if not isinstance(value, str) or not value.strip() or value.strip().casefold() in VAGUE:
                issue(f"give a specific {field}")
        if note_type == "claim":
            claim_id = fields.get("id")
            if not isinstance(claim_id, str) or not claim_id or claim_id in claims:
                issue("provide a unique claim id")
            else:
                claims[claim_id] = name
            figures = fields.get("figures")
            if (
                not isinstance(figures, list)
                or not figures
                or not all(isinstance(v, str) and v.strip() for v in figures)
            ):
                issue("figures must list nonempty text such as 38 minutes")
        found = []
        for link in links(body):
            lookup = link.removeprefix("brain/")
            matches = [lookup] if lookup in targets else by_name.get(lookup, [])
            if not matches:
                issue(f"broken link [[{link}]]")
            elif len(matches) > 1:
                warnings.append(f"brain/{name}.md: ambiguous link [[{link}]], use a folder")
            else:
                found.append(matches[0])
                edges.add((name, matches[0]))
        if kind == "inference" and not any(
            notes.get(target, ({}, ""))[0].get("kind") == "fact" for target in found
        ):
            issue("link an inference to a supporting fact")
        if note_type == "edit" and not found:
            issue("link this edit to the work it changes")
    connected = {node for edge in edges for node in edge}
    warnings.extend(f"brain/{name}.md: isolated note" for name in sorted(notes.keys() - connected))
    return errors, warnings, sorted(notes.keys() | connected), sorted(edges)


def register(subparsers):
    parser = subparsers.add_parser("brain", help="check evidence notes and show their links")
    commands = parser.add_subparsers(dest="brain_action", required=True)
    for action in ("check", "graph"):
        commands.add_parser(action).set_defaults(handler=handle)


def handle(args, root, now, stdout, stdin):
    errors, warnings, nodes, edges = inspect(root, now)
    if args.brain_action == "check":
        if args.format == "json":
            print(json.dumps({"errors": errors, "warnings": warnings}), file=stdout)
        else:
            for line in errors + warnings:
                print(line, file=stdout)
            print(
                f"{len(nodes)} linked or recorded notes; {len(errors)} error(s), {len(warnings)} warning(s).",
                file=stdout,
            )
        return int(bool(errors))
    if args.format == "json":
        print(json.dumps({"nodes": nodes, "edges": [{"from": a, "to": b} for a, b in edges]}), file=stdout)
    else:
        keys = {node: f"n{i}" for i, node in enumerate(nodes, 1)}
        print("graph LR", file=stdout)
        for node in nodes:
            safe = re.sub(r"[^A-Za-z0-9 /_.-]", "_", node)
            print(f'  {keys[node]}["{safe}"]', file=stdout)
        for a, b in edges:
            print(f"  {keys[a]} --> {keys[b]}", file=stdout)
    return 0
