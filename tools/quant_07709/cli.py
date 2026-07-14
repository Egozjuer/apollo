"""Command line interface for the 07709 signal engine."""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Dict, List

from tools.quant_07709.config import StrategyConfig, load_config
from tools.quant_07709.market_data import PriceBar, YahooFinanceClient
from tools.quant_07709.strategy import TradingSignal, build_signal


DEFAULT_CONFIG = Path(__file__).with_name("config.example.json")


def main(argv: List[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Generate 07709.HK leveraged product risk signals.")
    parser.add_argument("--config", default=str(DEFAULT_CONFIG), help="Path to strategy JSON config.")
    parser.add_argument("--format", choices=["text", "json"], default="text", help="Output format.")
    parser.add_argument("--demo", action="store_true", help="Use deterministic demo data instead of online data.")
    parser.add_argument("--watch", action="store_true", help="Keep polling and print a signal every cycle.")
    parser.add_argument("--poll-seconds", type=int, default=900, help="Polling interval when --watch is set.")
    args = parser.parse_args(argv)

    config = load_config(args.config)

    while True:
        history = demo_history(config) if args.demo else fetch_history(config)
        signal = build_signal(config, history)
        if args.format == "json":
            print(json.dumps(signal.to_dict(), ensure_ascii=False, indent=2, sort_keys=True))
        else:
            print(render_text(signal))
        sys.stdout.flush()
        if not args.watch:
            break
        time.sleep(args.poll_seconds)
    return 0


def fetch_history(config: StrategyConfig) -> Dict[str, List[PriceBar]]:
    client = YahooFinanceClient()
    return client.fetch_many(
        config.symbols.as_dict(),
        range_=config.history_range,
        interval=config.history_interval,
    )


def demo_history(config: StrategyConfig) -> Dict[str, List[PriceBar]]:
    """Build deterministic data for smoke tests and README examples."""

    del config
    return {
        "etp": make_bars(start=62.0, drift=0.15, volume=80_000),
        "sk_hynix": make_bars(start=100.0, drift=0.45, volume=1_500_000),
        "kospi": make_bars(start=100.0, drift=0.12, volume=10_000_000),
        "sox": make_bars(start=100.0, drift=0.30, volume=2_000_000),
        "nvda": make_bars(start=100.0, drift=0.35, volume=20_000_000),
        "mu": make_bars(start=100.0, drift=0.28, volume=10_000_000),
        "nasdaq100": make_bars(start=100.0, drift=0.18, volume=10_000_000),
        "usdkrw": make_bars(start=1400.0, drift=-0.50, volume=1_000_000),
    }


def make_bars(start: float, drift: float, volume: float, length: int = 90) -> List[PriceBar]:
    bars: List[PriceBar] = []
    price = start
    for index in range(length):
        # Add a tiny deterministic wave so volatility is non-zero.
        price += drift + ((index % 7) - 3) * 0.03
        bars.append(
            PriceBar(
                timestamp=index,
                date=f"demo-day-{index:03d}",
                open=price * 0.995,
                high=price * 1.01,
                low=price * 0.99,
                close=price,
                volume=volume,
            )
        )
    return bars


def render_text(signal: TradingSignal) -> str:
    lines = [
        "07709 量化信号",
        f"时间: {signal.as_of}",
        f"产品: {signal.product_symbol}",
        f"现价: {signal.current_price:.3f}",
        f"成本: {signal.cost_basis:.3f}",
        f"当前盈亏: {signal.unrealized_return_pct:.2f}%",
        f"回本所需涨幅: {signal.rebound_to_cost_required_pct:.2f}%",
        f"因子分数: {signal.score}/{signal.max_score}",
        f"风险等级: {signal.risk_level}",
        f"动作: {signal.action}",
        f"当前仓位: {signal.current_position_pct:.1f}%",
        f"目标仓位: {signal.target_position_pct:.1f}%",
        f"建议仓位变化: {signal.suggested_position_change_pct:+.1f}%",
    ]
    if signal.annualized_volatility_20d is not None:
        lines.append(f"07709 20日年化波动率: {signal.annualized_volatility_20d * 100:.2f}%")

    lines.extend(
        [
            "",
            "关键价位:",
            f"- 第一风控线: {signal.price_levels.stop_reduce_price:.2f}",
            f"- 深度降仓线: {signal.price_levels.stop_deep_reduce_price:.2f}",
            f"- 观察仓线: {signal.price_levels.stop_observation_price:.2f}",
            f"- 第一反弹减仓区: {signal.price_levels.rebound_first_reduce_price:.2f}",
            f"- 第二反弹减仓区: {signal.price_levels.rebound_second_reduce_price:.2f}",
            f"- 从现价涨60%目标: {signal.price_levels.current_price_plus_60pct:.2f}",
            f"- 回本价: {signal.price_levels.break_even_price:.2f}",
            f"- 成本盈利60%目标: {signal.price_levels.profit_60pct_on_cost_price:.2f}",
            "",
            "因子明细:",
        ]
    )
    for factor in signal.factors:
        state = "通过" if factor.passed else "未通过" if factor.passed is False else "无数据"
        value = "" if factor.value is None else f" value={factor.value:.6f}"
        lines.append(f"- {factor.name}: {factor.points}/{factor.max_points} {state}{value} - {factor.description}")

    lines.append("")
    lines.append("风险提示:")
    lines.extend(f"- {warning}" for warning in signal.warnings)
    return "\n".join(lines)


if __name__ == "__main__":
    raise SystemExit(main())
