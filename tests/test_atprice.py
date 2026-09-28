from datetime import date

from app.atprice import aggregate, channel_of, keep_rows
from app.catalog import AtCode
from app.prices import normal_price

CODE = AtCode(category="400", item="411", varieties=("05", "07"), grades=("04",), unit="개", unit_size="10")


def _row(day="20260923", vrty="05", grd="04", price="20000", sgg="1101", sgg_nm="서울", mrkt="A-대형마트",
         unit="개", unit_sz="10"):
    return {"exmn_ymd": day, "vrty_cd": vrty, "grd_cd": grd, "exmn_dd_prc": price, "sgg_cd": sgg,
            "sgg_nm": sgg_nm, "mrkt_nm": mrkt, "unit": unit, "unit_sz": unit_sz}


def test_channel_of():
    assert channel_of(_row(mrkt="경동")) == "전통시장"
    assert channel_of(_row(mrkt="A-대형마트")) == "대형마트"
    assert channel_of(_row(mrkt="F-유통")) == "대형마트"
    assert channel_of(_row(mrkt="A-SSM")) == "SSM·슈퍼"
    assert channel_of(_row(mrkt="B-백화점")) == "백화점"
    assert channel_of(_row(mrkt="C-생협")) == "생협·전문점"
    assert channel_of(_row(mrkt="온라인몰A", sgg="9998")) == "온라인"
    assert channel_of(_row(mrkt="가락도매")) is None


def test_keep_rows_filters_variety_grade_unit_and_bad_prices():
    rows = [
        _row(),
        _row(vrty="01"),            # 허용 품종 아님
        _row(grd="05"),             # 중품
        _row(unit_sz="5"),          # 단위가 다르다
        _row(price="-"),            # 가격 없음
        _row(price="0"),
    ]
    assert len(keep_rows(rows, CODE)) == 1


def test_aggregate_uses_dominant_variety_and_excludes_online_from_average():
    rows = [
        _row(price="20000", mrkt="경동"),
        _row(price="22000", mrkt="A-대형마트", sgg="2100", sgg_nm="부산"),
        _row(price="10000", mrkt="온라인몰A", sgg="9998", sgg_nm="온라인"),
        _row(vrty="07", price="90000"),   # 소수 품종 — 버린다
    ]
    day = aggregate(rows)["2026-09-23"]
    assert day["price"] == 21000
    assert day["n"] == 2
    assert day["channels"]["온라인"] == {"avg": 10000, "min": 10000, "n": 1}
    assert set(day["regions"]) == {"서울", "부산"}


def _flat(prices_by_year: dict[int, int], month=9, day=23):
    """해마다 같은 날짜 앞뒤로 같은 가격을 채운다."""
    result = {}
    for year, price in prices_by_year.items():
        for offset in range(-3, 4):
            result[date(year, month, day + offset).isoformat()] = price
    return result


def test_normal_price_drops_max_and_min_of_five_years():
    prices = _flat({2021: 100, 2022: 200, 2023: 300, 2024: 400, 2025: 10_000})
    assert normal_price(prices, date(2026, 9, 23)) == 300  # 200·300·400 평균


def test_normal_price_needs_three_years():
    assert normal_price(_flat({2024: 100, 2025: 200}), date(2026, 9, 23)) is None
    assert normal_price(_flat({2023: 100, 2024: 200, 2025: 300}), date(2026, 9, 23)) == 200
