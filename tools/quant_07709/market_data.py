"""Market data access for the 07709 signal engine."""

from __future__ import annotations

import csv
import json
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Optional


class MarketDataError(RuntimeError):
    """Raised when market data cannot be loaded or parsed."""


@dataclass(frozen=True)
class PriceBar:
    """A single OHLCV bar."""

    timestamp: int
    date: str
    open: Optional[float]
    high: Optional[float]
    low: Optional[float]
    close: float
    volume: Optional[float] = None

    @property
    def turnover(self) -> Optional[float]:
        if self.volume is None:
            return None
        return self.close * self.volume


class YahooFinanceClient:
    """Small Yahoo Finance chart API client.

    The API is unauthenticated and typically delayed. It is good enough for a
    signal dashboard or alert prototype, but not for fully automated execution.
    """

    base_url = "https://query1.finance.yahoo.com/v8/finance/chart"

    def __init__(self, timeout_seconds: float = 10.0, retries: int = 2) -> None:
        self.timeout_seconds = timeout_seconds
        self.retries = retries

    def fetch_history(self, symbol: str, range_: str = "6mo", interval: str = "1d") -> List[PriceBar]:
        query = urllib.parse.urlencode(
            {
                "range": range_,
                "interval": interval,
                "includePrePost": "false",
                "events": "div,splits",
            }
        )
        encoded_symbol = urllib.parse.quote(symbol, safe="")
        url = f"{self.base_url}/{encoded_symbol}?{query}"
        payload = self._request_json(url)
        return self._parse_chart_payload(symbol, payload)

    def fetch_many(
        self,
        symbols: Dict[str, str],
        range_: str = "6mo",
        interval: str = "1d",
    ) -> Dict[str, List[PriceBar]]:
        history: Dict[str, List[PriceBar]] = {}
        for logical_name, symbol in symbols.items():
            history[logical_name] = self.fetch_history(symbol, range_=range_, interval=interval)
        return history

    def _request_json(self, url: str) -> Dict[str, object]:
        last_error: Optional[BaseException] = None
        headers = {"User-Agent": "Mozilla/5.0 quant-07709-signal/0.1"}
        for attempt in range(self.retries + 1):
            request = urllib.request.Request(url, headers=headers)
            try:
                with urllib.request.urlopen(request, timeout=self.timeout_seconds) as response:
                    raw = response.read().decode("utf-8")
                return json.loads(raw)
            except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
                last_error = exc
                if attempt < self.retries:
                    time.sleep(0.5 * (attempt + 1))
        raise MarketDataError(f"failed to fetch market data: {last_error}")

    @staticmethod
    def _parse_chart_payload(symbol: str, payload: Dict[str, object]) -> List[PriceBar]:
        chart = payload.get("chart")
        if not isinstance(chart, dict):
            raise MarketDataError(f"invalid Yahoo response for {symbol}: missing chart")

        error = chart.get("error")
        if error:
            raise MarketDataError(f"Yahoo returned an error for {symbol}: {error}")

        results = chart.get("result")
        if not isinstance(results, list) or not results:
            raise MarketDataError(f"Yahoo returned no chart data for {symbol}")

        result = results[0]
        if not isinstance(result, dict):
            raise MarketDataError(f"invalid Yahoo response for {symbol}: malformed result")

        timestamps = result.get("timestamp")
        indicators = result.get("indicators")
        if not isinstance(timestamps, list) or not isinstance(indicators, dict):
            raise MarketDataError(f"invalid Yahoo response for {symbol}: missing timestamps")

        quotes = indicators.get("quote")
        if not isinstance(quotes, list) or not quotes:
            raise MarketDataError(f"invalid Yahoo response for {symbol}: missing quotes")

        quote = quotes[0]
        if not isinstance(quote, dict):
            raise MarketDataError(f"invalid Yahoo response for {symbol}: malformed quote")

        opens = quote.get("open") or []
        highs = quote.get("high") or []
        lows = quote.get("low") or []
        closes = quote.get("close") or []
        volumes = quote.get("volume") or []

        bars: List[PriceBar] = []
        for idx, timestamp in enumerate(timestamps):
            close = _value_at(closes, idx)
            if close is None:
                continue
            bars.append(
                PriceBar(
                    timestamp=int(timestamp),
                    date=time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime(int(timestamp))),
                    open=_value_at(opens, idx),
                    high=_value_at(highs, idx),
                    low=_value_at(lows, idx),
                    close=close,
                    volume=_value_at(volumes, idx),
                )
            )

        if not bars:
            raise MarketDataError(f"Yahoo returned only empty bars for {symbol}")
        return bars


def load_csv_history(path: str | Path) -> List[PriceBar]:
    """Load OHLCV data from a CSV file.

    Expected columns: timestamp,date,open,high,low,close,volume. Only close is
    strictly required. This helper makes the strategy testable with exported
    broker or data-vendor files.
    """

    bars: List[PriceBar] = []
    csv_path = Path(path)
    with csv_path.open("r", encoding="utf-8", newline="") as fp:
        reader = csv.DictReader(fp)
        for index, row in enumerate(reader):
            close = _parse_float(row.get("close"))
            if close is None:
                continue
            timestamp = int(_parse_float(row.get("timestamp")) or index)
            bars.append(
                PriceBar(
                    timestamp=timestamp,
                    date=row.get("date") or str(timestamp),
                    open=_parse_float(row.get("open")),
                    high=_parse_float(row.get("high")),
                    low=_parse_float(row.get("low")),
                    close=close,
                    volume=_parse_float(row.get("volume")),
                )
            )
    if not bars:
        raise MarketDataError(f"CSV file contains no usable rows: {csv_path}")
    return bars


def latest_bar(bars: Iterable[PriceBar]) -> PriceBar:
    bars_list = list(bars)
    if not bars_list:
        raise MarketDataError("missing price bars")
    return bars_list[-1]


def _value_at(values: object, index: int) -> Optional[float]:
    if not isinstance(values, list) or index >= len(values):
        return None
    return _parse_float(values[index])


def _parse_float(value: object) -> Optional[float]:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
