from __future__ import annotations

import unittest
from datetime import date, timedelta
from pathlib import Path
import tempfile

from quant_rotation.data import (
    align_asset_data,
    align_benchmark,
    load_benchmark_csv,
    load_stock_industry_map_csv,
    load_wide_asset_csv,
    load_wide_close_csv,
)
from quant_rotation.models import PriceData


class DataTests(unittest.TestCase):
    def test_load_wide_close_csv_returns_price_data(self) -> None:
        csv_content = (
            "date,AssetA,AssetB\n"
            "2024-01-01,100.0,200.0\n"
            "2024-01-02,101.0,202.0\n"
            "2024-01-03,99.0,201.0\n"
        )
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "test.csv"
            path.write_text(csv_content, encoding="utf-8")
            data = load_wide_close_csv(path)
            self.assertEqual(len(data.dates), 3)
            self.assertEqual(data.assets, ["AssetA", "AssetB"])
            self.assertEqual(data.closes["AssetA"], [100.0, 101.0, 99.0])

    def test_load_wide_close_csv_rejects_missing_values(self) -> None:
        csv_content = (
            "date,AssetA,AssetB\n"
            "2024-01-01,100.0,\n"
        )
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "test.csv"
            path.write_text(csv_content, encoding="utf-8")
            with self.assertRaises(ValueError):
                load_wide_close_csv(path)

    def test_align_asset_data_requires_all_dates_present(self) -> None:
        dates = [
            date(2024, 1, 1) + timedelta(days=i)
            for i in range(5)
        ]
        raw = PriceData(
            dates=[dates[1], dates[3]],
            closes={"AssetA": [101.0, 103.0]},
        )
        with self.assertRaises(ValueError):
            align_asset_data(dates, raw.assets, raw, value_name="test")

    def test_align_benchmark_requires_all_dates_present(self) -> None:
        dates = [date(2024, 1, 1) + timedelta(days=i) for i in range(5)]
        bench_dates = [dates[0], dates[2]]
        bench_closes = [100.0, 102.0]
        with self.assertRaises(ValueError):
            align_benchmark(dates, bench_dates, bench_closes)

    def test_align_benchmark_matches_existing(self) -> None:
        dates = [date(2024, 1, 1) + timedelta(days=i) for i in range(5)]
        bench_dates = list(dates)
        bench_closes = [100.0, 101.0, 102.0, 103.0, 104.0]
        aligned = align_benchmark(dates, bench_dates, bench_closes)
        self.assertEqual(len(aligned), len(dates))
        self.assertEqual(aligned, bench_closes)

    def test_load_benchmark_csv_reads_date_and_close(self) -> None:
        csv_content = (
            "date,close\n"
            "2024-01-01,5083.80\n"
            "2024-01-02,5049.70\n"
        )
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "bench.csv"
            path.write_text(csv_content, encoding="utf-8")
            dates, closes = load_benchmark_csv(path)
            self.assertEqual(len(dates), 2)
            self.assertEqual(closes, [5083.80, 5049.70])

    def test_load_stock_industry_map_csv_static_format(self) -> None:
        csv_content = (
            "stock,industry\n"
            "000001.SZ,bank\n"
            "000002.SZ,real_estate\n"
        )
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "map.csv"
            path.write_text(csv_content, encoding="utf-8")
            stock_map = load_stock_industry_map_csv(path)
            self.assertEqual(len(stock_map.snapshots), 1)

    def test_load_wide_asset_csv_with_value_name(self) -> None:
        csv_content = (
            "date,AssetA,AssetB\n"
            "2024-01-01,1.5,2.5\n"
        )
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "amount.csv"
            path.write_text(csv_content, encoding="utf-8")
            data = load_wide_asset_csv(path, value_name="amount")
            self.assertEqual(data.dates[0], date(2024, 1, 1))
            self.assertEqual(data.closes["AssetA"], [1.5])


if __name__ == "__main__":
    unittest.main()
