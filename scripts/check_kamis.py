"""items.csv의 KAMIS 품목 코드가 맞는지 확인한다.

    .venv\\Scripts\\python.exe scripts\\check_kamis.py

품목마다 최근 2주 가격을 요청해서, KAMIS가 돌려준 품목명·품종명과 가격 개수를 보여준다.
이름이 우리가 뜻한 것과 같고 가격이 나오면 items.csv의 kamis_verified를 1로 바꾼다.
"""

from __future__ import annotations

import sys
from datetime import timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import httpx  # noqa: E402

from app import config  # noqa: E402
from app.catalog import load_catalog  # noqa: E402
from app.kamis import BASE_URL, parse_period  # noqa: E402
from app.prices import today_kst  # noqa: E402


def main() -> None:
    if not config.kamis_enabled():
        sys.exit(".env에 KAMIS_CERT_KEY와 KAMIS_CERT_ID를 먼저 넣으세요.")
    end = today_kst()
    start = end - timedelta(days=14)
    client = httpx.Client(timeout=20)
    for item in load_catalog(config.DATA_DIR):
        if item.kamis is None:
            print(f"-  {item.name:<6} 코드 없음 (가격 없이 최저가만)")
            continue
        code = item.kamis
        params = {
            "action": "periodProductList", "p_productclscode": "01",
            "p_startday": start.isoformat(), "p_endday": end.isoformat(),
            "p_itemcategorycode": code.category, "p_itemcode": code.item, "p_kindcode": code.kind,
            "p_productrankcode": code.rank, "p_countrycode": "", "p_convert_kg_yn": "N",
            "p_cert_key": config.KAMIS_CERT_KEY, "p_cert_id": config.KAMIS_CERT_ID, "p_returntype": "json",
        }
        try:
            payload = client.get(BASE_URL, params=params).json()
            rows = payload.get("data", {}).get("item", []) if isinstance(payload.get("data"), dict) else []
            if isinstance(rows, dict):
                rows = [rows]
            names = {f"{r.get('itemname')}/{r.get('kindname')}" for r in rows}
            prices = [v for v in parse_period(payload).values() if v["price"]]
            mark = "OK" if prices else "!!"
            latest = prices[-1]["price"] if prices else None
            print(f"{mark} {item.name:<6} {code.category}-{code.item}-{code.kind} → {', '.join(sorted(names)) or '응답 없음'}"
                  f" · 가격 {len(prices)}일 · 최근 {latest}")
        except Exception as exc:  # 한 품목이 깨져도 나머지는 계속 본다
            print(f"!! {item.name:<6} 요청 실패: {exc}")


if __name__ == "__main__":
    main()
