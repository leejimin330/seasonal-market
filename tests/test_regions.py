from app import config
from app.regions import load_municipalities

M = load_municipalities(config.DATA_DIR)


def test_from_address_finds_city_and_handles_renamed_provinces():
    assert M.from_address("경북 구미시 선산읍")["name"] == "경북 구미시"
    assert M.from_address("전북특별자치도 고창군")["name"] == "전북 고창군"
    assert M.from_address("경상북도 포항시 남구")["name"] == "경북 포항시"   # 구가 나뉜 시는 시 하나로
    assert M.from_address("서울 동대문구 제기동")["name"] == "서울 동대문구"   # 광역시는 구까지
    assert M.from_address("제주특별자치도 남제주군 대정읍")["name"] == "제주 서귀포시"  # 옛 지명
    assert M.from_address("베트남") is None
    assert M.from_address("경기도") is None


def test_from_org_name_uses_place_in_coop_name():
    assert M.from_org_name("거제수산업협동조합")["name"] == "경남 거제시"
    assert M.from_org_name("삼천포수산업협동조합")["name"] == "경남 사천시"
    assert M.from_org_name("고성군수산업협동조합") is None                   # 강원·경남 둘 다 고성군
    assert M.from_org_name("고성군수산업협동조합", "강원도")["name"] == "강원 고성군"
    assert M.from_org_name("부경신항수산업협동조합") is None
