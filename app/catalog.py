"""품목 목록(items.csv)과 제철 표(seasons.csv).

둘 다 사람이 손으로 관리한다. aT 가격 데이터는 한 품목 안에 품종·등급·단위가 여럿 섞여
오고(고등어는 생물·냉동·수입 염장이 동시에 조사된다), 배추처럼 계절마다 조사 품종이
바뀌기도 한다. 어떤 행을 한 줄의 가격으로 이어 붙일지를 여기서 정한다.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass, field
from pathlib import Path

# 크기가 1이면 "1포기"처럼, 아니면 "100g", "10개"처럼 붙여 쓴다.
_UNITS_WITH_ONE = {"포기", "개", "마리", "kg", "손"}


@dataclass(frozen=True)
class AtCode:
    """공공데이터포털 aT 일별 도·소매 가격정보의 조회 조건."""

    category: str                 # 부류코드
    item: str                     # 품목코드
    varieties: tuple[str, ...]    # 이어 붙일 품종코드. 한 날짜에 여럿이면 조사 건수가 많은 쪽을 쓴다.
    grades: tuple[str, ...]       # 등급코드 (04 상품, 20 大 …)
    unit: str                     # 이 단위의 행만 쓴다 — 단위가 섞이면 가격이 튄다
    unit_size: str


@dataclass(frozen=True)
class Item:
    id: str
    name: str
    category: str
    at: AtCode
    season_months: frozenset[int] = field(default_factory=frozenset)
    main_region: str = ""
    season_note: str = ""

    @property
    def price_unit(self) -> str:
        return f"{self.at.unit_size}{self.at.unit}"

    def in_season(self, month: int) -> bool:
        return month in self.season_months


class Catalog:
    def __init__(self, items: list[Item]):
        self.items = items
        self._by_id = {item.id: item for item in items}

    def get(self, item_id: str) -> Item | None:
        return self._by_id.get(item_id)

    def __iter__(self):
        return iter(self.items)

    def __len__(self) -> int:
        return len(self.items)


def _codes(text: str) -> tuple[str, ...]:
    return tuple(code for code in text.split("|") if code)


def load_catalog(data_dir: Path) -> Catalog:
    seasons: dict[str, dict] = {}
    with open(data_dir / "seasons.csv", encoding="utf-8", newline="") as f:
        for row in csv.DictReader(f):
            seasons[row["item_id"]] = row

    items: list[Item] = []
    with open(data_dir / "items.csv", encoding="utf-8", newline="") as f:
        for row in csv.DictReader(f):
            at = AtCode(
                category=row["at_category"],
                item=row["at_item"],
                varieties=_codes(row["at_varieties"]),
                grades=_codes(row["at_grades"]),
                unit=row["at_unit"],
                unit_size=row["at_unit_size"],
            )
            if not (at.varieties and at.grades):
                raise ValueError(f"{row['id']}: 품종과 등급을 하나 이상 적어야 합니다")
            season = seasons.get(row["id"], {})
            months = frozenset(int(m) for m in season.get("months", "").split("|") if m)
            items.append(
                Item(
                    id=row["id"],
                    name=row["name"],
                    category=row["category"],
                    at=at,
                    season_months=months,
                    main_region=season.get("main_region", ""),
                    season_note=season.get("note", ""),
                )
            )
    missing = {item.id for item in items} - set(seasons)
    if missing:
        raise ValueError(f"seasons.csv에 없는 품목: {sorted(missing)}")
    return Catalog(items)
