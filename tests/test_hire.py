from datetime import datetime

import pytest

from app.config import KST
from app.hire import collect_hire, parse_detail, parse_list
from app.main import merge_duplicates, reclassify
from app.store import Store
from tests.conftest import fixture_text
from tests.test_cheongju import hwpx

NOW = datetime(2026, 11, 16, 23, 0, tzinfo=KST)
PLACES = {"초": {}, "유": {}}


class FakeHire:
    def __init__(self, attachment=b""):
        self.attachment = attachment
        self.list_calls, self.detail_calls, self.downloads = 0, [], []

    def list_page(self, page):
        self.list_calls += 1
        html = fixture_text("kj_list.html")
        return html if page == 1 else html.replace("nttInfoBtn", "x")

    def detail_page(self, pid):
        self.detail_calls.append(pid)
        return fixture_text("kj_detail_1582401.html")

    def download(self, key):
        self.downloads.append(key)
        return self.attachment


@pytest.fixture
def store(tmp_path):
    return Store(tmp_path)


def test_parse_list():
    rows = parse_list(fixture_text("kj_list.html"))
    assert len(rows) == 50
    r = rows[0]
    assert r["post_id"] == "1582401" and r["region"] == "청주" and r["levels"] == ["유치원"]
    assert r["title"].startswith("2026.학년말 방학중 방과후과정") and r["posted_at"] == "2026-11-16"


def test_parse_detail_file_key():
    d = parse_detail(fixture_text("kj_detail_1582401.html"))
    assert d["files"][0]["key"] == "cdd6ff2eb1988d25372ad8afc5ae47bc"
    assert d["files"][0]["name"].endswith(".hwp")


def test_collect_reads_deadline_from_attachment(store, settings):
    sc = FakeHire(hwpx("4. 서류 접수 기간 : 2026. 11. 16.(월) ~ 11. 20.(금) 16:00까지"))
    stats = {}
    collect_hire(sc, store, settings, NOW, stats)
    assert stats["kj_new_count"] == len(sc.detail_calls) > 0
    j = store.jobs["kj1582401"]
    assert (j["deadline"], j["deadline_source"]) == ("2026-11-20", "첨부 공고문")
    assert j["source"] == "충북교육청 기간제 채용공고" and j["author"] is None  # 담당자 이름
    assert j["url"].endswith("bbsId=1091&nttSn=1582401&mi=12127")
    assert all(j["category"] == "유치원" or "유치원" in j["title"] for j in store.jobs.values())
    # 두 번째 실행: 이미 본 글이라 1페이지에서 멈추고 다시 받지 않는다
    sc2 = FakeHire()
    collect_hire(sc2, store, settings, NOW, {})
    assert sc2.list_calls == 1 and sc2.detail_calls == []


def test_board_region_used_when_title_unclear(store, settings):
    collect_hire(FakeHire(), store, settings, NOW, {})
    reclassify(store, settings["filters"], PLACES)
    j = store.jobs["kj1582401"]  # 생명초등학교병설유치원 (기관 목록 없음) · 지역 칸 '청주'
    assert j["region"] == "청주" and j["match_status"] == "match"


def test_skip_post_already_in_pool_board(store, settings):
    rows = parse_list(fixture_text("kj_list.html"))
    store.jobs["1582999"] = {"post_id": "1582999", "title": rows[0]["title"], "posted_at": "2026-11-16"}
    stats = {}
    collect_hire(FakeHire(), store, settings, NOW, stats)
    assert stats["kj_duplicates"] == 1 and "kj1582401" not in store.jobs


def test_merge_order_pool_then_hire_then_cheongju(store):
    t = "2026. 봉덕초등학교병설유치원 겨울방학 중 방과후 과정 강사 채용 공고"
    store.jobs["cj6426-1"] = {"post_id": "cj6426-1", "title": t, "posted_at": "2026-11-16", "notified_at": "x"}
    store.jobs["kj1"] = {"post_id": "kj1", "title": t, "posted_at": "2026-11-16", "notified_at": None}
    assert merge_duplicates(store) == 1 and list(store.jobs) == ["kj1"]
    assert store.jobs["kj1"]["notified_at"] == "x"
    store.jobs["1582387"] = {"post_id": "1582387", "title": t, "posted_at": "2026-11-16", "notified_at": None}
    assert merge_duplicates(store) == 1 and list(store.jobs) == ["1582387"]
    assert store.jobs["1582387"]["notified_at"] == "x"


def test_same_title_template_different_school_is_not_duplicate():
    from app.cheongju import same_post
    a = {"title": "2026. 부윤초등학교병설유치원 겨울방학 중 방과후과정 강사 채용", "posted_at": "2026-11-16"}
    b = {"title": "2026학년도 소이초등학교병설유치원 겨울방학 중 방과후과정 강사 채용", "posted_at": "2026-11-16"}
    assert not same_post(a, b)


def test_new_post_read_as_already_closed_is_kept_open(store, settings):
    # 봉덕초 사례: 11/16 공고를 11/17에 처음 봤는데 마감 11/16으로 읽히면 '확인 필요'로 모집 중에 남긴다
    sc = FakeHire(hwpx("가. 공고 및 서류접수: 2026. 11. 16.(월) 14:00까지 나. 제출방법: 방문"))
    collect_hire(sc, store, settings, datetime(2026, 11, 17, 4, 0, tzinfo=KST), {})
    j = store.jobs["kj1582401"]
    assert j["deadline"] is None and j["notified_at"] is None


def test_body_date_same_as_posted_does_not_override_board():
    from app.main import apply_body_deadline
    j = {"posted_at": "2026-11-10", "deadline": "2026-11-12", "body": "3. 접수기간: 2026.11.10. 10:00부터 방문 접수"}
    apply_body_deadline(j)
    assert j["deadline"] == "2026-11-12"
