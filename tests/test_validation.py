from __future__ import annotations

import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path

from quant_rotation.data import load_wide_close_csv
from quant_rotation.models import StrategyConfig
from quant_rotation.sample_data import generate_sample_data
from quant_rotation.validation import (
    _recent_weighted_score,
    _regime_aware_score,
    bootstrap_oos_ci,
    resolve_walk_forward_splits,
    run_walk_forward_validation,
    resolve_train_test_split,
    run_train_test_validation,
    selected_by_train,
    write_walk_forward_validation_reports,
    write_train_test_validation_reports,
)


class TrainTestValidationTests(unittest.TestCase):
    @staticmethod
    def _equity_from_returns(returns: list[float]) -> list[float]:
        equity = [1.0]
        for value in returns:
            equity.append(equity[-1] * (1.0 + value))
        return equity

    def test_bootstrap_oos_ci_positive_returns(self) -> None:
        result = bootstrap_oos_ci(
            [0.10, 0.20, 0.15, 0.05, 0.18],
            n_bootstrap=2_000,
        )

        self.assertGreater(result["p_positive"], 0.90)
        self.assertGreater(result["ci_lower"], 0.0)

    def test_bootstrap_oos_ci_mixed_returns(self) -> None:
        result = bootstrap_oos_ci(
            [-0.20, -0.10, 0.10, 0.20],
            n_bootstrap=2_000,
        )

        self.assertLess(result["ci_lower"], 0.05)
        self.assertGreater(result["p_positive"], 0.30)
        self.assertLess(result["p_positive"], 0.70)

    def test_recent_weighted_score_favors_recent_performance(self) -> None:
        dates = [
            date(2024, 1, 1) + timedelta(days=i)
            for i in range(601)
        ]
        metrics = {
            "sharpe_ratio": 0.0,
            "excess_return_vs_equal_weight": 0.0,
            "calmar_ratio": 0.0,
            "average_turnover": 0.0,
            "max_drawdown": 0.0,
        }
        old_returns = [0.001, -0.0005] * 174
        recent_good = old_returns + [0.001, 0.002, 0.0005, 0.0015] * 63
        recent_bad = old_returns + [-0.002, -0.001, -0.0015, -0.0005] * 63

        good_score = _recent_weighted_score(
            metrics,
            dates,
            self._equity_from_returns(recent_good),
        )
        bad_score = _recent_weighted_score(
            metrics,
            dates,
            self._equity_from_returns(recent_bad),
        )

        self.assertGreater(good_score, bad_score)

    def test_regime_aware_score_bear_favors_low_drawdown(self) -> None:
        lower_drawdown = {
            "annualized_return": -0.05,
            "max_drawdown": -0.25,
            "sharpe_ratio": -0.3,
            "calmar_ratio": -0.2,
        }
        higher_drawdown = {
            "annualized_return": -0.05,
            "max_drawdown": -0.40,
            "sharpe_ratio": -0.3,
            "calmar_ratio": -0.6,
        }

        self.assertGreater(
            _regime_aware_score(lower_drawdown),
            _regime_aware_score(higher_drawdown),
        )

    def test_resolve_train_test_split_accepts_explicit_dates(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            data_dir = Path(tmp) / "data"
            generate_sample_data(data_dir, days=220, seed=19)
            prices = load_wide_close_csv(data_dir / "industry_close.csv")

            split = resolve_train_test_split(
                prices.dates,
                train_end=prices.dates[160],
                test_start=prices.dates[161],
            )

            self.assertEqual(split.train_end, prices.dates[160])
            self.assertEqual(split.test_start, prices.dates[161])

    def test_resolve_walk_forward_splits_rolls_fixed_windows(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            data_dir = Path(tmp) / "data"
            generate_sample_data(data_dir, days=180, seed=29)
            prices = load_wide_close_csv(data_dir / "industry_close.csv")

            splits = resolve_walk_forward_splits(
                prices.dates,
                train_window=60,
                test_window=20,
                step=20,
            )

            self.assertEqual(len(splits), 6)
            self.assertEqual(splits[0].train_start_index, 0)
            self.assertEqual(splits[0].train_end_index, 59)
            self.assertEqual(splits[0].test_start_index, 60)
            self.assertEqual(splits[0].test_end_index, 79)
            self.assertEqual(splits[-1].train_start_index, 100)
            self.assertEqual(splits[-1].test_end_index, 179)

    def test_train_test_validation_runs_and_writes_reports(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            data_dir = root / "data"
            report_dir = root / "reports"
            generate_sample_data(data_dir, days=260, seed=23)
            prices = load_wide_close_csv(data_dir / "industry_close.csv")

            runs = run_train_test_validation(
                prices,
                None,
                StrategyConfig(risk_control=False, market_score_control=False),
                top_k_values=(3, 5),
                risk_off_exposures=(0.0,),
                train_end=prices.dates[190],
                test_start=prices.dates[191],
            )
            write_train_test_validation_reports(runs, report_dir)
            selected = selected_by_train(runs)
            selected_by_sharpe_calmar = selected_by_train(runs, "sharpe_plus_calmar")

            self.assertGreater(len(runs), 0)
            self.assertIsNotNone(selected.train_metrics["annualized_return"])
            self.assertIsNotNone(selected_by_sharpe_calmar.train_metrics["sharpe_ratio"])
            self.assertTrue((report_dir / "train_test_validation.csv").exists())
            self.assertTrue((report_dir / "train_test_selected_equity.csv").exists())
            self.assertTrue((report_dir / "train_test_annual_returns.csv").exists())

            summary_header = (report_dir / "train_test_validation.csv").read_text(
                encoding="utf-8"
            ).splitlines()[0]
            equity_header = (report_dir / "train_test_selected_equity.csv").read_text(
                encoding="utf-8"
            ).splitlines()[0]
            self.assertIn("test_annualized_return", summary_header)
            self.assertIn("market_score_threshold", summary_header)
            self.assertIn("segment", equity_header)

    def test_walk_forward_validation_runs_and_writes_reports(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            data_dir = root / "data"
            report_dir = root / "reports"
            generate_sample_data(data_dir, days=320, seed=31)
            prices = load_wide_close_csv(data_dir / "industry_close.csv")

            folds = run_walk_forward_validation(
                prices,
                None,
                StrategyConfig(risk_control=False, market_score_control=False),
                top_k_values=(3, 5),
                risk_off_exposures=(0.0,),
                train_window=140,
                test_window=40,
                step=40,
            )
            write_walk_forward_validation_reports(folds, report_dir)

            self.assertGreater(len(folds), 1)
            self.assertTrue((report_dir / "walk_forward_candidates.csv").exists())
            self.assertTrue((report_dir / "walk_forward_folds.csv").exists())
            self.assertTrue((report_dir / "walk_forward_selected_equity.csv").exists())
            self.assertTrue((report_dir / "walk_forward_oos_equity.csv").exists())
            self.assertTrue((report_dir / "fixed_candidate_summary.csv").exists())
            self.assertTrue((report_dir / "walk_forward_summary.csv").exists())

            candidates_header = (report_dir / "walk_forward_candidates.csv").read_text(
                encoding="utf-8"
            ).splitlines()[0]
            folds_header = (report_dir / "walk_forward_folds.csv").read_text(
                encoding="utf-8"
            ).splitlines()[0]
            equity_header = (report_dir / "walk_forward_selected_equity.csv").read_text(
                encoding="utf-8"
            ).splitlines()[0]
            summary_text = (report_dir / "walk_forward_summary.csv").read_text(
                encoding="utf-8"
            )
            self.assertIn("test_annualized_return", folds_header)
            self.assertIn("selection_metric", candidates_header)
            self.assertIn("train_selection_score", candidates_header)
            self.assertIn("risk_control", candidates_header)
            self.assertIn("market_score_threshold", candidates_header)
            self.assertIn("selected_name", equity_header)
            self.assertIn("test_std,sharpe_ratio", summary_text)
            self.assertIn("bootstrap_ci_lower,annualized_return", summary_text)
            self.assertIn("bootstrap_ci_upper,annualized_return", summary_text)
            self.assertIn("bootstrap_p_positive,annualized_return", summary_text)
            oos_header = (report_dir / "walk_forward_oos_equity.csv").read_text(
                encoding="utf-8"
            ).splitlines()[0]
            self.assertIn("selected_name", oos_header)
            fixed_header = (report_dir / "fixed_candidate_summary.csv").read_text(
                encoding="utf-8"
            ).splitlines()[0]
            self.assertIn("oos_final_equity", fixed_header)
            self.assertIn("selection_count", summary_text)


if __name__ == "__main__":
    unittest.main()
