from datetime import date

from pywebpush import WebPushException

from app.config import load_settings
from app.push import build_messages, deadline_text, headline, plan, send

TODAY = date(2026, 10, 26)


def job(pid, status="match", deadline="2026-10-30", inst=None, jt=None, region=None):
    return {"post_id": pid, "match_status": status, "title": f"공고 {pid}", "deadline": deadline,
            "url": f"https://x/{pid}", "institution": inst, "job_type": jt, "region": region}


def test_deadline_text():
    assert deadline_text("2026-10-30", TODAY) == "마감 10/30(금) · D-4"
    assert deadline_text("2026-10-26", TODAY).endswith("오늘 마감")
    assert deadline_text(None, TODAY) == "마감일 확인 필요"


def test_individual_messages_link_to_post():
    msgs = build_messages([job("1"), job("2", "review")], 3, TODAY)
    assert len(msgs) == 2
    p = msgs[0]["payload"]
    assert p["url"] == "./?post=1" and p["source_url"] == "https://x/1"
    assert p["title"] == "공고 1"  # 기관을 모르면 원래 제목, 평가 꼬리표 없음


def test_headline_shows_institution_and_job():
    assert headline(job("1", inst="주중초병설유치원", jt="방과후강사")) == "주중초병설유치원 · 방과후 강사"
    assert headline(job("1", inst="오송솔미유치원", jt="교육공무직")) == "오송솔미유치원 · 교육공무직"


def test_many_become_summary():
    msgs = build_messages([job(str(i)) for i in range(5)], 3, TODAY)
    assert len(msgs) == 1
    assert msgs[0]["payload"]["url"] == "./?tab=open"
    assert msgs[0]["payload"]["body"].endswith("그 외 2건")
    assert msgs[0]["post_ids"] == [str(i) for i in range(5)]


class Resp:
    def __init__(self, code):
        self.status_code = code


def test_send_marks_delivered_and_collects_gone():
    calls = []

    def fake(subscription_info, **kw):
        calls.append(subscription_info["endpoint"])
        if subscription_info["endpoint"] == "gone":
            raise WebPushException("gone", response=Resp(410))

    subs = [{"id": "a", "subscription": {"endpoint": "ok"}}, {"id": "b", "subscription": {"endpoint": "gone"}}]
    res = send(build_messages([job("1"), job("2")], 3, TODAY), subs, "k", "mailto:x", webpush=fake)
    assert res["delivered"] == {"1", "2"}
    assert res["gone"] == {"b"}
    assert calls.count("gone") == 1  # 만료된 구독엔 다시 보내지 않음
    assert res["errors"] == []


def test_send_failure_not_delivered():
    def fake(subscription_info, **kw):
        raise WebPushException("boom", response=Resp(500))

    res = send(build_messages([job("1")], 3, TODAY), [{"id": "a", "subscription": {"endpoint": "e"}}],
               "k", "mailto:x", webpush=fake)
    assert res["delivered"] == set() and len(res["errors"]) == 1


def test_plan_uses_each_phones_conditions():
    settings = load_settings()
    pending = [job("a", jt="방과후강사", region="청주"), job("b", jt="교육공무직", region="청주"),
               job("c", jt="방과후강사", region="기타"), job("d", jt=None, region=None)]
    subs = [{"id": "mom", "prefs": {"cities": ["청주"], "types": ["방과후강사", "교육공무직"]}},
            {"id": "me"},  # 조건을 안 정한 폰 → 기본 (청주 + 강사·교사)
            {"id": "jin", "prefs": {"cities": ["진천", "엉뚱한값"], "types": ["방과후강사"]}}]
    got = {k: [j["post_id"] for j in v] for k, v in plan(pending, subs, settings, {}).items()}
    assert got["mom"] == ["a", "b", "d"]   # 지역·직무를 모르는 공고는 놓치지 않게 포함
    assert got["me"] == ["a", "d"]
    assert got["jin"] == ["d"]             # '기타' 지역은 진천인지 알 수 없어 제외, 모르는 값은 무시
