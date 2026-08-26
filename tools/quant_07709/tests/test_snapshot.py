"""Tests for 07709 three-market snapshot calculations."""

from __future__ import annotations

import unittest

from tools.quant_07709.snapshot import (
    parse_tencent_quote,
    pct_change,
    theoretical_adr_usd,
    theoretical_nav,
)


class SnapshotMathTest(unittest.TestCase):
    def test_official_premium_matches_screenshot(self) -> None:
        self.assertAlmostEqual(pct_change(37.24, 37.51), -0.7198, places=3)

    def test_theoretical_nav_uses_two_times_korea_return(self) -> None:
        nav = theoretical_nav(37.51, 0.54, leverage=2.0)
        self.assertIsNotNone(nav)
        self.assertAlmostEqual(nav, 37.9151, places=3)

    def test_theoretical_adr_and_official_premium(self) -> None:
        theory = theoretical_adr_usd(1_687_000, 1383.13, adr_ratio=10.0)
        self.assertIsNotNone(theory)
        self.assertAlmostEqual(theory, 121.97, places=2)
        self.assertAlmostEqual(pct_change(159.53, theory), 30.79, places=2)


class TencentParserTest(unittest.TestCase):
    def test_parse_hk7709_quote(self) -> None:
        raw = (
            'v_hk07709="100~南方2倍做多海力士~07709~37.240~36.700~32.900~161411200.0~0~0~37.240~'
            "0~0~0~0~0~0~0~0~0~37.240~0~0~0~0~0~0~0~0~0~161411200.0~2026/08/25 16:08:21~"
            '0.540~1.47~38.160~32.520~37.240~161411200.0~5673604838.180~0~0.00~~0~0~15.37~";'
        )
        quote = parse_tencent_quote(raw, "hk07709")
        self.assertEqual(quote.symbol, "07709")
        self.assertAlmostEqual(quote.price, 37.24)
        self.assertAlmostEqual(quote.change_pct, 1.47)
        self.assertEqual(quote.currency, "HKD")
        self.assertIn("2026-08-25", quote.as_of or "")

    def test_parse_skhy_quote_and_ratio(self) -> None:
        raw = (
            'v_usSKHY="200~SK海力士~SKHY.OQ~159.53~155.37~159.90~12287274~0~0~158.25~2900~'
            "0~0~0~0~0~0~0~0~158.48~100~0~0~0~0~0~0~0~0~~2026-08-25 16:00:01~4.16~2.68~"
            '161.20~156.24~USD~12287274~1949510088~0.17~10.87~~38.16~10:1~3.19~";'
        )
        quote = parse_tencent_quote(raw, "usSKHY")
        self.assertAlmostEqual(quote.price, 159.53)
        self.assertAlmostEqual(quote.change_pct, 2.68)
        self.assertEqual(quote.currency, "USD")
        self.assertEqual((quote.extra or {}).get("adr_ratio_text"), "10:1")

    def test_parse_korea_quote_uses_percent_not_absolute_change(self) -> None:
        raw = (
            'v_kr000660="352~SK hynix Inc.~000660.KS~1679000~1678000~1668000~717337~'
            "~~~~~~~~~~~~~~~~~~~~~~~2026-08-26 08:53:26~1000~0.05959476~1717000~1662000~"
            '~717337~~~~~~~~~11918463.6199~SK hynix Inc.~~2987000~253000~~~~~~~~~~~~~~~~~~~~~~";'
        )
        quote = parse_tencent_quote(raw, "kr000660")
        self.assertAlmostEqual(quote.price, 1_679_000)
        self.assertAlmostEqual(quote.change_pct, 0.0596, places=3)
        self.assertLess(abs(quote.change_pct), 5)


if __name__ == "__main__":
    unittest.main()
