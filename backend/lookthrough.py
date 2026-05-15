"""Look-through engine based on PRD §6.

Recursively expands ETF/fund holdings to find actual underlying exposure.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import date
from decimal import Decimal
from uuid import UUID

from .config import MAX_DEPTH, TOLERANCE
from .fx import convert as fx_convert_dynamic
from .models import (
    Coverage, ExposureLeaf, ExposureSummary, PathStep, Position,
    HoldingSnapshot, get_grade,
)
from .sector_labels import normalize_sector, normalize_sector_for_symbol
from .seed_data import ALL_INSTRUMENTS, ETF_HOLDINGS, ETFS

UNKNOWN_EXPOSURE_ID = UUID("00000000-0000-0000-0000-000000000001")


def _worst_coverage(a: Coverage, b: Coverage) -> Coverage:
    order = {Coverage.FULL: 0, Coverage.PARTIAL: 1, Coverage.PROXY: 2}
    return a if order[a] >= order[b] else b


def fx_convert(amount: Decimal, from_ccy: str, to_ccy: str) -> Decimal:
    """FX conversion with live rate (yfinance, TTL-cached) + hardcoded fallback.

    실제 환산은 `backend.fx.convert`에 위임. 외부 호출 실패 시 자동으로
    `config.FX_KRW_USD` 값으로 폴백되므로 호출자는 항상 안전한 결과 보장.
    """
    if from_ccy == to_ccy:
        return amount
    return fx_convert_dynamic(amount, from_ccy, to_ccy)


def expand(
    instrument_id: UUID,
    amount_base: Decimal,
    base_ccy: str,
    path: list[PathStep] | None = None,
    visited: set[UUID] | None = None,
    depth: int = 0,
) -> list[ExposureLeaf]:
    """Recursively expand holdings to leaf instruments."""
    path = path or []
    visited = visited or set()

    if depth > MAX_DEPTH or instrument_id in visited:
        inst = ALL_INSTRUMENTS.get(instrument_id)
        return [ExposureLeaf(
            underlying_instrument_id=instrument_id,
            instrument_name=inst.name_ko if inst else "Unknown",
            exposure_amount=amount_base,
            path=path,
            confidence=Decimal("0.30"),
            coverage_min=Coverage.PROXY,
            sector=inst.sector if inst else None,
            country=inst.country if inst else None,
            currency=inst.currency if inst else base_ccy,
        )]

    inst = ALL_INSTRUMENTS.get(instrument_id)
    if inst is None:
        return [ExposureLeaf(
            underlying_instrument_id=instrument_id,
            instrument_name="Unknown",
            exposure_amount=amount_base,
            path=path,
            confidence=Decimal("0.40"),
            coverage_min=Coverage.PROXY,
        )]

    # Terminal: stock, bond, cash, deposit
    if inst.instrument_type in {"stock", "bond", "cash", "deposit"}:
        return [ExposureLeaf(
            underlying_instrument_id=instrument_id,
            instrument_name=inst.name_ko or inst.name_en or inst.symbol,
            exposure_amount=amount_base,
            path=path,
            confidence=Decimal("1.00"),
            coverage_min=Coverage.FULL,
            sector=inst.sector,
            country=inst.country,
            currency=inst.currency,
        )]

    # ETF/Fund: get holdings
    snap: HoldingSnapshot | None = ETF_HOLDINGS.get(instrument_id)
    if snap is None:
        return [ExposureLeaf(
            underlying_instrument_id=instrument_id,
            instrument_name=inst.name_ko or inst.name_en or inst.symbol,
            exposure_amount=amount_base,
            path=path,
            confidence=Decimal("0.40"),
            coverage_min=Coverage.PROXY,
            sector=inst.sector,
            country=inst.country,
            currency=inst.currency,
        )]

    # Validate weight sum
    weight_sum = snap.weight_sum
    tol = Decimal(str(TOLERANCE))
    confidence_cap = Decimal("0.70") if abs(weight_sum - 1) > tol else Decimal("1.00")

    new_visited = visited | {instrument_id}
    leaves: list[ExposureLeaf] = []

    for h in snap.holdings:
        child_amount = amount_base * h.weight
        # Note: amount_base is already in base_ccy from position-level conversion
        # No further FX conversion needed here as weights are ratios

        step = PathStep(
            type="product",
            id=instrument_id,
            weight=h.weight,
            source=snap.source,
            coverage=snap.coverage,
        )
        leaves.extend(expand(
            h.holding_instrument_id,
            child_amount,
            base_ccy,
            path=path + [step],
            visited=new_visited,
            depth=depth + 1,
        ))

    # Unknown remainder
    if weight_sum < (Decimal("1") - tol):
        unknown_amount = amount_base * (Decimal("1") - weight_sum)
        leaves.append(ExposureLeaf(
            underlying_instrument_id=UNKNOWN_EXPOSURE_ID,
            instrument_name="미분류/기타",
            exposure_amount=unknown_amount,
            path=path + [PathStep(type="unknown", id=instrument_id)],
            confidence=Decimal("0.20"),
            coverage_min=Coverage.PROXY,
            sector="기타",
            country="Unknown",
        ))

    # Apply confidence cap
    return [
        leaf.model_copy(update={"confidence": min(leaf.confidence, confidence_cap)})
        for leaf in leaves
    ]


def aggregate(leaves: list[ExposureLeaf]) -> dict[UUID, ExposureLeaf]:
    """Aggregate exposure by underlying instrument."""
    bucket: dict[UUID, ExposureLeaf] = {}
    for leaf in leaves:
        uid = leaf.underlying_instrument_id
        if uid not in bucket:
            bucket[uid] = leaf.model_copy()
        else:
            existing = bucket[uid]
            existing.exposure_amount += leaf.exposure_amount
            existing.confidence = min(existing.confidence, leaf.confidence)
            existing.coverage_min = _worst_coverage(existing.coverage_min, leaf.coverage_min)
    return bucket


def compute_exposure(
    positions: list[Position],
    portfolio_id: str = "demo",
    base_currency: str = "KRW",
) -> ExposureSummary:
    """Compute full look-through exposure for a list of positions."""
    all_leaves: list[ExposureLeaf] = []
    total_value = Decimal("0")

    for pos in positions:
        # Convert market_value to base currency
        mv = pos.market_value
        if pos.currency != base_currency:
            mv = fx_convert(mv, pos.currency, base_currency)
        total_value += mv

        leaves = expand(
            pos.instrument_id,
            mv,
            base_currency,
        )
        all_leaves.extend(leaves)

    # Aggregate
    agg = aggregate(all_leaves)

    # Calculate weights
    if total_value > 0:
        for leaf in agg.values():
            leaf.exposure_weight = leaf.exposure_amount / total_value

    # Sort by exposure amount descending, take top 30
    sorted_leaves = sorted(agg.values(), key=lambda x: x.exposure_amount, reverse=True)
    top_30 = sorted_leaves[:30]

    # Sector aggregation
    by_sector: dict[str, float] = defaultdict(float)
    by_country: dict[str, float] = defaultdict(float)
    by_currency: dict[str, float] = defaultdict(float)
    coverage_dist: dict[str, float] = defaultdict(float)

    for leaf in agg.values():
        w = float(leaf.exposure_weight or 0)
        # leaf의 instrument를 다시 조회해 symbol 기반 정규화 적용
        # (NVDA, 005930 같은 반도체 본업 종목을 올바르게 격상).
        leaf_inst = ALL_INSTRUMENTS.get(leaf.underlying_instrument_id)
        leaf_symbol = leaf_inst.symbol if leaf_inst else None
        sector = normalize_sector_for_symbol(leaf_symbol, leaf.sector)
        by_sector[sector] += w
        by_country[leaf.country or "Unknown"] += w
        by_currency[leaf.currency] += w
        coverage_dist[leaf.coverage_min] += w

    # Determine overall data grade based on dominant coverage
    full_weight = coverage_dist.get(Coverage.FULL, 0) + coverage_dist.get("full", 0)
    partial_weight = coverage_dist.get(Coverage.PARTIAL, 0) + coverage_dist.get("partial", 0)

    if full_weight >= 0.5:
        grade = "A"
    elif full_weight + partial_weight >= 0.5:
        grade = "B"
    else:
        grade = "C"

    return ExposureSummary(
        portfolio_id=portfolio_id,
        as_of_date=date.today(),
        base_currency=base_currency,
        total_market_value=total_value,
        top_holdings=top_30,
        by_sector=dict(by_sector),
        by_country=dict(by_country),
        by_currency=dict(by_currency),
        data_grade=grade,
        coverage_distribution=dict(coverage_dist),
    )
