from __future__ import annotations

import tempfile
import unittest
from datetime import date
from pathlib import Path

from tools.annual_returns_summary import (
    load_annual_returns,
    print_multi_comparison,
    segment_stats,
    summarize,
)
from tools.data_integrity_check import check_metadata_warnings, check_missing_values
from tools.wf_segment_diagnosis import (
    _classify_segment,
    diagnose_folds,
    load_folds,
)


class ToolTests(unittest.TestCase):
    def test_annual_summary_reads_strategy_return_column(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "annual_returns.csv"
            path.write_text(
                "year,strategy_return,benchmark_return\n"
                "2024,0.1000000000,0.0500000000\n"
                "2025,-0.0200000000,0.0100000000\n",
                encoding="utf-8",
            )

            annuals = load_annual_returns(str(path))
            self.assertEqual(annuals, {2024: 0.10, 2025: -0.02})

            stats = summarize(annuals)
            self.assertEqual(stats["negative_years"], 1)
            self.assertAlmostEqual(stats["worst_year"], -0.02)

    def test_annual_summary_keeps_legacy_return_column(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "annual_returns.csv"
            path.write_text(
                "year,return\n"
                "2024,0.0300000000\n",
                encoding="utf-8",
            )

            self.assertEqual(load_annual_returns(str(path)), {2024: 0.03})

    def test_annual_summary_segment_stats(self) -> None:
        annuals = {
            2012: 0.05, 2013: -0.03, 2014: 0.10,
            2015: 0.15, 2016: -0.05, 2017: 0.03, 2018: -0.10, 2019: 0.20, 2020: 0.12,
            2021: 0.00, 2022: 0.00, 2023: -0.046, 2024: 0.086, 2025: 0.186,
        }
        segs = segment_stats(annuals)
        self.assertEqual(len(segs), 3)
        self.assertIn(1, segs)
        self.assertIn(2, segs)
        self.assertIn(3, segs)
        self.assertEqual(len(segs[1]), 3)
        self.assertEqual(len(segs[2]), 6)
        self.assertEqual(len(segs[3]), 5)

    def test_annual_summary_multi_comparison_does_not_crash(self) -> None:
        stats1 = summarize({2021: 0.0, 2022: 0.0, 2023: -0.046, 2024: 0.086, 2025: 0.186})
        stats2 = summarize({2021: 0.0, 2022: 0.0, 2023: -0.013, 2024: 0.149, 2025: 0.023})
        file_stats = [("prod.csv", stats1), ("phase_d.csv", stats2)]
        print_multi_comparison(file_stats)

    def test_annual_summary_empty_data(self) -> None:
        stats = summarize({})
        self.assertEqual(stats["negative_years"], 0)
        self.assertEqual(stats["annualized"], 0.0)

    def test_missing_value_check_flags_long_streak(self) -> None:
        dates = [date(2024, 1, day) for day in range(1, 9)]
        values = {"asset": [1.0, None, None, None, None, None, None, 1.1]}

        issues = check_missing_values(dates, values, max_gap=5)

        self.assertEqual(len(issues), 1)
        self.assertIn("6 consecutive", issues[0])

    def test_metadata_check_accepts_prosperity_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            prosperity = root / "industry_prosperity.csv"
            prosperity.write_text(
                "date,IndustryA\n2024-01-01,0.1\n",
                encoding="utf-8",
            )
            (root / "industry_prosperity_manifest.json").write_text(
                "{"
                "\"source_file\":\"industry_amount.csv\","
                "\"release_lag_days\":1,"
                "\"usable_from\":\"next_rebalance\""
                "}",
                encoding="utf-8",
            )

            warnings = check_metadata_warnings(
                {"industry_prosperity": str(prosperity)}
            )

        self.assertEqual(warnings, [])

    def test_metadata_check_warns_without_prosperity_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            prosperity = Path(tmp) / "industry_prosperity.csv"
            prosperity.write_text(
                "date,IndustryA\n2024-01-01,0.1\n",
                encoding="utf-8",
            )

            warnings = check_metadata_warnings(
                {"industry_prosperity": str(prosperity)}
            )

        self.assertTrue(any("release-lag metadata" in item for item in warnings))

    def test_wf_segment_classify_sw2000(self) -> None:
        fold = {"test_start": "2012-02-06", "test_end": "2012-08-07"}
        self.assertEqual(_classify_segment(fold), 1)

    def test_wf_segment_classify_sw2014(self) -> None:
        fold = {"test_start": "2016-04-01", "test_end": "2016-10-13"}
        self.assertEqual(_classify_segment(fold), 2)

    def test_wf_segment_classify_sw2021(self) -> None:
        fold = {"test_start": "2022-07-12", "test_end": "2023-01-12"}
        self.assertEqual(_classify_segment(fold), 3)

    def test_wf_segment_diagnose_with_sample_folds(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "walk_forward_folds.csv"
            path.write_text(
                "fold,test_rank,selection_metric,train_selection_score,test_selection_score,"
                "selected_name,factor_set,enabled_factors,top_k,risk_off_exposure,"
                "risk_control,market_score_control,market_score_threshold,"
                "train_start,train_end,test_start,test_end,"
                "train_final_equity,train_annualized_return,train_max_drawdown,"
                "train_sharpe_ratio,train_calmar_ratio,"
                "test_final_equity,test_annualized_return,test_max_drawdown,"
                "test_sharpe_ratio,test_calmar_ratio\n"
                "1,1,composite,-0.5,-1.0,cand1,ret60,ret60,3,0.0,true,false,0.0,"
                "2010-01-04,2012-02-03,2012-02-06,2012-08-07,"
                "0.9,-0.04,-0.19,-0.29,-0.22,"
                "0.9,-0.18,-0.12,-1.41,-1.41\n"
                "2,2,composite,-0.3,0.5,cand1,ret60,ret60,3,0.0,true,false,0.0,"
                "2010-07-13,2012-08-07,2012-08-08,2013-02-18,"
                "0.8,-0.09,-0.25,-0.59,-0.35,"
                "1.12,0.25,-0.03,2.41,8.49\n"
                "14,1,composite,0.5,-1.5,cand2,ret60_ret5,ret60;ret5,5,0.0,true,false,0.0,"
                "2018-10-30,2020-05-29,2020-06-01,2020-11-27,"
                "1.05,0.08,-0.14,0.45,0.57,"
                "0.92,-0.12,-0.10,-0.85,-1.20\n"
                "20,1,composite,-0.4,-2.0,cand1,ret60,ret60,3,0.0,true,false,0.0,"
                "2020-06-30,2022-07-11,2022-07-12,2023-01-12,"
                "1.02,0.12,-0.05,0.83,2.40,"
                "0.96,-0.07,-0.06,-1.53,-1.16\n",
                encoding="utf-8",
            )
            folds = load_folds(path)
            self.assertEqual(len(folds), 4)

            diagnosis = diagnose_folds(folds)
            self.assertEqual(diagnosis["total_folds"], 4)
            self.assertEqual(diagnosis["segment_counts"][1], 2)
            self.assertEqual(diagnosis["segment_counts"][2], 1)
            self.assertEqual(diagnosis["segment_counts"][3], 1)
            self.assertEqual(len(diagnosis["failure_folds"]), 3)

    def test_wf_segment_diagnose_empty_folds(self) -> None:
        diagnosis = diagnose_folds([])
        self.assertEqual(diagnosis["total_folds"], 0)
        self.assertEqual(len(diagnosis["failure_folds"]), 0)


if __name__ == "__main__":
    unittest.main()
