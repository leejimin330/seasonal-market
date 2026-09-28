"""주산지 이름 → 지도 위치.

seasons.csv의 주산지("해남·괴산", "제주 구좌")를 낱말로 쪼개 data/places.csv(시·군 이름, 시·도,
대략의 위도·경도)와 맞춘다. 좌표는 지도에 점을 찍기 위한 시청·읍 중심 정도의 값이다.
"경기", "강원"처럼 시·도 이름이면 점 없이 그 시·도만 칠하고, "전국", "근교"처럼 한 곳을
가리키지 않는 말은 지도에 올리지 않고 글로만 남긴다.
"""

from __future__ import annotations

import csv
from pathlib import Path

PROVINCE_WORDS = {"경기": "경기도", "강원": "강원도", "제주": "제주특별자치도"}


class Places:
    def __init__(self, points: dict[str, dict]):
        self.points = points

    def resolve(self, main_region: str) -> dict:
        points, provinces, other = [], [], []
        for word in main_region.replace("·", " ").split():
            if word in self.points:
                point = self.points[word]
                points.append(point)
                provinces.append(point["province"])
            elif word in PROVINCE_WORDS:
                provinces.append(PROVINCE_WORDS[word])
            else:
                other.append(word)
        return {
            "points": points,
            "provinces": sorted(set(provinces)),
            "other": other,  # 지도에 못 올린 말 ("전국", "근교" …)
        }


def load_places(data_dir: Path) -> Places:
    points = {}
    path = data_dir / "places.csv"
    if path.exists():
        with open(path, encoding="utf-8", newline="") as f:
            for row in csv.DictReader(f, delimiter="|"):
                points[row["name"]] = {
                    "name": row["name"],
                    "province": row["province"],
                    "lat": float(row["lat"]),
                    "lon": float(row["lon"]),
                }
    return Places(points)
