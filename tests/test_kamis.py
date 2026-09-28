import pytest

from app.kamis import KamisError, parse_period


def test_parse_period_takes_average_and_normal_rows():
    payload = {
        "data": {
            "error_code": "000",
            "item": [
                {"countyname": "평균", "yyyy": "2026", "regday": "09/25", "price": "3,480"},
                {"countyname": "평년", "yyyy": "2026", "regday": "09/25", "price": "3,900"},
                {"countyname": "서울", "yyyy": "2026", "regday": "09/25", "price": "3,600"},
                {"countyname": "평균", "yyyy": "2026", "regday": "09/26", "price": "-"},
            ],
        }
    }
    assert parse_period(payload) == {
        "2026-09-25": {"price": 3480, "normal_price": 3900},
        "2026-09-26": {"price": None, "normal_price": None},
    }


def test_parse_period_empty_result_is_not_an_error():
    assert parse_period({"data": ["001"]}) == {}


def test_parse_period_single_row_dict():
    payload = {"data": {"error_code": "000", "item": {"countyname": "평균", "yyyy": "2026", "regday": "01/02", "price": "100"}}}
    assert parse_period(payload)["2026-01-02"]["price"] == 100


def test_parse_period_error_code_raises():
    with pytest.raises(KamisError):
        parse_period({"data": {"error_code": "900"}})
