from datetime import datetime

import pytest

from app.config import KST
from app.main import collect, record_check
from app.parser import ParseError
from app.store import Store
from tests.conftest import fixture_text

NOW = datetime(2026, 10, 26, 9, 0, tzinfo=KST)
PLACES = {"초": {}, "유": {}}


class FakeScraper:
    def __init__(self, list_html, detail_html=None, fail_detail=False):
        self.list_html, self.detail_html, self.fail_detail = list_html, detail_html, fail_detail
        self.list_calls, self.detail_calls = 0, []

    def list_page(self, page):
        self.list_calls += 1
        return self.list_html if page == 1 else self.list_html.replace("nttInfoBtn", "x")  # 2페이지부터 빈 목록

    def detail_page(self, pid):
        self.detail_calls.append(pid)
        if self.fail_detail:
            raise RuntimeError("timeout")
        return self.detail_html or fixture_text("detail_1581252.html")


@pytest.fixture
def store(tmp_path):
    return Store(tmp_path)


def test_bootstrap_collects_kindergarten_posts_only(store, settings):
    sc = FakeScraper(fixture_text("list_100.html"))
    stats = collect(sc, store, settings, PLACES, NOW)
    assert stats["list_count"] == 100
    assert stats["new_count"] == stats["kinder_count"] > 0
    assert all(j["category"] == "유치원" or "유치원" in j["title"] for j in store.jobs.values())
    assert len(sc.detail_calls) == stats["new_count"]
    # 첫 실행: 이미 마감된 공고는 알림 대상에서 제외
    j = store.jobs["1581252"]
    assert j["notified_at"] is None and j["deadline"] == "2026-11-02"
    expired = [j for j in store.jobs.values() if j["deadline"] and j["deadline"] < "2026-10-26"]
    assert expired and all(j["notified_at"] == "bootstrap" for j in expired)


def test_person_author_not_stored(store, settings):
    collect(FakeScraper(fixture_text("list_100.html")), store, settings, PLACES, NOW)
    assert store.jobs["1581252"]["author"] is None          # '이민애'
    assert all(j["author"] is None or j["author"].endswith(("학교", "유치원")) for j in store.jobs.values())


def test_second_run_no_duplicates_no_detail_refetch(store, settings):
    collect(FakeScraper(fixture_text("list_100.html")), store, settings, PLACES, NOW)
    n = len(store.jobs)
    store.save()
    store2 = Store(store.dir)
    sc = FakeScraper(fixture_text("list_100.html"))
    stats = collect(sc, store2, settings, PLACES, NOW)
    assert len(store2.jobs) == n
    assert stats["new_count"] == 0 and sc.detail_calls == []
    assert sc.list_calls == 1  # 이미 본 글이 있으니 1페이지에서 멈춤


def test_changed_deadline_detected(store, settings):
    html = fixture_text("list_100.html")
    collect(FakeScraper(html), store, settings, PLACES, NOW)
    stats = collect(FakeScraper(html.replace("2026/11/02", "2026/11/05", 1)), store, settings, PLACES, NOW)
    assert stats["changed_count"] == 1
    assert store.jobs["1581252"]["deadline"] == "2026-11-05"


def test_detail_failure_keeps_post_as_review(store, settings):
    stats = collect(FakeScraper(fixture_text("list_100.html"), fail_detail=True), store, settings, PLACES, NOW)
    assert stats["detail_errors"] == stats["new_count"]
    j = store.jobs["1581252"]
    assert j["detail_error"] and j["match_status"] == "review"


def test_empty_first_page_is_failure(store, settings):
    with pytest.raises(ParseError):
        collect(FakeScraper(fixture_text("list_100.html").replace("nttInfoBtn", "x")), store, settings, PLACES, NOW)


def test_pending_skips_notified_and_expired(store, settings):
    collect(FakeScraper(fixture_text("list_100.html")), store, settings, PLACES, NOW)
    pending = store.pending_notifications(["match", "review"], NOW.date())
    assert pending
    assert all(j["notified_at"] is None for j in pending)
    assert all(not j["deadline"] or j["deadline"] >= "2026-10-26" for j in pending)
    assert all(j["match_status"] in ("match", "review") for j in pending)


def test_fail_streak_counts_and_resets():
    st = {}
    record_check(st, "success", "t1")
    record_check(st, "failed", "t2")
    record_check(st, "failed", "t3")
    assert st["fail_streak"] == 2 and st["last_success_at"] == "t1" and st["last_checked_at"] == "t3"
    record_check(st, "partial", "t4")
    assert st["fail_streak"] == 0 and st["last_success_at"] == "t4"


def test_merge_duplicates_and_body_deadline(store):
    from app.main import apply_body_deadline, merge_duplicates
    t = "2026학년도 오송솔미유치원 겨울방학 중 방과후과정 강사 채용 공고"
    store.jobs["1581507"] = {"post_id": "1581507", "title": t, "posted_at": "2026-10-30", "deadline": "2026-11-06",
                             "notified_at": None, "body": "4 . 서류 접수 및 제출 가 . 서류 접수 : 2026. 10. 30.( 금 ) ~ 11. 4.( 수 ) 15:00 까지"}
    store.jobs["cj6426-1"] = {"post_id": "cj6426-1", "title": t + "(1차)", "posted_at": "2026-10-30", "notified_at": "x"}
    assert merge_duplicates(store) == 1 and list(store.jobs) == ["1581507"]
    j = store.jobs["1581507"]
    assert j["notified_at"] == "x"
    apply_body_deadline(j)
    apply_body_deadline(j)  # 여러 번 돌려도 같다
    assert (j["deadline"], j["deadline_board"], j["deadline_source"]) == ("2026-11-04", "2026-11-06", "본문")
