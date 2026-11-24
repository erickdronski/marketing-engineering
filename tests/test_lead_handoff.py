"""Exercise the same CSV workflow a consultant runs in a client directory."""

import csv
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RECIPE = ROOT / "recipes" / "lead-handoff"


class LeadHandoffTest(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="lead handoff ")
        self.addCleanup(temporary.cleanup)
        self.work = Path(temporary.name)
        for filename in ("requests.csv", "bookings.csv"):
            shutil.copyfile(RECIPE / "example" / filename, self.work / filename)

    def run_recipe(self, date="2026-11-16", output="result", expected=0, extra=()):
        args = [
            sys.executable,
            str(RECIPE / "reconcile.py"),
            "--requests",
            "requests.csv",
            "--bookings",
            "bookings.csv",
            "--start",
            "2026-11-02",
            "--end",
            "2026-11-08",
            "--as-of",
            date,
            "--out",
            output,
            *extra,
        ]
        result = subprocess.run(args, cwd=self.work, capture_output=True, text=True, check=False)
        self.assertEqual(result.returncode, expected, result.stdout + result.stderr)
        self.assertNotIn("Traceback", result.stderr)
        return self.work / output

    @staticmethod
    def summary(path):
        return json.loads((path / "summary.json").read_text(encoding="utf-8"))

    @staticmethod
    def rows(path):
        with path.open(encoding="utf-8", newline="") as stream:
            return list(csv.DictReader(stream))

    def test_worked_counts_and_actionable_unknown_source(self):
        result = self.run_recipe()
        summary = self.summary(result)
        self.assertEqual(summary["status"], "ready")
        self.assertEqual((summary["mature_booked"], summary["mature_eligible"]), (2, 3))
        self.assertEqual(summary["by_source"]["service-page"], {"eligible": 2, "booked": 1})
        self.assertEqual(summary["tagged_mature_requests"], 2)
        self.assertEqual(summary["duplicate_request_rows"], 1)
        self.assertEqual(summary["test_requests_excluded"], 1)
        tasks = {(r["request_id"], r["status"]) for r in self.rows(result / "worklist.csv")}
        self.assertIn(("R2", "no_booking_in_window"), tasks)
        self.assertIn(("R3", "unknown_source"), tasks)
        self.assertEqual(self.rows(result / "exceptions.csv"), [])

    def test_matching_is_by_id_and_conflicts_are_held(self):
        with (self.work / "requests.csv").open("a", encoding="utf-8") as out:
            out.write("R2,2026-11-03,print,false\n,2026-11-02,print,false\n")
        with (self.work / "bookings.csv").open("a", encoding="utf-8") as out:
            out.write("B1,R1,2026-11-04\nB4,R404,2026-11-05\nB5,,2026-11-06\nB6,R3,2026-11-04\n")
        result = self.run_recipe(expected=1)
        summary = self.summary(result)
        self.assertEqual(summary["status"], "needs_review")
        self.assertIsNone(summary["booking_rate"])
        issues = {(r["record_id"], r["issue"]) for r in self.rows(result / "exceptions.csv")}
        self.assertEqual(
            issues,
            {
                ("R2", "conflicting_request_id"),
                ("", "missing_request_id"),
                ("B1", "conflicting_booking_id"),
                ("B4", "unmatched_request_id"),
                ("B5", "missing_request_id"),
                ("B6", "booking_precedes_request"),
            },
        )

    def test_as_of_and_booking_window(self):
        (self.work / "requests.csv").write_text(
            "request_id,request_date,source,is_test\nA,2026-11-02,site,false\nB,2026-11-08,site,false\n",
            encoding="utf-8",
        )
        (self.work / "bookings.csv").write_text(
            "booking_id,request_id,booked_date\na,A,2026-11-09\nb,B,2026-11-16\n",
            encoding="utf-8",
        )
        early = self.summary(self.run_recipe(date="2026-11-08", expected=1))
        self.assertEqual(early["provisional_requests"], 2)
        self.assertEqual(early["mature_booked"], 0)
        self.assertIsNone(early["booking_rate"])
        mature = self.summary(self.run_recipe(output="later"))
        self.assertEqual((mature["mature_booked"], mature["mature_eligible"]), (1, 2))
        self.assertEqual(mature["booking_rate"], 0.5)

    def test_empty_denominator_and_header_only_sources(self):
        for path in self.work.glob("*.csv"):
            heading = path.read_text(encoding="utf-8").splitlines()[0]
            path.write_text(heading + "\n", encoding="utf-8")
        summary = self.summary(self.run_recipe())
        self.assertEqual(summary["status"], "ready")
        self.assertEqual(summary["mature_eligible"], 0)
        self.assertIsNone(summary["booking_rate"])

    def test_replay_and_changed_result_do_not_overwrite_prior_evidence(self):
        result = self.run_recipe()
        before = {f.name: f.read_bytes() for f in result.iterdir()}
        self.run_recipe()
        with (self.work / "bookings.csv").open("a", encoding="utf-8") as out:
            out.write("B4,R2,2026-11-04\n")
        self.run_recipe(expected=2)
        self.assertEqual({f.name: f.read_bytes() for f in result.iterdir()}, before)
        new = self.summary(self.run_recipe(output="revised"))
        self.assertEqual(new["mature_booked"], 3)

    def test_extra_columns_or_malformed_values_publish_no_outputs(self):
        requests = self.work / "requests.csv"
        cases = [
            "request_id,request_date,source,is_test,phone\n",
            "request_id,request_date,source,is_test\nR1,2026-99-01,site,true\n",
            "request_id,request_date,source,is_test\nR1,2026-11-03,site,unknown\n",
        ]
        for text in cases:
            with self.subTest(text=text):
                requests.write_text(text, encoding="utf-8")
                self.assertFalse(self.run_recipe(expected=2).exists())
