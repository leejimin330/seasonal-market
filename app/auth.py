"""아이디 + 비밀번호 로그인. 헤아림(malice-dashboard)의 auth.py에서 가져왔다.

헤아림과 달리 여기는 누구나 가입하는 서비스라 계정마다 비밀번호가 따로 있다.
세션은 서버가 서명한 쿠키로 유지한다. 서버에 세션 목록을 두지 않으므로 재시작해도
로그인이 풀리지 않는다.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import re
import secrets
import time

COOKIE_NAME = "seasonal_session"
DEFAULT_TTL_SECONDS = 30 * 24 * 3600

USER_ID_PATTERN = re.compile(r"^[a-z0-9_]{3,20}$")
MIN_PASSWORD_LENGTH = 8

PBKDF2_ITERATIONS = 200_000


def validate_signup(user_id: str, password: str) -> str | None:
    """문제가 있으면 사용자에게 보여줄 문장을, 없으면 None."""
    if not USER_ID_PATTERN.match(user_id or ""):
        return "아이디는 영문 소문자, 숫자, 밑줄로 3~20자여야 합니다."
    if len(password or "") < MIN_PASSWORD_LENGTH:
        return f"비밀번호는 {MIN_PASSWORD_LENGTH}자 이상이어야 합니다."
    return None


def hash_password(password: str) -> str:
    """저장용 해시. 소금과 반복 횟수를 함께 담아 나중에 값을 올릴 수 있게 한다."""
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, PBKDF2_ITERATIONS)
    return f"pbkdf2${PBKDF2_ITERATIONS}${salt.hex()}${digest.hex()}"


def verify_password(password: str, stored: str) -> bool:
    """어떤 저장물이 와도 예외를 내지 않는다 — 형식이 깨졌으면 그냥 실패다."""
    try:
        scheme, iterations, salt_hex, digest_hex = stored.split("$")
        if scheme != "pbkdf2":
            return False
        digest = hashlib.pbkdf2_hmac(
            "sha256", password.encode(), bytes.fromhex(salt_hex), int(iterations)
        )
    except (ValueError, AttributeError):
        return False
    return hmac.compare_digest(digest.hex(), digest_hex)


# 없는 아이디로 로그인할 때도 같은 시간을 쓰게 하는 가짜 해시. 응답 시간으로 가입 여부가 새지 않게.
DUMMY_HASH = hash_password(secrets.token_hex(8))


def generate_secret() -> str:
    return secrets.token_urlsafe(32)


def _sign(payload: str, secret: str) -> str:
    digest = hmac.new(secret.encode(), payload.encode(), hashlib.sha256).digest()
    return base64.urlsafe_b64encode(digest).decode().rstrip("=")


def make_token(user_id: str, secret: str, *, expires_at: float | None = None) -> str:
    expiry = int(expires_at if expires_at is not None else time.time() + DEFAULT_TTL_SECONDS)
    name = base64.urlsafe_b64encode(user_id.encode()).decode().rstrip("=")
    payload = f"{name}.{expiry}"
    return f"{payload}.{_sign(payload, secret)}"


def read_token(token: str, secret: str) -> str | None:
    """유효하면 아이디를, 아니면 None. 어떤 입력에도 예외를 내지 않는다."""
    if not token:
        return None
    parts = token.split(".")
    if len(parts) != 3:
        return None

    name, expiry, signature = parts
    payload = f"{name}.{expiry}"
    # compare_digest로 비교한다 — 실패 시점이 서명 내용을 흘리지 않게
    if not hmac.compare_digest(signature, _sign(payload, secret)):
        return None

    try:
        if int(expiry) < time.time():
            return None
        padded = name + "=" * (-len(name) % 4)
        return base64.urlsafe_b64decode(padded).decode()
    except Exception:
        return None


class LoginThrottle:
    """키(IP 등)별 실패 횟수를 세어, 너무 많으면 잠시 막는다.

    메모리에만 두므로 서버를 재시작하면 초기화된다 — 대입 공격을 늦추는 것이 목적이지
    영구 차단이 아니다. 아이디별로 막지 않는 이유: 그러면 남이 일부러 틀려서 주인의
    로그인을 막을 수 있다. 가입 횟수 제한에도 같은 틀을 쓴다.
    """

    def __init__(self, max_failures: int = 10, window_seconds: float = 300, clock=time.monotonic):
        self.max_failures = max_failures
        self.window_seconds = window_seconds
        self.clock = clock
        self._failures: dict[str, list[float]] = {}

    def _recent(self, key: str) -> list[float]:
        cutoff = self.clock() - self.window_seconds
        recent = [t for t in self._failures.get(key, []) if t > cutoff]
        if recent:
            self._failures[key] = recent
        else:
            self._failures.pop(key, None)
        return recent

    def blocked(self, key: str) -> bool:
        return len(self._recent(key)) >= self.max_failures

    def record_failure(self, key: str) -> None:
        self._failures[key] = [*self._recent(key), self.clock()]
