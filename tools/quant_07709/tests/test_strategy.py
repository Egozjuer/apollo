"""Tests for the 07709 signal engine."""

from __future__ import annotations

import unittest

from tools.quant_07709.config import RiskConfig, StrategyConfig
from tools.quant_07709.market_data import PriceBar
from tools.quant_07709.strategy import build_signal


class StrategyTest(unittest.TestCase):
    def test_bullish_market_caps_position_at_configured_maximum(self) -> None:
        config = StrategyConfig(risk=RiskConfig(current_position_pct=20.0, max_position_pct=50.0))
        history = {
            "etp": make_bars(start=62.0, drift=0.20, volume=100_000),
            "sk_hynix": make_bars(start=100.0, drift=0.60),
            "sk_hynix_us": make_bars(start=100.0, drift=0.50, final_jump_pct=10.0),
            "kospi": make_bars(start=100.0, drift=0.10),
            "sox": make_bars(start=100.0, drift=0.40, final_jump_pct=2.5),
            "nvda": make_bars(start=100.0, drift=0.50, final_jump_pct=2.5),
            "mu": make_bars(start=100.0, drift=0.35, final_jump_pct=2.5),
            "nasdaq100": make_bars(start=100.0, drift=0.25, final_jump_pct=0.5),
            "usdkrw": make_bars(start=1400.0, drift=-0.60),
        }

        signal = build_signal(config, history)

        self.assertGreaterEqual(signal.score, 10)
        self.assertEqual(signal.target_position_pct, 50.0)
        self.assertEqual(signal.action, "allow_small_add_only_if_liquidity_ok")

    def test_weak_market_recommends_reduction(self) -> None:
        config = StrategyConfig(risk=RiskConfig(current_position_pct=70.0, max_position_pct=50.0))
        history = {
            "etp": make_bars(start=80.0, drift=-0.20, volume=100_000),
            "sk_hynix": make_bars(start=100.0, drift=-0.50),
            "sk_hynix_us": make_bars(start=100.0, drift=-0.50),
            "kospi": make_bars(start=100.0, drift=0.10),
            "sox": make_bars(start=100.0, drift=-0.40),
            "nvda": make_bars(start=100.0, drift=-0.50),
            "mu": make_bars(start=100.0, drift=-0.35),
            "nasdaq100": make_bars(start=100.0, drift=-0.25),
            "usdkrw": make_bars(start=1300.0, drift=0.60),
        }

        signal = build_signal(config, history)

        self.assertLessEqual(signal.score, 3)
        self.assertEqual(signal.target_position_pct, 20.0)
        self.assertEqual(signal.action, "reduce_to_target")
        self.assertIn("critical", signal.risk_level)

    def test_price_risk_override_caps_target_position(self) -> None:
        config = StrategyConfig(risk=RiskConfig(current_position_pct=70.0, max_position_pct=50.0))
        history = {
            "etp": make_bars(start=40.0, drift=0.05, volume=100_000),
            "sk_hynix": make_bars(start=100.0, drift=0.60),
            "sk_hynix_us": make_bars(start=100.0, drift=0.50, final_jump_pct=10.0),
            "kospi": make_bars(start=100.0, drift=0.10),
            "sox": make_bars(start=100.0, drift=0.40, final_jump_pct=2.5),
            "nvda": make_bars(start=100.0, drift=0.50, final_jump_pct=2.5),
            "mu": make_bars(start=100.0, drift=0.35, final_jump_pct=2.5),
            "nasdaq100": make_bars(start=100.0, drift=0.25, final_jump_pct=0.5),
            "usdkrw": make_bars(start=1400.0, drift=-0.60),
        }

        signal = build_signal(config, history)

        self.assertEqual(signal.target_position_pct, 10.0)
        self.assertEqual(signal.action, "reduce_to_target")
        self.assertEqual(signal.risk_level, "critical")

    def test_cost_metrics_match_user_position(self) -> None:
        config = StrategyConfig(risk=RiskConfig(cost_basis=110.0, current_position_pct=70.0))
        history = {
            "etp": flat_bars(62.0, volume=100_000),
            "sk_hynix": make_bars(start=100.0, drift=0.60),
            "sk_hynix_us": make_bars(start=100.0, drift=0.50, final_jump_pct=10.0),
            "kospi": make_bars(start=100.0, drift=0.10),
            "sox": make_bars(start=100.0, drift=0.40, final_jump_pct=2.5),
            "nvda": make_bars(start=100.0, drift=0.50, final_jump_pct=2.5),
            "mu": make_bars(start=100.0, drift=0.35, final_jump_pct=2.5),
            "nasdaq100": make_bars(start=100.0, drift=0.25, final_jump_pct=0.5),
            "usdkrw": make_bars(start=1400.0, drift=-0.60),
        }

        signal = build_signal(config, history)

        self.assertAlmostEqual(signal.unrealized_return_pct, -43.6363636, places=4)
        self.assertAlmostEqual(signal.rebound_to_cost_required_pct, 77.4193548, places=4)
        self.assertAlmostEqual(signal.price_levels.current_price_plus_60pct, 99.2, places=4)
        self.assertAlmostEqual(signal.price_levels.profit_60pct_on_cost_price, 176.0, places=4)

    def test_overnight_sk_hynix_strength_adds_points(self) -> None:
        config = StrategyConfig(risk=RiskConfig(overnight_sk_hynix_strong_pct=5.0))
        history = {
            "etp": flat_bars(62.0, volume=100_000),
            "sk_hynix": make_bars(start=100.0, drift=0.10),
            "sk_hynix_us": make_bars(start=100.0, drift=0.10, final_jump_pct=10.0),
            "kospi": make_bars(start=100.0, drift=0.10),
            "sox": make_bars(start=100.0, drift=0.10),
            "nvda": make_bars(start=100.0, drift=0.10),
            "mu": make_bars(start=100.0, drift=0.10),
            "nasdaq100": make_bars(start=100.0, drift=0.10),
            "usdkrw": make_bars(start=1400.0, drift=0.10),
        }

        signal = build_signal(config, history)
        overnight_factor = next(
            factor for factor in signal.factors if factor.name == "sk_hynix_us_overnight_strong"
        )

        self.assertTrue(overnight_factor.passed)
        self.assertEqual(overnight_factor.points, 2)


def make_bars(
    start: float,
    drift: float,
    volume: float = 1_000_000,
    length: int = 90,
    final_jump_pct: float = 0.0,
) -> list[PriceBar]:
    bars: list[PriceBar] = []
    price = start
    for index in range(length):
        price += drift
        if index == length - 1 and final_jump_pct:
            price *= 1 + final_jump_pct / 100.0
        bars.append(
            PriceBar(
                timestamp=index,
                date=f"day-{index:03d}",
                open=price,
                high=price,
                low=price,
                close=price,
                volume=volume,
            )
        )
    return bars


def flat_bars(price: float, volume: float = 1_000_000, length: int = 90) -> list[PriceBar]:
    return [
        PriceBar(
            timestamp=index,
            date=f"day-{index:03d}",
            open=price,
            high=price,
            low=price,
            close=price,
            volume=volume,
        )
        for index in range(length)
    ]


if __name__ == "__main__":
    unittest.main()
