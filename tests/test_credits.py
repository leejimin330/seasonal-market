import threading

import pytest

from app.credits import InsufficientCredits, LocalCredits
from app.db import Database


class Clock:
    def __init__(self):
        self.now = 1_000_000.0

    def __call__(self):
        return self.now


@pytest.fixture
def setup():
    db = Database(":memory:")
    db.create_user("kim", "h", bonus=5, now=0)
    clock = Clock()
    return db, LocalCredits(db, costs={"trend": 1, "where": 2}, unlock_hours=24, clock=clock), clock


def test_signup_bonus_is_in_ledger(setup):
    db, credits, _ = setup
    assert credits.balance("kim") == 5
    assert credits.history("kim")[0]["reason"] == "signup_bonus"


def test_use_charges_once_within_unlock(setup):
    _, credits, clock = setup
    first = credits.use("kim", "where", "crab")
    assert first.charged and first.balance == 3
    clock.now += 23 * 3600
    again = credits.use("kim", "where", "crab")
    assert not again.charged and again.balance == 3


def test_use_charges_again_after_expiry(setup):
    _, credits, clock = setup
    credits.use("kim", "trend", "crab")
    clock.now += 24 * 3600 + 1
    assert credits.use("kim", "trend", "crab").charged
    assert credits.balance("kim") == 3


def test_unlock_is_per_item_and_feature(setup):
    _, credits, _ = setup
    credits.use("kim", "trend", "crab")
    assert credits.use("kim", "trend", "apple").charged
    assert credits.use("kim", "where", "crab").charged
    assert credits.balance("kim") == 1


def test_insufficient_changes_nothing(setup):
    db, credits, _ = setup
    credits.use("kim", "where", "a")
    credits.use("kim", "where", "b")
    with pytest.raises(InsufficientCredits):
        credits.use("kim", "where", "c")
    assert credits.balance("kim") == 1
    assert credits.unlocked_until("kim", "where", "c") is None
    assert len(credits.history("kim")) == 3


def test_concurrent_use_never_goes_negative(setup):
    db, credits, _ = setup
    errors = []

    def worker(n):
        try:
            credits.use("kim", "where", f"item{n}")
        except InsufficientCredits:
            errors.append(n)

    threads = [threading.Thread(target=worker, args=(n,)) for n in range(10)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert credits.balance("kim") == 1
    assert len(errors) == 8


def test_grant_records_actor(setup):
    _, credits, _ = setup
    assert credits.grant("kim", 10, actor="boss", memo="테스터") == 15
    row = credits.history("kim")[0]
    assert (row["reason"], row["delta"], row["memo"]) == ("admin_grant", 10, "테스터")
    with pytest.raises(KeyError):
        credits.grant("nobody", 1, actor="boss", memo="")
