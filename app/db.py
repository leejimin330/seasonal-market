"""SQLite 저장소.

연결 하나를 잠금으로 감싸 쓴다. FastAPI의 동기 엔드포인트는 스레드 풀에서 돌기 때문에,
크레딧 차감처럼 "읽고 → 판단하고 → 쓰는" 일은 잠금 안의 트랜잭션 하나로 끝내야
동시에 두 번 눌렀을 때 잔액이 음수가 되지 않는다.
"""

from __future__ import annotations

import json
import sqlite3
import threading
from contextlib import contextmanager
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id            TEXT PRIMARY KEY,
    password_hash TEXT NOT NULL,
    credits       INTEGER NOT NULL DEFAULT 0 CHECK (credits >= 0),
    created_at    REAL NOT NULL
);

-- 크레딧이 움직인 모든 기록. 잔액은 users.credits에 두고, 이 표는 근거다.
-- 나중에 플랫폼 재화로 옮길 때도 이 장부가 기준이 된다.
CREATE TABLE IF NOT EXISTS credit_ledger (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id       TEXT NOT NULL REFERENCES users(id),
    delta         INTEGER NOT NULL,
    balance_after INTEGER NOT NULL,
    reason        TEXT NOT NULL,          -- signup_bonus / use / admin_grant
    feature       TEXT,                   -- trend / where (reason=use일 때)
    item_id       TEXT,
    memo          TEXT,
    actor         TEXT,                   -- 지급한 관리자
    created_at    REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_ledger_user ON credit_ledger(user_id, id);

-- 품목 하나 × 기능 하나의 이용권. 만료 전에는 다시 차감하지 않는다.
CREATE TABLE IF NOT EXISTS unlocks (
    user_id    TEXT NOT NULL,
    feature    TEXT NOT NULL,
    item_id    TEXT NOT NULL,
    expires_at REAL NOT NULL,
    PRIMARY KEY (user_id, feature, item_id)
);

-- 날짜별 전국 평균 소매가와 평년가. source는 at / sample — 샘플이 실제 데이터에 섞이지 않게 구분한다.
-- 평년가는 수집 뒤 과거 5년치로 다시 계산해 채운다.
CREATE TABLE IF NOT EXISTS daily_prices (
    item_id      TEXT NOT NULL,
    date         TEXT NOT NULL,           -- YYYY-MM-DD (KST)
    price        INTEGER,
    normal_price INTEGER,
    source       TEXT NOT NULL,
    PRIMARY KEY (item_id, date)
);

-- 최근 한 달의 판매처 유형별·지역별 가격 (유료 "어디서 살까"). 날짜별 JSON 한 덩어리.
CREATE TABLE IF NOT EXISTS price_breakdown (
    item_id TEXT NOT NULL,
    date    TEXT NOT NULL,
    data    TEXT NOT NULL,
    source  TEXT NOT NULL,
    PRIMARY KEY (item_id, date)
);

-- 수산물 산지 위판가: 어종 × 상태 × 날짜 합계. regions/market_prices는 {이름: [금액, 중량]} JSON.
CREATE TABLE IF NOT EXISTS fish_daily (
    code          TEXT NOT NULL,
    state         TEXT NOT NULL,
    date          TEXT NOT NULL,
    name          TEXT NOT NULL,
    amount        INTEGER NOT NULL,
    weight        REAL NOT NULL,
    n             INTEGER NOT NULL,
    markets       INTEGER NOT NULL,
    min_kg        INTEGER,
    max_kg        INTEGER,
    regions       TEXT NOT NULL,
    market_prices TEXT NOT NULL,
    PRIMARY KEY (code, state, date)
);
CREATE INDEX IF NOT EXISTS idx_fish_date ON fish_daily(date);

-- 위판 자료를 받은 날. 기록이 0건인 날(휴장)도 남겨 다시 받지 않게 한다.
CREATE TABLE IF NOT EXISTS fish_days (
    date       TEXT PRIMARY KEY,
    rows       INTEGER NOT NULL,
    fetched_at REAL NOT NULL
);

-- 농산물 도매시장 경매가 (전국 공영도매시장 실시간 경매정보). fish_daily와 같은 모양이고,
-- state 칸에는 품종, category 칸에는 부류(과실류·엽경채류 …)가 들어간다.
CREATE TABLE IF NOT EXISTS produce_daily (
    code          TEXT NOT NULL,
    state         TEXT NOT NULL,
    date          TEXT NOT NULL,
    name          TEXT NOT NULL,
    amount        INTEGER NOT NULL,
    weight        REAL NOT NULL,
    n             INTEGER NOT NULL,
    markets       INTEGER NOT NULL,
    min_kg        INTEGER,
    max_kg        INTEGER,
    regions       TEXT NOT NULL,
    market_prices TEXT NOT NULL,
    category      TEXT NOT NULL DEFAULT '',
    PRIMARY KEY (code, state, date)
);
CREATE INDEX IF NOT EXISTS idx_produce_date ON produce_daily(date);

CREATE TABLE IF NOT EXISTS produce_days (
    date       TEXT PRIMARY KEY,
    rows       INTEGER NOT NULL,
    fetched_at REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS meta (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

-- 사이트 열람 수. kind: item(소매 품목 id) | fish | produce (key는 "코드|상태").
CREATE TABLE IF NOT EXISTS page_views (
    kind  TEXT NOT NULL,
    key   TEXT NOT NULL,
    day   TEXT NOT NULL,
    count INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (kind, key, day)
);
"""


class InsufficientCredits(Exception):
    def __init__(self, balance: int, cost: int):
        super().__init__(f"크레딧 부족: 잔액 {balance}, 필요 {cost}")
        self.balance = balance
        self.cost = cost


class Database:
    def __init__(self, path: str):
        if path != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.path = path
        self._conn = sqlite3.connect(path, check_same_thread=False, isolation_level=None)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA foreign_keys = ON")
        if path != ":memory:":
            self._conn.execute("PRAGMA journal_mode = WAL")
        self._lock = threading.RLock()
        self._conn.executescript(SCHEMA)
        # 예전 DB에는 fish_daily.category가 없다.
        columns = {row["name"] for row in self._conn.execute("PRAGMA table_info(fish_daily)")}
        if "category" not in columns:
            self._conn.execute("ALTER TABLE fish_daily ADD COLUMN category TEXT NOT NULL DEFAULT ''")

    def close(self) -> None:
        self._conn.close()

    @contextmanager
    def transaction(self):
        with self._lock:
            self._conn.execute("BEGIN IMMEDIATE")
            try:
                yield self._conn
            except BaseException:
                self._conn.execute("ROLLBACK")
                raise
            else:
                self._conn.execute("COMMIT")

    def _query(self, sql: str, params=()) -> list[sqlite3.Row]:
        with self._lock:
            return self._conn.execute(sql, params).fetchall()

    # ── 열람 수 ─────────────────────────────────────────────

    def add_view(self, kind: str, key: str, day: str) -> None:
        with self._lock:
            self._conn.execute(
                "INSERT INTO page_views(kind, key, day, count) VALUES (?, ?, ?, 1) "
                "ON CONFLICT(kind, key, day) DO UPDATE SET count = count + 1",
                (kind, key, day),
            )

    def views_since(self, day: str) -> list[tuple[str, str, int]]:
        rows = self._query(
            "SELECT kind, key, SUM(count) AS n FROM page_views WHERE day >= ? GROUP BY kind, key", (day,))
        return [(r["kind"], r["key"], r["n"]) for r in rows]

    # ── 사용자 ──────────────────────────────────────────────

    def get_user(self, user_id: str) -> sqlite3.Row | None:
        rows = self._query("SELECT * FROM users WHERE id = ?", (user_id,))
        return rows[0] if rows else None

    def create_user(self, user_id: str, password_hash: str, *, bonus: int, now: float) -> bool:
        """이미 있으면 False. 가입 보너스도 같은 트랜잭션에서 장부에 남긴다."""
        with self.transaction() as conn:
            exists = conn.execute("SELECT 1 FROM users WHERE id = ?", (user_id,)).fetchone()
            if exists:
                return False
            conn.execute(
                "INSERT INTO users (id, password_hash, credits, created_at) VALUES (?, ?, ?, ?)",
                (user_id, password_hash, bonus, now),
            )
            if bonus:
                conn.execute(
                    "INSERT INTO credit_ledger (user_id, delta, balance_after, reason, created_at)"
                    " VALUES (?, ?, ?, 'signup_bonus', ?)",
                    (user_id, bonus, bonus, now),
                )
        return True

    def set_password(self, user_id: str, password_hash: str) -> None:
        with self.transaction() as conn:
            conn.execute("UPDATE users SET password_hash = ? WHERE id = ?", (password_hash, user_id))

    def list_users(self) -> list[dict]:
        rows = self._query("SELECT id, credits, created_at FROM users ORDER BY created_at DESC")
        return [dict(row) for row in rows]

    # ── 크레딧 ──────────────────────────────────────────────

    def balance(self, user_id: str) -> int:
        rows = self._query("SELECT credits FROM users WHERE id = ?", (user_id,))
        return rows[0]["credits"] if rows else 0

    def unlock_expiry(self, user_id: str, feature: str, item_id: str, now: float) -> float | None:
        rows = self._query(
            "SELECT expires_at FROM unlocks WHERE user_id = ? AND feature = ? AND item_id = ?"
            " AND expires_at > ?",
            (user_id, feature, item_id, now),
        )
        return rows[0]["expires_at"] if rows else None

    def use_feature(
        self, user_id: str, feature: str, item_id: str, *, cost: int, now: float, hours: float
    ) -> tuple[bool, float]:
        """이용권이 살아 있으면 그대로, 아니면 차감하고 새로 연다.

        돌려주는 값은 (이번에 차감했는지, 이용권 만료 시각). 잔액이 모자라면
        InsufficientCredits — 이때 DB는 아무것도 바뀌지 않는다.
        """
        with self.transaction() as conn:
            row = conn.execute(
                "SELECT expires_at FROM unlocks WHERE user_id = ? AND feature = ? AND item_id = ?"
                " AND expires_at > ?",
                (user_id, feature, item_id, now),
            ).fetchone()
            if row:
                return False, row["expires_at"]

            balance = conn.execute(
                "SELECT credits FROM users WHERE id = ?", (user_id,)
            ).fetchone()
            balance = balance["credits"] if balance else 0
            if balance < cost:
                raise InsufficientCredits(balance, cost)

            after = balance - cost
            expires_at = now + hours * 3600
            conn.execute("UPDATE users SET credits = ? WHERE id = ?", (after, user_id))
            conn.execute(
                "INSERT INTO credit_ledger (user_id, delta, balance_after, reason, feature, item_id,"
                " created_at) VALUES (?, ?, ?, 'use', ?, ?, ?)",
                (user_id, -cost, after, feature, item_id, now),
            )
            conn.execute(
                "INSERT OR REPLACE INTO unlocks (user_id, feature, item_id, expires_at)"
                " VALUES (?, ?, ?, ?)",
                (user_id, feature, item_id, expires_at),
            )
            return True, expires_at

    def grant(self, user_id: str, amount: int, *, actor: str, memo: str, now: float) -> int:
        """관리자 지급. 새 잔액을 돌려준다. 없는 사용자면 KeyError."""
        with self.transaction() as conn:
            row = conn.execute("SELECT credits FROM users WHERE id = ?", (user_id,)).fetchone()
            if row is None:
                raise KeyError(user_id)
            after = row["credits"] + amount
            conn.execute("UPDATE users SET credits = ? WHERE id = ?", (after, user_id))
            conn.execute(
                "INSERT INTO credit_ledger (user_id, delta, balance_after, reason, memo, actor,"
                " created_at) VALUES (?, ?, ?, 'admin_grant', ?, ?, ?)",
                (user_id, amount, after, memo, actor, now),
            )
            return after

    def ledger(self, user_id: str, limit: int = 50) -> list[dict]:
        rows = self._query(
            "SELECT delta, balance_after, reason, feature, item_id, memo, created_at"
            " FROM credit_ledger WHERE user_id = ? ORDER BY id DESC LIMIT ?",
            (user_id, limit),
        )
        return [dict(row) for row in rows]

    # ── 가격 ────────────────────────────────────────────────

    def upsert_prices(self, rows: list[tuple[str, str, int | None, int | None, str]]) -> None:
        """(item_id, date, price, normal_price, source) 목록을 넣는다. 같은 날짜는 덮어쓴다."""
        with self.transaction() as conn:
            conn.executemany(
                "INSERT OR REPLACE INTO daily_prices (item_id, date, price, normal_price, source)"
                " VALUES (?, ?, ?, ?, ?)",
                rows,
            )

    def delete_prices(self, source: str) -> None:
        with self.transaction() as conn:
            conn.execute("DELETE FROM daily_prices WHERE source = ?", (source,))

    def price_sources(self) -> set[str]:
        return {row["source"] for row in self._query("SELECT DISTINCT source FROM daily_prices")}

    def latest_prices(self) -> dict[str, dict]:
        """품목별 가장 최근의 (가격이 있는) 행."""
        rows = self._query(
            "SELECT p.item_id, p.date, p.price, p.normal_price, p.source FROM daily_prices p"
            " JOIN (SELECT item_id, MAX(date) AS date FROM daily_prices WHERE price IS NOT NULL"
            "       GROUP BY item_id) latest"
            " ON latest.item_id = p.item_id AND latest.date = p.date"
        )
        return {row["item_id"]: dict(row) for row in rows}

    def price_series(self, item_id: str, since: str) -> list[dict]:
        rows = self._query(
            "SELECT date, price, normal_price FROM daily_prices"
            " WHERE item_id = ? AND date >= ? ORDER BY date",
            (item_id, since),
        )
        return [dict(row) for row in rows]

    def last_price_date(self, item_id: str) -> str | None:
        rows = self._query(
            "SELECT MAX(date) AS date FROM daily_prices WHERE item_id = ?", (item_id,)
        )
        return rows[0]["date"] if rows else None

    def all_prices(self, item_id: str) -> dict[str, int]:
        """평년가 계산용. {날짜: 가격} 전체."""
        rows = self._query(
            "SELECT date, price FROM daily_prices WHERE item_id = ? AND price IS NOT NULL", (item_id,)
        )
        return {row["date"]: row["price"] for row in rows}

    def first_price_date(self, item_id: str) -> str | None:
        rows = self._query("SELECT MIN(date) AS date FROM daily_prices WHERE item_id = ?", (item_id,))
        return rows[0]["date"] if rows else None

    def set_normals(self, item_id: str, normals: dict[str, int | None]) -> None:
        with self.transaction() as conn:
            conn.executemany(
                "UPDATE daily_prices SET normal_price = ? WHERE item_id = ? AND date = ?",
                [(value, item_id, day) for day, value in normals.items()],
            )

    # ── 판매처 유형별 / 메타 ────────────────────────────────

    def put_breakdowns(self, rows: list[tuple[str, str, dict, str]]) -> None:
        """(item_id, date, data, source)"""
        with self.transaction() as conn:
            conn.executemany(
                "INSERT OR REPLACE INTO price_breakdown (item_id, date, data, source) VALUES (?, ?, ?, ?)",
                [(item, day, json.dumps(data, ensure_ascii=False), source) for item, day, data, source in rows],
            )

    def latest_breakdown(self, item_id: str) -> dict | None:
        rows = self._query(
            "SELECT date, data FROM price_breakdown WHERE item_id = ? ORDER BY date DESC LIMIT 1", (item_id,)
        )
        if not rows:
            return None
        return {"date": rows[0]["date"], **json.loads(rows[0]["data"])}

    def prune_breakdowns(self, before: str) -> None:
        with self.transaction() as conn:
            conn.execute("DELETE FROM price_breakdown WHERE date < ?", (before,))

    def delete_breakdowns(self, source: str) -> None:
        with self.transaction() as conn:
            conn.execute("DELETE FROM price_breakdown WHERE source = ?", (source,))

    # ── 경매가 (수산물 위판 fish / 농산물 도매 produce) ─────────

    AUCTION_TABLES = ("fish", "produce")

    def _auction(self, table: str) -> str:
        if table not in self.AUCTION_TABLES:  # 표 이름은 SQL에 그대로 들어가니 정해진 것만
            raise ValueError(table)
        return table

    def fish_days(self, table: str = "fish") -> set[str]:
        t = self._auction(table)
        return {row["date"] for row in self._query(f"SELECT date FROM {t}_days")}

    def put_fish_day(self, day: str, groups: list[dict], rows: int, now: float, table: str = "fish") -> None:
        t = self._auction(table)
        with self.transaction() as conn:
            conn.execute(f"DELETE FROM {t}_daily WHERE date = ?", (day,))
            conn.executemany(
                f"INSERT INTO {t}_daily (code, state, date, name, amount, weight, n, markets, min_kg, max_kg,"
                " regions, market_prices, category) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                [
                    (g["code"], g["state"], day, g["name"], g["amount"], g["weight"], g["n"], g["markets"],
                     g["min_kg"], g["max_kg"], json.dumps(g["regions"], ensure_ascii=False),
                     json.dumps(g["market_prices"], ensure_ascii=False), g.get("category", ""))
                    for g in groups
                ],
            )
            conn.execute(f"INSERT OR REPLACE INTO {t}_days (date, rows, fetched_at) VALUES (?, ?, ?)",
                         (day, rows, now))

    def fish_rows(self, since: str, code: str | None = None, table: str = "fish") -> list[dict]:
        t = self._auction(table)
        sql = f"SELECT * FROM {t}_daily WHERE date >= ?"
        params: tuple = (since,)
        if code:
            sql += " AND code = ?"
            params += (code,)
        rows = []
        for row in self._query(sql + " ORDER BY date", params):
            item = dict(row)
            item["regions"] = json.loads(item["regions"])
            item["market_prices"] = json.loads(item["market_prices"])
            rows.append(item)
        return rows

    def fish_totals(self, table: str = "fish") -> list[dict]:
        """전체 기간의 합계. 목록용이라 무거운 JSON 칸은 읽지 않는다."""
        t = self._auction(table)
        rows = self._query(f"SELECT code, state, name, date, amount, weight, category FROM {t}_daily ORDER BY date")
        return [dict(row) for row in rows]

    def fish_day_count(self, table: str = "fish") -> int:
        t = self._auction(table)
        return self._query(f"SELECT COUNT(*) AS n FROM {t}_days")[0]["n"]

    def fish_latest_date(self, table: str = "fish") -> str | None:
        t = self._auction(table)
        rows = self._query(f"SELECT MAX(date) AS date FROM {t}_daily")
        return rows[0]["date"] if rows else None

    def get_meta(self, key: str) -> str | None:
        rows = self._query("SELECT value FROM meta WHERE key = ?", (key,))
        return rows[0]["value"] if rows else None

    def set_meta(self, key: str, value: str) -> None:
        with self.transaction() as conn:
            conn.execute("INSERT OR REPLACE INTO meta (key, value) VALUES (?, ?)", (key, value))

    def backup_to(self, target: str) -> None:
        with self._lock:
            dest = sqlite3.connect(target)
            try:
                self._conn.backup(dest)
            finally:
                dest.close()


class AuctionStore:
    """경매 표 하나(fish 또는 produce)에 묶인 DB. 조회·수집 코드는 표 이름을 몰라도 된다."""

    def __init__(self, db: Database, table: str):
        db._auction(table)
        self.db = db
        self.table = table

    def fish_days(self):
        return self.db.fish_days(table=self.table)

    def put_fish_day(self, day, groups, rows, now):
        return self.db.put_fish_day(day, groups, rows, now, table=self.table)

    def fish_rows(self, since, code=None):
        return self.db.fish_rows(since, code, table=self.table)

    def fish_totals(self):
        return self.db.fish_totals(table=self.table)

    def fish_day_count(self):
        return self.db.fish_day_count(table=self.table)

    def fish_latest_date(self):
        return self.db.fish_latest_date(table=self.table)
