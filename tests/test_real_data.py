from __future__ import annotations

import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch

from quant_rotation.data import load_benchmark_csv, load_wide_asset_csv, load_wide_close_csv
from quant_rotation.models import PriceData
from quant_rotation.real_data import (
    IndexInfo,
    fetch_benchmark_close_data,
    fetch_sw_level1_close_data,
    parse_date,
    write_real_data_files,
)


class FakeFrame:
    def __init__(self, rows: list[dict[str, object]]) -> None:
        self.rows = rows

    def to_dict(self, orient: str) -> list[dict[str, object]]:
        if orient != "records":
            raise ValueError("FakeFrame only supports records")
        return self.rows


class FakeAk:
    def index_hist_sw(self, symbol: str, period: str) -> FakeFrame:
        self.period = period
        rows_by_symbol = {
            "801001": [
                {"日期": "2024-01-01", "收盘": "100.0"},
                {"日期": "2024-01-02", "收盘": "101.0"},
                {"日期": "2024-01-03", "收盘": "102.0"},
            ],
            "801002": [
                {"日期": "2024-01-02", "收盘": "200.0"},
                {"日期": "2024-01-03", "收盘": "202.0"},
            ],
        }
        return FakeFrame(rows_by_symbol[symbol])

    def stock_zh_index_daily_tx(
        self,
        symbol: str,
        start_date: str,
        end_date: str,
    ) -> FakeFrame:
        self.benchmark_request = (symbol, start_date, end_date)
        return FakeFrame(
            [
                {"date": "2024-01-02", "close": "3000.0"},
                {"date": "2024-01-03", "close": "3010.0"},
            ]
        )


class RealDataTests(unittest.TestCase):
    def test_parse_date_accepts_iso_and_compact_dates(self) -> None:
        self.assertEqual(parse_date("2024-01-02"), date(2024, 1, 2))
        self.assertEqual(parse_date("20240102"), date(2024, 1, 2))

    def test_fetch_sw_level1_close_data_uses_common_dates(self) -> None:
        fake_ak = FakeAk()
        infos = [IndexInfo("801001", "行业A"), IndexInfo("801002", "行业B")]

        with patch("quant_rotation.real_data.sw_level1_index_infos", return_value=infos):
            data = fetch_sw_level1_close_data(
                date(2024, 1, 1),
                date(2024, 1, 3),
                ak=fake_ak,
            )

        self.assertEqual(data.dates, [date(2024, 1, 2), date(2024, 1, 3)])
        self.assertEqual(data.closes["行业A"], [101.0, 102.0])
        self.assertEqual(data.closes["行业B"], [200.0, 202.0])

    def test_fetch_benchmark_close_data_requests_compact_dates(self) -> None:
        fake_ak = FakeAk()
        closes = fetch_benchmark_close_data(
            "sh000300",
            date(2024, 1, 1),
            date(2024, 1, 3),
            ak=fake_ak,
        )

        self.assertEqual(
            fake_ak.benchmark_request,
            ("sh000300", "20240101", "20240103"),
        )
        self.assertEqual(closes[date(2024, 1, 3)], 3010.0)

    def test_write_real_data_files_outputs_loadable_csvs(self) -> None:
        industry_data = PriceData(
            dates=[date(2024, 1, 1), date(2024, 1, 2), date(2024, 1, 3)],
            closes={
                "行业A": [100.0, 101.0, 102.0],
                "行业B": [200.0, 201.0, 202.0],
            },
        )
        amount_data = PriceData(
            dates=[date(2024, 1, 1), date(2024, 1, 2), date(2024, 1, 3)],
            closes={
                "行业A": [1000.0, 1100.0, 1200.0],
                "行业B": [2000.0, 2100.0, 2200.0],
            },
        )
        benchmark = {
            date(2024, 1, 2): 3000.0,
            date(2024, 1, 3): 3010.0,
        }

        with tempfile.TemporaryDirectory() as tmp:
            summary = write_real_data_files(
                Path(tmp),
                industry_data,
                benchmark,
                amount_data=amount_data,
                benchmark_symbol="sh000300",
            )
            loaded_industry = load_wide_close_csv(summary.industry_close_path)
            loaded_amount = load_wide_asset_csv(
                summary.industry_amount_path or "",
                value_name="amount",
            )
            loaded_benchmark_dates, loaded_benchmark = load_benchmark_csv(
                summary.benchmark_close_path
            )

        self.assertEqual(summary.rows, 2)
        self.assertIsNotNone(summary.industry_amount_path)
        self.assertEqual(loaded_industry.dates, [date(2024, 1, 2), date(2024, 1, 3)])
        self.assertEqual(loaded_industry.assets, ["行业A", "行业B"])
        self.assertEqual(loaded_amount.closes["行业A"], [1100.0, 1200.0])
        self.assertEqual(loaded_benchmark_dates, [date(2024, 1, 2), date(2024, 1, 3)])
        self.assertEqual(loaded_benchmark, [3000.0, 3010.0])


if __name__ == "__main__":
    unittest.main()
