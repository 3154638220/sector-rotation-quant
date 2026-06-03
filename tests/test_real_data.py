from __future__ import annotations

import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch

from quant_rotation.data import (
    load_benchmark_csv,
    load_stock_industry_map_csv,
    load_wide_asset_csv,
    load_wide_close_csv,
)
from quant_rotation.models import PriceData
from quant_rotation.real_data import (
    compute_industry_breadth,
    fetch_sw_level1_market_data,
    fetch_sw_level1_breadth_data,
    fetch_sw_level1_stock_data,
    IndexInfo,
    fetch_benchmark_close_data,
    fetch_market_close_data,
    fetch_sw_level1_close_data,
    parse_date,
    StockMarketData,
    sw_level1_index_infos,
    sw_level1_universe_names,
    write_breadth_data_files,
    write_real_data_files,
    write_stock_data_files,
)


class FakeFrame:
    def __init__(self, rows: list[dict[str, object]]) -> None:
        self.rows = rows

    def to_dict(self, orient: str) -> list[dict[str, object]]:
        if orient != "records":
            raise ValueError("FakeFrame only supports records")
        return self.rows


class FakeAk:
    def index_component_sw(self, symbol: str) -> FakeFrame:
        rows_by_symbol = {
            "801001": [
                {"证券代码": "000001", "证券名称": "A1"},
                {"证券代码": "000002", "证券名称": "A2"},
            ],
            "801002": [
                {"证券代码": "000003", "证券名称": "B1"},
                {"证券代码": "000004", "证券名称": "B2"},
            ],
        }
        return FakeFrame(rows_by_symbol[symbol])

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
        rows_by_symbol = {
            "sh000300": [
                {"date": "2024-01-02", "close": "3000.0"},
                {"date": "2024-01-03", "close": "3010.0"},
            ],
            "sh000985": [
                {"date": "2024-01-01", "close": "5000.0"},
                {"date": "2024-01-02", "close": "5010.0"},
                {"date": "2024-01-03", "close": "5020.0"},
            ],
            "sz399006": [
                {"date": "2024-01-02", "close": "2000.0"},
                {"date": "2024-01-03", "close": "2020.0"},
            ],
        }
        if symbol in rows_by_symbol:
            return FakeFrame(rows_by_symbol[symbol])
        return FakeFrame(
            [
                {"date": "2024-01-02", "close": "3000.0"},
                {"date": "2024-01-03", "close": "3010.0"},
            ]
        )

    def stock_zh_a_hist(
        self,
        symbol: str,
        period: str,
        start_date: str,
        end_date: str,
        adjust: str,
    ) -> FakeFrame:
        self.last_stock_request = (symbol, period, start_date, end_date, adjust)
        closes_by_symbol = {
            "000001": [1, 2, 3, 4, 5],
            "000002": [5, 4, 3, 2, 1],
            "000003": [1, 1, 2, 3, 4],
            "000004": [1, 2, 4, 8, 16],
        }
        rows = [
            {"日期": f"2024-01-0{index}", "股票代码": symbol, "收盘": close}
            for index, close in enumerate(closes_by_symbol[symbol], start=1)
        ]
        return FakeFrame(rows)


