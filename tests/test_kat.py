from app.db import AuctionStore, Database
from app.kat import ProduceService, aggregate_produce, to_auction_rows
from app.wipan import FishQueries


def _row(item="가지", variety="가지(일반)", category="과채류", price=5_000, unit_qty=5, qty=2, unit="kg",
         market="가락", corp="서울청과", origin="경기도 여주시", code=("04", "07")):
    return {"gds_lclsf_nm": category, "gds_lclsf_cd": code[0], "gds_mclsf_cd": code[1], "gds_mclsf_nm": item,
            "gds_sclsf_nm": variety, "scsbd_prc": str(price), "unit_qty": str(unit_qty), "qty": str(qty),
            "unit_nm": unit, "whsl_mrkt_nm": market, "corp_nm": corp, "plor_nm": origin}


def test_to_auction_rows_uses_package_price_times_quantity():
    rows, categories = to_auction_rows([
        _row(),
        _row(unit="개"),                         # kg 단위가 아니면 뺀다
        _row(category="농림가공"),               # 가공품 부류는 뺀다
        _row(item="곡물제조"),
        _row(price=0),
    ])
    assert len(rows) == 1
    row = rows[0]
    assert (row["csmtAmount"], row["csmtWt"], row["kdfshSttusNm"]) == (10_000, 10, "가지(일반)")
    assert categories == {"0407": "과채류"}


def test_aggregate_produce_gives_kg_price_and_category():
    (group,) = aggregate_produce([_row(price=5_000, unit_qty=5), _row(price=6_000, unit_qty=5, origin="충남 논산시")])
    assert group["category"] == "과채류"
    assert round(group["amount"] / group["weight"]) == 1_100
    assert set(group["regions"]) == {"경기도 여주시", "충남 논산시"}


class FakeKat:
    def fetch_day(self, day):
        return [_row(), _row(item="무화과", variety="무화과(일반)", category="과실류", price=20_000, unit_qty=2, qty=3,
                             code=("06", "12"))]


def test_produce_service_stores_today_and_queries_read_it():
    db = Database(":memory:")
    store = AuctionStore(db, "produce")
    ProduceService(store, FakeKat(), clock=lambda: 1_790_000_000.0).collect()
    data = FishQueries(store).species()
    by_name = {s["name"]: s for s in data["species"]}
    assert by_name["무화과"]["kg"] == 10_000 and by_name["무화과"]["category"] == "과실류"
    assert FishQueries(AuctionStore(db, "fish")).species()["species"] == []  # 수산물 표와 섞이지 않는다


def test_auction_detail_hides_series_and_trend_is_paid(tmp_path):
    from fastapi.testclient import TestClient
    from app.main import create_app

    app = create_app(db_path=str(tmp_path / "t.db"), secret="s", run_scheduler=False, clock=lambda: 1_790_000_000.0)
    ProduceService(AuctionStore(app.state.db, "produce"), FakeKat(), clock=lambda: 1_790_000_000.0).collect()
    client = TestClient(app)
    code = next(s["code"] for s in client.get("/api/produce").json()["species"] if s["name"] == "무화과")
    detail = client.get(f"/api/produce/{code}").json()
    assert "series" not in detail and detail["access"]["trend"]["cost"] == 1
    assert detail["emoji"] and detail["story"]
    assert client.post(f"/api/produce/{code}/trend?state=무화과(일반)").status_code == 401
    client.post("/api/signup", json={"user_id": "kim", "password": "12345678"})
    trend = client.post(f"/api/produce/{code}/trend?state=무화과(일반)").json()
    assert trend["charged"] and trend["series"][-1]["price"] == 10_000
