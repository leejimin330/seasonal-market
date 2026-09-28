import pytest

from app.catalog import Item
from app.shopping import parse_quantity, rank_offers


@pytest.mark.parametrize(
    ("title", "grams", "count"),
    [
        ("<b>활꽃게</b> 2kg", 2000, None),
        ("딸기 500g x 2팩", 1000, None),
        ("딸기 500gx2", 1000, None),
        ("국산 양파 3킬로", 3000, None),
        ("햇감자 2~3kg 특품", 2000, None),     # 범위는 적은 쪽
        ("생물 고등어 1손", None, 2),          # 1손 = 2마리
        ("제주 은갈치 3마리", None, 3),
        ("사과 5kg 16~20과", 5000, 16),
        ("수박 1통", None, 1),
        ("배추 3포기 1망", None, 3),
        ("신선한 시금치", None, None),
    ],
)
def test_parse_quantity(title, grams, count):
    q = parse_quantity(title)
    assert q.grams == grams
    assert q.count == count


def _item(unit="g", qty=1000):
    return Item(
        id="x", name="꽃게", category="수산", price_unit="1kg", kamis=None, shop_query="꽃게",
        shop_unit=unit, shop_qty=qty, shop_label="1kg",
    )


def _raw(title, price, mall="몰", category="식품"):
    return {"title": title, "lprice": str(price), "mallName": mall, "category1": category, "link": "L"}


def test_rank_sorts_by_unit_price_not_sticker_price():
    offers = rank_offers([_raw("꽃게 1kg", 20000, "A"), _raw("꽃게 3kg", 45000, "B")], _item())
    assert [o["mall"] for o in offers] == ["B", "A"]
    assert offers[0]["unit_price"] == 15000


def test_rank_drops_unparseable_nonfood_and_excluded():
    offers = rank_offers(
        [
            _raw("꽃게 대용량", 10000),               # 양을 모른다
            _raw("꽃게 모형 1kg", 1000),              # 제외어
            _raw("꽃게 1kg", 1000, category="완구"),  # 식품이 아님
            _raw("꽃게 1kg", 20000),
        ],
        _item(),
    )
    assert len(offers) == 1


def test_rank_drops_outlier_that_looks_misparsed():
    raws = [_raw(f"꽃게 {n}kg", 20000 * n, f"M{n}") for n in (1, 2, 3, 4)]
    raws.append(_raw("꽃게 10kg 중 1팩", 5000, "싼척"))  # 1kg당 500원 — 양을 잘못 읽은 것
    offers = rank_offers(raws, _item())
    assert "싼척" not in [o["mall"] for o in offers]


def test_rank_uses_count_for_each_items():
    offers = rank_offers([_raw("고등어 2마리", 8000), _raw("고등어 1손", 7000, "B")], _item("ea", 1))
    assert offers[0]["mall"] == "B" and offers[0]["unit_price"] == 3500
