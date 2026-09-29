"""주소·조합 이름 → 시·군·구와 지도 좌표.

- 농산물 도매: 산지 주소가 "경북 구미시 선산읍", "전북특별자치도 고창군"처럼 온다. 앞의 시·도와
  이어지는 시·군·구 낱말을 찾는다.
- 수산물 위판: 산지 칸은 대부분 시·도뿐이다. 대신 조합 이름("거제수산업협동조합", "통영수협")에
  지명이 들어 있어 거기서 시·군을 찾는다 — 위판장은 배가 들어오는 항구라 사실상 산지다.

좌표는 data/municipalities.csv — 통계청 2013 시·군·구 경계(southkorea-maps)에서 계산한 중심점.
"포항시북구"처럼 구가 나뉜 일반 시는 주소에 보통 "포항시"까지만 나와서 시 하나로 합친다.
"""

from __future__ import annotations

import csv
import re
import statistics
from pathlib import Path

from app.wipan import province_of

METRO = {"서울특별시", "부산광역시", "대구광역시", "인천광역시", "광주광역시", "대전광역시", "울산광역시"}
SHORT = {
    "서울특별시": "서울", "부산광역시": "부산", "대구광역시": "대구", "인천광역시": "인천", "광주광역시": "광주",
    "대전광역시": "대전", "울산광역시": "울산", "세종특별자치시": "세종", "경기도": "경기", "강원도": "강원",
    "충청북도": "충북", "충청남도": "충남", "전라북도": "전북", "전라남도": "전남", "경상북도": "경북",
    "경상남도": "경남", "제주특별자치도": "제주",
}
_CITY_WITH_GU = re.compile(r"^(.+시)(.+구)$")  # 포항시북구 → 포항시
# 주소·조합 이름에 아직 남아 있는 옛 지명
OLD_NAMES = {
    "남제주": ("제주특별자치도", "서귀포시"), "북제주": ("제주특별자치도", "제주시"),
    "삼천포": ("경상남도", "사천시"), "마산": ("경상남도", "창원시"), "진해": ("경상남도", "창원시"),
    "충무": ("경상남도", "통영시"),
}


class Municipalities:
    def __init__(self, places: dict[tuple[str, str], tuple[float, float]]):
        self.places = places  # (시·도, 시·군·구) → (위도, 경도)
        self.by_name: dict[str, list[tuple[str, str]]] = {}
        for province, name in places:
            self.by_name.setdefault(name, []).append((province, name))
        # 조합 이름 속에서 찾을 짧은 지명 ("거제시" → "거제"). 두 글자 이상만 — "중구" 같은 건 헷갈린다.
        self.stems: list[tuple[str, tuple[str, str]]] = []
        for province, name in places:
            stem = name[:-1] if name[-1] in "시군구" else name
            if len(stem) >= 2 and province not in METRO:
                self.stems.append((stem, (province, name)))
        self.stems.sort(key=lambda s: -len(s[0]))  # 긴 이름부터 — "남해"보다 "남해군"이 먼저 걸리게

    def _point(self, key: tuple[str, str]) -> dict:
        province, name = key
        lat, lon = self.places[key]
        return {"province": province, "name": f"{SHORT.get(province, province)} {name}", "lat": lat, "lon": lon}

    def from_address(self, address: str) -> dict | None:
        """"경북 구미시 선산읍" → 경북 구미시. 시·도만 있거나 못 찾으면 None."""
        tokens = (address or "").split()
        if len(tokens) < 2:
            return None
        province = province_of(tokens[0])
        for token in tokens[1:3]:
            for old, key in OLD_NAMES.items():
                if token.startswith(old) and key in self.places:
                    return self._point(key)
            if token[-1:] not in ("시", "군", "구"):
                continue
            if (province, token) in self.places:
                return self._point((province, token))
            # 시·도 이름이 바뀐 경우(전남광주통합특별시 광산구 …) 이름이 하나뿐이면 그걸 쓴다
            matches = self.by_name.get(token, [])
            if len(matches) == 1:
                return self._point(matches[0])
        return None

    def from_org_name(self, name: str, province_hint: str | None = None) -> dict | None:
        """"거제수산업협동조합" → 경남 거제시. 여러 곳이 걸리면(고성: 강원·경남) 시·도 힌트로 고르고,
        그래도 하나로 안 좁혀지면 None."""
        text = name or ""
        for old, key in OLD_NAMES.items():
            if old in text and key in self.places:
                return self._point(key)
        found = [(stem, key) for stem, key in self.stems if stem in text]
        if not found:
            return None
        longest = max(len(stem) for stem, _ in found)
        candidates = {key for stem, key in found if len(stem) == longest}
        if province_hint and len(candidates) > 1:
            candidates = {key for key in candidates if key[0] == province_hint} or candidates
        return self._point(candidates.pop()) if len(candidates) == 1 else None


def load_municipalities(data_dir: Path) -> Municipalities:
    grouped: dict[tuple[str, str], list[tuple[float, float]]] = {}
    path = data_dir / "municipalities.csv"
    if path.exists():
        with open(path, encoding="utf-8", newline="") as f:
            for row in csv.DictReader(f, delimiter="|"):
                province, name = row["province"], row["name"]
                match = _CITY_WITH_GU.match(name)
                if match and province not in METRO:
                    name = match.group(1)
                grouped.setdefault((province, name), []).append((float(row["lat"]), float(row["lon"])))
    places = {
        key: (round(statistics.fmean(p[0] for p in pts), 3), round(statistics.fmean(p[1] for p in pts), 3))
        for key, pts in grouped.items()
    }
    return Municipalities(places)
