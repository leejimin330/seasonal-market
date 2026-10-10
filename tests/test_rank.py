from tests.test_api import app_and_client, priced_db  # noqa: F401


def test_view_beacon_counts_and_ranks_by_views(app_and_client):
    _, client, _ = app_and_client
    item_id = client.get("/api/items").json()["items"][0]["id"]
    for _ in range(3):
        assert client.post("/api/view", json={"kind": "item", "key": item_id}).status_code == 200
    ranked = client.get("/api/rank", params={"by": "views"}).json()
    assert ranked["items"][0]["value"] == 3
    assert ranked["items"][0]["href"] == f"#/item/{item_id}"


def test_view_beacon_rejects_unknown_kind(app_and_client):
    _, client, _ = app_and_client
    assert client.post("/api/view", json={"kind": "x", "key": "a"}).status_code == 400


def test_rank_sales_and_volume_work_without_auction_rows(app_and_client):
    _, client, _ = app_and_client
    for by in ("sales", "volume"):
        r = client.get("/api/rank", params={"by": by, "kind": "all"})
        assert r.status_code == 200
        assert r.json()["items"] == []  # 샘플 DB에는 경매 자료가 없다


def test_rank_rejects_bad_params(app_and_client):
    _, client, _ = app_and_client
    assert client.get("/api/rank", params={"by": "x"}).status_code == 400
    assert client.get("/api/rank", params={"kind": "x"}).status_code == 400
