from datetime import date

from pywebpush import WebPushException

from app.push import build_messages, deadline_text, send

TODAY = date(2026, 10, 26)


def job(pid, status="match", deadline="2026-10-30"):
    return {"post_id": pid, "match_status": status, "title": f"공고 {pid}", "deadline": deadline,
            "url": f"https://x/{pid}"}


def test_deadline_text():
    assert deadline_text("2026-10-30", TODAY) == "마감 10/30(금) · D-4"
    assert deadline_text("2026-10-26", TODAY).endswith("오늘 마감")
    assert deadline_text(None, TODAY) == "마감일 확인 필요"


def test_individual_messages_link_to_post():
    msgs = build_messages([job("1"), job("2", "review")], 3, TODAY)
    assert len(msgs) == 2
    p = msgs[0]["payload"]
    assert p["url"] == "./?post=1" and p["source_url"] == "https://x/1"
    assert p["title"].startswith("[적합]")
    assert msgs[1]["payload"]["title"].startswith("[확인 필요]")


def test_many_become_summary():
    msgs = build_messages([job(str(i)) for i in range(5)], 3, TODAY)
    assert len(msgs) == 1
    assert msgs[0]["payload"]["url"] == "./?tab=new"
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
