"""도매·위판 품목의 이모지와 이야기 (data/auction_notes.csv, | 구분).

사람이 손으로 쓴 글이다. 없는 품목은 분류별 기본 이모지만 붙는다.
"""

from __future__ import annotations

import csv
from pathlib import Path

DEFAULT_EMOJI = {"fish": "🐟", "produce": "🥬"}


class Notes:
    def __init__(self, notes: dict[tuple[str, str], dict]):
        self.notes = notes

    def get(self, kind: str, name: str) -> dict:
        note = self.notes.get((kind, name))
        if note is None:
            # "갈치류" → "갈치", "홍합(섭조개)" → "홍합"으로 한 번 더 찾는다
            base = name.split("(")[0].removesuffix("류").strip()
            note = self.notes.get((kind, base))
        return {"emoji": (note or {}).get("emoji") or DEFAULT_EMOJI.get(kind, ""),
                "story": (note or {}).get("story", "")}


def load_notes(data_dir: Path) -> Notes:
    notes = {}
    path = data_dir / "auction_notes.csv"
    if path.exists():
        with open(path, encoding="utf-8", newline="") as f:
            for row in csv.DictReader(f, delimiter="|", quoting=csv.QUOTE_NONE):
                notes[(row["kind"], row["name"])] = row
    return Notes(notes)
