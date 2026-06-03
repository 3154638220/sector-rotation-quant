from __future__ import annotations

import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path

from quant_rotation.data import load_stock_industry_map_csv
from quant_rotation.models import PriceData, StockIndustryMap, StockSelectionConfig
from quant_rotation.stock_selection import stock_target_weights, stocks_by_industry


class StockSelectionTests(unittest.TestCase):
    def test_load_stock_industry_map_supports_static_csv(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "stock_industry_map.csv"
            path.write_text(
                "stock,industry\nAAA,IndustryA\nBBB,IndustryB\n",
                encoding="utf-8",
            )

            mapping = load_stock_industry_map_csv(path)

        self.assertEqual(
            mapping.get_map_at(date(2024, 1, 1)),
            {"AAA": "IndustryA", "BBB": "IndustryB"},
        )

    def test_load_stock_industry_map_supports_dated_snapshots(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "stock_industry_map.csv"
            path.write_text(
                "\n".join(
                    [
                        "snapshot_date,stock,industry",
                        "2024-01-01,AAA,IndustryA",
                        "2024-01-01,BBB,IndustryB",
                        "2024-03-01,AAA,IndustryB",
                        "2024-03-01,BBB,IndustryA",
                    ]
                ),
                encoding="utf-8",
            )

            mapping = load_stock_industry_map_csv(path)

        self.assertEqual(mapping.get_map_at(date(2024, 2, 1))["AAA"], "IndustryA")
        self.assertEqual(mapping.get_map_at(date(2024, 3, 1))["AAA"], "IndustryB")

    def test_stock_target_weights_use_snapshot_at_signal_date(self) -> None:
        dates = [date(2024, 1, 1) + timedelta(days=i) for i in range(130)]
        stock_data = PriceData(
            dates=dates,
            closes={
                "AAA": [100.0 * (1.003**i) for i in range(130)],
                "BBB": [100.0 * (1.002**i) for i in range(130)],
            },
        )
        mapping = StockIndustryMap(
            {
                date(2024, 1, 1): {"AAA": "IndustryA", "BBB": "IndustryB"},
                date(2024, 4, 1): {"AAA": "IndustryB", "BBB": "IndustryA"},
            }
        )
        config = StockSelectionConfig(
            enabled=True,
            top_n_per_industry=1,
            min_stocks_per_industry=1,
            max_stock_weight=1.0,
        )

        before = stock_target_weights(
            {"IndustryA": 1.0},
            stock_data,
            mapping,
            80,
            config,
            signal_date=dates[80],
        )
        after = stock_target_weights(
            {"IndustryA": 1.0},
            stock_data,
            mapping,
            110,
            config,
            signal_date=dates[110],
        )

        self.assertEqual(before, {"AAA": 1.0})
        self.assertEqual(after, {"BBB": 1.0})

    def test_stocks_by_industry_uses_latest_snapshot_when_no_date_is_given(self) -> None:
        mapping = StockIndustryMap(
            {
                date(2024, 1, 1): {"AAA": "IndustryA"},
                date(2024, 2, 1): {"AAA": "IndustryB"},
            }
        )

        grouped = stocks_by_industry(mapping, ["AAA"])

        self.assertEqual(grouped, {"IndustryB": ["AAA"]})


if __name__ == "__main__":
    unittest.main()
