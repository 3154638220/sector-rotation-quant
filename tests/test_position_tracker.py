from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from tools.position_tracker import compute_rebalance_diff


class PositionTrackerTests(unittest.TestCase):
    def test_diff_identifies_new_holdings(self) -> None:
        signal = {
            "signal_date": "2026-06-03",
            "weights": {"食品饮料": 0.2, "医药生物": 0.2, "电子": 0.2, "银行": 0.2, "电力设备": 0.2},
            "exposure": 1.0,
        }
        current = {"食品饮料": 0.2, "医药生物": 0.2, "电子": 0.2}
        diff = compute_rebalance_diff(signal, current)
        self.assertEqual(diff["buy"], ["电力设备", "银行"])
        self.assertEqual(diff["sell"], [])
        self.assertIn("食品饮料", diff["hold"])

    def test_diff_identifies_dropped_holdings(self) -> None:
        signal = {
            "signal_date": "2026-06-03",
            "weights": {"电力设备": 0.5, "煤炭": 0.5},
            "exposure": 1.0,
        }
        current = {"银行": 0.3, "电力设备": 0.5, "煤炭": 0.2}
        diff = compute_rebalance_diff(signal, current)
        self.assertEqual(diff["sell"], ["银行"])
        self.assertEqual(diff["buy"], [])

    def test_diff_handles_empty_current_positions(self) -> None:
        signal = {
            "signal_date": "2026-06-03",
            "weights": {"食品饮料": 1.0},
            "exposure": 1.0,
        }
        current: dict[str, float] = {}
        diff = compute_rebalance_diff(signal, current)
        self.assertEqual(diff["buy"], ["食品饮料"])
        self.assertEqual(diff["sell"], [])
        self.assertEqual(diff["num_changes"], 1)

    def test_diff_detects_weight_drift(self) -> None:
        signal = {
            "signal_date": "2026-06-03",
            "weights": {"A": 0.30, "B": 0.20},
            "exposure": 0.5,
        }
        current = {"A": 0.10, "B": 0.30}
        diff = compute_rebalance_diff(signal, current)
        self.assertEqual(diff["buy"], [])
        self.assertEqual(diff["sell"], [])
        self.assertEqual(diff["hold"], ["A", "B"])
        self.assertAlmostEqual(diff["drift"]["A"], 0.20)
        self.assertAlmostEqual(diff["drift"]["B"], -0.10)

    def test_diff_roundtrip_via_json(self) -> None:
        signal = {
            "signal_date": "2026-06-03",
            "weights": {"综合": 0.20, "通信": 0.20, "电子": 0.20, "电力设备": 0.20, "煤炭": 0.20},
            "exposure": 1.0,
        }
        current = {"综合": 0.20, "通信": 0.15, "电子": 0.25, "电力设备": 0.20, "煤炭": 0.20}

        with tempfile.TemporaryDirectory() as tmp:
            signal_path = Path(tmp) / "signal.json"
            signal_path.write_text(json.dumps(signal, ensure_ascii=False), encoding="utf-8")

            diff = compute_rebalance_diff(signal, current)
            diff_path = Path(tmp) / "diff.json"
            diff_path.write_text(json.dumps(diff, ensure_ascii=False, indent=2), encoding="utf-8")

            loaded = json.loads(diff_path.read_text(encoding="utf-8"))
            self.assertIn("drift", loaded)
            self.assertEqual(len(loaded["drift"]), 2)
            self.assertEqual(loaded["buy"], [])

    def test_diff_no_changes(self) -> None:
        signal = {
            "signal_date": "2026-06-03",
            "weights": {"A": 0.5, "B": 0.5},
            "exposure": 1.0,
        }
        current = {"A": 0.5, "B": 0.5}
        diff = compute_rebalance_diff(signal, current)
        self.assertEqual(diff["num_changes"], 0)
        self.assertEqual(diff["buy"], [])
        self.assertEqual(diff["sell"], [])
        self.assertEqual(diff["drift"], {})


if __name__ == "__main__":
    unittest.main()
