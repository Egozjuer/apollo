"""Configuration models for the 07709 signal engine."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Mapping, Optional


@dataclass(frozen=True)
class SymbolConfig:
    """Market symbols used by the strategy.

    Yahoo Finance symbols are used by the default data provider. Hong Kong
    tickers usually omit the leading zero, so 07709.HK is represented as
    7709.HK.
    """

    etp: str = "7709.HK"
    sk_hynix: str = "000660.KS"
    sk_hynix_us: str = "SKHY"
    kospi: str = "^KS11"
    sox: str = "^SOX"
    nvda: str = "NVDA"
    mu: str = "MU"
    nasdaq100: str = "^NDX"
    usdkrw: str = "KRW=X"

    @classmethod
    def from_mapping(cls, data: Mapping[str, Any]) -> "SymbolConfig":
        base = cls()
        values = {field_name: getattr(base, field_name) for field_name in cls.__dataclass_fields__}
        values.update({key: value for key, value in data.items() if key in values})
        return cls(**values)

    def as_dict(self) -> Dict[str, str]:
        return {
            "etp": self.etp,
            "sk_hynix": self.sk_hynix,
            "sk_hynix_us": self.sk_hynix_us,
            "kospi": self.kospi,
            "sox": self.sox,
            "nvda": self.nvda,
            "mu": self.mu,
            "nasdaq100": self.nasdaq100,
            "usdkrw": self.usdkrw,
        }


@dataclass(frozen=True)
class RiskConfig:
    """User-specific risk and position settings."""

    cost_basis: float = 110.0
    current_position_pct: float = 70.0
    desired_profit_on_cost_pct: float = 60.0
    max_position_pct: float = 50.0
    stop_reduce_price: float = 58.0
    stop_deep_reduce_price: float = 52.0
    stop_observation_price: float = 48.0
    rebound_first_reduce_price: float = 75.0
    rebound_second_reduce_price: float = 90.0
    rebound_take_profit_price: float = 99.0
    min_hkd_turnover: float = 2_000_000.0
    product_nav: Optional[float] = None
    max_premium_pct: float = 3.0
    overnight_sk_hynix_strong_pct: float = 5.0
    overnight_semis_strong_pct: float = 2.0
    overnight_nasdaq_positive_pct: float = 0.0

    @classmethod
    def from_mapping(cls, data: Mapping[str, Any]) -> "RiskConfig":
        base = cls()
        values = {field_name: getattr(base, field_name) for field_name in cls.__dataclass_fields__}
        values.update({key: value for key, value in data.items() if key in values})
        return cls(**values)


@dataclass(frozen=True)
class StrategyConfig:
    """Top-level strategy configuration."""

    symbols: SymbolConfig = field(default_factory=SymbolConfig)
    risk: RiskConfig = field(default_factory=RiskConfig)
    history_range: str = "6mo"
    history_interval: str = "1d"

    @classmethod
    def from_mapping(cls, data: Mapping[str, Any]) -> "StrategyConfig":
        return cls(
            symbols=SymbolConfig.from_mapping(data.get("symbols", {})),
            risk=RiskConfig.from_mapping(data.get("risk", {})),
            history_range=data.get("history_range", "6mo"),
            history_interval=data.get("history_interval", "1d"),
        )


def load_config(path: str | Path) -> StrategyConfig:
    """Load strategy configuration from a JSON file."""

    config_path = Path(path)
    with config_path.open("r", encoding="utf-8") as fp:
        data = json.load(fp)
    return StrategyConfig.from_mapping(data)
