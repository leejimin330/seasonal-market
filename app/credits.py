"""크레딧 조회·차감·지급.

나머지 코드는 이 파일의 `CreditService`만 부른다. 지금은 우리 DB에 잔액을 두는
`LocalCredits`이고, AI 웹 모음 플랫폼의 공용 재화 API가 생기면 같은 메서드를 가진
`PlatformCredits`를 만들어 `create_app`에서 갈아끼운다 — 라우트는 건드리지 않는다.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Protocol

from app.db import Database, InsufficientCredits

__all__ = ["CreditService", "LocalCredits", "InsufficientCredits", "Charge", "FEATURES"]

# 유료 기능 이름. 장부와 이용권 표에 이 문자열 그대로 남는다.
FEATURES = ("trend", "shop")


@dataclass(frozen=True)
class Charge:
    charged: bool        # 이번 요청에서 실제로 차감했는지 (이용권이 살아 있었으면 False)
    cost: int
    expires_at: float    # 이용권 만료 시각 (epoch 초)
    balance: int         # 처리 후 잔액


class CreditService(Protocol):
    def balance(self, user_id: str) -> int: ...

    def unlocked_until(self, user_id: str, feature: str, item_id: str) -> float | None: ...

    def can_afford(self, user_id: str, feature: str, item_id: str) -> bool:
        """차감 없이 "지금 쓰면 되는지"만 본다. 외부 호출 전에 쓴다 — 돈 안 낼 사람 때문에
        네이버 API를 부르지 않게."""
        ...

    def use(self, user_id: str, feature: str, item_id: str) -> Charge:
        """이용권이 있으면 그대로 통과, 없으면 차감하고 연다. 모자라면 InsufficientCredits."""
        ...

    def grant(self, user_id: str, amount: int, *, actor: str, memo: str) -> int: ...

    def history(self, user_id: str) -> list[dict]: ...


class LocalCredits:
    def __init__(self, db: Database, *, costs: dict[str, int], unlock_hours: float, clock=time.time):
        unknown = set(costs) - set(FEATURES)
        if unknown:
            raise ValueError(f"모르는 기능: {unknown}")
        self.db = db
        self.costs = dict(costs)
        self.unlock_hours = unlock_hours
        self.clock = clock

    def cost(self, feature: str) -> int:
        return self.costs[feature]

    def balance(self, user_id: str) -> int:
        return self.db.balance(user_id)

    def unlocked_until(self, user_id: str, feature: str, item_id: str) -> float | None:
        return self.db.unlock_expiry(user_id, feature, item_id, self.clock())

    def can_afford(self, user_id: str, feature: str, item_id: str) -> bool:
        if self.unlocked_until(user_id, feature, item_id):
            return True
        return self.balance(user_id) >= self.cost(feature)

    def use(self, user_id: str, feature: str, item_id: str) -> Charge:
        cost = self.cost(feature)
        charged, expires_at = self.db.use_feature(
            user_id, feature, item_id, cost=cost, now=self.clock(), hours=self.unlock_hours
        )
        return Charge(charged, cost if charged else 0, expires_at, self.balance(user_id))

    def grant(self, user_id: str, amount: int, *, actor: str, memo: str) -> int:
        return self.db.grant(user_id, amount, actor=actor, memo=memo, now=self.clock())

    def history(self, user_id: str) -> list[dict]:
        return self.db.ledger(user_id)
