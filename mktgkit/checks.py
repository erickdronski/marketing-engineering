"""Inspect the pieces a consultant hands over to the client."""

import json
import re

from . import brain, frontmatter, ledger, permissions, queue, warehouse
from .errors import MktgError
from .workspace import config, scoped, timestamp


def inspect(root, now):
    errors, warnings, _, _ = brain.inspect(root, now)
    checked = [
        "notes and evidence",
        "goals",
        "agent definitions",
        "permissions",
        "review history",
        "warehouse",
    ]
    for filename in (
        "AGENTS.md",
        "goals.md",
        ".mcp.json",
        ".claude/settings.json",
        "warehouse/schema.sql",
        "warehouse/views.sql",
        "warehouse/freshness.json",
        "log/ledger.jsonl",
    ):
        if not scoped(root, filename).is_file():
            errors.append(f"{filename}: missing workspace file")
    if not scoped(root, "agents/orchestrator.md").is_file():
        errors.append("agents/orchestrator.md: missing agent definition")
    if not any(scoped(root, "agents/channels").glob("*.md")):
        errors.append("agents/channels: define at least one channel owner")
    if all(
        scoped(root, name).is_file() for name in ("goals.md", "warehouse/schema.sql", "warehouse/views.sql")
    ):
        schema = "\n".join(
            scoped(root, name).read_text(encoding="utf-8")
            for name in ("warehouse/schema.sql", "warehouse/views.sql")
        )
        tables = {
            name.lower()
            for name in re.findall(r"(?i)CREATE\s+(?:TABLE|VIEW)\s+(?:IF\s+NOT\s+EXISTS\s+)?(\w+)", schema)
        }
        for line in scoped(root, "goals.md").read_text(encoding="utf-8").splitlines():
            cells = [c.strip() for c in line.strip().strip("|").split("|")]
            if re.fullmatch(r"G-?\d+", cells[0], re.IGNORECASE):
                if len(cells) != 6 or any(not cell for cell in cells):
                    errors.append(
                        f"goals.md: {cells[0]} needs a goal, metric, table, target and decision date"
                    )
                elif cells[3].strip("`").lower() not in tables:
                    errors.append(f"goals.md: {cells[0]} names an unknown table {cells[3]}")
    for path in sorted(scoped(root, "agents").rglob("*.md")):
        if path.name.lower() == "readme.md":
            continue
        rel = path.relative_to(root).as_posix()
        try:
            fields, _ = frontmatter.read(scoped(root, rel), rel=rel)
            if fields.get("role") not in ("orchestrator", "channel", "subagent"):
                errors.append(f"{rel}: role must identify the agent's work")
            if fields.get("role") == "channel" and (
                fields.get("status") not in ("active", "parked")
                or (fields.get("status") == "parked" and not fields.get("switch_on"))
            ):
                errors.append(f"{rel}: describe channel status and what activates a parked channel")
            wrapper = scoped(root, ".claude/agents/" + path.name)
            if not wrapper.exists() or rel not in wrapper.read_text(encoding="utf-8"):
                errors.append(f"{rel}: agent wrapper must reference its definition")
        except (MktgError, ValueError, OSError) as exc:
            errors.append(f"{rel}: {exc}")
    for fn in (lambda: permissions.load(root), lambda: queue.audit(root, now)):
        try:
            value = fn()
            if isinstance(value, list):
                errors.extend(value)
        except MktgError as exc:
            errors.append(f"{exc.path}: {exc.message}" if exc.path else exc.message)
        except (ValueError, OSError) as exc:
            errors.append(str(exc))
    try:
        for event in ledger.read(root):
            if event.get("attended") == "overridden":
                warnings.append(
                    f"Attendance override on {event.get('event')} for {event.get('item') or event.get('claim') or event.get('action')}: {event.get('override_reason') or 'reason missing'}"
                )
    except (MktgError, ValueError, OSError) as exc:
        errors.append(str(exc))
    if not scoped(root, "warehouse/warehouse.db").is_file():
        warnings.append("Warehouse not built. Run mktgkit warehouse build before querying.")
    else:
        try:
            for age in warehouse.freshness(root, now=now):
                if age.stale:
                    warnings.append(
                        f"warehouse/{age.table}: refresh before making decisions with this source"
                    )
        except (MktgError, OSError, ValueError) as exc:
            errors.append(str(exc))
    return {
        "workspace": config(root)["name"],
        "checked_at": timestamp(now),
        "checks": checked,
        "errors": errors,
        "warnings": warnings,
    }


def handle(args, root, now, stdout, stdin):
    result = inspect(root, now)
    if args.format == "json":
        print(json.dumps(result, ensure_ascii=False), file=stdout)
    else:
        print(f"Workspace: {result['workspace']}", file=stdout)
        for label in ("errors", "warnings"):
            for message in result[label]:
                print(f"  {label[:-1]}: {message}", file=stdout)
        print(f"Errors: {len(result['errors'])}. Warnings: {len(result['warnings'])}.", file=stdout)
    return int(bool(result["errors"]))
