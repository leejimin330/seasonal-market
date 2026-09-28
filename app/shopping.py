"""네이버 쇼핑 검색으로 판매처별 최저가를 찾는다.

상품명이 제각각이라("활꽃게 2kg", "딸기 500g x 2팩", "고등어 1손") 그대로 가격순으로
정렬하면 비교가 안 된다. 상품명에서 양을 읽어 기준 단위당 가격(1kg당, 1마리당)으로
바꾼 뒤 정렬한다. 양을 못 읽은 상품은 뺀다 — 틀린 비교를 보여주느니 빼는 게 낫다.
"""

from __future__ import annotations

import html
import re
import statistics
from dataclasses import dataclass

import httpx

from app.catalog import Item

API_URL = "https://openapi.naver.com/v1/search/shop.json"

_TAG = re.compile(r"<[^>]+>")
_NUM = r"(\d+(?:\.\d+)?)"
_WEIGHT_RANGE = re.compile(_NUM + r"\s*[~\-]\s*" + _NUM + r"\s*(kg|킬로그램|킬로|g|그램)", re.I)
_WEIGHT = re.compile(_NUM + r"\s*(kg|킬로그램|킬로|g|그램)(?![a-wyz])", re.I)
_MULTIPLY = re.compile(r"[x×\*]\s*(\d+)(?!\s*(?:kg|g|cm|mm))", re.I)
_PACKS = re.compile(r"(\d+)\s*(팩|봉|봉지|묶음|세트)")
_COUNT_RANGE = re.compile(r"(\d+)\s*[~\-]\s*(\d+)\s*(개|입|마리|포기|통|미|과)")
_COUNT = re.compile(r"(\d+)\s*(개|입|마리|포기|통|미|과|손)")

# 먹는 그 식재료가 아닌 상품을 걸러낸다. "청"처럼 짧은 말은 "청송사과"도 걸러버려 넣지 않았다.
EXCLUDE_WORDS = (
    "모종", "씨앗", "종자", "즙", "주스", "분말", "가루", "잼", "젤리", "과자", "캔디",
    "말랭이", "건조", "통조림", "화분", "모형", "장난감", "쿠션", "스티커", "비누",
)

MAX_MULTIPLIER = 20


class ShopError(Exception):
    pass


def clean_title(title: str) -> str:
    return html.unescape(_TAG.sub("", title or "")).strip()


@dataclass(frozen=True)
class Quantity:
    grams: float | None
    count: int | None


def parse_quantity(title: str) -> Quantity:
    """상품명에서 총 중량(g)과 총 개수를 읽는다. 범위("2~3kg")는 적은 쪽으로 — 사는 사람에게
    불리한 쪽으로 계산해야 "최저가"가 과장되지 않는다."""
    text = clean_title(title)

    grams = None
    match = _WEIGHT_RANGE.search(text)
    if match:
        grams = _to_grams(float(match.group(1)), match.group(3))
    else:
        match = _WEIGHT.search(text)
        if match:
            grams = _to_grams(float(match.group(1)), match.group(2))

    count = None
    match = _COUNT_RANGE.search(text)
    if match:
        count = int(match.group(1))
    else:
        match = _COUNT.search(text)
        if match:
            count = int(match.group(1)) * (2 if match.group(2) == "손" else 1)

    multiplier = 1
    for pattern in (_MULTIPLY, _PACKS):
        found = pattern.search(text)
        if found:
            multiplier = max(multiplier, int(found.group(1)))
    multiplier = min(multiplier, MAX_MULTIPLIER)

    if grams is not None:
        grams *= multiplier
    if count is not None and grams is None:
        count *= multiplier
    if grams is not None and grams <= 0:
        grams = None
    if count is not None and count <= 0:
        count = None
    return Quantity(grams, count)


def _to_grams(value: float, unit: str) -> float:
    return value if unit.lower() in ("g", "그램") else value * 1000


def rank_offers(raw_items: list[dict], item: Item, limit: int = 5) -> list[dict]:
    offers = []
    seen = set()
    for raw in raw_items:
        title = clean_title(raw.get("title", ""))
        if raw.get("category1") and raw.get("category1") != "식품":
            continue
        if any(word in title for word in EXCLUDE_WORDS):
            continue
        try:
            price = int(raw.get("lprice") or 0)
        except ValueError:
            continue
        if price <= 0:
            continue

        quantity = parse_quantity(title)
        if item.shop_unit == "g":
            amount = quantity.grams
        else:
            amount = quantity.count
        if not amount:
            continue

        key = (raw.get("mallName"), title)
        if key in seen:
            continue
        seen.add(key)
        offers.append(
            {
                "title": title,
                "mall": raw.get("mallName") or "",
                "price": price,
                "unit_price": round(price / amount * item.shop_qty),
                "amount": amount,
                "link": raw.get("link") or "",
                "image": raw.get("image") or "",
            }
        )

    if len(offers) >= 4:
        # 양을 잘못 읽은 상품(예: "10kg 중 1팩 발송")은 단위가격이 비정상적으로 싸게 나온다.
        median = statistics.median(offer["unit_price"] for offer in offers)
        offers = [o for o in offers if median * 0.3 <= o["unit_price"] <= median * 5]

    offers.sort(key=lambda offer: offer["unit_price"])
    return offers[:limit]


class NaverShopping:
    def __init__(self, client_id: str, client_secret: str, *, client: httpx.Client | None = None):
        self.headers = {"X-Naver-Client-Id": client_id, "X-Naver-Client-Secret": client_secret}
        self.client = client or httpx.Client(timeout=10)

    def search(self, query: str) -> list[dict]:
        params = {"query": query, "display": 40, "sort": "sim", "exclude": "used:rental:cbshop"}
        try:
            response = self.client.get(API_URL, params=params, headers=self.headers)
            response.raise_for_status()
            return response.json().get("items", [])
        except (httpx.HTTPError, ValueError) as exc:
            raise ShopError(f"네이버 쇼핑 요청 실패: {exc}") from exc


class ShopService:
    """품목별 최저가. 결과는 품목 단위로 잠시 캐시해 여러 사람이 같이 쓴다 — 결제는
    사람마다 따로 하지만 네이버 호출은 한 번이면 된다."""

    def __init__(self, db, naver: NaverShopping | None, *, cache_seconds: float, clock):
        self.db = db
        self.naver = naver
        self.cache_seconds = cache_seconds
        self.clock = clock

    @property
    def source(self) -> str:
        return "naver" if self.naver else "sample"

    def offers(self, item: Item) -> dict:
        """ShopError는 그대로 올린다 — 부르는 쪽이 차감하지 않고 안내만 하도록."""
        now = self.clock()
        cached = self.db.get_shop_cache(item.id)
        if cached and cached["source"] == self.source and now - cached["fetched_at"] < self.cache_seconds:
            return {"offers": cached["offers"], "fetched_at": cached["fetched_at"], "source": self.source}

        if self.naver is None:
            from app import sample

            raw = sample.shop_items(item)
        else:
            raw = self.naver.search(item.shop_query)
        offers = rank_offers(raw, item)
        self.db.put_shop_cache(item.id, offers, source=self.source, now=now)
        return {"offers": offers, "fetched_at": now, "source": self.source}
