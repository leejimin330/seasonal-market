"""품목별 영양성분 (식약처 식품영양성분DB, 100g 기준).

값은 `scripts/fetch_nutrition.py`가 받아 둔 data/nutrition.json에서 읽고, 품목과의 연결은
data/nutrition_map.csv(품목 id | 식품명)에서 사람이 정한다. 파일이 없으면 영양 정보 없이 돈다.
영양 수치는 사람 손으로 적지 않는다 — 틀린 숫자는 없는 것보다 나쁘다.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path

# 화면에 보여줄 영양소와 단위. 순서대로 표시한다.
SHOWN = [
    ("kcal", "열량", "kcal"),
    ("carbs", "탄수화물", "g"),
    ("sugar", "당류", "g"),
    ("fiber", "식이섬유", "g"),
    ("protein", "단백질", "g"),
    ("fat", "지방", "g"),
    ("sodium", "나트륨", "mg"),
    ("potassium", "칼륨", "mg"),
    ("calcium", "칼슘", "mg"),
    ("iron", "철", "mg"),
]


def _format(food_name: str, food: dict) -> dict:
    return {
        "food_name": food_name,
        "values": [
            {"key": key, "label": label, "unit": unit, "value": food.get(key)}
            for key, label, unit in SHOWN
            if food.get(key) is not None
        ],
    }


class Nutrition:
    def __init__(self, source: str, by_item: dict[str, dict], foods: dict[str, dict] | None = None):
        self.source = source
        self.by_item = by_item
        self.foods = foods or {}

    def get(self, item_id: str) -> dict | None:
        return self.by_item.get(item_id)

    def lookup(self, name: str) -> dict | None:
        """이름으로 "(이름), 생것"을 찾는다. 수산물 위판 어종처럼 연결표가 없는 것에 쓴다."""
        clean = name.split("(")[0].strip()
        for candidate in (f"{clean}, 생것", clean):
            if candidate in self.foods:
                return _format(candidate, self.foods[candidate])
        return None


def load_nutrition(data_dir: Path) -> Nutrition:
    data_path, map_path = data_dir / "nutrition.json", data_dir / "nutrition_map.csv"
    if not (data_path.exists() and map_path.exists()):
        return Nutrition("", {})
    payload = json.loads(data_path.read_text(encoding="utf-8"))
    foods = payload.get("foods", {})
    by_item = {}
    with open(map_path, encoding="utf-8", newline="") as f:
        for row in csv.DictReader(f, delimiter="|", quoting=csv.QUOTE_NONE):
            food = foods.get(row["food_name"])
            if not food:
                continue  # 식품명이 DB에서 바뀌었으면 조용히 뺀다 — 화면은 영양 칸 없이 뜬다
            by_item[row["item_id"]] = _format(row["food_name"], food)
    return Nutrition(f"{payload.get('source', '')}, {payload.get('fetched', '')} 기준", by_item, foods)
