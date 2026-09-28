"""KAMIS(aT 농산물유통정보) 기간별 가격 API.

`periodProductList`는 한 품목의 기간 가격을 돌려주는데, 같은 날짜에 지역별 행이
섞여 온다. 우리는 전국 "평균" 행을 소매가로, "평년" 행을 평년가로 쓴다.

⚠ 응답 형식은 공개 문서 기준으로 짰고, 실제 키로는 아직 확인하지 못했다.
키를 넣은 뒤 `python scripts/check_kamis.py`로 품목 코드와 함께 확인한다.
"""

from __future__ import annotations

from datetime import date, timedelta

import httpx

from app.catalog import KamisCode

BASE_URL = "https://www.kamis.or.kr/service/price/xml.do"
# 한 번에 요청하는 기간(일). 긴 기간을 한 번에 달라고 하면 잘리는 경우가 있어 나눠 받는다.
WINDOW_DAYS = 90


class KamisError(Exception):
    pass


def _to_int(text) -> int | None:
    if text is None:
        return None
    cleaned = str(text).replace(",", "").strip()
    if not cleaned or cleaned == "-":
        return None
    try:
        return int(float(cleaned))
    except ValueError:
        return None


def parse_period(payload: dict) -> dict[str, dict[str, int | None]]:
    """응답을 {"YYYY-MM-DD": {"price": …, "normal_price": …}}로.

    데이터가 없을 때 KAMIS는 `data`를 ["001"] 같은 목록으로 준다 — 오류가 아니라 빈 결과다.
    """
    data = payload.get("data")
    if not isinstance(data, dict):
        return {}
    code = str(data.get("error_code", "000"))
    if code not in ("000", "0"):
        raise KamisError(f"KAMIS 오류 코드 {code}")
    rows = data.get("item") or []
    if isinstance(rows, dict):
        rows = [rows]

    result: dict[str, dict[str, int | None]] = {}
    for row in rows:
        county = str(row.get("countyname", "")).strip()
        if county not in ("평균", "평년"):
            continue
        year = str(row.get("yyyy", "")).strip()
        regday = str(row.get("regday", "")).strip()  # "09/28"
        if not (year.isdigit() and "/" in regday):
            continue
        month, day = regday.split("/", 1)
        try:
            key = date(int(year), int(month), int(day)).isoformat()
        except ValueError:
            continue
        slot = result.setdefault(key, {"price": None, "normal_price": None})
        value = _to_int(row.get("price"))
        if county == "평균":
            slot["price"] = value
        else:
            slot["normal_price"] = value
    return result


class KamisClient:
    def __init__(self, cert_key: str, cert_id: str, *, client: httpx.Client | None = None):
        self.cert_key = cert_key
        self.cert_id = cert_id
        self.client = client or httpx.Client(timeout=20)

    def fetch_window(self, code: KamisCode, start: date, end: date) -> dict[str, dict]:
        params = {
            "action": "periodProductList",
            "p_productclscode": "01",  # 01 = 소매
            "p_startday": start.isoformat(),
            "p_endday": end.isoformat(),
            "p_itemcategorycode": code.category,
            "p_itemcode": code.item,
            "p_kindcode": code.kind,
            "p_productrankcode": code.rank,
            "p_countrycode": "",       # 비우면 전국
            "p_convert_kg_yn": "N",
            "p_cert_key": self.cert_key,
            "p_cert_id": self.cert_id,
            "p_returntype": "json",
        }
        try:
            response = self.client.get(BASE_URL, params=params)
            response.raise_for_status()
            return parse_period(response.json())
        except (httpx.HTTPError, ValueError) as exc:
            raise KamisError(f"KAMIS 요청 실패: {exc}") from exc

    def fetch_range(self, code: KamisCode, start: date, end: date) -> dict[str, dict]:
        merged: dict[str, dict] = {}
        cursor = start
        while cursor <= end:
            window_end = min(cursor + timedelta(days=WINDOW_DAYS - 1), end)
            merged.update(self.fetch_window(code, cursor, window_end))
            cursor = window_end + timedelta(days=1)
        return merged
