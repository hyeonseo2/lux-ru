"""Portfolio API router."""
from __future__ import annotations

import time

from fastapi import APIRouter, Query
from pydantic import BaseModel
from starlette.concurrency import run_in_threadpool

from ..historical import compute_backtest, compute_benchmark_comparison, list_scenarios, map_to_yfinance
from ..income_fees import compute_income_fees
from ..instrument_insights import get_instrument_insights
from ..live_data import analyze_live_portfolio
from ..lookthrough import compute_exposure
from ..overlap import find_overlaps
from ..risk import compute_market_risk
from ..models import Position, PortfolioAnalysis
from ..seed_data import FINLIFE_PRODUCTS
from ..search_universe import search_instruments as search_universe_instruments

router = APIRouter(prefix="/api/portfolio", tags=["portfolio"])

# In-memory session storage (demo)
_sessions: dict[str, dict] = {}
_MARKET_TAPE_CACHE: tuple[float, dict] | None = None
MARKET_TAPE_TTL_SECONDS = 5 * 60
MARKET_TAPE_SYMBOLS = [
    {"symbol": "GOOGL", "name": "Alphabet"},
    {"symbol": "AMZN", "name": "Amazon"},
    {"symbol": "META", "name": "Meta"},
    {"symbol": "005930", "name": "삼성전자"},
    {"symbol": "NVDA", "name": "NVIDIA"},
    {"symbol": "AAPL", "name": "Apple"},
    {"symbol": "000660", "name": "SK하이닉스"},
    {"symbol": "TSLA", "name": "Tesla"},
    {"symbol": "373220", "name": "LG에너지솔루션"},
    {"symbol": "035720", "name": "카카오"},
]


class AnalyzeRequest(BaseModel):
    session_id: str
    positions: list[dict]


class AnalyzeResponse(BaseModel):
    success: bool
    message: str
    data: dict | None = None


def _series_close_values(df, yf_symbol: str, symbol_count: int) -> list[float]:
    """Extract non-null close values from a yfinance DataFrame for one symbol."""
    try:
        is_multi = getattr(df.columns, "nlevels", 1) > 1
        if is_multi:
            close = df[yf_symbol]["Close"]
        elif symbol_count == 1 and "Close" in df.columns:
            close = df["Close"]
        else:
            return []
        close = close.dropna()
        return [float(v) for v in close.tolist() if float(v) > 0]
    except Exception:
        return []


def _load_market_tape() -> dict:
    """Return recent daily percentage changes for the top ticker tape."""
    global _MARKET_TAPE_CACHE
    now = time.time()
    if _MARKET_TAPE_CACHE and _MARKET_TAPE_CACHE[0] > now:
        return _MARKET_TAPE_CACHE[1]

    symbols: list[str] = []
    symbol_meta: dict[str, dict] = {}
    for item in MARKET_TAPE_SYMBOLS:
        yf_symbol = map_to_yfinance(item["symbol"]) or item["symbol"]
        symbols.append(yf_symbol)
        symbol_meta[yf_symbol] = item

    items: list[dict] = []
    try:
        import yfinance as yf

        df = yf.download(
            symbols,
            period="10d",
            interval="1d",
            auto_adjust=True,
            group_by="ticker",
            progress=False,
            threads=True,
            timeout=10,
        )
    except Exception as exc:
        result = {"success": False, "message": f"market data unavailable: {exc}", "items": []}
        _MARKET_TAPE_CACHE = (now + 60, result)
        return result

    if df is None or getattr(df, "empty", True):
        result = {"success": False, "message": "empty market data", "items": []}
        _MARKET_TAPE_CACHE = (now + 60, result)
        return result

    for yf_symbol in symbols:
        closes = _series_close_values(df, yf_symbol, len(symbols))
        if len(closes) < 2:
            continue
        prev, last = closes[-2], closes[-1]
        if prev <= 0:
            continue
        change_pct = (last / prev - 1.0) * 100
        meta = symbol_meta[yf_symbol]
        items.append({
            "symbol": meta["symbol"],
            "yf_symbol": yf_symbol,
            "name": meta["name"],
            "change_pct": change_pct,
            "direction": "up" if change_pct >= 0 else "down",
            "price": last,
            "source": "yfinance",
        })

    result = {
        "success": bool(items),
        "message": "ok" if items else "no valid market data",
        "as_of": int(now),
        "items": items,
    }
    _MARKET_TAPE_CACHE = (now + MARKET_TAPE_TTL_SECONDS, result)
    return result


