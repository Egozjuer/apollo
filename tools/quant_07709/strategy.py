"""Signal engine for the 07709.HK leveraged product."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Dict, Iterable, List, Optional

from tools.quant_07709.config import RiskConfig, StrategyConfig
from tools.quant_07709.indicators import (
    annualized_volatility,
    average_turnover,
    is_above_sma,
    latest_close,
    rate_of_change,
    relative_strength,
    simple_moving_average,
)
from tools.quant_07709.market_data import PriceBar


@dataclass(frozen=True)
class FactorResult:
    name: str
    points: int
    max_points: int
    passed: Optional[bool]
    value: Optional[float]
    description: str


@dataclass(frozen=True)
class PriceLevels:
    current_price: float
    cost_basis: float
    break_even_price: float
    current_price_plus_60pct: float
    profit_60pct_on_cost_price: float
    stop_reduce_price: float
    stop_deep_reduce_price: float
    stop_observation_price: float
    rebound_first_reduce_price: float
    rebound_second_reduce_price: float
    rebound_take_profit_price: float


@dataclass(frozen=True)
class TradingSignal:
    as_of: str
    product_symbol: str
    current_price: float
    cost_basis: float
    unrealized_return_pct: float
    rebound_to_cost_required_pct: float
    score: int
    max_score: int
    risk_level: str
    action: str
    target_position_pct: float
    current_position_pct: float
    suggested_position_change_pct: float
    annualized_volatility_20d: Optional[float]
    price_levels: PriceLevels
    factors: List[FactorResult]
    warnings: List[str]

    def to_dict(self) -> Dict[str, object]:
        return asdict(self)


class SignalEngineError(RuntimeError):
    """Raised when a signal cannot be computed from available data."""


def build_signal(config: StrategyConfig, history: Dict[str, List[PriceBar]]) -> TradingSignal:
    """Build a trading signal from historical bars keyed by logical symbol."""

    required = ["etp", "sk_hynix", "kospi", "sox", "nvda", "mu", "nasdaq100", "usdkrw"]
    missing = [name for name in required if not history.get(name)]
    if missing:
        raise SignalEngineError(f"missing market data for: {', '.join(missing)}")

    risk = config.risk
    etp_bars = history["etp"]
    current_price = latest_close(etp_bars)
    if current_price is None:
        raise SignalEngineError("missing current 07709 price")

    factors: List[FactorResult] = []
    add_trend_factor(
        factors,
        "sk_hynix_above_sma20",
        history["sk_hynix"],
        window=20,
        points=2,
        description="SK海力士收盘价站上20日均线",
    )
    add_trend_factor(
        factors,
        "sk_hynix_above_sma60",
        history["sk_hynix"],
        window=60,
        points=2,
        description="SK海力士收盘价站上60日均线",
    )
    add_sma_cross_factor(
        factors,
        "sk_hynix_sma20_above_sma60",
        history["sk_hynix"],
        fast_window=20,
        slow_window=60,
        points=2,
        description="SK海力士20日均线高于60日均线",
    )
    add_relative_strength_factor(
        factors,
        "sk_hynix_outperforms_kospi_20d",
        history["sk_hynix"],
        history["kospi"],
        lookback=20,
        points=1,
        description="SK海力士20日表现跑赢KOSPI",
    )
    add_trend_factor(
        factors,
        "kospi_above_sma60",
        history["kospi"],
        window=60,
        points=1,
        description="KOSPI站上60日均线",
    )
    add_trend_factor(
        factors,
        "sox_above_sma20",
        history["sox"],
        window=20,
        points=1,
        description="费城半导体指数站上20日均线",
    )
    add_trend_factor(
        factors,
        "nvda_above_sma20",
        history["nvda"],
        window=20,
        points=1,
        description="英伟达站上20日均线",
    )
    add_trend_factor(
        factors,
        "mu_above_sma20",
        history["mu"],
        window=20,
        points=1,
        description="美光站上20日均线",
    )
    add_trend_factor(
        factors,
        "nasdaq100_above_sma20",
        history["nasdaq100"],
        window=20,
        points=1,
        description="纳斯达克100站上20日均线",
    )
    add_usdkrw_factor(
        factors,
        "usdkrw_weakens_5d",
        history["usdkrw"],
        lookback=5,
        points=1,
        description="USD/KRW 5日下行，代表韩元相对走强",
    )
    add_liquidity_factor(
        factors,
        "etp_turnover_ok",
        etp_bars,
        min_turnover=risk.min_hkd_turnover,
        points=1,
        description="07709近5日平均成交额达到配置阈值",
    )
    add_premium_factor(
        factors,
        "etp_premium_ok",
        current_price=current_price,
        product_nav=risk.product_nav,
        max_premium_pct=risk.max_premium_pct,
        points=1,
        description="07709相对产品净值没有明显溢价；未配置NAV时不计分",
    )

    score = sum(factor.points for factor in factors)
    max_score = sum(factor.max_points for factor in factors)
    target_position_pct = score_to_target_position(score, risk)
    warnings = build_warnings(current_price, risk, score, max_score)
    target_position_pct = apply_price_risk_overrides(current_price, risk, target_position_pct)
    risk_level = classify_risk(score, max_score, current_price, risk)
    action = classify_action(
        current_position_pct=risk.current_position_pct,
        target_position_pct=target_position_pct,
        score=score,
        current_price=current_price,
        risk=risk,
    )

    if current_price == 0:
        rebound_to_cost_required_pct = 0.0
    else:
        rebound_to_cost_required_pct = ((risk.cost_basis / current_price) - 1.0) * 100.0

    price_levels = PriceLevels(
        current_price=current_price,
        cost_basis=risk.cost_basis,
        break_even_price=risk.cost_basis,
        current_price_plus_60pct=current_price * 1.6,
        profit_60pct_on_cost_price=risk.cost_basis * (1 + risk.desired_profit_on_cost_pct / 100.0),
        stop_reduce_price=risk.stop_reduce_price,
        stop_deep_reduce_price=risk.stop_deep_reduce_price,
        stop_observation_price=risk.stop_observation_price,
        rebound_first_reduce_price=risk.rebound_first_reduce_price,
        rebound_second_reduce_price=risk.rebound_second_reduce_price,
        rebound_take_profit_price=risk.rebound_take_profit_price,
    )

    latest_date = etp_bars[-1].date
    return TradingSignal(
        as_of=latest_date,
        product_symbol=config.symbols.etp,
        current_price=current_price,
        cost_basis=risk.cost_basis,
        unrealized_return_pct=((current_price / risk.cost_basis) - 1.0) * 100.0,
        rebound_to_cost_required_pct=rebound_to_cost_required_pct,
        score=score,
        max_score=max_score,
        risk_level=risk_level,
        action=action,
        target_position_pct=target_position_pct,
        current_position_pct=risk.current_position_pct,
        suggested_position_change_pct=target_position_pct - risk.current_position_pct,
        annualized_volatility_20d=annualized_volatility(etp_bars, lookback=20),
        price_levels=price_levels,
        factors=factors,
        warnings=warnings,
    )


def add_trend_factor(
    factors: List[FactorResult],
    name: str,
    bars: Iterable[PriceBar],
    window: int,
    points: int,
    description: str,
) -> None:
    passed = is_above_sma(bars, window)
    sma = simple_moving_average(bars, window)
    factors.append(FactorResult(name, points if passed else 0, points, passed, sma, description))


def add_sma_cross_factor(
    factors: List[FactorResult],
    name: str,
    bars: Iterable[PriceBar],
    fast_window: int,
    slow_window: int,
    points: int,
    description: str,
) -> None:
    fast = simple_moving_average(bars, fast_window)
    slow = simple_moving_average(bars, slow_window)
    passed = None if fast is None or slow is None else fast > slow
    value = None if fast is None or slow is None else fast - slow
    factors.append(FactorResult(name, points if passed else 0, points, passed, value, description))


def add_relative_strength_factor(
    factors: List[FactorResult],
    name: str,
    stock_bars: Iterable[PriceBar],
    benchmark_bars: Iterable[PriceBar],
    lookback: int,
    points: int,
    description: str,
) -> None:
    strength = relative_strength(stock_bars, benchmark_bars, lookback)
    passed = None if strength is None else strength > 0
    factors.append(FactorResult(name, points if passed else 0, points, passed, strength, description))


def add_usdkrw_factor(
    factors: List[FactorResult],
    name: str,
    bars: Iterable[PriceBar],
    lookback: int,
    points: int,
    description: str,
) -> None:
    roc = rate_of_change(bars, lookback)
    passed = None if roc is None else roc < 0
    factors.append(FactorResult(name, points if passed else 0, points, passed, roc, description))


def add_liquidity_factor(
    factors: List[FactorResult],
    name: str,
    bars: Iterable[PriceBar],
    min_turnover: float,
    points: int,
    description: str,
) -> None:
    turnover = average_turnover(bars, lookback=5)
    passed = None if turnover is None else turnover >= min_turnover
    factors.append(FactorResult(name, points if passed else 0, points, passed, turnover, description))


def add_premium_factor(
    factors: List[FactorResult],
    name: str,
    current_price: float,
    product_nav: Optional[float],
    max_premium_pct: float,
    points: int,
    description: str,
) -> None:
    if product_nav is None or product_nav <= 0:
        factors.append(FactorResult(name, 0, 0, None, None, description))
        return
    premium_pct = ((current_price / product_nav) - 1.0) * 100.0
    passed = premium_pct <= max_premium_pct
    factors.append(FactorResult(name, points if passed else 0, points, passed, premium_pct, description))


def score_to_target_position(score: int, risk: RiskConfig) -> float:
    if score <= 3:
        return min(20.0, risk.max_position_pct)
    if score <= 6:
        return min(35.0, risk.max_position_pct)
    return min(50.0, risk.max_position_pct)


def apply_price_risk_overrides(current_price: float, risk: RiskConfig, target_position_pct: float) -> float:
    if current_price < risk.stop_observation_price:
        return min(target_position_pct, 10.0)
    if current_price < risk.stop_deep_reduce_price:
        return min(target_position_pct, 30.0)
    if current_price < risk.stop_reduce_price:
        return min(target_position_pct, 50.0)
    return target_position_pct


def classify_risk(score: int, max_score: int, current_price: float, risk: RiskConfig) -> str:
    score_ratio = score / max_score if max_score else 0.0
    if current_price < risk.stop_observation_price or score_ratio < 0.25:
        return "critical"
    if current_price < risk.stop_deep_reduce_price or score_ratio < 0.45:
        return "high"
    if current_price < risk.stop_reduce_price or score_ratio < 0.70:
        return "medium"
    return "low"


def classify_action(
    current_position_pct: float,
    target_position_pct: float,
    score: int,
    current_price: float,
    risk: RiskConfig,
) -> str:
    if current_position_pct > target_position_pct + 5.0:
        return "reduce_to_target"
    if current_price >= risk.rebound_take_profit_price and current_position_pct > 35.0:
        return "take_partial_profit_or_reduce"
    if score >= 7 and current_position_pct < target_position_pct - 5.0:
        return "allow_small_add_only_if_liquidity_ok"
    return "hold_or_watch"


def build_warnings(current_price: float, risk: RiskConfig, score: int, max_score: int) -> List[str]:
    warnings: List[str] = [
        "07709是每日2倍杠杆产品；本工具只生成信号，不自动下单，也不构成投资建议。",
        "默认Yahoo行情通常延迟，不能替代券商实时行情或风控系统。",
    ]
    if risk.current_position_pct > risk.max_position_pct:
        warnings.append(
            f"当前仓位{risk.current_position_pct:.1f}%高于配置上限{risk.max_position_pct:.1f}%，优先考虑降风险。"
        )
    if current_price < risk.stop_reduce_price:
        warnings.append(f"价格低于第一风控线{risk.stop_reduce_price:.2f}，不建议补仓摊平。")
    if current_price >= risk.rebound_first_reduce_price:
        warnings.append("已经进入反弹减仓观察区，若趋势分数不足，应优先降低杠杆暴露。")
    if max_score and score / max_score < 0.45:
        warnings.append("趋势分数偏弱，策略只允许小仓位或减仓，不允许亏损驱动型补仓。")
    return warnings
