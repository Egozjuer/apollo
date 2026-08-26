"""Three-market snapshot for 07709 / SK hynix / SKHY."""

from __future__ import annotations

import json
import re
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any, Dict, Optional
from zoneinfo import ZoneInfo

from tools.quant_07709.market_data import MarketDataError, YahooFinanceClient


HK_TZ = ZoneInfo("Asia/Hong_Kong")
KR_TZ = ZoneInfo("Asia/Seoul")
US_ET = ZoneInfo("America/New_York")

CSOP_NAV_URL = "https://website-api.csopasset.com/cmsApi/NAV/product"
CSOP_PRODUCT_NAMES = (
    "CSOP SK Hynix Daily Max (2x) Leveraged Product",
    "CSOP SK Hynix Daily (2x) Leveraged Product",
)
TENCENT_QUOTES = {
    "hk7709": "hk07709",
    "hk7709_realtime": "r_hk07709",
    "kr_hynix": "kr000660",
    "us_skhy": "usSKHY",
}
DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/javascript, */*; q=0.8",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
}


@dataclass
class Quote:
    symbol: str
    name: str
    price: float
    previous_close: Optional[float]
    change: Optional[float]
    change_pct: Optional[float]
    open: Optional[float] = None
    high: Optional[float] = None
    low: Optional[float] = None
    volume: Optional[float] = None
    as_of: Optional[str] = None
    currency: str = ""
    source: str = ""
    session: Optional[str] = None
    extra: Optional[Dict[str, Any]] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class OfficialNav:
    value: float
    currency: str
    as_of: str
    change_pct: Optional[float]
    source: str
    product_name: str

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class SnapshotError(RuntimeError):
    """Raised when a required snapshot input cannot be loaded."""


def http_get(url: str, headers: Optional[Dict[str, str]] = None, timeout: float = 12.0) -> bytes:
    merged = dict(DEFAULT_HEADERS)
    if headers:
        merged.update(headers)
    request = urllib.request.Request(url, headers=merged)
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.read()


def http_post_json(url: str, payload: Dict[str, Any], timeout: float = 12.0) -> Any:
    data = json.dumps(payload).encode("utf-8")
    headers = dict(DEFAULT_HEADERS)
    headers.update(
        {
            "Content-Type": "application/json",
            "Origin": "https://www.csopasset.com",
            "Referer": "https://www.csopasset.com/tc/products/hk-skhy-2l",
        }
    )
    request = urllib.request.Request(url, data=data, headers=headers)
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def _parse_float(value: object) -> Optional[float]:
    if value is None or value == "":
        return None
    if isinstance(value, str):
        value = value.replace(",", "").replace("%", "").strip()
        if value in {"", "--", "None", "nan"}:
            return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def parse_tencent_quote(raw: str, fallback_symbol: str) -> Quote:
    """Parse a Tencent `qt.gtimg.cn` quote string."""

    match = re.search(r'="(.*)"', raw, re.S)
    if not match:
        raise MarketDataError(f"invalid Tencent quote: {raw[:80]}")
    payload = match.group(1)
    if payload in {"1", ""} or "pv_none_match" in raw:
        raise MarketDataError(f"Tencent returned no match for {fallback_symbol}")
    fields = payload.split("~")
    if len(fields) < 6:
        raise MarketDataError(f"Tencent quote too short for {fallback_symbol}")

    symbol = fields[2] or fallback_symbol
    name = fields[1] or fallback_symbol
    price = _parse_float(fields[3])
    previous = _parse_float(fields[4])
    if price is None:
        raise MarketDataError(f"Tencent quote missing price for {fallback_symbol}")

    change = None
    change_pct = None
    as_of = None
    extra: Dict[str, Any] = {}
    for field in fields:
        if re.match(r"\d{4}[-/]\d{2}[-/]\d{2}", field):
            as_of = field.replace("/", "-")
            break

    if symbol.startswith("07709") or fallback_symbol.startswith("hk07709") or "7709" in symbol:
        change = _parse_float(fields[31]) if len(fields) > 31 else None
        change_pct = _parse_float(fields[32]) if len(fields) > 32 else None
        currency = "HKD"
        session = "港股收市" if as_of and "16:" in as_of else "港股报价"
    elif "000660" in symbol or fallback_symbol.startswith("kr"):
        # Korean Tencent quotes put absolute change and percent at 31/32.
        change = _parse_float(fields[31]) if len(fields) > 31 else None
        change_pct = _parse_float(fields[32]) if len(fields) > 32 else None
        currency = "KRW"
        session = classify_korea_session(as_of)
        extra["reference_close"] = previous
    elif "SKHY" in symbol.upper() or fallback_symbol.upper().endswith("SKHY"):
        change = _parse_float(fields[31]) if len(fields) > 31 else None
        change_pct = _parse_float(fields[32]) if len(fields) > 32 else None
        currency = "USD"
        session = "美股常规交易" if as_of and "16:00" in as_of else "美股报价"
        for field in fields:
            if re.match(r"\d+:\d+$", field):
                extra["adr_ratio_text"] = field
                break
    else:
        currency = ""
        session = None

    computed_change = None if previous is None else price - previous
    computed_pct = None if previous in (None, 0) else computed_change / previous * 100.0
    if change is None:
        change = computed_change
    if change_pct is None or abs(change_pct) > 80:
        change_pct = computed_pct
    if computed_pct is not None and change_pct is not None and abs(change_pct - computed_pct) > 5:
        change = computed_change
        change_pct = computed_pct

    return Quote(
        symbol=symbol,
        name=name,
        price=price,
        previous_close=previous,
        change=change,
        change_pct=change_pct,
        open=_parse_float(fields[5]) if len(fields) > 5 else None,
        volume=_parse_float(fields[6]) if len(fields) > 6 else None,
        as_of=as_of,
        currency=currency,
        source="Tencent qt.gtimg.cn",
        session=session,
        extra=extra or None,
    )


def classify_korea_session(as_of: Optional[str]) -> str:
    if not as_of:
        return "韩国报价"
    try:
        stamp = datetime.strptime(as_of[:19], "%Y-%m-%d %H:%M:%S").replace(tzinfo=KR_TZ)
    except ValueError:
        return "韩国报价"
    minutes = stamp.hour * 60 + stamp.minute
    if 9 * 60 <= minutes <= 15 * 60 + 30:
        return "Regular Session"
    return "After-hours"


def fetch_tencent_quote(code: str) -> Quote:
    raw = http_get(f"https://qt.gtimg.cn/q={code}").decode("gb18030", errors="replace")
    return parse_tencent_quote(raw, code)


def fetch_yahoo_quote(symbol: str, currency: str, source_label: str) -> Quote:
    client = YahooFinanceClient()
    bars = client.fetch_history(symbol, range_="5d", interval="1d")
    latest = bars[-1]
    previous = bars[-2].close if len(bars) > 1 else None
    change = None if previous is None else latest.close - previous
    change_pct = None if previous in (None, 0) else change / previous * 100.0
    return Quote(
        symbol=symbol,
        name=symbol,
        price=latest.close,
        previous_close=previous,
        change=change,
        change_pct=change_pct,
        as_of=latest.date,
        currency=currency,
        source=source_label,
        session="Yahoo日线/延迟",
    )


def fetch_quote_with_fallback(tencent_code: str, yahoo_symbol: str, currency: str) -> Quote:
    try:
        return fetch_tencent_quote(tencent_code)
    except (MarketDataError, urllib.error.URLError, TimeoutError, UnicodeError) as exc:
        quote = fetch_yahoo_quote(yahoo_symbol, currency, "Yahoo Finance fallback")
        quote.extra = {"fallback_reason": str(exc)}
        return quote


def fetch_official_nav() -> OfficialNav:
    last_error: Optional[BaseException] = None
    for name in CSOP_PRODUCT_NAMES:
        try:
            payload = http_post_json(CSOP_NAV_URL, {"productName": name})
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
            last_error = exc
            continue
        if not isinstance(payload, list):
            continue
        hkd_rows = [row for row in payload if isinstance(row, dict) and row.get("Currency") == "HKD"]
        if not hkd_rows:
            continue
        row = hkd_rows[0]
        value = _parse_float(row.get("NAV"))
        if value is None:
            continue
        change_pct = _parse_float(str(row.get("NAVChange") or "").replace("%", ""))
        return OfficialNav(
            value=value,
            currency="HKD",
            as_of=str(row.get("HstDateFormat") or row.get("HstDate") or ""),
            change_pct=change_pct,
            source="CSOP website-api.csopasset.com",
            product_name=name,
        )
    raise SnapshotError(f"failed to load CSOP official NAV: {last_error}")


def fetch_fx_usdkrw() -> Quote:
    return fetch_yahoo_quote("KRW=X", "KRW", "Yahoo Finance KRW=X")


def pct_change(new: Optional[float], old: Optional[float]) -> Optional[float]:
    if new is None or old in (None, 0):
        return None
    return (new / old - 1.0) * 100.0


def theoretical_nav(official_nav: float, korea_return_pct: Optional[float], leverage: float = 2.0) -> Optional[float]:
    if korea_return_pct is None:
        return None
    return official_nav * (1.0 + leverage * korea_return_pct / 100.0)


def theoretical_adr_usd(korea_price: float, usdkrw: float, adr_ratio: float = 10.0) -> Optional[float]:
    if usdkrw <= 0 or adr_ratio <= 0:
        return None
    return korea_price / adr_ratio / usdkrw


def build_snapshot(leverage: float = 2.0, adr_ratio: float = 10.0) -> Dict[str, Any]:
    warnings = [
        "本看板只做三市场估值对照，不构成投资建议，也不自动下单。",
        "07709 是每日杠杆产品，官方目标杠杆可能低于 2 倍；理论 NAV 默认按 2 倍估算。",
        "当前环境没有通达信 MCP。行情优先用腾讯行情，官方净值用 CSOP API；失败时才会降级到 Yahoo，并会标明来源。",
    ]
    errors: Dict[str, str] = {}

    hk = _safe_fetch(errors, "hk7709", lambda: fetch_quote_with_fallback("hk07709", "7709.HK", "HKD"))
    kr = _safe_fetch(errors, "kr_hynix", lambda: fetch_quote_with_fallback("kr000660", "000660.KS", "KRW"))
    us = _safe_fetch(errors, "us_skhy", lambda: fetch_quote_with_fallback("usSKHY", "SKHY", "USD"))
    fx = _safe_fetch(errors, "usdkrw", fetch_fx_usdkrw)
    nav = _safe_fetch(errors, "csop_nav", fetch_official_nav)

    korea_return_pct = None if kr is None else kr.change_pct
    theory_nav = None if nav is None else theoretical_nav(nav.value, korea_return_pct, leverage)
    theory_adr = None
    if kr is not None and fx is not None:
        theory_adr = theoretical_adr_usd(kr.price, fx.price, adr_ratio)

    official_premium_pct = None
    if hk is not None and nav is not None:
        official_premium_pct = pct_change(hk.price, nav.value)
    theory_gap_pct = None
    if hk is not None and theory_nav is not None:
        theory_gap_pct = pct_change(hk.price, theory_nav)
    adr_premium_pct = None
    if us is not None and theory_adr is not None:
        adr_premium_pct = pct_change(us.price, theory_adr)

    generated_at = datetime.now(HK_TZ).strftime("%Y/%m/%d %H:%M:%S")
    return {
        "generated_at": generated_at,
        "timezone": "HKT",
        "leverage_assumption": leverage,
        "adr_ratio": adr_ratio,
        "quotes": {
            "hk7709": None if hk is None else hk.to_dict(),
            "kr_hynix": None if kr is None else kr.to_dict(),
            "us_skhy": None if us is None else us.to_dict(),
            "usdkrw": None if fx is None else fx.to_dict(),
        },
        "official_nav": None if nav is None else nav.to_dict(),
        "derived": {
            "official_premium_pct": official_premium_pct,
            "theoretical_nav": theory_nav,
            "theoretical_nav_gap_pct": theory_gap_pct,
            "theoretical_adr_usd": theory_adr,
            "adr_official_premium_pct": adr_premium_pct,
            "korea_return_pct": korea_return_pct,
        },
        "errors": errors,
        "warnings": warnings,
        "data_policy": {
            "preferred": ["Tencent qt.gtimg.cn", "CSOP official NAV API"],
            "fallback": ["Yahoo Finance"],
            "missing": ["Tongdaxin MCP"],
            "silent_web_scrape": False,
        },
    }


def _safe_fetch(errors: Dict[str, str], key: str, loader):
    try:
        return loader()
    except Exception as exc:  # noqa: BLE001 - surface any data-source failure in the UI
        errors[key] = str(exc)
        return None


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()
