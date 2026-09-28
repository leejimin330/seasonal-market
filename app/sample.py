"""API 키가 없을 때 쓰는 샘플 데이터.

화면을 먼저 써볼 수 있게 하려는 것이지 실제 시세가 아니다. 저장할 때 source="sample"을
달고, 화면은 이 표시를 보고 "샘플 데이터" 띠를 띄운다. 실제 키가 들어오면 샘플 행은
지우고 KAMIS 값으로 다시 채운다.

같은 품목·날짜에는 항상 같은 값이 나오게 품목 id로 난수 씨앗을 고정한다.
"""

from __future__ import annotations

import hashlib
import math
import random
from datetime import date, timedelta

from app.catalog import Item

# 단위당 대략의 기준가. 그럴듯한 숫자를 만들기 위한 것일 뿐이다.
BASE_PRICE = {
    "cabbage": 4500, "radish": 2500, "cabbage_head": 4000, "spinach": 1200, "lettuce": 1300,
    "cucumber": 9000, "zucchini": 1800, "tomato": 6000, "strawberry": 2200, "watermelon": 22000,
    "chamoe": 20000, "carrot": 5000, "onion": 3000, "green_onion": 3500, "garlic": 11000,
    "potato": 450, "sweet_potato": 6000, "green_pepper": 1500, "paprika": 2200, "minari": 1100,
    "apple": 28000, "pear": 38000, "peach": 25000, "grape": 15000, "tangerine": 4000,
    "persimmon": 17000, "kiwi": 9000, "mackerel": 4500, "hairtail": 13000, "squid": 6500,
    "pollack": 4000, "blue_crab": 30000, "oyster": 22000, "abalone": 60000, "shrimp": 38000,
}


def _rng(*parts: str) -> random.Random:
    seed = hashlib.sha256("|".join(parts).encode()).digest()
    return random.Random(int.from_bytes(seed[:8], "big"))


def _season_factor(item: Item, day: date) -> float:
    """제철이면 싸고(-), 비수기면 비싸다(+). 월 경계에서 튀지 않게 부드럽게 잇는다."""
    if not item.season_months:
        return 0.0
    # 앞뒤 한 달의 제철 여부를 평균낸다. 꽃게처럼 제철이 두 번인 품목도 두 번 싸진다.
    window = [day + timedelta(days=offset) for offset in range(-30, 31, 3)]
    share = sum(d.month in item.season_months for d in window) / len(window)
    return 0.14 - 0.34 * share


def price_rows(item: Item, start: date, end: date) -> list[tuple]:
    base = BASE_PRICE.get(item.id, 5000)
    rng = _rng("price", item.id)
    # 시작일과 상관없이 같은 날짜엔 같은 값이 나오도록, 기준일부터 걸어온다.
    origin = date(2025, 1, 1)
    walk = 0.0
    rows = []
    day = origin
    while day <= end:
        walk = walk * 0.92 + rng.gauss(0, 0.025)
        if day >= start:
            factor = _season_factor(item, day)
            normal = base * (1 + factor)
            price = normal * (1 + walk + 0.04 * math.sin(day.toordinal() / 9))
            rows.append((item.id, day.isoformat(), _round(price), _round(normal), "sample"))
        day += timedelta(days=1)
    return rows


def _round(value: float) -> int:
    step = 10 if value < 5000 else 100
    return int(round(value / step) * step)


MALLS = ["샘플몰 가", "샘플몰 나", "샘플몰 다", "샘플마켓", "샘플농장 직송", "샘플수산"]


def shop_items(item: Item) -> list[dict]:
    """네이버 쇼핑 응답과 같은 모양의 가짜 상품 목록. 실제 파서를 그대로 통과시킨다."""
    rng = _rng("shop", item.id)
    base = BASE_PRICE.get(item.id, 5000)
    items = []
    for n in range(14):
        if item.shop_unit == "g":
            grams = rng.choice([500, 1000, 1500, 2000, 3000, 5000])
            label = f"{grams // 1000}kg" if grams % 1000 == 0 else f"{grams}g"
            per_kg = base * (1000 / _unit_grams(item.price_unit)) if _unit_grams(item.price_unit) else base
            price = per_kg * grams / 1000 * rng.uniform(0.75, 1.35)
        else:
            count = rng.choice([1, 1, 2, 3, 5])
            label = f"{count}{item.shop_label.lstrip('1')}"
            price = base / _unit_count(item.price_unit) * count * rng.uniform(0.8, 1.4)
        items.append(
            {
                "title": f"[샘플] 국산 {item.name} {label}",
                "link": "",
                "lprice": str(_round(price)),
                "mallName": MALLS[n % len(MALLS)],
                "category1": "식품",
            }
        )
    return items


def _unit_grams(unit: str) -> int | None:
    if unit.endswith("kg"):
        return int(float(unit[:-2]) * 1000)
    if unit.endswith("g"):
        return int(unit[:-1])
    return None


def _unit_count(unit: str) -> int:
    digits = "".join(ch for ch in unit if ch.isdigit())
    return int(digits) if digits else 1
