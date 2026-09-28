"""수산물 산지 위판가 (공공데이터포털 "해양수산부_위판장별 위탁판매 현황", select0040List).

전국 수협 위판장에서 어민이 경매로 판 기록이 한 건씩 온다 — 하루 8~9천 건, 150여 어종.
aT 소매가격 조사에 없는 쥐치·쏨뱅이·물메기 같은 어종을 여기서 얻는다.

- 가격은 경매가(도매)라 마트 소매가보다 훨씬 싸다. 화면에서 "산지 위판가"로 구분한다.
- kg당 가격 = 위판금액 합 ÷ 위판중량 합. 활어·선어·냉동은 값이 크게 달라 따로 묶는다.
- 한 번에 100건까지만 준다(그 이상을 달라면 빈 응답). 하루치가 90번 안팎의 요청이고, 하루
  호출 한도가 1만 번이라 처음엔 최근 60일만 받고 매일 30일씩 과거로 늘린다.
"""

from __future__ import annotations

import json
import logging
import time
from collections import defaultdict
from datetime import date, datetime, timedelta

import httpx

from app import config

log = logging.getLogger(__name__)

API_URL = "https://apis.data.go.kr/1192000/select0040List/getselect0040List"
PAGE_SIZE = 100
REQUEST_DEADLINE = 60

FIRST_DAYS = 60        # 처음 받는 기간
BACKFILL_PER_RUN = 30  # 한 번 돌 때 과거로 더 받는 날 수
MAX_DAYS = 400         # 이보다 오래된 날은 받지 않는다
RECHECK_DAYS = 4       # 최근 며칠은 늦게 올라오는 기록이 있어 다시 받는다


class WipanError(Exception):
    pass


def _num(value) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def aggregate_day(rows: list[dict]) -> list[dict]:
    """하루치 행을 어종 × 상태(활어/선어/냉동 …)별로 묶는다. "기타…" 어종은 뺀다."""
    groups: dict[tuple, dict] = {}
    for row in rows:
        name = (row.get("mprcStdCodeNm") or "").strip()
        amount, weight = _num(row.get("csmtAmount")), _num(row.get("csmtWt"))
        if not name or name.startswith("기타") or amount <= 0 or weight <= 0:
            continue
        key = (row.get("mprcStdCode"), row.get("kdfshSttusNm") or "-")
        g = groups.setdefault(key, {
            "code": key[0], "state": key[1], "name": name, "amount": 0.0, "weight": 0.0, "n": 0,
            "markets": set(), "min_kg": None, "max_kg": None,
            "regions": defaultdict(lambda: [0.0, 0.0]), "market_prices": defaultdict(lambda: [0.0, 0.0]),
        })
        kg = amount / weight
        g["amount"] += amount
        g["weight"] += weight
        g["n"] += 1
        g["markets"].add(row.get("csmtmktNm"))
        g["min_kg"] = kg if g["min_kg"] is None else min(g["min_kg"], kg)
        g["max_kg"] = kg if g["max_kg"] is None else max(g["max_kg"], kg)
        region = row.get("orgplceSeNm") or "기타"
        g["regions"][region][0] += amount
        g["regions"][region][1] += weight
        market = f"{row.get('csmtmktNm') or ''} ({row.get('mxtrNm') or ''})"
        g["market_prices"][market][0] += amount
        g["market_prices"][market][1] += weight

    result = []
    for g in groups.values():
        result.append({
            "code": g["code"], "state": g["state"], "name": g["name"],
            "amount": round(g["amount"]), "weight": round(g["weight"], 1), "n": g["n"],
            "markets": len(g["markets"]), "min_kg": round(g["min_kg"]), "max_kg": round(g["max_kg"]),
            "regions": {k: [round(a), round(w, 1)] for k, (a, w) in g["regions"].items()},
            "market_prices": {k: [round(a), round(w, 1)] for k, (a, w) in g["market_prices"].items()},
        })
    return result


