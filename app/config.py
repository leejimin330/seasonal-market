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

# 공공데이터포털 "한국농수산식품유통공사_일별 도,소매 가격정보" 일반 인증키.
# KAMIS 오픈API는 기업 정보가 있어야 신청돼서 이쪽을 쓴다 (개인 자동승인). 없으면 샘플 데이터로 돈다.
DATA_GO_KR_KEY = os.environ.get("DATA_GO_KR_KEY", "").strip()

# 크레딧 (설계 2/4). 이용권은 품목 하나 × 기능 하나 단위로 24시간 열린다.
# 유료: 가격 추이(소매·도매·위판 모두, 2026-09-29 다시 유료로), 어디서 살까.
SIGNUP_BONUS = int(os.environ.get("SEASONAL_SIGNUP_BONUS", "20"))
TREND_COST = int(os.environ.get("SEASONAL_TREND_COST", "1"))
WHERE_COST = int(os.environ.get("SEASONAL_WHERE_COST", "2"))
UNLOCK_HOURS = float(os.environ.get("SEASONAL_UNLOCK_HOURS", "24"))

# 관리자 아이디. 계정 자체는 `python -m app.cli create-user`로 만든다 —
# 가입 화면으로 만들게 하면 남이 먼저 그 아이디를 선점할 수 있다.
ADMIN_USERS = frozenset(
    name.strip() for name in os.environ.get("SEASONAL_ADMIN_USERS", "").split(",") if name.strip()
)

# 가입 보너스를 노린 반복 가입을 늦춘다. IP당 하루 이 횟수까지만 가입할 수 있다.
SIGNUPS_PER_IP_PER_DAY = int(os.environ.get("SEASONAL_SIGNUPS_PER_IP_PER_DAY", "3"))

# 매일 가격을 수집하는 시각(KST, 시). aT는 그날 조사 가격을 오후에 올리고, 다음 날 새벽이면 확실하다.
COLLECT_HOUR = int(os.environ.get("SEASONAL_COLLECT_HOUR", "5"))
# 처음 켤 때 먼저 채우는 기간(일). 추이 그래프(최대 1년)가 첫날부터 비어 있지 않게.
RECENT_DAYS = int(os.environ.get("SEASONAL_RECENT_DAYS", "400"))
# 평년가 계산에 쓰는 햇수. KAMIS와 같이 5년 중 최고·최저를 뺀 3년 평균.
NORMAL_YEARS = int(os.environ.get("SEASONAL_NORMAL_YEARS", "5"))
# 농산물 도매 경매를 다시 받는 주기(초). 오늘 자료만 주는 API라 자주 받아 오늘 치를 채운다.
PRODUCE_INTERVAL = float(os.environ.get("SEASONAL_PRODUCE_INTERVAL", str(3 * 3600)))
# 판매처 유형별 비교를 남겨두는 기간(일).
BREAKDOWN_DAYS = int(os.environ.get("SEASONAL_BREAKDOWN_DAYS", "30"))


def at_enabled() -> bool:
    return bool(DATA_GO_KR_KEY)
