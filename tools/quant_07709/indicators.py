"""Technical indicators used by the 07709 strategy."""

from __future__ import annotations

import math
from statistics import mean, stdev
from typing import Iterable, List, Optional

from tools.quant_07709.market_data import PriceBar


def closes(bars: Iterable[PriceBar]) -> List[float]:
    return [bar.close for bar in bars]


def latest_close(bars: Iterable[PriceBar]) -> Optional[float]:
    values = closes(bars)
    if not values:
        return None
    return values[-1]


def simple_moving_average(bars: Iterable[PriceBar], window: int) -> Optional[float]:
    values = closes(bars)
    if len(values) < window or window <= 0:
        return None
    return mean(values[-window:])


def rate_of_change(bars: Iterable[PriceBar], lookback: int) -> Optional[float]:
    values = closes(bars)
    if len(values) <= lookback or lookback <= 0:
        return None
    previous = values[-lookback - 1]
    if previous == 0:
        return None
    return (values[-1] / previous) - 1.0


def relative_strength(stock_bars: Iterable[PriceBar], benchmark_bars: Iterable[PriceBar], lookback: int) -> Optional[float]:
    stock_roc = rate_of_change(stock_bars, lookback)
    benchmark_roc = rate_of_change(benchmark_bars, lookback)
    if stock_roc is None or benchmark_roc is None:
        return None
    return stock_roc - benchmark_roc


def annualized_volatility(bars: Iterable[PriceBar], lookback: int = 20, periods_per_year: int = 252) -> Optional[float]:
    values = closes(bars)
    if len(values) <= lookback:
        return None
    returns: List[float] = []
    window = values[-lookback - 1 :]
    for previous, current in zip(window, window[1:]):
        if previous <= 0:
            continue
        returns.append(math.log(current / previous))
    if len(returns) < 2:
        return None
    return stdev(returns) * math.sqrt(periods_per_year)


def average_turnover(bars: Iterable[PriceBar], lookback: int = 5) -> Optional[float]:
    values = [bar.turnover for bar in list(bars)[-lookback:] if bar.turnover is not None]
    if not values:
        return None
    return mean(values)


def is_above_sma(bars: Iterable[PriceBar], window: int) -> Optional[bool]:
    price = latest_close(bars)
    sma = simple_moving_average(bars, window)
    if price is None or sma is None:
        return None
    return price > sma
