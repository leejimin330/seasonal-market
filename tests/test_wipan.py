from datetime import date, timedelta

from app.db import Database
from app.wipan import FishQueries, aggregate_day


def _row(name="쥐치", code="620101", state="선어", amount=100_000, weight=10, market="삼천포 위판장",
         coop="삼천포수협", region="경상남도"):
    return {"mprcStdCodeNm": name, "mprcStdCode": code, "kdfshSttusNm": state, "csmtAmount": str(amount),
            "csmtWt": str(weight), "csmtmktNm": market, "mxtrNm": coop, "orgplceSeNm": region}


def test_aggregate_day_weights_by_kg_and_splits_state():
    groups = aggregate_day([
        _row(amount=100_000, weight=10),                       # 1만 원/kg
        _row(amount=60_000, weight=2, market="통영 위판장"),    # 3만 원/kg
        _row(state="활어", amount=90_000, weight=3),
        _row(name="기타해면어류", amount=1, weight=1),          # 기타는 뺀다
        _row(name="(활)기타", amount=50_000, weight=5),
        _row(amount=0, weight=5),                              # 금액 없음
    ])
    by_state = {g["state"]: g for g in groups}
    assert set(by_state) == {"선어", "활어"}
    fresh = by_state["선어"]
    assert (fresh["amount"], fresh["weight"], fresh["markets"]) == (160_000, 12, 2)
    assert (fresh["min_kg"], fresh["max_kg"]) == (10_000, 30_000)
    assert fresh["regions"] == {"경상남도": [160_000, 12]}


def _db_with_two_weeks():
    db = Database(":memory:")
    end = date(2026, 9, 23)
    for k in range(14):
        day = end - timedelta(days=k)
        price = 10_000 if k >= 7 else 12_000  # 이번 주가 20% 비싸다
        db.put_fish_day(day.isoformat(), aggregate_day([
            _row(amount=price * 10, weight=10),
            _row(name="물메기", code="600999", amount=1_000, weight=1),  # 한 주 7kg — 목록 기준(5kg) 넘음
            _row(name="달고기", code="600888", amount=50_000, weight=0.5) if k == 0 else _row(amount=0),
        ]), 3, 0)
    return db


def test_species_compares_week_over_week_and_hides_tiny_volume():
    data = FishQueries(_db_with_two_weeks()).species()
    assert data["latest"] == "2026-09-23"
    names = {s["name"]: s for s in data["species"]}
    assert names["쥐치"]["kg"] == 12_000 and names["쥐치"]["change"] == 20.0
    assert "물메기" in names
    assert "달고기" not in names  # 0.5kg — 가격이 튄다


def test_detail_series_and_markets():
    detail = FishQueries(_db_with_two_weeks()).detail("620101")
    assert detail["name"] == "쥐치" and detail["state"] == "선어"
    assert len(detail["series"]) == 14 and detail["series"][-1]["price"] == 12_000
    assert detail["regions"][0]["name"] == "경상남도"
    assert FishQueries(Database(":memory:")).detail("nope") is None


def test_province_of_normalizes_short_and_renamed_names():
    from app.wipan import province_of

    assert province_of("경북 포항시") == "경상북도"
    assert province_of("경상남도") == "경상남도"
    assert province_of("강원특별자치도") == "강원도"
    assert province_of("전북특별자치도") == "전라북도"
    assert province_of("원양") == "원양"


def test_aggregate_day_drops_outlier_trades():
    rows = [_row(amount=20_000 * 3, weight=3) for _ in range(5)]
    rows.append(_row(amount=4_000 * 10, weight=10, market="이상한 위판장"))  # 중앙값의 1/5
    rows.append(_row(amount=60_000 * 3, weight=3, market="비싼 위판장"))     # 3배 — 남긴다
    (group,) = aggregate_day(rows)
    assert group["min_kg"] == 20_000 and group["max_kg"] == 60_000
    assert "이상한 위판장 (삼천포수협)" not in group["market_prices"]
