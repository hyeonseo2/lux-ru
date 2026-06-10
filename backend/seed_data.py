"""Seed data for demo: ETF holdings, instruments, and FinLife products.

Contains realistic top holdings for major Korean and US ETFs.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal
from uuid import UUID, uuid5, NAMESPACE_DNS

from .models import (
    Instrument, InstrumentType, HoldingSnapshot, HoldingItem,
    Coverage, FinLifeProduct,
)

# ── Deterministic UUID generator ──────────────────────────────

def _id(name: str) -> UUID:
    return uuid5(NAMESPACE_DNS, f"pxray.{name}")


# ── Instruments (stocks) ──────────────────────────────────────

STOCKS: dict[UUID, Instrument] = {}

# sector 필드는 yfinance Ticker(symbol).info["sector"]가 실제로 반환하는
# 어휘를 따른다 ("Technology", "Financial Services", "Healthcare",
# "Consumer Cyclical", "Consumer Defensive", "Basic Materials" 등).
# 그래야 yfinance 실시간 응답과 시드 fallback이 동일한 입력으로 정규화되어
# 동일한 한국어 라벨을 산출한다.
_stock_data = [
    ("AAPL", "Apple Inc", "애플", "NASDAQ", "USD", "US", "Technology"),
    ("MSFT", "Microsoft Corp", "마이크로소프트", "NASDAQ", "USD", "US", "Technology"),
    ("NVDA", "NVIDIA Corp", "엔비디아", "NASDAQ", "USD", "US", "Technology"),
    ("AMZN", "Amazon.com Inc", "아마존", "NASDAQ", "USD", "US", "Consumer Cyclical"),
    ("GOOGL", "Alphabet Inc", "알파벳", "NASDAQ", "USD", "US", "Communication Services"),
    ("META", "Meta Platforms", "메타", "NASDAQ", "USD", "US", "Communication Services"),
    ("TSLA", "Tesla Inc", "테슬라", "NASDAQ", "USD", "US", "Consumer Cyclical"),
    ("BRK.B", "Berkshire Hathaway", "버크셔해서웨이", "NYSE", "USD", "US", "Financial Services"),
    ("AVGO", "Broadcom Inc", "브로드컴", "NASDAQ", "USD", "US", "Technology"),
    ("JPM", "JPMorgan Chase", "JP모간", "NYSE", "USD", "US", "Financial Services"),
    ("LLY", "Eli Lilly", "일라이릴리", "NYSE", "USD", "US", "Healthcare"),
    ("V", "Visa Inc", "비자", "NYSE", "USD", "US", "Financial Services"),
    ("UNH", "UnitedHealth", "유나이티드헬스", "NYSE", "USD", "US", "Healthcare"),
    ("MA", "Mastercard", "마스터카드", "NYSE", "USD", "US", "Financial Services"),
    ("XOM", "Exxon Mobil", "엑슨모빌", "NYSE", "USD", "US", "Energy"),
    ("HD", "Home Depot", "홈디포", "NYSE", "USD", "US", "Consumer Cyclical"),
    ("PG", "Procter & Gamble", "P&G", "NYSE", "USD", "US", "Consumer Defensive"),
    ("COST", "Costco", "코스트코", "NASDAQ", "USD", "US", "Consumer Defensive"),
    ("JNJ", "Johnson & Johnson", "존슨앤존슨", "NYSE", "USD", "US", "Healthcare"),
    ("ABBV", "AbbVie Inc", "애브비", "NYSE", "USD", "US", "Healthcare"),
    ("CRM", "Salesforce", "세일즈포스", "NYSE", "USD", "US", "Technology"),
    ("NFLX", "Netflix Inc", "넷플릭스", "NASDAQ", "USD", "US", "Communication Services"),
    ("AMD", "AMD Inc", "AMD", "NASDAQ", "USD", "US", "Technology"),
    ("ADBE", "Adobe Inc", "어도비", "NASDAQ", "USD", "US", "Technology"),
    ("WMT", "Walmart Inc", "월마트", "NYSE", "USD", "US", "Consumer Defensive"),
    ("PEP", "PepsiCo Inc", "펩시코", "NASDAQ", "USD", "US", "Consumer Defensive"),
    ("KO", "Coca-Cola", "코카콜라", "NYSE", "USD", "US", "Consumer Defensive"),
    ("MRK", "Merck & Co", "머크", "NYSE", "USD", "US", "Healthcare"),
    ("CSCO", "Cisco Systems", "시스코", "NASDAQ", "USD", "US", "Technology"),
    ("ACN", "Accenture", "액센츄어", "NYSE", "USD", "US", "Technology"),
    ("TMO", "Thermo Fisher", "써모피셔", "NYSE", "USD", "US", "Healthcare"),
    ("ORCL", "Oracle Corp", "오라클", "NYSE", "USD", "US", "Technology"),
    ("BAC", "Bank of America", "뱅크오브아메리카", "NYSE", "USD", "US", "Financial Services"),
    ("CVX", "Chevron Corp", "셰브론", "NYSE", "USD", "US", "Energy"),
    ("INTC", "Intel Corp", "인텔", "NASDAQ", "USD", "US", "Technology"),
    ("QCOM", "Qualcomm", "퀄컴", "NASDAQ", "USD", "US", "Technology"),
    ("VZ", "Verizon", "버라이즌", "NYSE", "USD", "US", "Communication Services"),
    ("T", "AT&T Inc", "AT&T", "NYSE", "USD", "US", "Communication Services"),
    ("PFE", "Pfizer Inc", "화이자", "NYSE", "USD", "US", "Healthcare"),
    ("CMCSA", "Comcast Corp", "컴캐스트", "NASDAQ", "USD", "US", "Communication Services"),
    # Korean stocks — yfinance도 동일하게 영문 yfinance 어휘를 사용
    ("005930", "Samsung Electronics", "삼성전자", "KRX", "KRW", "KR", "Technology"),
    ("000660", "SK Hynix", "SK하이닉스", "KRX", "KRW", "KR", "Technology"),
    ("373220", "LG에너지솔루션", "LG에너지솔루션", "KRX", "KRW", "KR", "Industrials"),
    ("005380", "Hyundai Motor", "현대자동차", "KRX", "KRW", "KR", "Consumer Cyclical"),
    ("035420", "NAVER Corp", "네이버", "KRX", "KRW", "KR", "Communication Services"),
    ("000270", "Kia Corp", "기아", "KRX", "KRW", "KR", "Consumer Cyclical"),
    ("068270", "Celltrion", "셀트리온", "KRX", "KRW", "KR", "Healthcare"),
    ("035720", "Kakao Corp", "카카오", "KRX", "KRW", "KR", "Communication Services"),
    ("105560", "KB Financial", "KB금융", "KRX", "KRW", "KR", "Financial Services"),
    ("055550", "Shinhan Financial", "신한지주", "KRX", "KRW", "KR", "Financial Services"),
    ("006400", "Samsung SDI", "삼성SDI", "KRX", "KRW", "KR", "Technology"),
    ("003670", "POSCO Holdings", "포스코홀딩스", "KRX", "KRW", "KR", "Basic Materials"),
    ("051910", "LG Chem", "LG화학", "KRX", "KRW", "KR", "Basic Materials"),
    ("005940", "NH Investment & Securities", "NH투자증권", "KRX", "KRW", "KR", "Financial Services"),
    ("086520", "Ecopro", "에코프로", "KOSDAQ", "KRW", "KR", "Basic Materials"),
    ("247540", "Ecopro BM", "에코프로비엠", "KOSDAQ", "KRW", "KR", "Industrials"),
    ("028260", "Samsung C&T", "삼성물산", "KRX", "KRW", "KR", "Industrials"),
    ("012330", "Hyundai Mobis", "현대모비스", "KRX", "KRW", "KR", "Consumer Cyclical"),
    ("042700", "Hanmi Semiconductor", "한미반도체", "KRX", "KRW", "KR", "Technology"),
    ("058470", "Leeno Industrial", "리노공업", "KOSDAQ", "KRW", "KR", "Technology"),
    ("000990", "DB HiTek", "DB하이텍", "KRX", "KRW", "KR", "Technology"),
    ("095340", "ISC", "ISC", "KOSDAQ", "KRW", "KR", "Technology"),
    ("403870", "HPSP", "HPSP", "KOSDAQ", "KRW", "KR", "Technology"),
    ("357780", "Soulbrain", "솔브레인", "KOSDAQ", "KRW", "KR", "Technology"),
    ("240810", "Wonik IPS", "원익IPS", "KOSDAQ", "KRW", "KR", "Technology"),
    ("005290", "Dongjin Semichem", "동진쎄미켐", "KOSDAQ", "KRW", "KR", "Technology"),
    ("108320", "LX Semicon", "LX세미콘", "KRX", "KRW", "KR", "Technology"),
    ("039030", "EO Technics", "이오테크닉스", "KOSDAQ", "KRW", "KR", "Technology"),
    ("036930", "Jusung Engineering", "주성엔지니어링", "KOSDAQ", "KRW", "KR", "Technology"),
    # Bond proxy — yfinance에는 없는 분류이지만 시드 전용. 기본 매핑은 "기타".
    ("BOND_KR", "Korea Treasury Bond", "한국 국채", "KRX", "KRW", "KR", "Fixed Income"),
    ("BOND_US", "US Treasury Bond", "미국 국채", "NYSE", "USD", "US", "Fixed Income"),
    ("CASH_KRW", "Cash KRW", "현금(원화)", "KRX", "KRW", "KR", "Cash"),
    ("CASH_USD", "Cash USD", "현금(달러)", "NYSE", "USD", "US", "Cash"),
]

for sym, name_en, name_ko, market, ccy, country, sector in _stock_data:
    _type = InstrumentType.STOCK
    if "Bond" in name_en or "Treasury" in name_en:
        _type = InstrumentType.BOND
    elif "Cash" in name_en:
        _type = InstrumentType.CASH
    inst = Instrument(
        id=_id(f"stock.{sym}"),
        market=market,
        symbol=sym,
        name_en=name_en,
        name_ko=name_ko,
        instrument_type=_type,
        currency=ccy,
        country=country,
        sector=sector,
    )
    STOCKS[inst.id] = inst


# ── ETF Instruments ───────────────────────────────────────────

ETFS: dict[UUID, Instrument] = {}

_etf_data = [
    ("360750", "TIGER 미국S&P500", "TIGER US S&P500", "KRX", "KRW", "KR", "미래에셋자산운용"),
    ("133690", "TIGER 미국나스닥100", "TIGER US NASDAQ100", "KRX", "KRW", "KR", "미래에셋자산운용"),
    ("069500", "KODEX 200", "KODEX 200", "KRX", "KRW", "KR", "삼성자산운용"),
    ("091160", "KODEX 반도체", "KODEX Semiconductor", "KRX", "KRW", "KR", "삼성자산운용"),
    ("379800", "KODEX 미국S&P500TR", "KODEX US S&P500TR", "KRX", "KRW", "KR", "삼성자산운용"),
    ("273130", "KODEX 종합채권(AA-이상)액티브", "KODEX Active Bond", "KRX", "KRW", "KR", "삼성자산운용"),
    ("SPY", "SPDR S&P 500 ETF Trust", "SPY", "NYSE", "USD", "US", "State Street"),
    ("QQQ", "Invesco QQQ Trust", "QQQ", "NASDAQ", "USD", "US", "Invesco"),
    ("VOO", "Vanguard S&P 500 ETF", "VOO", "NYSE", "USD", "US", "Vanguard"),
    ("SCHD", "Schwab US Dividend Equity", "SCHD", "NYSE", "USD", "US", "Schwab"),
]

for sym, name_ko, name_en, market, ccy, country, issuer in _etf_data:
    etf = Instrument(
        id=_id(f"etf.{sym}"),
        market=market,
        symbol=sym,
        name_ko=name_ko,
        name_en=name_en,
        instrument_type=InstrumentType.ETF,
        currency=ccy,
        country=country,
        issuer=issuer,
    )
    ETFS[etf.id] = etf

ALL_INSTRUMENTS: dict[UUID, Instrument] = {**STOCKS, **ETFS}


# ── Helpers ───────────────────────────────────────────────────

def _h(sym: str, weight: float, sector: str | None = None,
       country: str = "US", currency: str = "USD") -> HoldingItem:
    stock = STOCKS.get(_id(f"stock.{sym}"))
    return HoldingItem(
        holding_instrument_id=_id(f"stock.{sym}"),
        name=stock.name_ko if stock else sym,
        weight=Decimal(str(weight)),
        currency=currency,
        country=country,
        sector=sector or (stock.sector if stock else "Other"),
    )


# ── ETF Holdings ──────────────────────────────────────────────

ETF_HOLDINGS: dict[UUID, HoldingSnapshot] = {}

# TIGER 미국S&P500 (360750) — S&P 500 tracker
_sp500_top = [
    ("AAPL", 0.0720), ("MSFT", 0.0680), ("NVDA", 0.0650), ("AMZN", 0.0380),
    ("GOOGL", 0.0240), ("META", 0.0260), ("TSLA", 0.0190), ("BRK.B", 0.0175),
    ("AVGO", 0.0200), ("JPM", 0.0135), ("LLY", 0.0150), ("V", 0.0105),
    ("UNH", 0.0115), ("MA", 0.0095), ("XOM", 0.0120), ("HD", 0.0095),
    ("PG", 0.0100), ("COST", 0.0090), ("JNJ", 0.0085), ("ABBV", 0.0080),
    ("CRM", 0.0075), ("NFLX", 0.0075), ("AMD", 0.0065), ("ADBE", 0.0060),
    ("WMT", 0.0070), ("PEP", 0.0055), ("KO", 0.0055), ("MRK", 0.0060),
    ("CSCO", 0.0050), ("ACN", 0.0045),
]
_sp500_sum = sum(w for _, w in _sp500_top)
ETF_HOLDINGS[_id("etf.360750")] = HoldingSnapshot(
    product_instrument_id=_id("etf.360750"),
    as_of_date=date(2026, 5, 8),
    holdings=[_h(s, w / _sp500_sum) for s, w in _sp500_top],
    source="seed_data", coverage=Coverage.FULL, confidence=Decimal("0.95"),
)

# TIGER 미국나스닥100 (133690)
_ndx_top = [
    ("AAPL", 0.0880), ("MSFT", 0.0810), ("NVDA", 0.0780), ("AMZN", 0.0530),
    ("GOOGL", 0.0310), ("META", 0.0370), ("TSLA", 0.0290), ("AVGO", 0.0270),
    ("COST", 0.0150), ("NFLX", 0.0130), ("AMD", 0.0120), ("ADBE", 0.0110),
    ("CSCO", 0.0095), ("QCOM", 0.0090), ("INTC", 0.0060), ("CMCSA", 0.0055),
    ("PEP", 0.0080), ("CRM", 0.0100), ("ORCL", 0.0085), ("ACN", 0.0035),
]
_ndx_sum = sum(w for _, w in _ndx_top)
ETF_HOLDINGS[_id("etf.133690")] = HoldingSnapshot(
    product_instrument_id=_id("etf.133690"),
    as_of_date=date(2026, 5, 8),
    holdings=[_h(s, w / _ndx_sum) for s, w in _ndx_top],
    source="seed_data", coverage=Coverage.FULL, confidence=Decimal("0.95"),
)

# KODEX 200 (069500) — KOSPI 200 tracker
_kospi200_top = [
    ("005930", 0.2900, "Technology", "KR", "KRW"),
    ("000660", 0.0700, "Technology", "KR", "KRW"),
    ("373220", 0.0450, "Industrials", "KR", "KRW"),
    ("005380", 0.0350, "Consumer Cyclical", "KR", "KRW"),
    ("035420", 0.0280, "Communication Services", "KR", "KRW"),
    ("000270", 0.0260, "Consumer Cyclical", "KR", "KRW"),
    ("068270", 0.0240, "Healthcare", "KR", "KRW"),
    ("035720", 0.0180, "Communication Services", "KR", "KRW"),
    ("105560", 0.0170, "Financial Services", "KR", "KRW"),
    ("055550", 0.0150, "Financial Services", "KR", "KRW"),
    ("006400", 0.0140, "Technology", "KR", "KRW"),
    ("003670", 0.0130, "Basic Materials", "KR", "KRW"),
    ("051910", 0.0120, "Basic Materials", "KR", "KRW"),
    ("028260", 0.0100, "Industrials", "KR", "KRW"),
    ("012330", 0.0090, "Consumer Cyclical", "KR", "KRW"),
]
_kospi200_sum = sum(w for _, w, _, _, _ in _kospi200_top)
ETF_HOLDINGS[_id("etf.069500")] = HoldingSnapshot(
    product_instrument_id=_id("etf.069500"),
    as_of_date=date(2026, 5, 8),
    holdings=[
        _h(s, w / _kospi200_sum, sec, ctry, ccy)
        for s, w, sec, ctry, ccy in _kospi200_top
    ],
    source="seed_data", coverage=Coverage.FULL, confidence=Decimal("0.95"),
)

# KODEX 반도체 (091160) — KRX PDF 실패 시 사용하는 fallback.
_kodex_semiconductor_top = [
    ("005930", 0.2800, "Technology", "KR", "KRW"),
    ("000660", 0.2300, "Technology", "KR", "KRW"),
    ("042700", 0.1200, "Technology", "KR", "KRW"),
    ("058470", 0.0600, "Technology", "KR", "KRW"),
    ("000990", 0.0500, "Technology", "KR", "KRW"),
    ("095340", 0.0500, "Technology", "KR", "KRW"),
    ("403870", 0.0400, "Technology", "KR", "KRW"),
    ("357780", 0.0400, "Technology", "KR", "KRW"),
    ("240810", 0.0300, "Technology", "KR", "KRW"),
    ("005290", 0.0300, "Technology", "KR", "KRW"),
    ("108320", 0.0300, "Technology", "KR", "KRW"),
    ("039030", 0.0200, "Technology", "KR", "KRW"),
    ("036930", 0.0200, "Technology", "KR", "KRW"),
]
_kodex_semiconductor_sum = sum(w for _, w, _, _, _ in _kodex_semiconductor_top)
ETF_HOLDINGS[_id("etf.091160")] = HoldingSnapshot(
    product_instrument_id=_id("etf.091160"),
    as_of_date=date(2026, 5, 8),
    holdings=[
        _h(s, w / _kodex_semiconductor_sum, sec, ctry, ccy)
        for s, w, sec, ctry, ccy in _kodex_semiconductor_top
    ],
    source="seed_data", coverage=Coverage.PARTIAL, confidence=Decimal("0.85"),
)

# KODEX 미국S&P500TR (379800) — same as SP500 tracker
ETF_HOLDINGS[_id("etf.379800")] = HoldingSnapshot(
    product_instrument_id=_id("etf.379800"),
    as_of_date=date(2026, 5, 8),
    holdings=[_h(s, w / _sp500_sum) for s, w in _sp500_top],
    source="seed_data", coverage=Coverage.FULL, confidence=Decimal("0.95"),
)

# KODEX 종합채권 (273130)
ETF_HOLDINGS[_id("etf.273130")] = HoldingSnapshot(
    product_instrument_id=_id("etf.273130"),
    as_of_date=date(2026, 5, 8),
    holdings=[
        HoldingItem(holding_instrument_id=_id("stock.BOND_KR"),
                    name="한국 국채", weight=Decimal("0.95"),
                    currency="KRW", country="KR", sector="Fixed Income"),
        HoldingItem(holding_instrument_id=_id("stock.CASH_KRW"),
                    name="현금(원화)", weight=Decimal("0.05"),
                    currency="KRW", country="KR", sector="Cash"),
    ],
    source="seed_data", coverage=Coverage.PARTIAL, confidence=Decimal("0.80"),
)

# SPY — same top as S&P500
ETF_HOLDINGS[_id("etf.SPY")] = HoldingSnapshot(
    product_instrument_id=_id("etf.SPY"),
    as_of_date=date(2026, 5, 8),
    holdings=[_h(s, w / _sp500_sum) for s, w in _sp500_top],
    source="issuer_csv", coverage=Coverage.FULL, confidence=Decimal("0.98"),
)

# QQQ — same as NDX100
ETF_HOLDINGS[_id("etf.QQQ")] = HoldingSnapshot(
    product_instrument_id=_id("etf.QQQ"),
    as_of_date=date(2026, 5, 8),
    holdings=[_h(s, w / _ndx_sum) for s, w in _ndx_top],
    source="issuer_csv", coverage=Coverage.FULL, confidence=Decimal("0.98"),
)

# VOO — same top as S&P500
ETF_HOLDINGS[_id("etf.VOO")] = HoldingSnapshot(
    product_instrument_id=_id("etf.VOO"),
    as_of_date=date(2026, 5, 8),
    holdings=[_h(s, w / _sp500_sum) for s, w in _sp500_top],
    source="issuer_csv", coverage=Coverage.FULL, confidence=Decimal("0.98"),
)

# SCHD — Schwab dividend ETF
_schd_top = [
    ("ABBV", 0.0450), ("HD", 0.0430), ("PEP", 0.0410), ("KO", 0.0400),
    ("CSCO", 0.0380), ("AVGO", 0.0370), ("MRK", 0.0360), ("PFE", 0.0340),
    ("XOM", 0.0320), ("CVX", 0.0310), ("VZ", 0.0300), ("JPM", 0.0290),
    ("PG", 0.0280), ("JNJ", 0.0270), ("BAC", 0.0260), ("T", 0.0240),
    ("INTC", 0.0230), ("V", 0.0220), ("UNH", 0.0210), ("WMT", 0.0200),
]
_schd_sum = sum(w for _, w in _schd_top)
ETF_HOLDINGS[_id("etf.SCHD")] = HoldingSnapshot(
    product_instrument_id=_id("etf.SCHD"),
    as_of_date=date(2026, 5, 8),
    holdings=[_h(s, w / _schd_sum) for s, w in _schd_top],
    source="issuer_csv", coverage=Coverage.FULL, confidence=Decimal("0.98"),
)

# ── Symbol lookup ─────────────────────────────────────────────

SYMBOL_TO_ETF: dict[str, UUID] = {}
for uid, etf in ETFS.items():
    SYMBOL_TO_ETF[etf.symbol] = uid
    if etf.name_ko:
        SYMBOL_TO_ETF[etf.name_ko] = uid
    if etf.name_en:
        SYMBOL_TO_ETF[etf.name_en] = uid

# Short aliases
SYMBOL_TO_ETF["TIGER미국S&P500"] = _id("etf.360750")
SYMBOL_TO_ETF["TIGER미국나스닥100"] = _id("etf.133690")
SYMBOL_TO_ETF["KODEX200"] = _id("etf.069500")
SYMBOL_TO_ETF["KODEX 200"] = _id("etf.069500")
SYMBOL_TO_ETF["KOSPI200"] = _id("etf.069500")
SYMBOL_TO_ETF["KODEX반도체"] = _id("etf.091160")
SYMBOL_TO_ETF["KODEX 반도체"] = _id("etf.091160")
SYMBOL_TO_ETF["KODEX미국S&P500TR"] = _id("etf.379800")
SYMBOL_TO_ETF["KODEX종합채권"] = _id("etf.273130")
SYMBOL_TO_ETF["KODEX종합채권액티브"] = _id("etf.273130")

# Instrument lookup (ETF + stock)
SYMBOL_TO_INSTRUMENT: dict[str, UUID] = {}


def _register_symbol(key: str | None, uid: UUID) -> None:
    if not key:
        return
    clean = key.strip()
    if not clean:
        return
    SYMBOL_TO_INSTRUMENT[clean] = uid

    # ASCII symbol convenience (e.g. spy, qqq, aapl)
    if clean.isascii():
        SYMBOL_TO_INSTRUMENT[clean.upper()] = uid


for uid, inst in ALL_INSTRUMENTS.items():
    _register_symbol(inst.symbol, uid)
    _register_symbol(inst.name_ko, uid)
    _register_symbol(inst.name_en, uid)

# Keep Korean short aliases
for alias, uid in SYMBOL_TO_ETF.items():
    _register_symbol(alias, uid)


def resolve_instrument(name_or_symbol: str) -> UUID | None:
    """Resolve a product name or symbol to its UUID."""
    clean = name_or_symbol.strip()

    # Direct symbol/name match
    if clean in SYMBOL_TO_INSTRUMENT:
        return SYMBOL_TO_INSTRUMENT[clean]
    if clean.upper() in SYMBOL_TO_INSTRUMENT:
        return SYMBOL_TO_INSTRUMENT[clean.upper()]

    # Fuzzy match (substring, normalized spaces)
    clean_lower = clean.lower().replace(" ", "")
    for key, uid in SYMBOL_TO_INSTRUMENT.items():
        if clean_lower in key.lower().replace(" ", ""):
            return uid

    return None


# ── FinLife Seed Products ─────────────────────────────────────

FINLIFE_PRODUCTS: list[FinLifeProduct] = [
    FinLifeProduct(
        id="FL001", company="KB국민은행", product_name="KB Star 정기예금",
        product_type="deposit", base_rate=3.45, max_rate=3.70,
        term_months=12, join_way="인터넷,스마트폰,영업점",
        special_conditions="급여이체 시 우대금리 +0.1%p",
    ),
    FinLifeProduct(
        id="FL002", company="신한은행", product_name="신한 SOL 정기예금",
        product_type="deposit", base_rate=3.50, max_rate=3.75,
        term_months=12, join_way="스마트폰",
        special_conditions="모바일 가입 우대 +0.05%p",
    ),
    FinLifeProduct(
        id="FL003", company="하나은행", product_name="하나 원큐 정기예금",
        product_type="deposit", base_rate=3.40, max_rate=3.65,
        term_months=12, join_way="인터넷,스마트폰",
    ),
    FinLifeProduct(
        id="FL004", company="우리은행", product_name="우리 Super 정기예금",
        product_type="deposit", base_rate=3.35, max_rate=3.60,
        term_months=12, join_way="인터넷,스마트폰,영업점",
    ),
    FinLifeProduct(
        id="FL005", company="토스뱅크", product_name="토스뱅크 정기예금",
        product_type="deposit", base_rate=3.60, max_rate=3.80,
        term_months=12, join_way="스마트폰",
        special_conditions="비대면 전용",
    ),
    FinLifeProduct(
        id="FL006", company="카카오뱅크", product_name="카카오뱅크 정기예금",
        product_type="deposit", base_rate=3.55, max_rate=3.70,
        term_months=12, join_way="스마트폰",
        special_conditions="비대면 전용",
    ),
    FinLifeProduct(
        id="FL007", company="KB국민은행", product_name="KB 적금 플러스",
        product_type="saving", base_rate=3.80, max_rate=4.50,
        term_months=12, join_way="스마트폰",
        special_conditions="매월 납입, 카드 실적 우대",
    ),
    FinLifeProduct(
        id="FL008", company="미래에셋증권", product_name="미래에셋 연금저축펀드",
        product_type="pension", base_rate=0.0, max_rate=0.0,
        term_months=0, join_way="인터넷,스마트폰",
        special_conditions="연간 세액공제 한도 600만원",
    ),
    FinLifeProduct(
        id="FL009", company="삼성증권", product_name="삼성 연금저축 ETF",
        product_type="pension", base_rate=0.0, max_rate=0.0,
        term_months=0, join_way="인터넷,스마트폰",
        special_conditions="ETF 직접 투자 가능",
    ),
    FinLifeProduct(
        id="FL010", company="신한은행", product_name="신한 급여 자유적금",
        product_type="saving", base_rate=4.00, max_rate=5.00,
        term_months=6, join_way="스마트폰",
        special_conditions="급여이체 필수, 월 자유납입",
    ),
]