class WipanClient:
    def __init__(self, service_key: str, *, client: httpx.Client | None = None):
        self.service_key = service_key
        self.client = client or httpx.Client(timeout=httpx.Timeout(30, connect=10))

    def _page(self, day: date, page: int) -> tuple[list[dict], int]:
        params = {"serviceKey": self.service_key, "type": "json", "baseDt": day.strftime("%Y%m%d"),
                  "numOfRows": PAGE_SIZE, "pageNo": page}
        last_error = None
        for attempt in range(3):
            try:
                deadline = time.monotonic() + REQUEST_DEADLINE
                chunks = []
                with self.client.stream("GET", API_URL, params=params) as response:
                    response.raise_for_status()
                    for chunk in response.iter_bytes():
                        chunks.append(chunk)
                        if time.monotonic() > deadline:
                            raise TimeoutError("응답이 너무 오래 걸림")
                payload = json.loads(b"".join(chunks) or b"{}")
                break
            except (httpx.HTTPError, ValueError, TimeoutError) as exc:
                last_error = exc
                time.sleep(2 * (attempt + 1))
        else:
            raise WipanError(f"위판 API 요청 실패: {type(last_error).__name__}")

        body_root = payload.get("responseJson")
        if body_root is None:
            raise WipanError("위판 API 응답 형식이 다름")
        header = body_root.get("header") or {}
        if str(header.get("resultCode")) not in ("00", "0"):
            raise WipanError(f"위판 API 오류: {header.get('resultCode')} {header.get('resultMsg')}")
        items = (body_root.get("body") or {}).get("item") or []
        if isinstance(items, dict):
            items = [items]
        return items, int(header.get("totalCount") or 0)

    def fetch_day(self, day: date) -> list[dict]:
        rows, page = [], 1
        while True:
            items, total = self._page(day, page)
            rows.extend(items)
            if not items or page * PAGE_SIZE >= total:
                return rows
            page += 1


class FishService:
    def __init__(self, db, client: WipanClient | None, *, clock=time.time):
        self.db = db
        self.client = client
        self.clock = clock

    @property
    def enabled(self) -> bool:
        return self.client is not None

    def _today(self) -> date:
        return datetime.fromtimestamp(self.clock(), config.KST).date()

    def collect(self) -> dict:
        """받을 날을 정해 받는다: 최근 FIRST_DAYS일 중 빠진 날 + 최근 RECHECK_DAYS일 + 과거로 BACKFILL_PER_RUN일."""
        if not self.client:
            return {"skipped": "no key"}
        today = self._today()
        done = self.db.fish_days()
        targets = []
        for offset in range(FIRST_DAYS, -1, -1):
            day = today - timedelta(days=offset)
            if day.isoformat() not in done or offset <= RECHECK_DAYS:
                targets.append(day)
        oldest = min((date.fromisoformat(d) for d in done), default=today - timedelta(days=FIRST_DAYS))
        for k in range(1, BACKFILL_PER_RUN + 1):
            day = oldest - timedelta(days=k)
            if (today - day).days > MAX_DAYS:
                break
            if day.isoformat() not in done:
                targets.append(day)

        fetched, failed = 0, []
        for day in targets:
            try:
                rows = self.client.fetch_day(day)
            except WipanError as exc:
                log.warning("%s 위판 수집 실패: %s", day, exc)
                failed.append(day.isoformat())
                continue
            self.db.put_fish_day(day.isoformat(), aggregate_day(rows), len(rows), self.clock())
            fetched += 1
        return {"fetched": fetched, "failed": failed}


# 위판 자료의 산지 이름을 지도(2013년 경계)의 시·도 이름에 맞춘다. "경상북도"와 "경북 포항시"가
# 섞여 오고, 그 사이 이름이 바뀐 곳(강원·전북 특별자치도)도 있다.
PROVINCE_PREFIXES = {
    "서울": "서울특별시", "부산": "부산광역시", "대구": "대구광역시", "인천": "인천광역시", "광주": "광주광역시",
    "대전": "대전광역시", "울산": "울산광역시", "세종": "세종특별자치시", "경기": "경기도", "강원": "강원도",
    "충북": "충청북도", "충청북": "충청북도", "충남": "충청남도", "충청남": "충청남도",
    "전북": "전라북도", "전라북": "전라북도", "전남": "전라남도", "전라남": "전라남도",
    "경북": "경상북도", "경상북": "경상북도", "경남": "경상남도", "경상남": "경상남도", "제주": "제주특별자치도",
}


def province_of(name: str) -> str:
    for prefix in sorted(PROVINCE_PREFIXES, key=len, reverse=True):
        if name.startswith(prefix):
            return PROVINCE_PREFIXES[prefix]
    return name  # 원양·수입 등은 그대로 둔다
