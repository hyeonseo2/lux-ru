"""Overlap analysis based on PRD §9.

Computes pairwise overlap between ETFs using weighted Jaccard.
"""
from __future__ import annotations

from decimal import Decimal
from uuid import UUID

from .models import Overlap, Position
from .seed_data import ALL_INSTRUMENTS, ETF_HOLDINGS


def pairwise_overlap(etf_a_id: UUID, etf_b_id: UUID) -> float:
    """Compute weighted overlap between two ETFs."""
    snap_a = ETF_HOLDINGS.get(etf_a_id)
    snap_b = ETF_HOLDINGS.get(etf_b_id)
    if not snap_a or not snap_b:
        return 0.0

    weights_a = {h.holding_instrument_id: float(h.weight) for h in snap_a.holdings}
    weights_b = {h.holding_instrument_id: float(h.weight) for h in snap_b.holdings}

    common = set(weights_a.keys()) & set(weights_b.keys())
    if not common:
        return 0.0

    overlap = sum(min(weights_a[i], weights_b[i]) for i in common)
    return overlap


def find_overlaps(
    positions: list[Position],
    threshold: float = 0.05,
) -> list[Overlap]:
    """Find overlapping ETF pairs in a portfolio."""
    # Get ETF positions
    etf_positions = [p for p in positions if p.instrument_id in ETF_HOLDINGS]
    overlaps: list[Overlap] = []

    for i, pos_a in enumerate(etf_positions):
        for pos_b in etf_positions[i + 1:]:
            score = pairwise_overlap(pos_a.instrument_id, pos_b.instrument_id)
            if score < threshold:
                continue

            # Get common holding names
            snap_a = ETF_HOLDINGS[pos_a.instrument_id]
            snap_b = ETF_HOLDINGS[pos_b.instrument_id]
            ids_a = {h.holding_instrument_id for h in snap_a.holdings}
            ids_b = {h.holding_instrument_id for h in snap_b.holdings}
            common_ids = ids_a & ids_b
            common_names = []
            for cid in common_ids:
                inst = ALL_INSTRUMENTS.get(cid)
                if inst:
                    common_names.append(inst.name_ko or inst.name_en or inst.symbol)

            inst_a = ALL_INSTRUMENTS.get(pos_a.instrument_id)
            inst_b = ALL_INSTRUMENTS.get(pos_b.instrument_id)

            overlaps.append(Overlap(
                etf_a_name=inst_a.name_ko if inst_a else str(pos_a.instrument_id),
                etf_b_name=inst_b.name_ko if inst_b else str(pos_b.instrument_id),
                etf_a_id=str(pos_a.instrument_id),
                etf_b_id=str(pos_b.instrument_id),
                overlap_score=round(score, 4),
                common_holdings=sorted(common_names)[:10],
                common_count=len(common_ids),
                etf_a_value=float(pos_a.market_value),
                etf_b_value=float(pos_b.market_value),
            ))

    return sorted(overlaps, key=lambda x: x.overlap_score, reverse=True)
