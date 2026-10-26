import pytest

from app.filters import classify, institutions

NO_PLACES = {"초": {}, "유": {}}


def row(title, author="", category="유치원"):
    return {"title": title, "author": author, "category": category}


@pytest.mark.parametrize("title,author,want_status,want_type", [
    # 청주 단서 있음 + 원하는 직무 → 적합
    ("2026. 오송유치원 겨울방학 중 방과후과정 강사 채용 공고", "김선희", "match", "방과후강사"),
    ("2026학년도 청주소로초등학교병설유치원 여름방학 중 방과후 과정 강사 채용 공고(3차)", "청주소로초등학교", "match", "방과후강사"),
    ("2026. 9. 1.자 병설유치원 계약제교원(기간제교사) 채용 공고", "청주금천초등학교", "match", "기간제교사"),
    # 청주지만 교육공무직 → 확인 필요
    ("2026. 오송솔미유치원 교육공무직원(유치원돌봄전담사) 채용 재공고", "오송솔미유치원", "review", "교육공무직"),
    # 지역 모름 → 확인 필요 (놓치지 않기)
    ("2026. 주중초병설유치원 겨울방학 중 방과후과정 강사 채용 공고", "이민애", "review", "방과후강사"),
    ("2026. 유치원 여름방학 중 방과후과정 강사 채용 공고", "칠성초등학교", "review", "방과후강사"),
    # 다른 지역 → 부적합
    ("2026. 초평초병설유치원 방과후과정 특성화 강사 모집 공고", "김혜원", "not_match", "방과후강사"),
    ("2026. 진천유치원 여름방학 중 방과후과정 강사 채용 공고", "권혜선", "not_match", "방과후강사"),
    ("음성 금왕유치원 특수교육 온나누미(자원봉사자) 모집", "강진희", "not_match", "자원봉사"),
    ("2026학년도 충주중앙탑초등학교병설유치원 여름방학 중 방과후 과정 강사 채용 공고", "충주중앙탑초등학교", "not_match", "방과후강사"),
    # 자원봉사 → 부적합 (청주라도)
    ("오송유치원 돌봄교실 자원봉사자 모집 공고", "김선희", "not_match", "자원봉사"),
])
def test_classify_cases(f, title, author, want_status, want_type):
    c = classify(row(title, author), f, NO_PLACES)
    assert (c["match_status"], c["job_type"]) == (want_status, want_type), c["reason"]


def test_not_kindergarten(f):
    c = classify(row("2026학년도 대성중학교 교육공무직원(조리실무사) 공개채용 공고", "대성중학교", "중등학교"), f, NO_PLACES)
    assert c["match_status"] == "not_match"


def test_kindergarten_word_in_title_overrides_category(f):
    c = classify(row("청주 OO초등학교병설유치원 기간제교사 채용", "", "초등학교"), f, NO_PLACES)
    assert c["match_status"] == "match"


def test_places_lookup_decides_region(f):
    places = {"초": {"주중": "청주", "칠성": "괴산"}, "유": {}}
    assert classify(row("2026. 주중초병설유치원 방과후과정 강사 채용", "이민애"), f, places)["match_status"] == "match"
    assert classify(row("2026. 유치원 방과후과정 강사 채용", "칠성초등학교"), f, places)["match_status"] == "not_match"


def test_body_cheongju_word(f):
    c = classify(row("2026. 주중초병설유치원 방과후과정 강사 채용", ""), f, NO_PLACES, body="청주시 청원구 ... 주중초등학교")
    assert c["match_status"] == "match"


def test_body_common_word_not_used(f):
    # '문의'(문의면)는 본문에 흔한 단어라 지역 근거로 쓰지 않는다
    c = classify(row("2026. 주중초병설유치원 방과후과정 강사 채용", ""), f, NO_PLACES, body="자세한 사항은 행정실로 문의")
    assert c["region"] == "미상"


@pytest.mark.parametrize("text,want", [
    ("2026. 주중초병설유치원 겨울방학", [("초", "주중", "주중초병설유치원")]),
    ("솔밭초등학교병설유치원 전일제강사", [("초", "솔밭", "솔밭초등학교병설유치원")]),
    ("오송솔미초등학교 병설유치원 아침", [("초", "오송솔미", "오송솔미초등학교병설유치원")]),
    ("(솔강초병설유)", [("초", "솔강", "솔강초병설유")]),
    ("2026.초롱꽃유치원 특수", [("유", "초롱꽃", "초롱꽃유치원")]),
    ("2026. 9. 1.자 병설유치원 계약제교원", []),
])
def test_institutions(text, want):
    assert institutions(text) == want
