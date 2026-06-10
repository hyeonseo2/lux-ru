"""Generate a mock brokerage portfolio screenshot for testing /api/upload/screenshot.

가상의 보유종목 화면을 PNG로 만들어 `static/assets/sample-screenshot.png`에 저장한다.
실제 증권사 UI가 아니라 테스트 전용 더미 디자인.
"""
from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

FONT_REG = "/usr/share/fonts/truetype/nanum/NanumSquareR.ttf"
FONT_BOLD = "/usr/share/fonts/truetype/nanum/NanumSquareB.ttf"

OUT = Path(__file__).resolve().parent.parent / "static" / "assets" / "sample-screenshot.png"

# (계좌 라벨, 종목명, 종목코드/티커, 평가금액 KRW, 변동률 %)
HOLDINGS = [
    ("주식계좌",   "삼성전자",          "005930", 12_400_000,  +1.82),
    ("주식계좌",   "SK하이닉스",        "000660",  4_350_000,  -0.45),
    ("주식계좌",   "KODEX 반도체",       "091160",  8_120_000,  +0.61),
    ("연금저축",   "QQQ",               "QQQ",     6_780_000,  +2.14),
    ("연금저축",   "SCHD",              "SCHD",    3_900_000,  +0.07),
    ("ISA",        "KODEX 종합채권",    "273130",  2_100_000,  -0.12),
    ("주식계좌",   "엔비디아",          "NVDA",   11_900_000,  +3.45),
]

W, H = 720, 1080
BG = (248, 250, 252)
CARD = (255, 255, 255)
BORDER = (226, 232, 240)
PRIMARY = (49, 130, 246)
TEXT = (30, 41, 59)
MUTED = (100, 116, 139)
UP = (220, 38, 38)      # 한국 관습: 상승=빨강
DOWN = (37, 99, 235)    # 하락=파랑


def load(path: str, size: int):
    return ImageFont.truetype(path, size)


def fmt_krw(v: int) -> str:
    return f"{v:,}원"


def fmt_pct(v: float) -> str:
    sign = "+" if v >= 0 else ""
    return f"{sign}{v:.2f}%"


def main() -> None:
    img = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(img)

    f_title = load(FONT_BOLD, 30)
    f_sub = load(FONT_REG, 16)
    f_acc_hdr = load(FONT_BOLD, 18)
    f_name = load(FONT_BOLD, 19)
    f_code = load(FONT_REG, 14)
    f_amt = load(FONT_BOLD, 20)
    f_pct = load(FONT_BOLD, 14)
    f_total_label = load(FONT_REG, 14)
    f_total_val = load(FONT_BOLD, 28)

    # ── App header
    d.rectangle([(0, 0), (W, 70)], fill=PRIMARY)
    d.text((24, 18), "● MyBroker", font=f_title, fill=(255, 255, 255))
    d.text((24, 50), "내 보유종목 (테스트용 더미 화면)", font=f_sub, fill=(219, 234, 254))

    # ── Total summary card
    total = sum(h[3] for h in HOLDINGS)
    card_y = 92
    d.rounded_rectangle([(20, card_y), (W - 20, card_y + 110)], radius=12, fill=CARD, outline=BORDER, width=1)
    d.text((36, card_y + 18), "총 평가금액", font=f_total_label, fill=MUTED)
    d.text((36, card_y + 38), fmt_krw(total), font=f_total_val, fill=TEXT)
    d.text((36, card_y + 80), f"{len(HOLDINGS)}개 종목 · 3개 계좌", font=f_sub, fill=MUTED)

    # ── Holdings grouped by account
    by_account: dict[str, list] = {}
    for h in HOLDINGS:
        by_account.setdefault(h[0], []).append(h)

    y = card_y + 130
    for account_label, items in by_account.items():
        # account header
        d.text((24, y), f"📁 {account_label}", font=f_acc_hdr, fill=TEXT)
        y += 34

        for (_, name, code, amount, pct) in items:
            card_h = 86
            d.rounded_rectangle([(20, y), (W - 20, y + card_h)], radius=10, fill=CARD, outline=BORDER, width=1)

            d.text((34, y + 14), name, font=f_name, fill=TEXT)
            d.text((34, y + 42), code, font=f_code, fill=MUTED)

            amt_text = fmt_krw(amount)
            amt_w = d.textlength(amt_text, font=f_amt)
            d.text((W - 36 - amt_w, y + 16), amt_text, font=f_amt, fill=TEXT)

            pct_text = fmt_pct(pct)
            pct_color = UP if pct >= 0 else DOWN
            pct_w = d.textlength(pct_text, font=f_pct)
            d.text((W - 36 - pct_w, y + 50), pct_text, font=f_pct, fill=pct_color)

            y += card_h + 10
        y += 12

    # ── Footer
    d.text(
        (24, H - 30),
        "※ 본 화면은 LUX-RU 스크린샷 파싱 기능 테스트용 더미 데이터입니다.",
        font=load(FONT_REG, 12),
        fill=MUTED,
    )

    OUT.parent.mkdir(parents=True, exist_ok=True)
    img.save(OUT, "PNG", optimize=True)
    print(f"saved: {OUT} ({OUT.stat().st_size:,} bytes)")


if __name__ == "__main__":
    main()