MIN_WEEK_WEIGHT = 5.0  # 한 주 거래가 이보다 적은 어종은 가격이 튀어서 목록에서 뺀다(kg)


def _kg(amount: float, weight: float) -> int | None:
    return round(amount / weight) if weight > 0 else None


def _sum(rows: list[dict]) -> tuple[float, float]:
    return sum(r["amount"] for r in rows), sum(r["weight"] for r in rows)


def _merge(rows: list[dict], field: str) -> list[dict]:
    """여러 날의 {이름: [금액, 중량]}을 합쳐 kg당 가격 목록으로. 산지는 시·도 단위로 모은다."""
    total: dict[str, list[float]] = defaultdict(lambda: [0.0, 0.0])
    for row in rows:
        for name, (amount, weight) in row[field].items():
            key = province_of(name) if field == "regions" else name
            total[key][0] += amount
            total[key][1] += weight
    return [{"name": name, "kg": _kg(a, w), "weight": round(w, 1)} for name, (a, w) in total.items() if w > 0]


class FishQueries:
    """화면용 요약. 최신 날짜 기준 최근 7일과 그 전 7일을 비교한다."""

    def __init__(self, db, nutrition=None):
        self.db = db
        self.nutrition = nutrition

    def _windows(self) -> tuple[str, str, str] | None:
        latest = self.db.fish_latest_date()
        if not latest:
            return None
        d = date.fromisoformat(latest)
        return latest, (d - timedelta(days=6)).isoformat(), (d - timedelta(days=13)).isoformat()

    def species(self) -> dict:
        windows = self._windows()
        if not windows:
            return {"latest": None, "species": []}
        latest, week_start, prev_start = windows
        by_key: dict[tuple, list[dict]] = defaultdict(list)
        for row in self.db.fish_rows(prev_start):
            by_key[(row["code"], row["state"])].append(row)

        result = []
        for (code, state), rows in by_key.items():
            week = [r for r in rows if r["date"] >= week_start]
            prev = [r for r in rows if r["date"] < week_start]
            wa, ww = _sum(week)
            if ww < MIN_WEEK_WEIGHT:
                continue
            pa, pw = _sum(prev)
            kg, prev_kg = _kg(wa, ww), _kg(pa, pw) if pw >= MIN_WEEK_WEIGHT else None
            regions = sorted(_merge(week, "regions"), key=lambda r: -r["weight"])
            result.append({
                "code": code, "state": state, "name": rows[-1]["name"], "kg": kg,
                "change": round((kg / prev_kg - 1) * 100, 1) if prev_kg else None,
                "weight": round(ww), "markets": max(r["markets"] for r in week),
                "regions": [r["name"] for r in regions[:2]],
            })
        result.sort(key=lambda s: -s["weight"])
        return {"latest": latest, "species": result}

    def detail(self, code: str, state: str | None = None) -> dict | None:
        rows = self.db.fish_rows("0000-00-00", code)
        if not rows:
            return None
        weights: dict[str, float] = defaultdict(float)
        for row in rows:
            weights[row["state"]] += row["weight"]
        states = sorted(weights, key=lambda s: -weights[s])
        state = state if state in weights else states[0]
        rows = [r for r in rows if r["state"] == state]
        name = rows[-1]["name"]

        latest = rows[-1]["date"]
        week_start = (date.fromisoformat(latest) - timedelta(days=6)).isoformat()
        week = [r for r in rows if r["date"] >= week_start]
        wa, ww = _sum(week)
        regions = sorted(_merge(week, "regions"), key=lambda r: -r["weight"])
        markets = sorted((m for m in _merge(week, "market_prices") if m["weight"] >= 1), key=lambda m: m["kg"])

        return {
            "code": code, "name": name, "state": state, "states": states, "latest": latest,
            "kg": _kg(wa, ww), "weight": round(ww), "min_kg": min(r["min_kg"] for r in week),
            "max_kg": max(r["max_kg"] for r in week),
            "series": [{"date": r["date"], "price": _kg(r["amount"], r["weight"]), "weight": r["weight"],
                        "normal_price": None} for r in rows],
            "regions": regions,
            "markets": markets[:8],
            "nutrition": self.nutrition.lookup(name) if self.nutrition else None,
        }
