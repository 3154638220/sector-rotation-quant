from __future__ import annotations

import unittest

from quant_rotation.portfolio import (
    adaptive_top_k,
    equal_weight_target,
    softmax_weight_target,
    vol_parity_target,
)


class PortfolioTests(unittest.TestCase):
    def test_softmax_weights_sum_to_exposure(self) -> None:
        scores = {"a": 2.5, "b": 1.5, "c": 1.0, "d": 0.5, "e": 0.3}
        weights = softmax_weight_target(scores, 5, 1.0, 0.30, temperature=1.0)
        self.assertAlmostEqual(sum(weights.values()), 1.0, places=6)
        self.assertEqual(len(weights), 5)

    def test_softmax_higher_score_gets_higher_weight(self) -> None:
        scores = {"a": 3.0, "b": 1.0}
        weights = softmax_weight_target(scores, 2, 1.0, 0.70, temperature=1.0)
        self.assertGreater(weights["a"], weights["b"])

    def test_softmax_temperature_affects_concentration(self) -> None:
        scores = {"a": 3.0, "b": 1.0, "c": 0.5, "d": 0.2, "e": 0.1}
        weights_low_t = softmax_weight_target(scores, 5, 1.0, 1.0, temperature=0.5)
        weights_high_t = softmax_weight_target(scores, 5, 1.0, 1.0, temperature=2.0)
        concentration_low = weights_low_t["a"] - weights_low_t["b"]
        concentration_high = weights_high_t["a"] - weights_high_t["b"]
        self.assertGreater(concentration_low, concentration_high)

    def test_softmax_respects_max_weight(self) -> None:
        scores = {"a": 10.0, "b": 0.1}
        weights = softmax_weight_target(scores, 2, 0.40, 0.25, temperature=0.5)
        for w in weights.values():
            self.assertLessEqual(w, 0.25 + 1e-10)

    def test_softmax_zero_exposure_returns_empty(self) -> None:
        scores = {"a": 2.0, "b": 1.0}
        weights = softmax_weight_target(scores, 2, 0.0, 0.30, temperature=1.0)
        self.assertEqual(weights, {})

    def test_vol_parity_weights_inverse_vol(self) -> None:
        scores = {"a": 1.0, "b": 1.0}
        vol = {"a": 0.01, "b": 0.02}
        weights = vol_parity_target(scores, vol, 2, 1.0, 0.70)
        self.assertAlmostEqual(weights["a"], 2.0 * weights["b"], places=6)

    def test_vol_parity_respects_max_weight(self) -> None:
        scores = {"a": 1.0, "b": 1.0}
        vol = {"a": 0.001, "b": 0.99}
        weights = vol_parity_target(scores, vol, 2, 1.0, 0.30)
        for w in weights.values():
            self.assertLessEqual(w, 0.30 + 1e-10)

    def test_adaptive_top_k_concentration(self) -> None:
        scores = {"a": 5.0, "b": 1.0, "c": 1.0, "d": 1.0, "e": 1.0}
        k = adaptive_top_k(scores, base_k=5, concentration_threshold=1.5)
        self.assertEqual(k, 3)

    def test_adaptive_top_k_dispersed(self) -> None:
        scores = {"a": -0.1, "b": -0.1, "c": -0.1, "d": -0.1, "e": -0.1}
        k = adaptive_top_k(scores, base_k=5, concentration_threshold=1.5)
        self.assertEqual(k, 7)

    def test_adaptive_top_k_default(self) -> None:
        scores = {"a": 2.0, "b": 1.8, "c": 1.5, "d": 1.3, "e": 1.0}
        k = adaptive_top_k(scores, base_k=5, concentration_threshold=1.5)
        self.assertEqual(k, 5)

    def test_equal_weight_still_works(self) -> None:
        scores = {"a": 10.0, "b": 1.0, "c": 0.5}
        weights = equal_weight_target(scores, 2, 0.60, 0.30)
        self.assertAlmostEqual(sum(weights.values()), 0.60, places=6)
        self.assertEqual(weights["a"], 0.30)
        self.assertEqual(weights["b"], 0.30)
        self.assertNotIn("c", weights)


if __name__ == "__main__":
    unittest.main()