class RealDataTests(unittest.TestCase):
    def test_parse_date_accepts_iso_and_compact_dates(self) -> None:
        self.assertEqual(parse_date("2024-01-02"), date(2024, 1, 2))
        self.assertEqual(parse_date("20240102"), date(2024, 1, 2))

    def test_sw_level1_index_infos_supports_predefined_universe(self) -> None:
        self.assertIn("sw2014", sw_level1_universe_names())

        infos = sw_level1_index_infos(universe="sw2014")
        codes = [info.code for info in infos]

        self.assertEqual(len(infos), 28)
        self.assertIn("801020", codes)
        self.assertNotIn("801960", codes)

    def test_sw_level1_index_infos_rejects_unknown_universe(self) -> None:
        with self.assertRaises(ValueError):
            sw_level1_index_infos(universe="unknown")

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

    def test_fetch_sw_level1_market_data_accepts_explicit_industries(self) -> None:
        fake_ak = FakeAk()
        data = fetch_sw_level1_market_data(
            date(2024, 1, 1),
            date(2024, 1, 3),
            ak=fake_ak,
            industries=[IndexInfo("801002", "IndustryB")],
            require_amount=False,
        )

        self.assertEqual(data.close.dates, [date(2024, 1, 2), date(2024, 1, 3)])
        self.assertEqual(data.close.assets, ["IndustryB"])
        self.assertEqual(data.close.closes["IndustryB"], [200.0, 202.0])

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

    def test_fetch_market_close_data_uses_common_dates_and_asset_names(self) -> None:
        fake_ak = FakeAk()
        market_data = fetch_market_close_data(
            [
                IndexInfo("sh000300", "CSI300"),
                IndexInfo("sh000985", "CSIAll"),
                IndexInfo("sz399006", "ChiNext"),
            ],
            date(2024, 1, 1),
            date(2024, 1, 3),
            ak=fake_ak,
        )

        self.assertEqual(market_data.dates, [date(2024, 1, 2), date(2024, 1, 3)])
        self.assertEqual(market_data.assets, ["CSI300", "CSIAll", "ChiNext"])
        self.assertEqual(market_data.closes["CSI300"], [3000.0, 3010.0])
        self.assertEqual(market_data.closes["CSIAll"], [5010.0, 5020.0])

    def test_compute_industry_breadth_counts_stocks_above_ma(self) -> None:
        stock_closes = {
            "000001": {
                date(2024, 1, 1): 1.0,
                date(2024, 1, 2): 2.0,
                date(2024, 1, 3): 3.0,
            },
            "000002": {
                date(2024, 1, 1): 5.0,
                date(2024, 1, 2): 4.0,
                date(2024, 1, 3): 3.0,
            },
        }

        breadth = compute_industry_breadth(
            {"IndustryA": ["000001", "000002"]},
            stock_closes,
            date(2024, 1, 1),
            date(2024, 1, 3),
            windows=(3,),
        )

        self.assertEqual(breadth[3].dates, [date(2024, 1, 3)])
        self.assertEqual(breadth[3].closes["IndustryA"], [0.5])

    def test_fetch_sw_level1_breadth_data_uses_current_constituents(self) -> None:
        fake_ak = FakeAk()
        breadth = fetch_sw_level1_breadth_data(
            date(2024, 1, 3),
            date(2024, 1, 5),
            ak=fake_ak,
            industries=[
                IndexInfo("801001", "IndustryA"),
                IndexInfo("801002", "IndustryB"),
            ],
            windows=(3,),
            lookback_days=3,
        )

        self.assertEqual(
            breadth[3].dates,
            [date(2024, 1, 3), date(2024, 1, 4), date(2024, 1, 5)],
        )
        self.assertEqual(breadth[3].closes["IndustryA"], [0.5, 0.5, 0.5])
        self.assertEqual(breadth[3].closes["IndustryB"], [1.0, 1.0, 1.0])

    def test_fetch_sw_level1_stock_data_uses_current_constituents(self) -> None:
        fake_ak = FakeAk()
        stock_data = fetch_sw_level1_stock_data(
            date(2024, 1, 1),
            date(2024, 1, 5),
            ak=fake_ak,
            industries=[
                IndexInfo("801001", "IndustryA"),
                IndexInfo("801002", "IndustryB"),
            ],
            max_stocks_per_industry=1,
        )

        self.assertEqual(stock_data.close.assets, ["000001", "000003"])
        self.assertEqual(
            stock_data.close.dates,
            [
                date(2024, 1, 1),
                date(2024, 1, 2),
                date(2024, 1, 3),
                date(2024, 1, 4),
                date(2024, 1, 5),
            ],
        )
        self.assertEqual(stock_data.close.closes["000001"], [1.0, 2.0, 3.0, 4.0, 5.0])
        self.assertEqual(
            stock_data.industry_map,
            {"000001": "IndustryA", "000003": "IndustryB"},
        )

    def test_write_breadth_data_files_outputs_loadable_csvs(self) -> None:
        breadth = PriceData(
            dates=[date(2024, 1, 3), date(2024, 1, 4)],
            closes={
                "IndustryA": [0.5, 0.75],
                "IndustryB": [1.0, 0.25],
            },
        )

        with tempfile.TemporaryDirectory() as tmp:
            summary = write_breadth_data_files(
                Path(tmp),
                {20: breadth},
                min_stocks=1,
            )
            loaded = load_wide_asset_csv(
                summary.breadth_paths[20],
                value_name="breadth20",
            )
            manifest = summary.manifest_path.read_text(encoding="utf-8")

        self.assertEqual(summary.rows, 2)
        self.assertEqual(loaded.assets, ["IndustryA", "IndustryB"])
        self.assertEqual(loaded.closes["IndustryA"], [0.5, 0.75])
        self.assertIn("survivor_bias_warning", manifest)

    def test_write_stock_data_files_outputs_loadable_csvs(self) -> None:
        close = PriceData(
            dates=[date(2024, 1, 1), date(2024, 1, 2)],
            closes={
                "000001": [10.0, 11.0],
                "000002": [20.0, 19.0],
            },
        )
        amount = PriceData(
            dates=[date(2024, 1, 1), date(2024, 1, 2)],
            closes={
                "000001": [1000.0, 1100.0],
                "000002": [2000.0, 2100.0],
            },
        )
        stock_data = StockMarketData(
            close=close,
            amount=amount,
            industry_map={"000001": "IndustryA", "000002": "IndustryB"},
        )

        with tempfile.TemporaryDirectory() as tmp:
            summary = write_stock_data_files(Path(tmp), stock_data)
            loaded_close = load_wide_close_csv(summary.stock_close_path)
            loaded_amount = load_wide_asset_csv(
                summary.stock_amount_path or "",
                value_name="stock amount",
            )
            loaded_map = load_stock_industry_map_csv(summary.stock_industry_map_path)
            manifest = summary.manifest_path.read_text(encoding="utf-8")

        self.assertEqual(summary.rows, 2)
        self.assertEqual(summary.stocks, 2)
        self.assertEqual(loaded_close.closes["000001"], [10.0, 11.0])
        self.assertEqual(loaded_amount.closes["000002"], [2000.0, 2100.0])
        self.assertEqual(
            loaded_map.get_map_at(date(2024, 1, 2)),
            {"000001": "IndustryA", "000002": "IndustryB"},
        )
        self.assertIn("survivor_bias_warning", manifest)

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
        market_data = PriceData(
            dates=[date(2024, 1, 1), date(2024, 1, 2), date(2024, 1, 3)],
            closes={
                "CSI300": [2990.0, 3000.0, 3010.0],
                "CSIAll": [4990.0, 5000.0, 5010.0],
            },
        )

        with tempfile.TemporaryDirectory() as tmp:
            summary = write_real_data_files(
                Path(tmp),
                industry_data,
                benchmark,
                amount_data=amount_data,
                market_data=market_data,
                benchmark_symbol="sh000300",
                market_symbols={"CSI300": "sh000300", "CSIAll": "sh000985"},
                industry_universe="sw2014",
                industry_symbols={"行业A": "801001", "行业B": "801002"},
            )
            loaded_industry = load_wide_close_csv(summary.industry_close_path)
            loaded_amount = load_wide_asset_csv(
                summary.industry_amount_path or "",
                value_name="amount",
            )
            loaded_market = load_wide_close_csv(summary.market_close_path or "")
            loaded_benchmark_dates, loaded_benchmark = load_benchmark_csv(
                summary.benchmark_close_path
            )
            manifest = summary.manifest_path.read_text(encoding="utf-8")

        self.assertEqual(summary.rows, 2)
        self.assertIsNotNone(summary.industry_amount_path)
        self.assertIsNotNone(summary.market_close_path)
        self.assertEqual(loaded_market.dates, [date(2024, 1, 2), date(2024, 1, 3)])
        self.assertEqual(loaded_market.assets, ["CSI300", "CSIAll"])
        self.assertEqual(loaded_market.closes["CSIAll"], [5000.0, 5010.0])
        self.assertEqual(loaded_industry.dates, [date(2024, 1, 2), date(2024, 1, 3)])
        self.assertEqual(loaded_industry.assets, ["行业A", "行业B"])
        self.assertEqual(loaded_amount.closes["行业A"], [1100.0, 1200.0])
        self.assertEqual(loaded_benchmark_dates, [date(2024, 1, 2), date(2024, 1, 3)])
        self.assertEqual(loaded_benchmark, [3000.0, 3010.0])
        self.assertIn('"industry_universe": "sw2014"', manifest)
        self.assertIn('"行业A": "801001"', manifest)


if __name__ == "__main__":
    unittest.main()
