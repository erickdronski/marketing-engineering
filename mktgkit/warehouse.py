"""Build a local warehouse from exports and query one consistent read-only snapshot."""

# Keep Optional usable by runtime type inspection on Python 3.9.
# ruff: noqa: UP045
from __future__ import annotations

import csv
import json
import math
import os
import sqlite3
import tempfile
import time
from contextlib import closing
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Optional

from .errors import MktgError
from .workspace import clock, config, parse_time, scoped

TABLES = ("web_sessions", "posts", "ad_spend", "email_events", "signups", "load_log")
VIEWS = ("campaign_performance", "attribution_coverage")
MAX_ROWS = 1000
SAFE_FUNCTIONS = frozenset(
    [
        "abs",
        "avg",
        "cast",
        "ceil",
        "ceiling",
        "char",
        "coalesce",
        "concat",
        "count",
        "cume_dist",
        "current_date",
        "current_time",
        "current_timestamp",
        "date",
        "datetime",
        "dense_rank",
        "first_value",
        "floor",
        "glob",
        "group_concat",
        "hex",
        "ifnull",
        "iif",
        "instr",
        "julianday",
        "lag",
        "last_value",
        "lead",
        "length",
        "like",
        "likelihood",
        "likely",
        "lower",
        "ltrim",
        "max",
        "min",
        "nth_value",
        "ntile",
        "nullif",
        "percent_rank",
        "quote",
        "rank",
        "replace",
        "round",
        "row_number",
        "rtrim",
        "sign",
        "strftime",
        "substr",
        "substring",
        "sum",
        "time",
        "total",
        "trim",
        "typeof",
        "unicode",
        "unixepoch",
        "unlikely",
        "upper",
    ]
)


@dataclass
class TableAge:
    table: str
    loaded_at: Optional[str]
    age_hours: Optional[float]
    limit_hours: Optional[float]
    stale: bool


@dataclass
class QueryResult:
    columns: list[str]
    rows: list[list[Any]]
    truncated: bool
    tables: list[str]
    freshness: list[TableAge]


def db_path(root):
    return scoped(root, "warehouse/warehouse.db")


def _trusted_statement(*_):
    # Python 3.9 does not reliably clear an authorizer with None.
    return sqlite3.SQLITE_OK


def _schema_policy(action, first, second, database, source):
    if database not in ("main", None):
        return sqlite3.SQLITE_DENY
    if action == sqlite3.SQLITE_CREATE_TABLE and first in TABLES:
        return sqlite3.SQLITE_OK
    if action == sqlite3.SQLITE_CREATE_VIEW and first in VIEWS:
        return sqlite3.SQLITE_OK
    if action == sqlite3.SQLITE_CREATE_INDEX and second in TABLES:
        return sqlite3.SQLITE_OK
    if action in (sqlite3.SQLITE_INSERT, sqlite3.SQLITE_UPDATE) and first == "sqlite_master":
        return sqlite3.SQLITE_OK
    if action in (sqlite3.SQLITE_READ, sqlite3.SQLITE_SELECT, sqlite3.SQLITE_REINDEX):
        return sqlite3.SQLITE_OK
    if action == sqlite3.SQLITE_FUNCTION and second in SAFE_FUNCTIONS:
        return sqlite3.SQLITE_OK
    return sqlite3.SQLITE_DENY


def _load_csv(connection, root, table):
    columns = [r[1] for r in connection.execute('PRAGMA table_info("' + table + '")')]
    relative = "warehouse/seed/" + table + ".csv"
    insert = "INSERT INTO " + table + " VALUES (" + ",".join("?" for _ in columns) + ")"
    with scoped(root, relative).open(encoding="utf-8-sig", newline="") as source:
        reader = csv.reader(source, strict=True)
        if next(reader, []) != columns:
            raise MktgError("unexpected CSV header", path=relative, fix="Expected " + ",".join(columns))
        count = 0
        for row in reader:
            try:
                if len(row) != len(columns):
                    raise ValueError(f"expected {len(columns)} columns")
                if table == "load_log":
                    # Canonical UTC makes SQL timestamp ordering chronological.
                    stamp = parse_time(row[1])
                    row[1] = stamp.strftime("%Y-%m-%dT%H:%M:%SZ")
                connection.execute(insert, tuple(None if x == "" else x for x in row))
            except (sqlite3.Error, ValueError, MktgError) as exc:
                raise MktgError(f"row {reader.line_num}: {exc}", path=relative) from exc
            count += 1
    return count


def _source_load(conn, table, actual_count=None):
    latest = conn.execute(
        "SELECT loaded_at, row_count FROM load_log WHERE table_name = ? ORDER BY loaded_at DESC LIMIT 1",
        (table,),
    ).fetchone()
    if latest is None:
        return None
    stamp, declared = latest
    if actual_count is None:
        actual_count = conn.execute("SELECT count(*) FROM " + table).fetchone()[0]
    if actual_count != declared:
        raise MktgError(
            f"{table}: latest load at {stamp} declares {declared} rows, but the snapshot contains {actual_count}",
            path="warehouse",
            fix=f"Reconcile seed/{table}.csv with its source export and seed/load_log.csv, then rebuild.",
        )
    return stamp