def _to_search_payload(query: str, limit: int = 20) -> dict:
    query = query or ""
    hits = search_universe_instruments(query, limit=limit)
    return {
        "query": query,
        "results": [
            {
                "symbol": item["symbol"],
                "name": item["name"],
                "name_ko": item.get("name_ko", ""),
                "name_en": item.get("name_en", ""),
                "symbol_type": item.get("symbol_type", "stock"),
                "market": item.get("market", ""),
                "score": item.get("score", 5),
            }
            for item in hits
        ],
    }


def _get_session(session_id: str) -> dict:
    if session_id not in _sessions:
        _sessions[session_id] = {
            "positions": [],
            "analysis": None,
        }
    return _sessions[session_id]


@router.post("/analyze")
async def analyze_portfolio(req: AnalyzeRequest) -> dict:
    """Run full X-Ray analysis on positions."""
    from decimal import Decimal
    from uuid import UUID

    session = _get_session(req.session_id)

    # Convert dict positions to Position objects
    positions = []
    for p in req.positions:
        positions.append(Position(
            account_type=p.get("account_type", "taxable"),
            broker=p.get("broker"),
            instrument_id=UUID(p["instrument_id"]),
            instrument_name=p.get("instrument_name", ""),
            quantity=Decimal(str(p.get("quantity", 0))),
            market_value=Decimal(str(p.get("market_value", 0))),
            currency=p.get("currency", "KRW"),
        ))

    # Compute exposure
    exposure = compute_exposure(positions)

    # Find overlaps
    overlaps = find_overlaps(positions)

    # FinLife recommendations (based on cash exposure)
    cash_weight = exposure.by_sector.get("Cash", 0)
    finlife_recs = []
    if cash_weight > 0.03:
        finlife_recs = [p for p in FINLIFE_PRODUCTS if p.product_type == "deposit"][:3]
    elif any(p.account_type == "pension_saving" for p in positions):
        finlife_recs = [p for p in FINLIFE_PRODUCTS if p.product_type == "pension"][:2]

    # Build analysis result
    analysis = PortfolioAnalysis(
        exposure=exposure,
        overlaps=overlaps,
        finlife_recommendations=finlife_recs,
        positions=positions,
    )

    # Store in session
    analysis_dict = analysis.model_dump(mode="json")
    session["positions"] = [p.model_dump(mode="json") for p in positions]
    session["analysis"] = analysis_dict

    return {
        "success": True,
        "message": "분석 완료",
        "data": analysis_dict,
    }


@router.get("/analysis/{session_id}")
async def get_analysis(session_id: str) -> dict:
    """Get latest analysis result."""
    session = _get_session(session_id)
    if session["analysis"] is None:
        return {"success": False, "message": "분석 결과가 없습니다. 먼저 CSV를 업로드해주세요."}
    return {"success": True, "data": session["analysis"]}


@router.get("/sessions/{session_id}")
async def get_session_info(session_id: str) -> dict:
    """Get session info."""
    session = _get_session(session_id)
    return {
        "session_id": session_id,
        "has_positions": len(session["positions"]) > 0,
        "has_analysis": session["analysis"] is not None,
        "position_count": len(session["positions"]),
    }


@router.get("/search-instruments")
async def search_instruments_api(q: str = "", limit: int = 12) -> dict:
    """Return symbols and instrument names matching query for UI autocomplete."""
    limit = max(1, min(limit, 30))
    return _to_search_payload(q, limit=limit)


