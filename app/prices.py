"""가격 수집, 평년가 계산, 요약.

수집은 두 단계다.
  1) `collect()` — 품목마다 최근 400일(처음) 또는 마지막 날짜 일주일 전부터(매일) 받는다.
     aT가 지난 며칠 값을 고치기도 해서 겹쳐 받는다. 화면이 빨리 차도록 이것부터 한다.
  2) `collect_history()` — 평년가를 계산할 과거 5년치를 품목마다 한 번만 받는다.
     호출이 많아(품목당 수십 번) 1)이 끝난 뒤 천천히 돈다. 끝나기 전에는 평년가가 비어 있다.
평년가는 KAMIS와 같은 정의: 지난 5년 같은 날짜(앞뒤 7일 평균) 중 최고·최저를 뺀 3년 평균.
"""

from __future__ import annotations

import logging
import statistics
import time
from datetime import date, datetime, timedelta

from app import config, sample
from app.atprice import AtClient, AtError, aggregate
from app.catalog import Catalog, Item
from app.db import Database

log = logging.getLogger(__name__)

REFETCH_DAYS = 7
NORMAL_WINDOW_DAYS = 7


def today_kst(clock=time.time) -> date:
    return datetime.fromtimestamp(clock(), config.KST).date()


def _years_before(day: date, years: int) -> date:
    try:
        return day.replace(year=day.year - years)
    except ValueError:  # 2월 29일
        return day.replace(year=day.year - years, day=28)


def normal_price(prices: dict[str, int], day: date, years: int = config.NORMAL_YEARS) -> int | None:
    """`day`의 평년가. 해마다 앞뒤 NORMAL_WINDOW_DAYS일 평균을 내고(주말·휴일 결측을 메운다),
    5년치가 다 있으면 최고·최저를 빼고 평균, 3~4년치면 그냥 평균, 그보다 적으면 None."""
    yearly = []
    for k in range(1, years + 1):
        center = _years_before(day, k)
        window = [
            prices[d.isoformat()]
            for offset in range(-NORMAL_WINDOW_DAYS, NORMAL_WINDOW_DAYS + 1)
            if (d := center + timedelta(days=offset)).isoformat() in prices
        ]
        if window:
            yearly.append(statistics.fmean(window))
    if len(yearly) < 3:
        return None
    if len(yearly) >= 5:
        yearly = sorted(yearly)[1:-1]
    return round(statistics.fmean(yearly))


class PriceService:
    def __init__(
        self,
        db: Database,
        catalog: Catalog,
        at: AtClient | None,
        *,
        recent_days: int = config.RECENT_DAYS,
        normal_years: int = config.NORMAL_YEARS,
        breakdown_days: int = config.BREAKDOWN_DAYS,
        clock=time.time,
    ):
        self.db = db
        self.catalog = catalog
        self.at = at
        self.recent_days = recent_days
        self.normal_years = normal_years
        self.breakdown_days = breakdown_days
        self.clock = clock

    @property
    def source(self) -> str:
        return "at" if self.at else "sample"

    # ── 수집 ────────────────────────────────────────────────

    def collect(self) -> dict:
        today = today_kst(self.clock)
        # 모드가 바뀌었으면 다른 출처의 행을 지운다. 샘플과 실제 시세가 한 그래프에 섞이면 안 된다.
        for stale in self.db.price_sources() - {self.source}:
            log.info("가격 출처가 %s로 바뀌어 %s 행을 지웁니다", self.source, stale)
            self.db.delete_prices(stale)
            self.db.delete_breakdowns(stale)

        failed = []
        for item in self.catalog:
            last = self.db.last_price_date(item.id)
            if last:
                start = date.fromisoformat(last) - timedelta(days=REFETCH_DAYS)
            else:
                start = today - timedelta(days=self.recent_days)
            try:
                self._store(item, start, today)
            except AtError as exc:
                log.warning("%s 가격 수집 실패: %s", item.id, exc)
                failed.append(item.id)

        self.db.prune_breakdowns((today - timedelta(days=self.breakdown_days)).isoformat())
        result = {
            "source": self.source,
            "at": datetime.fromtimestamp(self.clock(), config.KST).isoformat(timespec="seconds"),
            "failed": failed,
        }
        self.db.set_meta("last_collect", result["at"])
        return result

    def collect_history(self) -> dict:
        """평년가용 과거 데이터. 품목마다 한 번만 — 끝난 품목은 meta에 적어 건너뛴다."""
        done, failed = [], []
        for item in self.catalog:
            flag = f"history:{self.source}:{item.id}"
            if self.db.get_meta(flag):
                continue
            first = self.db.first_price_date(item.id)
            if not first:
                continue  # 최근 데이터부터 채워져야 한다
            end = date.fromisoformat(first) - timedelta(days=1)
            start = _years_before(date.fromisoformat(first), self.normal_years) - timedelta(days=NORMAL_WINDOW_DAYS)
            try:
                if start <= end:
                    self._store(item, start, end, breakdowns=False)
            except AtError as exc:
                log.warning("%s 과거 가격 수집 실패: %s", item.id, exc)
                failed.append(item.id)
                continue
            self.db.set_meta(flag, datetime.now(config.KST).isoformat(timespec="seconds"))
            done.append(item.id)
        return {"done": done, "failed": failed}

    def _store(self, item: Item, start: date, end: date, *, breakdowns: bool = True) -> None:
        if self.at is None:
            days = sample.aggregate(item, start, end)
        else:
            days = aggregate(self.at.fetch_rows(item.at, start, end))
        if days:
            self.db.upsert_prices(
                [(item.id, day, values["price"], None, self.source) for day, values in sorted(days.items())]
            )
        if breakdowns:
            since = (today_kst(self.clock) - timedelta(days=self.breakdown_days)).isoformat()
            self.db.put_breakdowns(
                [
                    (item.id, day, {"channels": v["channels"], "regions": v["regions"], "n": v["n"]}, self.source)
                    for day, v in days.items()
                    if day >= since
                ]
            )
        self._refresh_normals(item.id)

    def _refresh_normals(self, item_id: str) -> None:
        prices = self.db.all_prices(item_id)
        since = (today_kst(self.clock) - timedelta(days=self.recent_days)).isoformat()
        targets = [day for day in prices if day >= since]
        self.db.set_normals(
            item_id, {day: normal_price(prices, date.fromisoformat(day), self.normal_years) for day in targets}
        )

    # ── 읽기 ────────────────────────────────────────────────

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

    def breakdown(self, item_id: str) -> dict | None:
        return self.db.latest_breakdown(item_id)

    def history_progress(self) -> dict:
        done = sum(1 for item in self.catalog if self.db.get_meta(f"history:{self.source}:{item.id}"))
        return {"done": done, "total": len(self.catalog)}