def _import_snapshot(conn, root):
    try:
        for script in ("schema.sql", "views.sql"):
            relative = "warehouse/" + script
            conn.set_authorizer(_schema_policy)
            conn.executescript(scoped(root, relative).read_text(encoding="utf-8"))
            conn.set_authorizer(_trusted_statement)
        counts = {table: _load_csv(conn, root, table) for table in TABLES}
        for table in TABLES[:-1]:
            _source_load(conn, table, counts[table])
        for view in VIEWS:
            conn.execute("SELECT * FROM " + view + " LIMIT 0")
        return counts
    except (OSError, UnicodeError, csv.Error, sqlite3.Error) as exc:
        message = getattr(exc, "strerror", None) or str(exc)
        raise MktgError(message, path="warehouse", fix="Check the schema, views and seed CSV files.") from exc


def validate_exports(root):
    # SQLite manages this temporary database outside the client's workspace.
    with closing(sqlite3.connect("")) as conn:
        _import_snapshot(conn, root)


def build(root):
    target = db_path(root)
    folder = target.parent
    if not folder.is_dir():
        raise MktgError("warehouse folder missing", fix="Run mktgkit init to create a workspace.")
    fd, tmp = tempfile.mkstemp(prefix=".warehouse-", suffix=".db", dir=folder)
    os.close(fd)
    try:
        with closing(sqlite3.connect(tmp)) as conn:
            counts = _import_snapshot(conn, root)
            conn.commit()
        os.replace(tmp, target)
        return counts
    except (OSError, sqlite3.Error) as exc:
        raise MktgError(
            str(exc), path="warehouse", fix="Check available disk space and permissions."
        ) from exc
    finally:
        Path(tmp).unlink(missing_ok=True)


def _reader(root):
    target = db_path(root)
    if not target.is_file():
        raise MktgError("warehouse has not been built", fix="Run mktgkit warehouse build.")
    return sqlite3.connect(target.as_uri() + "?mode=ro", uri=True, cached_statements=0)


def _ages(conn, root, tables, now):
    try:
        limits = json.loads(scoped(root, "warehouse/freshness.json").read_text(encoding="utf-8"))[
            "max_age_hours"
        ]
        if not isinstance(limits, dict):
            raise TypeError
        if any(
            type(limits.get(t)) not in (float, int) or not math.isfinite(limits[t]) or limits[t] <= 0
            for t in TABLES[:-1]
        ):
            raise ValueError
    except (OSError, KeyError, ValueError, TypeError) as exc:
        raise MktgError(
            "each data table needs a positive max_age_hours", path="warehouse/freshness.json"
        ) from exc
    # The log measures source ingestion, independently of when this database was built.
    result = []
    for table in tables:
        if table not in TABLES:
            raise MktgError("unknown source table: " + str(table), fix="Choose one of " + ", ".join(TABLES))
        if table == "load_log":
            stamp = conn.execute("SELECT MAX(loaded_at) FROM load_log").fetchone()[0]
        else:
            stamp = _source_load(conn, table)
        hours = (now - parse_time(stamp)).total_seconds() / 3600 if stamp else None
        limit = limits.get(table)
        stale = hours is None or hours < 0 or (limit is not None and hours > limit)
        result.append(TableAge(table, stamp, hours, limit, stale))
    return result


def freshness(root, tables=None, *, now=None):
    now = now or clock(config(root), None, os.environ)
    with closing(_reader(root)) as conn:
        conn.execute("BEGIN")
        return _ages(conn, root, TABLES[:-1] if tables is None else tables, now)


def list_tables(root):
    with closing(_reader(root)) as conn:
        available = dict(conn.execute("SELECT name, type FROM sqlite_master WHERE type IN ('table','view')"))
    return [{"name": name, "type": available[name]} for name in TABLES + VIEWS if name in available]


def describe(root, name):
    if name not in TABLES + VIEWS:
        raise MktgError("unknown table or view: " + str(name), fix="Use list_tables to see available names.")
    with closing(_reader(root)) as conn:
        return [
            {"name": r[1], "type": r[2] or "derived"}
            for r in conn.execute('PRAGMA table_info("' + name + '")')
        ]


