import io
import zipfile
from datetime import date, datetime

import pytest

from app.cheongju import collect_cheongju, parse_detail, parse_list, same_post
from app.config import KST
from app.docs import doc_text, find_deadline
from app.main import collect
from app.store import Store
from tests.conftest import fixture_text

NOW = datetime(2026, 10, 28, 9, 0, tzinfo=KST)


def hwpx(text: str) -> bytes:
    """테스트용 아주 작은 HWPX (ZIP 안의 section XML)."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("Contents/section0.xml", f'<hs:sec xmlns:hp="x"><hp:p><hp:run><hp:t>{text}</hp:t></hp:run></hp:p></hs:sec>')
    return buf.getvalue()


# ---------- 목록·상세 ----------
def test_parse_school_list():
    rows = parse_list(fixture_text("cj_school_list.html"))
    assert len(rows) == 50
    r = next(r for r in rows if "각리초등학교병설유치원" in r["title"])
    assert r["no"] == "38390393" and r["level"] == "유치원" and r["posted_at"] == "2026-10-27"


def test_parse_office_list_has_no_level():
    rows = parse_list(fixture_text("cj_office_list.html"))
    assert rows and all(r["level"] is None for r in rows)


def test_parse_detail_attachments():
    d = parse_detail(fixture_text("cj_detail_38260028.html"))
    assert [f["name"] for f in d["files"]] == ["유치원 특수학급 전일제 강사 채용 공고.hwp"]
    assert d["files"][0]["href"].startswith("/base/download/bbs.php")


# ---------- 첨부 공고문 ----------
def test_hwpx_text():
    assert "접수 기간" in doc_text("공고.hwpx", hwpx("3. 접수 기간: 2026. 11. 3.(화) ~ 11. 6.(금)"))


@pytest.mark.parametrize("text, want", [
    ("원서접수 - 기간: 2026.8.5.(수) 14:00~2026.8.10.(월) 15:00 - 장소: 행정실", "2026-08-10"),
    ("1) 서류 제출: 2026. 9. 14.(월) ~ 9. 17.(목) 09:30 ※ 면접 대상자 개별 통보", "2026-09-17"),
    ("5 신청서 접수 가. 기간 : 2026년 9월 28일 ~ 9월 30일 09:00 ~ 16:00, 10월 1일 09:00 ~ 12:00 나. 장소", "2026-10-01"),
    ("계약기간 : 2026. 10. 07. ~ 2027. 01. 06. 접수 방법: 방문", None),  # 계약 기간은 마감일이 아님
    ("특별한 날짜 없음", None),
])
def test_find_deadline(text, want):
    assert find_deadline(text, date(2026, 8, 5) if "8.5" in text else date(2026, 9, 14)) == want


# 실제 공고에서 틀렸던 형식들 (2026-11-17 원문 대조). (문구, 등록일, 마감일)
@pytest.mark.parametrize("text, posted, want", [
    ("가. 공고 및 서류접수: 11.16(월)-11.18.(수) 14:00까지 나. 제출방법: 방문 접수", "2026-11-16", "2026-11-18"),  # 봉덕초
    ("3. 접수기간: 2026.11.10.~11.12.10:00 *방문접수가 어려운 경우", "2026-11-10", "2026-11-12"),       # 요일 괄호 없음
    ("*접수기간: 2026.11.6~11.9 10시 *접수방법: 방문", "2026-11-06", "2026-11-09"),
    ("- 서류접수 기한: 2026.11.11.(수)~11,17.(화) 12:00까지 - 접수처: 연구실", "2026-11-11", "2026-11-17"),  # 쉼표 오타
    ("서류접수 2026. 10. 20.(화)~ 2026. 10. 23.(금) 10:00 서류 제출 방법: 전자우편 2 서류전형 합격자 발표 "
     "2026. 10. 23.(금) 15:00 3 면접 심사 2026. 10. 27.(화) 10:00", "2026-10-20", "2026-10-23"),    # 면접일은 마감 아님
    ("서류접수 기간: 11. 16.(월) ~ 11. 19.(목) 13:00 유치원 방문 접수 면접심사 예정: 11. 20.(금) 14:00", "2026-11-16", "2026-11-19"),
    ("◦ 모집기간 : 겨울방학 (2027. 1. 4.~ 2. 23.(35 일간)) 2. 모집 기관", "2026-11-06", None),        # 근무 기간
    ("인력풀시스템 활용 접수 기간 2026. 11. 16.(월) ~ 11. 20.(금) 16:00까지 점심시간 제외 (12:00~13:00) "
     "1차 서류 심사 2026. 11. 24.(화) 14:30", "2026-11-16", "2026-11-20"),                              # 소이초: 심사일 아님
    ("가. 서류 접수 및 면접 - 기간 및 장소 : [전자우편] 1차: 2026. 10. 26.(월) ~ 2026. 10. 30.(금) 11시", "2026-10-27", "2026-10-30"),
    ("가. 접수 기간 : 2026. 11. 6.( 금 ) ~ 2026. 11. 12.( 목 ) 15:00 나 . 접수 방법 : 교무실, 043-214-4506", "2026-11-06", "2026-11-12"),
])
def test_find_deadline_real_cases(text, posted, want):
    assert find_deadline(text, date.fromisoformat(posted)) == want


# ---------- 중복 ----------
def test_same_post():
    a = {"title": "2026.초롱꽃유치원 특수교육 통합형 방과후학교 시간제 근무 기간제교사 채용 공고(2차)", "posted_at": "2026-08-27"}
    b = {"title": "2026. 초롱꽃유치원 특수교육 통합형 방과후학교 시간제근무 기간제교사 채용 공고(2차)", "posted_at": "2026-08-27"}
    assert same_post(a, b)
    assert not same_post(a, {**b, "title": b["title"].replace("2차", "3차")})   # 차수가 다르면 다른 공고
    assert not same_post(a, {**b, "posted_at": "2026-10-01"})                    # 한참 뒤에 다시 올린 글


# ---------- 수집 ----------
class FakeCheongju:
    def __init__(self):
        self.detail_calls, self.downloads = [], 0

    def list_page(self, menukey, page):
        if page > 1:
            return "<table class='board'><thead><tr><th>제목</th><th>작성자</th><th>등록일</th></tr></thead><tbody></tbody></table>"
        return fixture_text("cj_school_list.html" if menukey == 6426 else "cj_office_list.html")

    def detail_page(self, menukey, no):
        self.detail_calls.append(no)
        return fixture_text("cj_detail_38260028.html")

    def download(self, href):
        self.downloads += 1
        return hwpx("2 채용 세부사항 다. 서류 제출: 2026. 11. 3.(화) ~ 11. 6.(금) 17:00")


@pytest.fixture
def store(tmp_path):
    return Store(tmp_path)


def test_collect_keeps_kindergarten_and_typed_office_posts(store, settings):
    sc, stats = FakeCheongju(), {}
    collect_cheongju(sc, store, settings, NOW, stats)
    titles = [j["title"] for j in store.jobs.values()]
    assert any("각리초등학교병설유치원" in t for t in titles)
    assert not any("고등학교" in t and "유치원" not in t for t in titles if "cj6426" in t)
    office = [j for j in store.jobs.values() if j["category"] == "교육지원청"]
    assert office and not any("합격자" in j["title"] for j in office)       # 결과 발표 글 제외
    assert not any("소방기사" in j["title"] for j in office)                 # 직무를 모르는 글 제외
    j = next(j for j in store.jobs.values() if "각리초" in j["title"])
    assert j["deadline"] == "2026-11-06" and j["deadline_source"] == "첨부 공고문"
    assert j["source"] == "청주교육지원청" and j["url"].endswith("no=38390393")
    assert sc.downloads == len(store.jobs)


def test_collect_second_run_does_not_refetch(store, settings):
    collect_cheongju(FakeCheongju(), store, settings, NOW, {})
    store.save()
    store2 = Store(store.dir)
    sc = FakeCheongju()
    collect_cheongju(sc, store2, settings, NOW, {})
    assert sc.detail_calls == [] and len(store2.jobs) == len(store.jobs)


def test_skip_post_already_on_chungbuk_board(store, settings):
    store.jobs["1581338"] = {"post_id": "1581338", "posted_at": "2026-10-27",
                             "title": "2026학년도 각리초등학교병설유치원 학년말 방학 중 방과후 과정 강사 채용 공고"}
    stats = {}
    collect_cheongju(FakeCheongju(), store, settings, NOW, stats)
    assert not any(k.startswith("cj") and "각리초" in j["title"] for k, j in store.jobs.items())
    assert stats["cj_duplicates"] >= 1


def test_chungbuk_post_replaces_earlier_cheongju_copy(store, settings):
    """청주교육지원청에서 먼저 받은 공고가 나중에 충북교육청 게시판에도 올라오면 하나만 남는다."""
    from tests.test_collect import FakeScraper
    lst = fixture_text("list_100.html")
    pool_title = "2026. 주중초병설유치원 겨울방학 중 방과후과정 강사 채용 공고"
    store.jobs["cj6426-1"] = {"post_id": "cj6426-1", "title": pool_title, "posted_at": "2026-10-26",
                              "notified_at": "2026-10-26T12:00:00+09:00"}
    collect(FakeScraper(lst), store, settings, {"초": {}, "유": {}}, datetime(2026, 10, 26, 9, 0, tzinfo=KST))
    assert "cj6426-1" not in store.jobs
    kept = [j for j in store.jobs.values() if j["title"] == pool_title]
    assert len(kept) == 1 and kept[0]["notified_at"] == "2026-10-26T12:00:00+09:00"  # 다시 알리지 않음


def test_first_round_mark_matches_unmarked_title():
    a = {"title": "2026학년도 오송솔미유치원 겨울방학 중 방과후과정 강사 채용 공고(1차)", "posted_at": "2026-10-30"}
    b = {"title": "2026학년도 오송솔미유치원 겨울방학 중 방과후과정 강사 채용 공고", "posted_at": "2026-10-30"}
    assert same_post(a, b)
    assert not same_post(a, {**b, "title": b["title"] + "(2차)"})


def test_open_ended_period_is_not_deadline():
    assert find_deadline("1) 기 간 : 2026. 8. 10.( 월 ) ~ 채용시까지 - 필요에 따라", date(2026, 8, 10)) is None
