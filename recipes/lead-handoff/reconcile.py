"""Reconcile form requests to booked estimates using two de-identified CSV exports."""

import argparse
import csv
import io
import json
import re
import sys
import tempfile
from datetime import date, timedelta
from pathlib import Path

REQUEST_FIELDS = ("request_id", "request_date", "source", "is_test")
BOOKING_FIELDS = ("booking_id", "request_id", "booked_date")
KEY = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,95}")


def parse_date(value):
    if not re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", value):
        raise ValueError("expected YYYY-MM-DD")
    return date.fromisoformat(value)


def read_export(path, fields, date_column, as_of):
    with path.open(encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream, strict=True)
        if sorted(reader.fieldnames or []) != sorted(fields):
            raise ValueError(f"{path.name} must contain exactly these columns: {', '.join(fields)}")
        for row in reader:
            if None in row or None in row.values():
                raise ValueError(f"{path.name} line {reader.line_num}: wrong number of columns")
            row = {key: value.strip() for key, value in row.items()}
            try:
                row[date_column] = parse_date(row[date_column])
                if row[date_column] > as_of:
                    continue
                for key, value in row.items():
                    if key == date_column:
                        continue
                    if key == "is_test":
                        if value.lower() not in {"true", "false"}:
                            raise ValueError("is_test must be true or false")
                        row[key] = value.lower() == "true"
                    elif value and not KEY.fullmatch(value):
                        raise ValueError(f"{key} must be a short ID or source code")
            except ValueError as error:
                raise ValueError(f"{path.name} line {reader.line_num}: {error}") from error
            yield reader.line_num, row


def index_rows(rows, fields, dataset, issues):
    grouped = {}
    duplicates = 0
    for line, row in rows:
        key = row[fields[0]]
        if not key:
            issues.append((dataset, "", f"missing_{fields[0]}", str(line)))
            continue
        values = tuple(row[field] for field in fields[1:])
        group = grouped.setdefault(key, set())
        if values in group:
            duplicates += 1
        group.add(values)
    clean = {}
    for key, group in grouped.items():
        if len(group) == 1:
            clean[key] = next(iter(group))
        else:
            issues.append((dataset, key, f"conflicting_{fields[0]}", ""))
    return clean, duplicates


def csv_bytes(headers, rows):
    stream = io.StringIO(newline="")
    writer = csv.writer(stream, lineterminator="\n")
    writer.writerow(headers)
    writer.writerows(sorted(rows))
    return stream.getvalue().encode("utf-8")


def reconcile(request_path, booking_path, start, end, as_of, window):
    if end < start or as_of < end or window < 0:
        raise ValueError("use start <= end <= as-of and a nonnegative window")
    cohort_matures = end + timedelta(days=window)
    issues = []
    requests, repeated_requests = index_rows(
        read_export(request_path, REQUEST_FIELDS, "request_date", as_of), REQUEST_FIELDS, "requests", issues
    )
    bookings, repeated_bookings = index_rows(
        read_export(booking_path, BOOKING_FIELDS, "booked_date", as_of), BOOKING_FIELDS, "bookings", issues
    )
    first_booking = {}
    for booking_id, (request_id, booked) in bookings.items():
        if not request_id or request_id not in requests:
            problem = "unmatched_request_id" if request_id else "missing_request_id"
            issues.append(("bookings", booking_id, problem, ""))
            continue
        received = requests[request_id][0]
        if booked < received:
            issues.append(("bookings", booking_id, "booking_precedes_request", ""))
        elif start <= received <= end and booked <= received + timedelta(days=window):
            first_booking[request_id] = min(booked, first_booking.get(request_id, booked))

    groups = {}
    worklist = []
    provisional = 0
    ignored_tests = 0
    for request_id, (received, source, is_test) in sorted(requests.items()):
        if not start <= received <= end:
            continue
        if is_test:
            ignored_tests += 1
            continue
        source = source or "unknown"
        if received + timedelta(days=window) > as_of:
            provisional += 1
            worklist.append((request_id, source, "provisional", "", "Wait for the booking window to close."))
            continue
        booked = first_booking.get(request_id)
        group = groups.setdefault(source, {"eligible": 0, "booked": 0})
        group["eligible"] += 1
        group["booked"] += int(booked is not None)
        if source == "unknown":
            worklist.append((request_id, source, "unknown_source", "", "Check the original campaign field."))
        if booked:
            worklist.append((request_id, source, "booked", booked.isoformat(), "Reconcile to dispatch."))
        else:
            worklist.append((request_id, source, "no_booking_in_window", "", "Verify the dispatch record."))
    eligible = sum(row["eligible"] for row in groups.values())
    booked = sum(row["booked"] for row in groups.values())
    state = "ready"
    if issues:
        state = "needs_review"
    elif as_of < cohort_matures:
        state = "provisional"
    summary = {
        "status": state,
        "start": start.isoformat(),
        "end": end.isoformat(),
        "as_of": as_of.isoformat(),
        "booking_window_days": window,
        "mature_eligible": eligible,
        "mature_booked": booked,
        "booking_rate": booked / eligible if state == "ready" and eligible else None,
        "by_source": groups,
        "tagged_mature_requests": eligible - groups.get("unknown", {}).get("eligible", 0),
        "provisional_requests": provisional,
        "test_requests_excluded": ignored_tests,
        "duplicate_request_rows": repeated_requests,
        "duplicate_booking_rows": repeated_bookings,
        "input_exceptions": len(issues),
    }
    return summary, {
        "summary.json": (json.dumps(summary, indent=2, sort_keys=True) + "\n").encode("utf-8"),
        "worklist.csv": csv_bytes(
            ("request_id", "source", "status", "first_booked_date", "next_step"), worklist
        ),
        "exceptions.csv": csv_bytes(("export", "record_id", "issue", "line_if_id_missing"), issues),
    }


def save_outputs(target, files):
    target.parent.mkdir(parents=True, exist_ok=True)

    def same_result():
        return (
            target.is_dir()
            and not target.is_symlink()
            and {p.name for p in target.iterdir()} == set(files)
            and all(
                (target / name).is_file()
                and not (target / name).is_symlink()
                and (target / name).read_bytes() == contents
                for name, contents in files.items()
            )
        )

    if target.exists() or target.is_symlink():
        if same_result():
            return
        raise ValueError("output exists with different contents; choose a new directory")
    with tempfile.TemporaryDirectory(dir=target.parent) as temporary:
        staged = Path(temporary) / "result"
        staged.mkdir()
        for name, data in files.items():
            (staged / name).write_bytes(data)
        try:
            staged.rename(target)
        except OSError:
            if not same_result():
                raise


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--requests", type=Path, required=True)
    parser.add_argument("--bookings", type=Path, required=True)
    parser.add_argument("--start", type=parse_date, required=True)
    parser.add_argument("--end", type=parse_date, required=True)
    parser.add_argument("--as-of", type=parse_date, required=True)
    parser.add_argument("--window-days", type=int, default=7)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        summary, files = reconcile(
            args.requests, args.bookings, args.start, args.end, args.as_of, args.window_days
        )
        save_outputs(args.out, files)
    except (ValueError, OverflowError, OSError, csv.Error) as error:
        print(f"Reconciliation failed: {error}", file=sys.stderr)
        return 2
    print(
        f"{summary['status']}: {summary['mature_booked']} booked / "
        f"{summary['mature_eligible']} mature eligible requests. Results in {args.out}"
    )
    return 1 if summary["status"] != "ready" else 0


if __name__ == "__main__":
    raise SystemExit(main())