def _query_policy(tables):
    def authorize(action, first, second, database, source):
        if action == sqlite3.SQLITE_READ and database in (None, "main") and first in TABLES + VIEWS:
            if first in TABLES:
                tables.add(first)
            return sqlite3.SQLITE_OK
        # SQLite labels a CTE COUNT(*) read with its ephemeral name and no database.
        if (
            action == sqlite3.SQLITE_READ
            and database is None
            and second == ""
            and not first.startswith("sqlite_")
        ):
            return sqlite3.SQLITE_OK
        if action in (sqlite3.SQLITE_SELECT, getattr(sqlite3, "SQLITE_RECURSIVE", 33)):
            return sqlite3.SQLITE_OK
        if action == sqlite3.SQLITE_FUNCTION and (second or "").lower() in SAFE_FUNCTIONS:
            return sqlite3.SQLITE_OK
        return sqlite3.SQLITE_DENY

    return authorize


def query(root, sql, *, limit=200, timeout_s=5.0, now=None):
    if type(limit) is not int or not 1 <= limit <= MAX_ROWS:
        raise MktgError("limit must be an integer from 1 to at most 1000")
    if not isinstance(sql, str) or not sql.strip() or len(sql) > 32000:
        raise MktgError("provide one read-only SQL query of at most 32000 characters")
    if type(timeout_s) not in (int, float) or not math.isfinite(timeout_s) or timeout_s <= 0:
        raise MktgError("timeout must be a positive number of seconds")
    now = now or clock(config(root), None, os.environ)
    tables = set()
    with closing(_reader(root)) as conn:
        conn.execute("BEGIN")
        if hasattr(conn, "setlimit"):
            conn.setlimit(sqlite3.SQLITE_LIMIT_LENGTH, 1_000_000)
        conn.set_authorizer(_query_policy(tables))
        deadline = time.monotonic() + timeout_s
        conn.set_progress_handler(lambda: int(time.monotonic() >= deadline), 1000)
        try:
            cursor = conn.execute(sql)
            if not cursor.description:
                raise MktgError("expected one read-only SELECT query")
            columns = [c[0] for c in cursor.description]
            rows = [list(row) for row in cursor.fetchmany(limit + 1)]
            if any(
                isinstance(value, bytes) or (isinstance(value, float) and not math.isfinite(value))
                for row in rows
                for value in row
            ):
                raise MktgError("use text and finite numeric result values")
        except (sqlite3.Error, sqlite3.Warning) as exc:
            message = "query stopped at its time limit" if str(exc) == "interrupted" else str(exc)
            raise MktgError(
                message, fix="Use one read-only SELECT against the listed tables or views."
            ) from exc
        finally:
            conn.set_progress_handler(None, 0)
            conn.set_authorizer(_trusted_statement)
        names = sorted(tables)
        return QueryResult(columns, rows[:limit], len(rows) > limit, names, _ages(conn, root, names, now))


def footer(ages):
    parts = []
    for item in ages:
        if item.loaded_at is None:
            detail = "never loaded"
        else:
            limit = f", limit {item.limit_hours:g} h" if item.limit_hours is not None else ""
            detail = "loaded {} UTC, {:g} h old{}".format(
                parse_time(item.loaded_at).strftime("%Y-%m-%d %H:%M"), round(item.age_hours, 2), limit
            )
        parts.append("{} ({}){}".format(item.table, detail, " STALE" if item.stale else ""))
    return "Source freshness: " + ("; ".join(parts) if parts else "no source tables read")


def render_table(columns, rows):
    return "\n".join(" | ".join("—" if x is None else str(x) for x in row) for row in [columns] + list(rows))


def render_query(result):
    body = render_table(result.columns, result.rows)
    if result.truncated:
        body += "\nRow limit reached; more rows are available."
    return body + "\n" + footer(result.freshness)


def _command(args, root, now, stdout, stdin):
    as_json = getattr(args, "format", "text") == "json"
    if args.warehouse_command == "build":
        counts = build(root)
        print(json.dumps(counts) if as_json else render_table(["Table", "Rows"], counts.items()), file=stdout)
        return 0
    if args.warehouse_command == "query":
        result = query(root, args.sql, limit=args.limit, now=now)
        values = result.freshness
        text = json.dumps(asdict(result), ensure_ascii=False) if as_json else render_query(result)
    else:
        values = freshness(root, args.tables or None, now=now)
        text = json.dumps([asdict(x) for x in values]) if as_json else footer(values)
    print(text, file=stdout)
    return 5 if args.require_fresh and any(item.stale for item in values) else 0


def register(subparsers):
    parent = subparsers.add_parser("warehouse", help="Load CSV exports and query measured outcomes")
    commands = parent.add_subparsers(dest="warehouse_command", required=True)
    create = commands.add_parser("build", help="Build or replace the SQLite warehouse from CSV")
    select = commands.add_parser("query", help="Run a read-only SQL query")
    select.add_argument("sql")
    select.add_argument("--limit", type=int, default=200)
    ages = commands.add_parser("freshness", help="Read data ages from the source load log")
    ages.add_argument("tables", nargs="*", choices=None)
    for command in (select, ages):
        command.add_argument("--require-fresh", action="store_true")
    for command in (create, select, ages):
        command.set_defaults(handler=_command)
