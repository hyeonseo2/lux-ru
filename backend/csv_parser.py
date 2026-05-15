"""CSV parser for broker portfolio exports.

Handles column mapping for major Korean brokers.
"""
from __future__ import annotations

import csv
import io
from decimal import Decimal, InvalidOperation
from uuid import uuid4

from .models import AccountType, Position
from .seed_data import resolve_instrument, ALL_INSTRUMENTS


# ── Broker column mappings ────────────────────────────────────

BROKER_MAPPINGS: dict[str, dict[str, str]] = {
    "미래에셋": {
        "account": ["계좌", "계좌구분", "account"],
        "product_name": ["종목명", "상품명", "product_name", "종목"],
        "short_code": ["종목코드", "단축코드", "short_code", "코드"],
        "quantity": ["수량", "보유수량", "quantity"],
        "market_value": ["평가금액", "평가액", "market_value", "평가금"],
        "avg_price": ["평균단가", "매입단가", "avg_price"],
        "currency": ["통화", "currency", "통화코드"],
    },
    "키움": {
        "account": ["계좌", "계좌구분"],
        "product_name": ["종목명", "상품명"],
        "short_code": ["종목코드"],
        "quantity": ["잔고수량", "보유수량"],
        "market_value": ["평가금액"],
        "avg_price": ["평균매입가"],
        "currency": ["통화"],
    },
    "토스": {
        "account": ["계좌유형"],
        "product_name": ["종목명"],
        "short_code": ["종목코드"],
        "quantity": ["보유수량"],
        "market_value": ["평가금액"],
        "avg_price": ["매입단가"],
        "currency": ["통화"],
    },
    "삼성": {
        "account": ["계좌구분"],
        "product_name": ["종목명"],
        "short_code": ["종목코드"],
        "quantity": ["수량"],
        "market_value": ["평가금액"],
        "avg_price": ["매입단가"],
        "currency": ["통화"],
    },
    "NH": {
        "account": ["계좌유형"],
        "product_name": ["종목명", "상품명"],
        "short_code": ["종목코드"],
        "quantity": ["보유수량"],
        "market_value": ["평가금액"],
        "avg_price": ["평균매입가"],
        "currency": ["통화"],
    },
    "auto": {
        "account": ["account", "계좌", "계좌구분", "계좌유형"],
        "product_name": ["product_name", "종목명", "상품명", "종목"],
        "short_code": ["short_code", "종목코드", "단축코드", "코드", "ticker"],
        "quantity": ["quantity", "수량", "보유수량", "잔고수량"],
        "market_value": ["market_value", "평가금액", "평가액", "평가금"],
        "avg_price": ["avg_price", "평균단가", "매입단가", "평균매입가"],
        "currency": ["currency", "통화", "통화코드"],
        "broker": ["broker", "증권사"],
    },
}


ACCOUNT_TYPE_MAP: dict[str, AccountType] = {
    "일반계좌": AccountType.TAXABLE,
    "일반": AccountType.TAXABLE,
    "taxable": AccountType.TAXABLE,
    "isa": AccountType.ISA,
    "ISA": AccountType.ISA,
    "연금저축": AccountType.PENSION_SAVING,
    "pension": AccountType.PENSION_SAVING,
    "pension_saving": AccountType.PENSION_SAVING,
    "irp": AccountType.IRP,
    "IRP": AccountType.IRP,
    "예금": AccountType.DEPOSIT,
    "deposit": AccountType.DEPOSIT,
}


def _find_column(headers: list[str], candidates: list[str]) -> int | None:
    """Find column index matching any candidate name."""
    for i, h in enumerate(headers):
        clean = h.strip().lower()
        for c in candidates:
            if clean == c.lower():
                return i
    return None


def _parse_number(val: str) -> Decimal:
    """Parse a number string, handling Korean formatting."""
    cleaned = val.strip().replace(",", "").replace("원", "").replace("$", "")
    if not cleaned or cleaned == "-":
        return Decimal("0")
    try:
        return Decimal(cleaned)
    except InvalidOperation:
        return Decimal("0")


