"""FastAPI 앱.

`create_app`을 팩토리로 둔 이유는 테스트에서 DB 경로, 외부 API 클라이언트, 시계를
갈아끼우기 위해서다. 실제 실행은 `uvicorn --factory app.main:build_default_app`
(모듈을 불러오기만 해도 실제 DB를 여는 일이 없게 전역 app을 두지 않는다).
"""

from __future__ import annotations

import asyncio
import logging
import time
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app import auth, config
from app.catalog import load_catalog
from app.credits import LocalCredits
from app.db import Database
from app.atprice import AtClient
from app.prices import PriceService
from app.routes import router
from app.scheduler import run_daily

WEB_DIR = config.ROOT / "web"
DAY = 24 * 3600


def _load_secret(data_dir: Path) -> str:
    """쿠키 서명 키. 파일에 두어 재시작해도 로그인이 풀리지 않게 한다."""
    path = data_dir / "secret.key"
    if path.exists():
        return path.read_text(encoding="utf-8").strip()
    data_dir.mkdir(parents=True, exist_ok=True)
    secret = auth.generate_secret()
    path.write_text(secret, encoding="utf-8")
    return secret


def create_app(
    *,
    db_path: str = config.DB_PATH,
    data_dir: Path = config.DATA_DIR,
    at: AtClient | None = None,
    admins: frozenset[str] = config.ADMIN_USERS,
    secret: str | None = None,
    clock=time.time,
    run_scheduler: bool = True,
) -> FastAPI:
    db = Database(db_path)
    catalog = load_catalog(data_dir)
    prices = PriceService(db, catalog, at, clock=clock)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        task = None
        if run_scheduler:
            task = asyncio.create_task(
                run_daily(prices, db, hour=config.COLLECT_HOUR, backup_dir=data_dir / "backups")
            )
        yield
        if task:
            task.cancel()
        db.close()

    app = FastAPI(title="제철 장바구니", lifespan=lifespan)
    state = app.state
    state.db = db
    state.catalog = catalog
    state.prices = prices
    state.credits = LocalCredits(
        db,
        costs={"trend": config.TREND_COST, "where": config.WHERE_COST},
        unlock_hours=config.UNLOCK_HOURS,
        clock=clock,
    )
    state.admins = admins
    state.secret = secret or _load_secret(data_dir)
    state.signup_bonus = config.SIGNUP_BONUS
    state.clock = clock
    state.login_throttle = auth.LoginThrottle()
    state.signup_throttle = auth.LoginThrottle(
        max_failures=config.SIGNUPS_PER_IP_PER_DAY, window_seconds=DAY
    )

    @app.middleware("http")
    async def revalidate_static(request, call_next):
        # 화면 파일은 매번 바뀌었는지 묻게 한다(ETag로 안 바뀌었으면 304). 안 그러면
        # 고친 JS가 브라우저 캐시에 막혀 예전 화면이 한동안 보인다.
        response = await call_next(request)
        if not request.url.path.startswith("/api/"):
            response.headers.setdefault("Cache-Control", "no-cache")
        return response

    app.include_router(router)
    if WEB_DIR.exists():
        app.mount("/", StaticFiles(directory=WEB_DIR, html=True), name="web")
    return app


def build_default_app() -> FastAPI:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    at = AtClient(config.DATA_GO_KR_KEY) if config.at_enabled() else None
    return create_app(at=at)



