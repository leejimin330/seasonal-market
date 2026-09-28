"""품목 목록(items.csv)과 제철 표(seasons.csv).

둘 다 사람이 손으로 관리한다. KAMIS 품목 코드는 등급·단위가 복잡해서 API로 자동
매핑하기보다 좁은 목록을 직접 맞추는 쪽이 빠르고 정확하다 (기획서 10절).
"""

from __future__ import annotations

import csv
from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True)
class KamisCode:
    category: str
    item: str
    kind: str
    rank: str
    verified: bool


@dataclass(frozen=True)
class Item:
    id: str
    name: str
    category: str
    price_unit: str          # KAMIS 소매가의 단위 ("100g", "1포기" …). 화면에 가격과 함께 쓴다.
    kamis: KamisCode | None  # 코드를 모르는 품목은 None — 가격 없이 최저가만 제공한다
    shop_query: str
    shop_unit: str           # "g" 또는 "ea"
    shop_qty: int            # 비교 기준량. g이면 1000(=1kg당), ea이면 1(=1개당)
    shop_label: str          # 화면용 기준 단위 ("1kg", "1마리")
    season_months: frozenset[int] = field(default_factory=frozenset)
    main_region: str = ""
    season_note: str = ""

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


def load_catalog(data_dir: Path) -> Catalog:
    seasons: dict[str, dict] = {}
    with open(data_dir / "seasons.csv", encoding="utf-8", newline="") as f:
        for row in csv.DictReader(f):
            seasons[row["item_id"]] = row

    items: list[Item] = []
    with open(data_dir / "items.csv", encoding="utf-8", newline="") as f:
        for row in csv.DictReader(f):
            if row["shop_unit"] not in ("g", "ea"):
                raise ValueError(f"{row['id']}: shop_unit은 g 또는 ea여야 합니다")
            kamis = None
            if row["kamis_item"]:
                kamis = KamisCode(
                    category=row["kamis_category"],
                    item=row["kamis_item"],
                    kind=row["kamis_kind"],
                    rank=row["kamis_rank"],
                    verified=row["kamis_verified"] == "1",
                )
            season = seasons.get(row["id"], {})
            months = frozenset(int(m) for m in season.get("months", "").split("|") if m)
            items.append(
                Item(
                    id=row["id"],
                    name=row["name"],
                    category=row["category"],
                    price_unit=row["price_unit"],
                    kamis=kamis,
                    shop_query=row["shop_query"],
                    shop_unit=row["shop_unit"],
                    shop_qty=int(row["shop_qty"]),
                    shop_label=row["shop_label"],
                    season_months=months,
                    main_region=season.get("main_region", ""),
                    season_note=season.get("note", ""),
                )
            )
    missing = {item.id for item in items} - set(seasons)
    if missing:
        raise ValueError(f"seasons.csv에 없는 품목: {sorted(missing)}")
    return Catalog(items)
