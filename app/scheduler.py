"""매일 정해진 시각(KST)에 가격을 수집하고 DB를 백업한다.

외부 스케줄러(작업 스케줄러, cron)를 쓰지 않고 서버 안에서 돈다 — 서버를 켜두기만
하면 되고, 꺼져 있던 동안 빠진 날은 다음 수집 때 `collect()`가 알아서 채운다.
"""

from __future__ import annotations

import asyncio
import logging
import time
from datetime import datetime, timedelta
from pathlib import Path

from app import config

log = logging.getLogger(__name__)

BACKUPS_TO_KEEP = 14


def seconds_until(hour: int, now: datetime) -> float:
    target = now.replace(hour=hour, minute=0, second=0, microsecond=0)
    if target <= now:
        target += timedelta(days=1)
    return (target - now).total_seconds()


def backup_database(db, backup_dir: Path, now: datetime) -> Path | None:
    """하루 한 개. 같은 날 다시 불리면 건너뛴다."""
    if db.path == ":memory:":
        return None
    backup_dir.mkdir(parents=True, exist_ok=True)
    target = backup_dir / f"seasonal-{now:%Y%m%d}.db"
    if target.exists():
        return None
    db.backup_to(str(target))
    for old in sorted(backup_dir.glob("seasonal-*.db"))[:-BACKUPS_TO_KEEP]:
        old.unlink(missing_ok=True)
    return target


async def run_daily(prices, db, *, hour: int, backup_dir: Path, clock=time.time, fish=None) -> None:
    # 켜자마자 한 번. 처음 켤 때는 이게 1년치 거꾸로 채우기다.
    await _collect_once(prices, fish)
    while True:
        now = datetime.fromtimestamp(clock(), config.KST)
        await asyncio.sleep(seconds_until(hour, now))
        await _collect_once(prices, fish)
        try:
            await asyncio.to_thread(backup_database, db, backup_dir, datetime.now(config.KST))
        except Exception:
            log.exception("DB 백업 실패")


async def _collect_once(prices, fish=None) -> None:
    """화면에 바로 쓰이는 것(최근 소매가, 위판가)을 먼저 받고, 오래 걸리는 과거 자료는 마지막에."""
    try:
        result = await asyncio.to_thread(prices.collect)
        log.info("가격 수집 완료: %s", result)
    except Exception:
        # 수집이 실패해도 서버는 마지막 데이터로 계속 돈다. 화면에 기준일이 찍힌다.
        log.exception("가격 수집 실패")
    if fish is not None and fish.enabled:
        try:
            result = await asyncio.to_thread(fish.collect)
            log.info("수산물 위판 수집: %s", result)
        except Exception:
            log.exception("수산물 위판 수집 실패")
    try:
        # 평년가용 과거 데이터. 이미 받은 품목은 건너뛰어서 두 번째부터는 금방 끝난다.
        result = await asyncio.to_thread(prices.collect_history)
        log.info("과거 가격 수집: %s", result)
    except Exception:
        log.exception("과거 가격 수집 실패")
