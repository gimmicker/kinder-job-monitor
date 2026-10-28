from app.kinders import find, key_for, merge_places

KINDERS = {
    "초:주중": {"name": "주중초등학교병설유치원", "city": "청주", "kids": 29},
    "유:비봉": {"name": "비봉유치원", "city": "청주", "kids": 115},
    "유:홍광": {"name": "홍광유치원", "city": "제천", "kids": 128},
}


def test_key_for_normalizes_names():
    assert key_for("주중초병설유치원") == key_for("주중초등학교병설유치원") == "초:주중"
    assert key_for("솔강초병설유") == "초:솔강"
    assert key_for("비봉유치원") == "유:비봉"
    assert key_for("교육지원청") is None


def test_find_matches_title_or_author():
    assert find({"title": "2026. 주중초병설유치원 겨울방학 중 강사 채용"}, KINDERS)["kids"] == 29
    assert find({"title": "시간강사 추가 채용", "author": "비봉유치원"}, KINDERS)["name"] == "비봉유치원"
    assert find({"title": "어딘가유치원 채용"}, KINDERS) is None


def test_merge_places_keeps_manual_values():
    places = {"초": {}, "유": {"홍광": "충주"}}  # 손으로 넣은 값이 이긴다
    merged = merge_places(places, KINDERS)
    assert merged["초"]["주중"] == "청주"
    assert merged["유"]["비봉"] == "청주"
    assert merged["유"]["홍광"] == "충주"
    assert places["유"] == {"홍광": "충주"}  # 원본은 그대로
