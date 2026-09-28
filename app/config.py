"""환경 설정. 값은 환경변수 또는 `.env`에서 온다."""

import os
from datetime import timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"


def _load_dotenv() -> None:
    env_file = ROOT / ".env"
    if not env_file.exists():
        return
    for line in env_file.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip())


_load_dotenv()

# 윈도우에는 tzdata가 없어 zoneinfo("Asia/Seoul")가 깨진다. 한국은 서머타임이 없으니 고정 오프셋이면 된다.
KST = timezone(timedelta(hours=9))

DB_PATH = os.environ.get("SEASONAL_DB_PATH", str(DATA_DIR / "seasonal.db"))
PORT = int(os.environ.get("SEASONAL_PORT", "8741"))

# KAMIS(aT 농산물유통정보) 오픈API. 둘 다 있어야 실제 가격을 받는다. 없으면 샘플 데이터로 돈다.
KAMIS_CERT_KEY = os.environ.get("KAMIS_CERT_KEY", "").strip()
KAMIS_CERT_ID = os.environ.get("KAMIS_CERT_ID", "").strip()

# 네이버 검색 API(쇼핑). 없으면 최저가도 샘플로 돈다.
NAVER_CLIENT_ID = os.environ.get("NAVER_CLIENT_ID", "").strip()
NAVER_CLIENT_SECRET = os.environ.get("NAVER_CLIENT_SECRET", "").strip()

# 크레딧 (설계 2/4). 이용권은 품목 하나 × 기능 하나 단위로 24시간 열린다.
SIGNUP_BONUS = int(os.environ.get("SEASONAL_SIGNUP_BONUS", "20"))
TREND_COST = int(os.environ.get("SEASONAL_TREND_COST", "1"))
SHOP_COST = int(os.environ.get("SEASONAL_SHOP_COST", "2"))
UNLOCK_HOURS = float(os.environ.get("SEASONAL_UNLOCK_HOURS", "24"))

# 관리자 아이디. 계정 자체는 `python -m app.cli create-user --admin`으로 만든다 —
# 가입 화면으로 만들게 하면 남이 먼저 그 아이디를 선점할 수 있다.
ADMIN_USERS = frozenset(
    name.strip() for name in os.environ.get("SEASONAL_ADMIN_USERS", "").split(",") if name.strip()
)

# 가입 보너스를 노린 반복 가입을 늦춘다. IP당 하루 이 횟수까지만 가입할 수 있다.
SIGNUPS_PER_IP_PER_DAY = int(os.environ.get("SEASONAL_SIGNUPS_PER_IP_PER_DAY", "3"))

# 네이버 결과를 품목별로 공유 캐시하는 시간(초). 결제는 사람마다, 호출은 한 번.
SHOP_CACHE_SECONDS = float(os.environ.get("SEASONAL_SHOP_CACHE_SECONDS", "3600"))

# 매일 가격을 수집하는 시각(KST, 시). KAMIS는 전날 조사 가격이 아침에 올라온다.
COLLECT_HOUR = int(os.environ.get("SEASONAL_COLLECT_HOUR", "5"))
# 처음 켤 때 거꾸로 채우는 기간(일). 추이 그래프가 첫날부터 비어 있지 않게.
BACKFILL_DAYS = int(os.environ.get("SEASONAL_BACKFILL_DAYS", "400"))


def kamis_enabled() -> bool:
    return bool(KAMIS_CERT_KEY and KAMIS_CERT_ID)


def naver_enabled() -> bool:
    return bool(NAVER_CLIENT_ID and NAVER_CLIENT_SECRET)
