"""Portfolio API router."""
from __future__ import annotations

from fastapi import APIRouter, Query
from pydantic import BaseModel

from ..historical import compute_backtest, compute_benchmark_comparison, list_scenarios
from ..instrument_insights import get_instrument_insights
from ..live_data import analyze_live_portfolio
from ..lookthrough import compute_exposure
from ..overlap import find_overlaps
from ..models import Position, PortfolioAnalysis
from ..seed_data import FINLIFE_PRODUCTS, ALL_INSTRUMENTS

router = APIRouter(prefix="/api/portfolio", tags=["portfolio"])

# In-memory session storage (demo)
_sessions: dict[str, dict] = {}


class AnalyzeRequest(BaseModel):
    session_id: str
    positions: list[dict]


class AnalyzeResponse(BaseModel):
    success: bool
    message: str
    data: dict | None = None


def _normalize_search_query(raw: str) -> str:
    return str(raw or "").strip().lower()


def _instrument_name_for_search(inst):
    candidates = []
    if inst.name_ko:
        candidates.append(str(inst.name_ko).strip())
    if inst.name_en:
        candidates.append(str(inst.name_en).strip())
    if inst.symbol:
        candidates.append(str(inst.symbol).strip())
    if inst.market:
        candidates.append(str(inst.market).strip())
    return candidates


def _score_symbol_match(query: str, symbol: str, display_name: str) -> int:
    if not query:
        return 99
    q = query.strip().lower()
    s = symbol.strip().lower()
    d = display_name.strip().lower()

    if s == q:
        return 0
    if s.startswith(q):
        return 1
    if q in s:
        return 2
    if d:
        if d.startswith(q):
            return 3
        if q in d:
            return 4
    return 5


def _search_instruments(query: str, limit: int = 20) -> list[dict]:
    q = _normalize_search_query(query)
    if not q:
        return []

    results: list[dict] = []
    for inst in ALL_INSTRUMENTS.values():
        symbol = str(inst.symbol or "").strip()
        if not symbol:
            continue
        name_candidates = _instrument_name_for_search(inst)
        merged_name = " ".join([x for x in name_candidates if x]).strip()

        if q in symbol.lower() or any(q in (x.lower()) for x in [x for x in name_candidates if x]):
            score = _score_symbol_match(q, symbol, merged_name)
            item = {
                "symbol": symbol,
                "name": merged_name or symbol,
                "name_ko": inst.name_ko or "",
                "name_en": inst.name_en or "",
                "type": (inst.instrument_type.value if getattr(inst, "instrument_type", None) else "instrument"),
                "market": inst.market,
                "score": score,
            }
            results.append(item)

    results.sort(key=lambda x: (x["score"], len(x["symbol"]), x["name"].lower()))
    return results[: max(1, limit)]


def _to_search_payload(query: str, limit: int = 20) -> dict:
    query = query or ""
    hits = _search_instruments(query, limit=limit)
    return {
        "query": query,
        "results": [
            {
                "symbol": item["symbol"],
                "name": item["name"],
                "name_ko": item.get("name_ko", ""),
                "name_en": item.get("name_en", ""),
                "symbol_type": item["type"],
                "market": item["market"],
                "score": item["score"],
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


# ---- Live (사용자 직접 입력) 분석 ----
class LiveRequest(BaseModel):
    positions: list[dict]  # [{"ticker": "SPY", "amount": 10000000, "account_type": "taxable"}]


@router.post("/analyze_real")
async def analyze_real_portfolio(req: LiveRequest) -> dict:
    """Analyze a user-input portfolio (ticker + amount)."""
    return analyze_live_portfolio(req.positions)


class BacktestRequest(BaseModel):
    positions: list[dict]
    scenario_id: str


class BenchmarkCompareRequest(BaseModel):
    positions: list[dict]
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
    return compute_benchmark_comparison(req.positions, req.period_days)


@router.get("/instrument-insights")
async def instrument_insights_api(
    ticker: str = Query(default="", description="Stock ticker/symbol"),
    days: int = Query(default=30, ge=7, le=90),
    news_limit: int = Query(default=30, ge=10, le=80),
) -> dict:
    """Return recent event/news insights for a selected stock node."""
    return get_instrument_insights(ticker=ticker, days=days, news_limit=news_limit)
