"""공공데이터포털 "한국농수산식품유통공사_일별 도,소매 가격정보" (perDay/price).

KAMIS와 같은 aT 조사 가격인데, 전국 평균·평년가를 계산해 주지 않고 **조사처(시장·마트)
한 곳당 한 행**으로 준다. 그래서 여기서
  1) 품목표가 정한 품종·등급·단위의 행만 남기고
  2) 날짜별 전국 평균(온라인 제외)을 내고
  3) 판매처 유형별·지역별 평균과 최저가를 묶는다.
평년가는 쌓인 과거 가격으로 prices.py가 계산한다.

조사처 이름은 익명 처리돼 온다("A-대형마트", "온라인몰B"). 그래서 "어느 쇼핑몰이 싸다"가
아니라 "어떤 유형의 판매처가 싸다"를 보여준다.
"""

from __future__ import annotations

import json
import statistics
import time
from collections import Counter, defaultdict
from datetime import date, timedelta

import httpx

from app.catalog import AtCode

API_URL = "https://apis.data.go.kr/B552845/perDay/price"
PAGE_SIZE = 1000          # 명세상 최대
WINDOW_DAYS = 180         # 한 번에 요청하는 기간. 넘으면 페이지가 너무 많아진다.
ONLINE_REGION = "9998"
REQUEST_DEADLINE = 60     # 요청 하나에 쓰는 최대 시간(초)
FIELDS = "exmn_ymd,vrty_cd,grd_cd,sgg_cd,sgg_nm,mrkt_nm,unit,unit_sz,exmn_dd_prc"

# 화면에 보여줄 순서
CHANNELS = ("전통시장", "대형마트", "SSM·슈퍼", "백화점", "생협·전문점", "온라인")


class AtError(Exception):
    pass


def channel_of(row: dict) -> str | None:
    """조사처 이름으로 판매처 유형을 가른다. 도매시장은 소매 비교에서 뺀다(None)."""
    if row.get("sgg_cd") == ONLINE_REGION:
        return "온라인"
    name = row.get("mrkt_nm") or ""
    if "도매" in name:
        return None
    if "대형마트" in name or name.endswith("-유통") or name.endswith("-마트"):
        return "대형마트"  # "X-유통"은 KAMIS가 말하는 대형유통업체를 익명 처리한 것
    if "SSM" in name or "슈퍼" in name:
        return "SSM·슈퍼"
    if "백화점" in name:
        return "백화점"
    if "생협" in name or "전문점" in name:
        return "생협·전문점"
    return "전통시장"


def _price(row: dict) -> int | None:
    try:
        value = int(float(str(row.get("exmn_dd_prc", "")).replace(",", "")))
    except ValueError:
        return None
    return value if value > 0 else None


def keep_rows(rows: list[dict], code: AtCode) -> list[dict]:
    return [
        row for row in rows
        if row.get("vrty_cd") in code.varieties
        and row.get("grd_cd") in code.grades
        and row.get("unit") == code.unit
        and str(row.get("unit_sz")) == code.unit_size
        and _price(row) is not None
    ]


def _iso(ymd: str) -> str:
    return f"{ymd[:4]}-{ymd[4:6]}-{ymd[6:8]}"


def aggregate(rows: list[dict]) -> dict[str, dict]:
    """걸러진 행을 날짜별로 묶는다.

    돌려주는 값: {"YYYY-MM-DD": {"price": 전국 평균, "n": 조사처 수,
                  "channels": {유형: {"avg", "min", "n"}}, "regions": {지역: {"avg", "min", "n"}}}}

    한 날짜에 허용 품종이 둘 이상 있으면(사과 후지·홍로가 겹치는 가을) 조사처가 많은 품종 하나만
    쓴다 — 섞어서 평균 내면 품종 비중에 따라 선이 출렁인다.
    """
    by_day: dict[str, list[dict]] = defaultdict(list)
    for row in rows:
        by_day[row["exmn_ymd"]].append(row)

    result = {}
    for ymd, day_rows in by_day.items():
        variety = Counter(row["vrty_cd"] for row in day_rows).most_common(1)[0][0]
        day_rows = [row for row in day_rows if row["vrty_cd"] == variety]

        offline = [_price(row) for row in day_rows if row.get("sgg_cd") != ONLINE_REGION]
        if not offline:
            continue
        groups: dict[str, dict[str, list[int]]] = {"channels": defaultdict(list), "regions": defaultdict(list)}
        for row in day_rows:
            price = _price(row)
            channel = channel_of(row)
            if channel:
                groups["channels"][channel].append(price)
            if row.get("sgg_cd") != ONLINE_REGION and row.get("sgg_nm"):
                groups["regions"][row["sgg_nm"]].append(price)

        result[_iso(ymd)] = {
            "price": round(statistics.fmean(offline)),
            "n": len(offline),
            **{
                kind: {
                    name: {"avg": round(statistics.fmean(prices)), "min": min(prices), "n": len(prices)}
                    for name, prices in values.items()
                }
                for kind, values in groups.items()
            },
        }
    return result


