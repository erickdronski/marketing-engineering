import csv
import json
import shutil
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from mktgkit import warehouse
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
