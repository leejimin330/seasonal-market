import pytest
from fastapi.testclient import TestClient

from app.main import create_app


class Clock:
    def __init__(self):
        self.now = 1_790_000_000.0  # 2026-09-22 KST 무렵

    def __call__(self):
        return self.now


@pytest.fixture
def app_and_client():
    clock = Clock()
    app = create_app(db_path=":memory:", admins=frozenset({"boss"}), secret="s", clock=clock,
                     run_scheduler=False)
    app.state.prices.collect()
    app.state.prices.collect_history()
    return app, TestClient(app), clock


def _signup(client, user_id="kim"):
    r = client.post("/api/signup", json={"user_id": user_id, "password": "12345678"})
    assert r.status_code == 200, r.text
    return r.json()


def test_free_views_need_no_login(app_and_client):
    _, client, _ = app_and_client
    items = client.get("/api/items").json()["items"]
    assert len(items) >= 30
    assert all(item["price"] for item in items)  # 샘플 모드에서는 모두 가격이 있다
    detail = client.get("/api/items/mackerel").json()
    assert detail["access"]["trend"] == {"cost": 1, "unlocked_until": None}
    assert client.get("/api/items/nope").status_code == 404


def test_paid_features_need_login(app_and_client):
    _, client, _ = app_and_client
    assert client.post("/api/items/mackerel/trend").status_code == 401
    assert client.post("/api/items/mackerel/where").status_code == 401


def test_signup_gives_bonus_and_trend_charges_once(app_and_client):
    _, client, _ = app_and_client
    assert _signup(client)["credits"] == 20
    first = client.post("/api/items/mackerel/trend").json()
    assert first["charged"] and first["balance"] == 19 and len(first["series"]) > 200  # 평일 조사분만
    again = client.post("/api/items/mackerel/trend").json()
    assert not again["charged"] and again["balance"] == 19
    assert client.get("/api/items/mackerel").json()["access"]["trend"]["unlocked_until"]


def test_where_returns_channels_and_regions(app_and_client):
    _, client, _ = app_and_client
    _signup(client)
    data = client.post("/api/items/blue_crab/where").json()
    assert data["charged"] and data["balance"] == 18
    assert "전통시장" in data["channels"] and data["regions"]
    assert data["price_unit"] == "1kg"


def test_free_summary_has_normal_after_history(app_and_client):
    _, client, _ = app_and_client
    items = client.get("/api/items").json()["items"]
    assert all(item["vs_normal"] is not None for item in items)


def test_insufficient_credits_is_402(app_and_client):
    app, client, _ = app_and_client
    _signup(client)
    ids = [item.id for item in app.state.catalog][:10]
    for item_id in ids:
        assert client.post(f"/api/items/{item_id}/where").status_code == 200
    r = client.post(f"/api/items/{[i.id for i in app.state.catalog][10]}/where")
    assert r.status_code == 402
    assert r.json()["detail"]["balance"] == 0


def test_login_logout_and_wrong_password(app_and_client):
    _, client, _ = app_and_client
    _signup(client)
    client.post("/api/logout")
    assert client.get("/api/me").json()["user"] is None
    assert client.post("/api/login", json={"user_id": "kim", "password": "wrong-pass"}).status_code == 401
    assert client.post("/api/login", json={"user_id": "nobody", "password": "12345678"}).status_code == 401
    assert client.post("/api/login", json={"user_id": "KIM", "password": "12345678"}).status_code == 200


def test_signup_rules(app_and_client):
    _, client, _ = app_and_client
    assert client.post("/api/signup", json={"user_id": "a", "password": "12345678"}).status_code == 400
    assert client.post("/api/signup", json={"user_id": "kim", "password": "short"}).status_code == 400
    assert client.post("/api/signup", json={"user_id": "boss", "password": "12345678"}).status_code == 409
    _signup(client)
    assert client.post("/api/signup", json={"user_id": "kim", "password": "12345678"}).status_code == 409


def test_signup_throttled_per_ip(app_and_client):
    _, client, _ = app_and_client
    for n in range(3):
        _signup(client, f"user{n}")
    r = client.post("/api/signup", json={"user_id": "user9", "password": "12345678"})
    assert r.status_code == 429


def test_admin_grant(app_and_client):
    app, client, _ = app_and_client
    _signup(client)
    assert client.post("/api/admin/grant", json={"user_id": "kim", "amount": 5}).status_code == 403

    app.state.db.create_user("boss", "x", bonus=0, now=0)
    from app import auth

    client.cookies.set(auth.COOKIE_NAME, auth.make_token("boss", "s"))
    r = client.post("/api/admin/grant", json={"user_id": "kim", "amount": 5, "memo": "테스트"})
    assert r.json()["balance"] == 25
    assert client.post("/api/admin/grant", json={"user_id": "ghost", "amount": 5}).status_code == 404
    assert client.post("/api/admin/grant", json={"user_id": "kim", "amount": 0}).status_code == 422
    assert [u["id"] for u in client.get("/api/admin/users").json()["users"]] == ["kim", "boss"]


def test_switching_to_real_source_drops_sample_rows(app_and_client):
    app, _, _ = app_and_client
    assert app.state.db.price_sources() == {"sample"}

    class FakeAt:
        def fetch_rows(self, code, start, end):
            return [{"exmn_ymd": end.strftime("%Y%m%d"), "vrty_cd": code.varieties[0], "grd_cd": code.grades[0],
                     "exmn_dd_prc": "1000", "sgg_cd": "1101", "sgg_nm": "서울", "mrkt_nm": "경동",
                     "unit": code.unit, "unit_sz": code.unit_size}]

    app.state.prices.at = FakeAt()
    app.state.prices.collect()
    assert app.state.db.price_sources() == {"at"}
    assert app.state.prices.breakdown("apple")["channels"]["전통시장"]["avg"] == 1000
