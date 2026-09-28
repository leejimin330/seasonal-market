"""가격 수집과 요약.

`collect()` 하나로 처음 켤 때의 거꾸로 채우기와 매일의 추가 수집을 모두 한다 —
품목마다 마지막 날짜를 보고 비어 있는 만큼만 받는다. KAMIS는 지난 며칠 값을
고치기도 해서 마지막 날짜의 일주일 전부터 다시 받는다.
"""

from __future__ import annotations

import logging
import time
from datetime import date, datetime, timedelta

from app import config, sample
from app.catalog import Catalog
from app.db import Database
from app.kamis import KamisClient, KamisError

log = logging.getLogger(__name__)

REFETCH_DAYS = 7


def today_kst(clock=time.time) -> date:
    return datetime.fromtimestamp(clock(), config.KST).date()


class PriceService:
    def __init__(
        self,
        db: Database,
        catalog: Catalog,
        kamis: KamisClient | None,
        *,
        backfill_days: int = config.BACKFILL_DAYS,
        clock=time.time,
    ):
        self.db = db
        self.catalog = catalog
        self.kamis = kamis
        self.backfill_days = backfill_days
        self.clock = clock

    @property
    def source(self) -> str:
        return "kamis" if self.kamis else "sample"

    def collect(self) -> dict:
        today = today_kst(self.clock)
        # 모드가 바뀌었으면 다른 출처의 행을 지운다. 샘플과 실제 시세가 한 그래프에 섞이면 안 된다.
        for stale in self.db.price_sources() - {self.source}:
            log.info("가격 출처가 %s로 바뀌어 %s 행을 지웁니다", self.source, stale)
            self.db.delete_prices(stale)

        failed = []
        for item in self.catalog:
            last = self.db.last_price_date(item.id)
            if last:
                start = date.fromisoformat(last) - timedelta(days=REFETCH_DAYS)
            else:
                start = today - timedelta(days=self.backfill_days)
            try:
                rows = self._fetch(item, start, today)
            except KamisError as exc:
                log.warning("%s 가격 수집 실패: %s", item.id, exc)
                failed.append(item.id)
                continue
            if rows:
                self.db.upsert_prices(rows)

        result = {
            "source": self.source,
            "at": datetime.fromtimestamp(self.clock(), config.KST).isoformat(timespec="seconds"),
            "failed": failed,
        }
        self.db.set_meta("last_collect", result["at"])
        return result

    def _fetch(self, item, start: date, end: date) -> list[tuple]:
        if self.kamis is None:
            return sample.price_rows(item, start, end)
        if item.kamis is None:
            return []  # 코드를 모르는 품목은 가격 없이 최저가만 제공한다
        found = self.kamis.fetch_range(item.kamis, start, end)
        return [
            (item.id, day, values["price"], values["normal_price"], "kamis")
            for day, values in sorted(found.items())
        ]

    def summaries(self) -> dict[str, dict]:
        """품목별 무료 요약: 최근 가격, 기준일, 평년 대비 등락률(%)."""
        latest = self.db.latest_prices()
        result = {}
        for item in self.catalog:
            row = latest.get(item.id)
            if not row:
                result[item.id] = {"price": None, "date": None, "vs_normal": None, "source": None}
                continue
            vs_normal = None
            if row["price"] and row["normal_price"]:
                vs_normal = round((row["price"] / row["normal_price"] - 1) * 100, 1)
            result[item.id] = {
                "price": row["price"],
                "date": row["date"],
                "vs_normal": vs_normal,
                "source": row["source"],
            }
        return result

    def series(self, item_id: str, days: int = 366) -> list[dict]:
        since = (today_kst(self.clock) - timedelta(days=days)).isoformat()
        return self.db.price_series(item_id, since)