@router.get("/market-tape")
async def market_tape() -> dict:
    """Return live-ish daily market moves for the landing ticker tape."""
    return await run_in_threadpool(_load_market_tape)


# ---- Live (사용자 직접 입력) 분석 ----
class LiveRequest(BaseModel):
    positions: list[dict]  # [{"ticker": "SPY", "amount": 10000000, "account_type": "taxable"}]
    source_mode: str = "seed_fast"


@router.post("/analyze_real")
async def analyze_real_portfolio(req: LiveRequest) -> dict:
    """Analyze a user-input portfolio (ticker + amount)."""
    return analyze_live_portfolio(req.positions, source_mode=req.source_mode)


class BacktestRequest(BaseModel):
    positions: list[dict]
    scenario_id: str


class BenchmarkCompareRequest(BaseModel):
    positions: list[dict]
    period_days: int = 365


class IncomeFeesRequest(BaseModel):
    positions: list[dict]


class RiskMetricsRequest(BaseModel):
    exposures: list[dict]
    total_value: float | None = None
    gross_value: float | None = None
    hhi: float | None = None
    leverage_ratio: float | None = None
    period_days: int = 365


@router.get("/backtest/scenarios")
async def get_backtest_scenarios() -> dict:
    """List available historical event scenarios for backtesting."""
    return {"scenarios": list_scenarios()}


@router.post("/backtest")
async def run_backtest(req: BacktestRequest) -> dict:
    """Backtest positions against a historical market event.

    Uses real yfinance daily close prices for the scenario's date range,
    falling back to KOSPI bond proxy for fixed-income placeholders.
    """
    return compute_backtest(req.positions, req.scenario_id)


@router.post("/benchmark-compare")
async def compare_benchmarks(req: BenchmarkCompareRequest) -> dict:
    """Compare portfolio cumulative return with benchmark indices."""
    return await run_in_threadpool(compute_benchmark_comparison, req.positions, req.period_days)


@router.post("/income-fees")
async def income_fees(req: IncomeFeesRequest) -> dict:
    """Return live dividend and fee lookups for portfolio positions."""
    return await run_in_threadpool(compute_income_fees, req.positions)


@router.post("/risk-metrics")
async def risk_metrics(req: RiskMetricsRequest) -> dict:
    """Return volatility and beta from real historical daily prices."""
    return await run_in_threadpool(
        compute_market_risk,
        req.exposures,
        req.total_value,
        req.gross_value,
        req.hhi,
        req.leverage_ratio,
        req.period_days,
    )


@router.get("/instrument-insights")
async def instrument_insights_api(
    ticker: str = Query(default="", description="Stock ticker/symbol"),
    days: int = Query(default=30, ge=7, le=90),
    news_limit: int = Query(default=3, ge=1, le=80),
) -> dict:
    """Return recent event/news insights for a selected stock node."""
    return await run_in_threadpool(
        get_instrument_insights,
        ticker=ticker,
        days=days,
        news_limit=news_limit,
    )


class ScreenerRequest(BaseModel):
    sectors: list[str] | None = None
    countries: list[str] | None = None
    instrument_types: list[str] | None = None
    pe_min: float | None = None
    pe_max: float | None = None
    mcap_min: float | None = None
    mcap_max: float | None = None
    sort_by: str = "market_cap"
    sort_desc: bool = True
    query: str = ""
    limit: int = 80


@router.post("/screener")
async def run_screener(req: ScreenerRequest) -> dict:
    """Screen and rank universe of instruments based on filters and real-time metrics."""
    from ..screener import screen_instruments
    results = await run_in_threadpool(
        screen_instruments,
        sectors=req.sectors,
        countries=req.countries,
        instrument_types=req.instrument_types,
        pe_min=req.pe_min,
        pe_max=req.pe_max,
        mcap_min=req.mcap_min,
        mcap_max=req.mcap_max,
        sort_by=req.sort_by,
        sort_desc=req.sort_desc,
        query=req.query,
        limit=req.limit,
    )
    return {"success": True, "results": results}
