"""Pydantic data models based on PRD §12.1."""
from __future__ import annotations

from datetime import date
from decimal import Decimal
from enum import Enum
from typing import Literal, Optional, Union
from uuid import UUID, uuid4

from pydantic import BaseModel, Field


# ── Enums ──────────────────────────────────────────────────────

class Coverage(str, Enum):
    FULL = "full"
    PARTIAL = "partial"
    PROXY = "proxy"


class InstrumentType(str, Enum):
    STOCK = "stock"
    ETF = "etf"
    FUND = "fund"
    BOND = "bond"
    DEPOSIT = "deposit"
    CASH = "cash"
    OTHER = "other"


class AccountType(str, Enum):
    TAXABLE = "taxable"
    ISA = "isa"
    PENSION_SAVING = "pension_saving"
    IRP = "irp"
    DEPOSIT = "deposit"
    ETC = "etc"


# ── Confidence Grade ───────────────────────────────────────────

GRADE_MAP: dict[tuple[str, Coverage], str] = {
    ("issuer_pdf", Coverage.FULL): "A",
    ("krx_pdf", Coverage.FULL): "A",
    ("issuer_csv", Coverage.FULL): "A",
    ("sec_nport", Coverage.FULL): "A",
    ("issuer_web", Coverage.PARTIAL): "B",
    ("kofia", Coverage.PARTIAL): "C",
    ("dart", Coverage.PARTIAL): "C",
    ("benchmark", Coverage.PROXY): "D",
    ("seed_data", Coverage.FULL): "A",
    ("unknown", Coverage.PROXY): "E",
}


def get_grade(source: str, coverage: Coverage) -> str:
    return GRADE_MAP.get((source, coverage), "E")


# ── Core Models ────────────────────────────────────────────────

class Instrument(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    market: str  # KRX, NYSE, NASDAQ
    symbol: str
    isin: str | None = None
    name_ko: str | None = None
    name_en: str | None = None
    instrument_type: InstrumentType
    currency: str = "KRW"
    country: str = "KR"
    sector: str | None = None
    issuer: str | None = None


class HoldingItem(BaseModel):
    holding_instrument_id: UUID
    name: str
    weight: Decimal
    currency: str = "USD"
    country: str = "US"
    sector: str | None = None


class HoldingSnapshot(BaseModel):
    product_instrument_id: UUID
    as_of_date: date
    holdings: list[HoldingItem]
    source: str = "seed_data"
    coverage: Coverage = Coverage.FULL
    confidence: Decimal = Decimal("0.95")

    @property
    def weight_sum(self) -> Decimal:
        return sum((h.weight for h in self.holdings), Decimal("0"))


class Position(BaseModel):
    account_type: AccountType = AccountType.TAXABLE
    broker: str | None = None
    instrument_id: UUID
    instrument_name: str = ""
    quantity: Decimal
    market_value: Decimal
    currency: str = "KRW"


class PathStep(BaseModel):
    type: Literal["account", "product", "unknown"]
    id: UUID
    weight: Decimal | None = None
    source: str | None = None
    coverage: Coverage | None = None


class ExposureLeaf(BaseModel):
    underlying_instrument_id: UUID
    instrument_name: str = ""
    exposure_amount: Decimal
    exposure_weight: Decimal | None = None
    path: list[PathStep] = Field(default_factory=list)
    confidence: Decimal = Field(ge=0, le=1, default=Decimal("0.95"))
    coverage_min: Coverage = Coverage.FULL
    sector: str | None = None
    country: str | None = None
    currency: str = "KRW"


class ExposureSummary(BaseModel):
    portfolio_id: str
    as_of_date: date
    base_currency: str = "KRW"
    total_market_value: Decimal
    top_holdings: list[ExposureLeaf]
    by_sector: dict[str, float]
    by_country: dict[str, float]
    by_currency: dict[str, float]
    data_grade: str = "A"
    coverage_distribution: dict[str, float] = Field(default_factory=dict)


class Overlap(BaseModel):
    etf_a_name: str
    etf_b_name: str
    etf_a_id: str
    etf_b_id: str
    overlap_score: float
    common_holdings: list[str]
    common_count: int
    etf_a_value: float = 0
    etf_b_value: float = 0


class FinLifeProduct(BaseModel):
    id: str
    company: str
    product_name: str
    product_type: str  # deposit, saving, pension
    base_rate: float
    max_rate: float
    term_months: int
    join_way: str = "인터넷,스마트폰"
    special_conditions: str = ""


class PortfolioAnalysis(BaseModel):
    """Complete analysis result."""
    exposure: ExposureSummary
    overlaps: list[Overlap]
    finlife_recommendations: list[FinLifeProduct]
    positions: list[Position]
