from __future__ import annotations

import tempfile
import unittest
from datetime import date
from pathlib import Path

from quant_rotation.data import load_stock_industry_map_csv
from quant_rotation.real_data import (
    validate_constituent_snapshot_csv,
    import_constituent_snapshot,
)


class ConstituentSnapshotTests(unittest.TestCase):
    def _write_csv(self, path: Path, content: str) -> None:
        path.write_text(content, encoding="utf-8")

    def test_valid_snapshot_passes_validation(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            csv_path = Path(tmp) / "snapshot.csv"
            self._write_csv(csv_path, (
                "snapshot_date,stock,industry\n"
                "2014-02-21,601318.SH,保险\n"
                "2014-02-21,600036.SH,银行\n"
                "2021-12-13,300750.SZ,电力设备\n"
            ))
            issues = validate_constituent_snapshot_csv(csv_path)
            self.assertEqual(issues, [])

    def test_missing_required_column_returns_issue(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            csv_path = Path(tmp) / "bad.csv"
            self._write_csv(csv_path, "date,stock,foo\n2024-01-01,A,1\n")
            issues = validate_constituent_snapshot_csv(csv_path)
            self.assertTrue(any("industry" in i for i in issues))

    def test_empty_csv_returns_issue(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            csv_path = Path(tmp) / "empty.csv"
            self._write_csv(csv_path, "snapshot_date,stock,industry\n")
            issues = validate_constituent_snapshot_csv(csv_path)
            self.assertTrue(len(issues) > 0)

    def test_invalid_date_returns_issue(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            csv_path = Path(tmp) / "bad.csv"
            self._write_csv(csv_path, (
                "snapshot_date,stock,industry\n"
                "bad-date,601318.SH,保险\n"
            ))
            issues = validate_constituent_snapshot_csv(csv_path)
            self.assertTrue(any("date" in i.lower() for i in issues))

    def test_duplicate_stock_returns_issue(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            csv_path = Path(tmp) / "dup.csv"
            self._write_csv(csv_path, (
                "snapshot_date,stock,industry\n"
                "2014-02-21,601318.SH,保险\n"
                "2014-02-21,601318.SH,银行\n"
            ))
            issues = validate_constituent_snapshot_csv(csv_path)
            self.assertTrue(any("duplicate" in i.lower() for i in issues))

    def test_import_creates_target_and_is_loadable(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / "src.csv"
            tgt = Path(tmp) / "out.csv"
            self._write_csv(src, (
                "snapshot_date,stock,industry\n"
                "2014-02-21,601318.SH,保险\n"
                "2021-12-13,300750.SZ,电力设备\n"
            ))
            rows = import_constituent_snapshot(src, tgt)
            self.assertEqual(rows, 2)
            self.assertTrue(tgt.exists())

            snap = load_stock_industry_map_csv(tgt)
            self.assertEqual(len(snap.snapshots), 2)
            self.assertEqual(
                snap.get_map_at(date(2022, 1, 1))["300750.SZ"],
                "电力设备",
            )

    def test_import_rejects_overwrite_without_flag(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / "src.csv"
            tgt = Path(tmp) / "out.csv"
            self._write_csv(src, "snapshot_date,stock,industry\n2014-02-21,601318.SH,保险\n")
            import_constituent_snapshot(src, tgt)
            with self.assertRaises(FileExistsError):
                import_constituent_snapshot(src, tgt)

    def test_import_overwrite_flag_allows_replace(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            src1 = Path(tmp) / "src1.csv"
            src2 = Path(tmp) / "src2.csv"
            tgt = Path(tmp) / "out.csv"
            self._write_csv(src1, "snapshot_date,stock,industry\n2014-02-21,601318.SH,保险\n")
            self._write_csv(src2, "snapshot_date,stock,industry\n2021-12-13,300750.SZ,电力设备\n")
            import_constituent_snapshot(src1, tgt)
            rows = import_constituent_snapshot(src2, tgt, overwrite=True)
            self.assertEqual(rows, 1)
            snap = load_stock_industry_map_csv(tgt)
            self.assertNotIn("601318.SH", snap.get_map_at(date(2022, 1, 1)))

    def test_snapshot_uses_date_column_alias(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            csv_path = Path(tmp) / "alias.csv"
            self._write_csv(csv_path, (
                "date,stock,industry\n"
                "2014-02-21,601318.SH,保险\n"
            ))
            issues = validate_constituent_snapshot_csv(csv_path)
            self.assertEqual(issues, [])

    def test_build_constituents_from_different_snapshots(self) -> None:
        from quant_rotation.models import StockIndustryMap
        from quant_rotation.real_data import build_constituents_from_snapshot

        early_map = {"stock_A": "行业X", "stock_B": "行业X"}
        late_map = {"stock_A": "行业Y", "stock_B": "行业X"}
        stock_map = StockIndustryMap({
            date(2014, 2, 21): early_map,
            date(2021, 12, 13): late_map,
        })

        early_const = build_constituents_from_snapshot(stock_map, date(2020, 1, 1))
        self.assertIn("行业X", early_const)
        self.assertNotIn("行业Y", early_const)
        self.assertEqual(early_const["行业X"], ["stock_A", "stock_B"])

        late_const = build_constituents_from_snapshot(stock_map, date(2022, 1, 1))
        self.assertIn("行业Y", late_const)
        self.assertIn("行业X", late_const)
        self.assertEqual(late_const["行业Y"], ["stock_A"])


if __name__ == "__main__":
    unittest.main()
