import csv
import io
import json
import shutil
import sqlite3
import tempfile
import unittest
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path

from mktgkit import cli, scaffold, warehouse
from mktgkit.errors import MktgError

ROOT = Path(__file__).resolve().parents[1]
NOW = datetime(2026, 11, 20, 15, tzinfo=timezone.utc)


class WarehouseTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="client space ")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        shutil.copytree(ROOT / "examples/wrenfield/warehouse", self.root / "warehouse")
        (self.root / "mktgkit.json").write_text(
            json.dumps({"name": "fixture", "now": "2026-11-20T15:00:00Z"}), encoding="utf-8"
        )

    def test_campaign_totals_and_coverage_are_derived_at_source_grain(self):
        counts = warehouse.build(self.root)
        self.assertEqual(counts["web_sessions"], 1500)
        self.assertEqual(counts["signups"], 125)
        result = warehouse.query(self.root, "SELECT * FROM attribution_coverage")
        self.assertEqual(result.rows, [[125, 76, 0.608]])
        self.assertEqual(result.tables, ["signups"])
        self.assertEqual(result.freshness[0].age_hours, 9)
        result = warehouse.query(self.root, "SELECT * FROM campaign_performance ORDER BY spend_usd DESC")
        self.assertEqual(result.tables, ["ad_spend", "signups", "web_sessions"])
        self.assertEqual(result.rows[0], ["route-planning", 1001.20, 453, 18, 55.62])
        self.assertIsNone(result.rows[-1][-1])
        self.assertIn("57 h old, limit 26 h) STALE", warehouse.footer(result.freshness))

    def test_rebuild_preserves_previous_data_after_schema_or_input_error(self):
        warehouse.build(self.root)
        target = self.root / "warehouse/seed/signups.csv"
        target.write_text("id,when\n1,maybe\n", encoding="utf-8")
        with self.assertRaises(MktgError) as ctx:
            warehouse.build(self.root)
        self.assertIn("signup_id,signed_up_at", ctx.exception.fix)
        expected = warehouse.query(self.root, "SELECT count(*) FROM signups")
        self.assertEqual(expected.rows, [[125]])
        self.assertFalse(list((self.root / "warehouse").glob(".warehouse-*")))

    def test_partial_export_refused_and_check_flags_pending_input(self):
        client = self.root / "practice"
        scaffold.init(client, example=True)
        warehouse.build(client)
        csv_path = client / "warehouse/seed/signups.csv"
        lines = csv_path.read_text(encoding="utf-8").splitlines()
        csv_path.write_text("\n".join(lines[:2]) + "\n", encoding="utf-8")

        out, err = io.StringIO(), io.StringIO()
        self.assertEqual(cli.main(["warehouse", "build", "-w", str(client)], stdout=out, stderr=err), 1)
        self.assertIn("declares 125 rows, but the snapshot contains 1", err.getvalue())
        self.assertEqual(warehouse.query(client, "SELECT COUNT(*) FROM signups").rows, [[125]])
        self.assertFalse(list((client / "warehouse").glob(".warehouse-*")))
        for built in (True, False):
            if not built:
                warehouse.db_path(client).unlink()
            out = io.StringIO()
            self.assertEqual(cli.main(["check", "-w", str(client), "--format", "json"], stdout=out), 1)
            errors = json.loads(out.getvalue())["errors"]
            self.assertTrue(any("signups: latest load" in e and "contains 1" in e for e in errors))
            self.assertEqual(warehouse.db_path(client).exists(), built)

    def test_load_history_uses_latest_timestamp_per_source_independent_of_csv_order(self):
        log = self.root / "warehouse/seed/load_log.csv"
        with log.open("a", encoding="utf-8") as f:
            f.write("signups,2026-11-20T07:00:00+02:00,117,previous export\n")
        warehouse.build(self.root)
        self.assertEqual(warehouse.freshness(self.root, ["signups"])[0].loaded_at, "2026-11-20T06:00:00Z")
        with log.open("a", encoding="utf-8") as f:
            f.write("signups,2026-11-20T08:00:00Z,0,latest export\n")
        with self.assertRaisesRegex(MktgError, "declares 0 rows, but the snapshot contains 125"):
            warehouse.build(self.root)
        signups = self.root / "warehouse/seed/signups.csv"
        signups.write_text(signups.read_text(encoding="utf-8").splitlines()[0] + "\n", encoding="utf-8")
        self.assertEqual(warehouse.build(self.root)["signups"], 0)
        self.assertFalse(warehouse.freshness(self.root, ["signups"])[0].stale)

    def test_legacy_inconsistent_database_is_refused_on_affected_reads(self):
        client = self.root / "practice"
        scaffold.init(client, example=True)
        warehouse.build(client)
        with closing(sqlite3.connect(warehouse.db_path(client))) as conn:
            conn.execute("DELETE FROM signups WHERE signup_id <> (SELECT min(signup_id) FROM signups)")
            conn.commit()
        for args in (
            ["warehouse", "query", "SELECT * FROM attribution_coverage", "--require-fresh"],
            ["warehouse", "freshness", "signups", "--require-fresh"],
        ):
            out, err = io.StringIO(), io.StringIO()
            self.assertEqual(cli.main([*args, "-w", str(client)], stdout=out, stderr=err), 1)
            self.assertIn("declares 125 rows, but the snapshot contains 1", err.getvalue())
            self.assertEqual(out.getvalue(), "")
        out = io.StringIO()
        self.assertEqual(cli.main(["check", "-w", str(client), "--format", "json"], stdout=out), 1)
        self.assertTrue(any("declares 125 rows" in e for e in json.loads(out.getvalue())["errors"]))
        self.assertEqual(warehouse.query(client, "SELECT COUNT(*) FROM web_sessions").rows, [[1500]])
        warehouse.build(client)
        self.assertEqual(
            warehouse.query(client, "SELECT * FROM attribution_coverage").rows, [[125, 76, 0.608]]
        )

    def test_source_with_invalid_numeric_cell_reports_file_and_row(self):
        target = self.root / "warehouse/seed/ad_spend.csv"
        text = target.read_text(encoding="utf-8").splitlines()
        row = text[1].split(",")
        row[3] = "invalid"
        target.write_text(text[0] + "\n" + ",".join(row) + "\n", encoding="utf-8")
        with self.assertRaises(MktgError) as exc:
            warehouse.build(self.root)
        self.assertEqual(exc.exception.path, "warehouse/seed/ad_spend.csv")
        self.assertIn("row 2", str(exc.exception))
        self.assertFalse(warehouse.db_path(self.root).exists())

    def test_seed_dates_respect_each_source_cutoff(self):
        warehouse.build(self.root)
        sql = "SELECT max(day) FROM ad_spend"
        result = warehouse.query(self.root, sql)
        self.assertLess(result.rows[0][0], result.freshness[0].loaded_at[:10])

    def test_required_fresh_cli_retains_the_evidence_and_returns_five(self):
        import io

        from mktgkit.cli import main

        warehouse.build(self.root)
        out, err = io.StringIO(), io.StringIO()
        args = [
            "warehouse",
            "query",
            "SELECT * FROM campaign_performance",
            "--require-fresh",
            "--format",
            "json",
            "-w",
            str(self.root),
        ]
        self.assertEqual(main(args, stdout=out, stderr=err), 5, err.getvalue())
        report = json.loads(out.getvalue())
        self.assertEqual([x["table"] for x in report["freshness"] if x["stale"]], ["ad_spend"])
        out, err = io.StringIO(), io.StringIO()
        args = ["warehouse", "freshness", "signups", "--require-fresh", "-w", str(self.root)]
        self.assertEqual(main(args, stdout=out, stderr=err), 0, err.getvalue())

    def test_zero_rows_never_loaded_and_future_loads(self):
        shutil.copytree(ROOT / "mktgkit/template/warehouse", self.root / "warehouse", dirs_exist_ok=True)
        self.assertEqual(sum(warehouse.build(self.root).values()), 0)
        self.assertIn("never loaded", warehouse.footer(warehouse.freshness(self.root, ["signups"])))
        self.assertEqual(
            warehouse.query(self.root, "SELECT * FROM attribution_coverage").rows, [[0, 0, None]]
        )
        source = self.root / "warehouse/seed/load_log.csv"
        with source.open("a", encoding="utf-8") as f:
            f.write("signups,2027-01-01T00:00:00Z,0,export\n")
        warehouse.build(self.root)
        self.assertTrue(warehouse.freshness(self.root, ["signups"])[0].stale)

    def test_unbuilt_error_has_remedy(self):
        with self.assertRaises(MktgError) as ctx:
            warehouse.query(self.root, "SELECT 1")
        self.assertIn("mktgkit warehouse build", ctx.exception.fix)

    def test_queries_cannot_change_data_or_read_undeclared_objects(self):
        warehouse.build(self.root)
        for sql in (
            "UPDATE signups SET plan='other'",
            "DROP TABLE posts",
            "PRAGMA table_info(signups)",
            "SELECT * FROM sqlite_master",
            "SELECT 1; SELECT 2",
        ):
            with self.subTest(sql=sql), self.assertRaises(MktgError):
                warehouse.query(self.root, sql)
        self.assertEqual(warehouse.query(self.root, "SELECT COUNT(*) FROM signups").rows, [[125]])

    def test_result_caps_and_timeout(self):
        warehouse.build(self.root)
        result = warehouse.query(self.root, "SELECT signup_id FROM signups ORDER BY signup_id", limit=2)
        self.assertTrue(result.truncated)
        self.assertEqual(len(result.rows), 2)
        self.assertFalse(warehouse.query(self.root, "SELECT 1", limit=1).truncated)
        with self.assertRaisesRegex(MktgError, "at most 1000"):
            warehouse.query(self.root, "SELECT 1", limit=1001)
        with self.assertRaisesRegex(MktgError, "stopped"):
            warehouse.query(
                self.root,
                "WITH RECURSIVE n(x) AS (SELECT 1 UNION ALL SELECT x+1 FROM n) SELECT COUNT(*) FROM n",
                timeout_s=0.02,
            )

    def test_public_metadata_and_valid_but_unknown_values(self):
        warehouse.build(self.root)
        self.assertEqual(
            [x["name"] for x in warehouse.list_tables(self.root)], list(warehouse.TABLES + warehouse.VIEWS)
        )
        self.assertEqual(warehouse.describe(self.root, "signups")[0], {"name": "signup_id", "type": "TEXT"})
        with self.assertRaises(MktgError):
            warehouse.describe(self.root, "absent")
        with self.assertRaises(MktgError):
            warehouse.freshness(self.root, ["absent"])
        with self.assertRaisesRegex(MktgError, "finite"):
            warehouse.query(self.root, "SELECT 1e999")

    def test_seed_rebuild_is_reproducible(self):
        from tools.make_seed_data import generate

        out = self.root / "regenerated"
        generate(out)
        for generated in out.glob("*.csv"):
            expected = ROOT / "examples/wrenfield/warehouse/seed" / generated.name
            self.assertEqual(generated.read_text(encoding="utf-8"), expected.read_text(encoding="utf-8"))
            with expected.open(encoding="utf-8", newline="") as full:
                columns = next(csv.reader(full))
            with (ROOT / "mktgkit/template/warehouse/seed" / generated.name).open(
                encoding="utf-8", newline=""
            ) as empty:
                self.assertEqual(list(csv.reader(empty)), [columns])
