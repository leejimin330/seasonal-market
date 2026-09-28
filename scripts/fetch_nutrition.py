"""식약처 식품영양성분DB에서 원재료성 식품(생것 등)의 영양성분을 받아 data/nutrition.json에 저장한다.

    .venv\\Scripts\\python.exe scripts\\fetch_nutrition.py

영양성분은 자주 바뀌지 않아서 서버가 매번 부르지 않고, 이 스크립트로 가끔 한 번 받아 둔다.
품목과의 연결은 data/nutrition_map.csv(품목 id | 식품명)에서 사람이 정한다.

응답의 AMT_NUM 번호는 명세를 못 구해 실제 값으로 확인했다(2026-09-28): 수분+단백질+지방+회분+탄수화물이
정확히 100g이 되고, 에너지가 4·9·4 계산과 맞는다 — 배추·시금치·고등어·굴 등.
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import httpx  # noqa: E402

from app import config  # noqa: E402

API_URL = "https://apis.data.go.kr/1471000/FoodNtrCpntDbInfo03/getFoodNtrCpntDbInq03"
CATEGORIES = ["채소류", "과일류", "버섯류", "어패류", "감자 및 전분류", "견과 및 종실류"]
# 해조류는 식품대분류가 비어 있어 분류로는 안 잡힌다. 이름으로 찾는다.
NAME_SEARCHES = ["미역", "다시마", "김, "]
FIELDS = {  # AMT_NUMn → (키, 단위)
    1: "kcal", 2: "water", 3: "protein", 4: "fat", 5: "ash", 6: "carbs",
    7: "sugar", 8: "fiber", 9: "calcium", 10: "iron", 11: "phosphorus", 12: "potassium", 13: "sodium",
}


def _num(value) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def main() -> None:
    if not config.at_enabled():
        sys.exit(".env에 DATA_GO_KR_KEY를 먼저 넣으세요.")
    client = httpx.Client(timeout=60)
    foods: dict[str, dict] = {}
    queries = [("FOOD_CAT1_NM", c) for c in CATEGORIES] + [("FOOD_NM_KR", n) for n in NAME_SEARCHES]
    for field, category in queries:
        page = 1
        while True:
            params = {"serviceKey": config.DATA_GO_KR_KEY, "type": "json", "numOfRows": 100, "pageNo": page,
                      field: category}
            body = client.get(API_URL, params=params).json().get("body") or {}
            items = body.get("items") or []
            for item in items:
                if item.get("DB_GRP_NM") != "원재료성" or item.get("SERVING_SIZE") != "100g":
                    continue
                foods[item["FOOD_NM_KR"]] = {
                    "category": item.get("FOOD_CAT1_NM") or "해조류",
                    **{key: _num(item.get(f"AMT_NUM{n}")) for n, key in FIELDS.items()},
                }
            print(f"{category} {page}쪽 · 누적 {len(foods)}", flush=True)
            if not items or page * 100 >= int(body.get("totalCount") or 0):
                break
            page += 1
            time.sleep(0.2)

    out = config.DATA_DIR / "nutrition.json"
    out.write_text(json.dumps(
        {"source": "식품의약품안전처 식품영양성분DB (100g 기준)", "fetched": time.strftime("%Y-%m-%d"), "foods": foods},
        ensure_ascii=False, indent=0,
    ), encoding="utf-8")
    print(f"{len(foods)}개 저장 → {out}")


if __name__ == "__main__":
    main()
