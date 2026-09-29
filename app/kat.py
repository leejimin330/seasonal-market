"""농산물 도매 경락가 (공공데이터포털 "한국농수산식품유통공사_전국 공영도매시장 실시간 경매정보", trades2).

가락시장 등 전국 32개 공영도매시장의 경매 낙찰 기록이 한 건씩 온다 — 하루 8만 건 넘게, 140여 품목.
aT 소매가격 조사에 없는 가지·부추·무화과·연근·두릅 같은 품목을 여기서 얻는다.

- **오늘 자료만 준다.** 지난 날짜로 물으면 0건이다. 그래서 과거를 채울 수 없고, 서버가 켜져 있는
  날만 쌓인다. 경매가 새벽부터 오후까지 이어지니 몇 시간마다 오늘 자료를 다시 받아 덮어쓴다.
- 가격은 도매 경락가라 소매가보다 싸다. 화면에서 "도매 경락가"로 구분한다.
- 한 건의 낙찰가(scsbd_prc)는 포장 하나 값이고, 포장 하나가 unit_qty kg이며 qty개를 팔았다.
  kg당 가격 = 낙찰가 ÷ 포장 kg. 집계는 수산물 위판과 같은 방식(wipan.aggregate_day)을 쓴다.
"""

from __future__ import annotations

import json
import logging
import time
from datetime import date, datetime

import httpx

from app import config
from app.wipan import aggregate_day

log = logging.getLogger(__name__)

API_URL = "https://apis.data.go.kr/B552845/katRealTime2/trades2"
PAGE_SIZE = 1000  # 이보다 크게 달라고 해도 1000건씩 온다
REQUEST_DEADLINE = 60
# 가공품·사료처럼 장바구니와 거리가 먼 부류는 뺀다.
SKIP_CATEGORIES = {"농림가공"}
SKIP_ITEMS = {"곡물제조", "전분 및 사료제조", "조미제품", "절임식품", "안스리움", "어묵,어분,어비", "조미가공", "건가공(해조)류"}


class KatError(Exception):
    pass


def _num(value) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def to_auction_rows(rows: list[dict]) -> tuple[list[dict], dict[str, str]]:
    """도매 경매 행을 위판 집계가 읽는 모양으로 바꾼다. 품목 코드 → 부류 이름도 함께 돌려준다."""
    converted, categories = [], {}
    for row in rows:
        category = row.get("gds_lclsf_nm") or ""
        name = (row.get("gds_mclsf_nm") or "").strip()
        if category in SKIP_CATEGORIES or name in SKIP_ITEMS or row.get("unit_nm") != "kg":
            continue
        price, unit_kg, qty = _num(row.get("scsbd_prc")), _num(row.get("unit_qty")), _num(row.get("qty"))
        if price <= 0 or unit_kg <= 0 or qty <= 0:
            continue
        code = f"{row.get('gds_lclsf_cd')}{row.get('gds_mclsf_cd')}"
        categories[code] = category
        converted.append({
            "mprcStdCodeNm": name,
            "mprcStdCode": code,
            "kdfshSttusNm": (row.get("gds_sclsf_nm") or "-").strip(),  # 품종
            "csmtAmount": price * qty,
            "csmtWt": unit_kg * qty,
            "csmtmktNm": row.get("whsl_mrkt_nm") or "",
            "mxtrNm": row.get("corp_nm") or "",
            "orgplceSeNm": row.get("plor_nm") or "",
        })
    return converted, categories


def aggregate_produce(rows: list[dict]) -> list[dict]:
    converted, categories = to_auction_rows(rows)
    groups = aggregate_day(converted)
    for group in groups:
        group["category"] = categories.get(group["code"], "")
    return groups


class KatClient:
    def __init__(self, service_key: str, *, client: httpx.Client | None = None):
        self.service_key = service_key
        self.client = client or httpx.Client(timeout=httpx.Timeout(30, connect=10))

    def _page(self, day: date, page: int) -> tuple[list[dict], int]:
        params = {"serviceKey": self.service_key, "returnType": "JSON", "pageNo": page, "numOfRows": PAGE_SIZE,
                  "cond[trd_clcln_ymd::EQ]": day.isoformat()}
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
            raise KatError(f"도매 경매 API 요청 실패: {type(last_error).__name__}")

        root = payload.get("response") or {}
        header = root.get("header") or {}
        if str(header.get("resultCode")) not in ("0", "00"):
            raise KatError(f"도매 경매 API 오류: {header.get('resultCode')} {header.get('resultMsg')}")
        body = root.get("body") or {}
        items = (body.get("items") or {}).get("item") or []
        if isinstance(items, dict):
            items = [items]
        return items, int(body.get("totalCount") or 0)

    def fetch_day(self, day: date) -> list[dict]:
        rows, page = [], 1
        while True:
            items, total = self._page(day, page)
            rows.extend(items)
            if not items or page * PAGE_SIZE >= total:
                return rows
            page += 1


class ProduceService:
    """오늘 자료를 받아 오늘 날짜로 덮어쓴다. 지난 날은 API가 주지 않아 되돌아가 채울 수 없다."""

    def __init__(self, store, client: KatClient | None, *, clock=time.time):
        self.store = store
        self.client = client
        self.clock = clock

    @property
    def enabled(self) -> bool:
        return self.client is not None

    def collect(self) -> dict:
        if not self.client:
            return {"skipped": "no key"}
        today = datetime.fromtimestamp(self.clock(), config.KST).date()
        rows = self.client.fetch_day(today)
        groups = aggregate_produce(rows)
        self.store.put_fish_day(today.isoformat(), groups, len(rows), self.clock())
        return {"date": today.isoformat(), "rows": len(rows), "groups": len(groups)}