class AtClient:
    def __init__(self, service_key: str, *, client: httpx.Client | None = None, pause: float = 0.1):
        self.service_key = service_key
        self.client = client or httpx.Client(timeout=httpx.Timeout(30, connect=10))
        self.pause = pause  # 공공 API를 몰아서 두드리지 않게 호출 사이를 조금 띄운다

    def _get_json(self, params: dict) -> dict:
        """요청 하나에 전체 시간 상한을 둔다.

        httpx의 timeout은 "한 번 읽을 때" 기준이라, 서버가 응답을 찔끔찔끔 흘려보내면 끝없이
        기다린다 — 실제로 한 요청이 1시간 반 동안 멈춰 뒤의 수집까지 막은 적이 있다.
        """
        deadline = time.monotonic() + REQUEST_DEADLINE
        chunks = []
        with self.client.stream("GET", API_URL, params=params) as response:
            response.raise_for_status()
            for chunk in response.iter_bytes():
                chunks.append(chunk)
                if time.monotonic() > deadline:
                    raise TimeoutError(f"응답이 {REQUEST_DEADLINE}초 안에 끝나지 않음")
        return json.loads(b"".join(chunks))

    def _page(self, code: AtCode, start: date, end: date, page: int) -> tuple[list[dict], int]:
        params = {
            "serviceKey": self.service_key,
            "returnType": "JSON",
            "pageNo": page,
            "numOfRows": PAGE_SIZE,
            "cond[exmn_ymd::GTE]": start.strftime("%Y%m%d"),
            "cond[exmn_ymd::LTE]": end.strftime("%Y%m%d"),
            "cond[se_cd::EQ]": "01",  # 소매
            "cond[ctgry_cd::EQ]": code.category,
            "cond[item_cd::EQ]": code.item,
            "selectable": FIELDS,
        }
        # 조건이 하나뿐이면 서버에서 거른다 — 받는 행 수가 크게 준다.
        if len(code.varieties) == 1:
            params["cond[vrty_cd::EQ]"] = code.varieties[0]
        if len(code.grades) == 1:
            params["cond[grd_cd::EQ]"] = code.grades[0]

        last_error = None
        for attempt in range(3):
            try:
                payload = self._get_json(params)
                break
            except (httpx.HTTPError, ValueError, TimeoutError) as exc:
                last_error = exc
                time.sleep(2 * (attempt + 1))
        else:
            # 키가 오류 메시지에 섞여 나가지 않게 URL은 빼고 적는다.
            raise AtError(f"가격 API 요청 실패: {type(last_error).__name__}")

        body = (payload.get("response") or {}).get("body")
        if body is None:
            header = (payload.get("response") or {}).get("header") or {}
            raise AtError(f"가격 API 오류: {header.get('resultCode')} {header.get('resultMsg')}")
        items = body.get("items") or []
        if isinstance(items, dict):
            items = items.get("item") or []
        if isinstance(items, dict):
            items = [items]
        return items, int(body.get("totalCount") or 0)

    def fetch_rows(self, code: AtCode, start: date, end: date) -> list[dict]:
        rows: list[dict] = []
        cursor = start
        while cursor <= end:
            window_end = min(cursor + timedelta(days=WINDOW_DAYS - 1), end)
            page = 1
            while True:
                items, total = self._page(code, cursor, window_end, page)
                rows.extend(items)
                time.sleep(self.pause)
                if not items or page * PAGE_SIZE >= total:
                    break
                page += 1
            cursor = window_end + timedelta(days=1)
        return keep_rows(rows, code)
