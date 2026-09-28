"""API 키가 없을 때 쓰는 샘플 데이터.

화면을 먼저 써볼 수 있게 하려는 것이지 실제 시세가 아니다. 저장할 때 source="sample"을
달고, 화면은 이 표시를 보고 "샘플 데이터" 띠를 띄운다. 실제 키가 들어오면 샘플 행은
지우고 실제 값으로 다시 채운다.

같은 품목·날짜에는 항상 같은 값이 나오게 품목 id로 난수 씨앗을 고정한다.
모양은 atprice.aggregate와 같다 — 뒤쪽 코드는 샘플인지 모른다.
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
    "cucumber": 9000, "zucchini": 1800, "tomato": 6000, "strawberry": 9000, "watermelon": 22000,
    "chamoe": 20000, "carrot": 5000, "onion": 3000, "green_onion": 3500, "garlic": 11000,
    "potato": 450, "sweet_potato": 6000, "green_pepper": 1500, "paprika": 1500, "minari": 1100,
    "apple": 28000, "pear": 38000, "peach": 25000, "grape": 25000, "tangerine": 4000,
    "persimmon": 8000, "kiwi": 9000, "mackerel": 4500, "hairtail": 13000, "squid": 6500,
    "pollack": 4000, "blue_crab": 30000, "oyster": 22000, "abalone": 25000,
}

ORIGIN = date(2019, 1, 1)
CHANNEL_FACTOR = {"전통시장": 0.93, "대형마트": 1.04, "SSM·슈퍼": 1.07, "백화점": 1.22, "생협·전문점": 1.12, "온라인": 0.97}
REGIONS = ["서울", "부산", "대구", "인천", "광주", "대전", "울산", "수원", "청주", "전주", "창원", "제주"]


def _rng(*parts: str) -> random.Random:
    seed = hashlib.sha256("|".join(parts).encode()).digest()
    return random.Random(int.from_bytes(seed[:8], "big"))


def _season_factor(item: Item, day: date) -> float:
    """제철이면 싸고(-), 비수기면 비싸다(+). 앞뒤 한 달의 제철 여부를 평균내 부드럽게 잇는다."""
    if not item.season_months:
        return 0.0
    window = [day + timedelta(days=offset) for offset in range(-30, 31, 3)]
    share = sum(d.month in item.season_months for d in window) / len(window)
    return 0.14 - 0.34 * share


def _round(value: float) -> int:
    step = 10 if value < 5000 else 100
    return int(round(value / step) * step)


def aggregate(item: Item, start: date, end: date) -> dict[str, dict]:
    base = BASE_PRICE.get(item.id, 5000)
    rng = _rng("price", item.id)
    # 시작일과 상관없이 같은 날짜엔 같은 값이 나오도록, 기준일부터 걸어온다.
    walk, day, result = 0.0, ORIGIN, {}
    year_level = {}
    while day <= end:
        walk = walk * 0.92 + rng.gauss(0, 0.025)
        if day.year not in year_level:
            year_level[day.year] = 1 + rng.gauss(0, 0.06)  # 해마다 작황이 다르다
        if day >= start and day.weekday() < 5:  # 조사는 평일에만 한다
            price = base * (1 + _season_factor(item, day)) * year_level[day.year] * (1 + walk)
            # 판매처별 값은 최근 것만 쓰인다. 과거 수년치까지 만들면 느리기만 하다.
            detail = _breakdown(item, day, price) if day >= end - timedelta(days=45) else {"channels": {}, "regions": {}}
            result[day.isoformat()] = {"price": _round(price), "n": 40, **detail}
        day += timedelta(days=1)
    return result


def _breakdown(item: Item, day: date, price: float) -> dict:
    rng = _rng("mix", item.id, day.isoformat())
    channels = {}
    for name, factor in CHANNEL_FACTOR.items():
        avg = price * factor * rng.uniform(0.96, 1.04)
        channels[name] = {"avg": _round(avg), "min": _round(avg * rng.uniform(0.8, 0.95)), "n": rng.randint(2, 12)}
    regions = {}
    for name in REGIONS:
        avg = price * rng.uniform(0.88, 1.12)
        regions[name] = {"avg": _round(avg), "min": _round(avg * rng.uniform(0.85, 0.97)), "n": rng.randint(1, 5)}
    return {"channels": channels, "regions": regions}