def parse_csv(
    content: str | bytes,
    broker: str = "auto",
) -> tuple[list[Position], list[dict], list[str]]:
    """Parse a CSV file and return positions, column mapping, and warnings.

    Returns:
        (positions, column_mapping_info, warnings)
    """
    if isinstance(content, bytes):
        # Try UTF-8, then EUC-KR
        for enc in ("utf-8-sig", "utf-8", "euc-kr", "cp949"):
            try:
                content = content.decode(enc)
                break
            except UnicodeDecodeError:
                continue
        else:
            content = content.decode("utf-8", errors="replace")

    reader = csv.reader(io.StringIO(content))
    rows = list(reader)

    if len(rows) < 2:
        return [], [], ["CSV에 데이터가 없습니다."]

    headers = [h.strip() for h in rows[0]]
    mapping = BROKER_MAPPINGS.get(broker, BROKER_MAPPINGS["auto"])

    # Find column indices
    col_account = _find_column(headers, mapping.get("account", []))
    col_product = _find_column(headers, mapping.get("product_name", []))
    col_code = _find_column(headers, mapping.get("short_code", []))
    col_qty = _find_column(headers, mapping.get("quantity", []))
    col_value = _find_column(headers, mapping.get("market_value", []))
    col_price = _find_column(headers, mapping.get("avg_price", []))
    col_ccy = _find_column(headers, mapping.get("currency", []))
    col_broker = _find_column(headers, mapping.get("broker", []))

    if col_product is None and col_code is None:
        return [], [], ["종목명 또는 종목코드 컬럼을 찾을 수 없습니다."]

    column_info = [
        {"field": "account", "mapped_to": headers[col_account] if col_account is not None else None},
        {"field": "product_name", "mapped_to": headers[col_product] if col_product is not None else None},
        {"field": "short_code", "mapped_to": headers[col_code] if col_code is not None else None},
        {"field": "quantity", "mapped_to": headers[col_qty] if col_qty is not None else None},
        {"field": "market_value", "mapped_to": headers[col_value] if col_value is not None else None},
        {"field": "currency", "mapped_to": headers[col_ccy] if col_ccy is not None else None},
    ]

    positions: list[Position] = []
    warnings: list[str] = []

    for row_idx, row in enumerate(rows[1:], start=2):
        if not row or all(c.strip() == "" for c in row):
            continue

        # Extract values
        product_name = row[col_product].strip() if col_product is not None and col_product < len(row) else ""
        short_code = row[col_code].strip() if col_code is not None and col_code < len(row) else ""
        account_str = row[col_account].strip() if col_account is not None and col_account < len(row) else "일반계좌"
        qty_str = row[col_qty] if col_qty is not None and col_qty < len(row) else "0"
        value_str = row[col_value] if col_value is not None and col_value < len(row) else "0"
        ccy = row[col_ccy].strip() if col_ccy is not None and col_ccy < len(row) else "KRW"
        broker_name = row[col_broker].strip() if col_broker is not None and col_broker < len(row) else broker

        quantity = _parse_number(qty_str)
        market_value = _parse_number(value_str)

        # If no market_value but has quantity and avg_price, compute it
        if market_value == 0 and col_price is not None and col_price < len(row):
            avg_price = _parse_number(row[col_price])
            if avg_price > 0 and quantity > 0:
                market_value = quantity * avg_price

        # Resolve instrument
        resolve_key = short_code or product_name
        instrument_id = resolve_instrument(resolve_key)

        if instrument_id is None:
            warnings.append(f"행 {row_idx}: '{resolve_key}' 매핑 실패 (데모 데이터에 없음)")
            continue

        account_type = ACCOUNT_TYPE_MAP.get(account_str, AccountType.TAXABLE)

        positions.append(Position(
            account_type=account_type,
            broker=broker_name if broker_name != "auto" else None,
            instrument_id=instrument_id,
            instrument_name=product_name or short_code,
            quantity=quantity,
            market_value=market_value,
            currency=ccy.upper() if ccy else "KRW",
        ))

    return positions, column_info, warnings
