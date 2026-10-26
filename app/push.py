"""새 공고 푸시 발송. 사이트 배포가 끝난 뒤 실행한다.

필요 환경변수: WORKER_URL, WORKER_ADMIN_TOKEN, VAPID_PRIVATE_KEY, VAPID_SUBJECT(mailto: 또는 https:)
사용: python -m app.push           새 공고 발송
      python -m app.push --test    테스트 알림 1건
"""
import json
import os
import sys
from datetime import date

import requests

from . import mailer
from .config import iso, load_settings, now_kst
from .store import Store

WEEKDAY = "월화수목금토일"
LABEL = {"match": "적합", "review": "확인 필요"}


def deadline_text(deadline: str | None, today: date) -> str:
    if not deadline:
        return "마감일 확인 필요"
    d = date.fromisoformat(deadline)
    left = (d - today).days
    dday = "오늘 마감" if left == 0 else (f"D-{left}" if left > 0 else "마감됨")
    return f"마감 {d.month}/{d.day}({WEEKDAY[d.weekday()]}) · {dday}"


def build_messages(pending: list[dict], threshold: int, today: date) -> list[dict]:
    """반환: [{payload, post_ids}]"""
    if not pending:
        return []
    if len(pending) > threshold:
        n_match = sum(1 for j in pending if j["match_status"] == "match")
        body = f"적합 {n_match}건 · 확인 필요 {len(pending) - n_match}건\n" + \
               "\n".join(f"· {j['title'][:40]}" for j in pending[:3])
        return [{"post_ids": [j["post_id"] for j in pending],
                 "payload": {"title": f"새 유치원 공고 {len(pending)}건", "body": body,
                             "url": "./?tab=new", "tag": "summary"}}]
    out = []
    for j in pending:
        out.append({"post_ids": [j["post_id"]],
                    "payload": {"title": f"[{LABEL[j['match_status']]}] {j['title'][:70]}",
                                "body": deadline_text(j.get("deadline"), today),
                                "url": f"./?post={j['post_id']}", "tag": f"post-{j['post_id']}",
                                "post_id": j["post_id"], "source_url": j["url"]}})
    return out


class Worker:
    def __init__(self, url: str, token: str, session=None):
        self.url, self.s = url.rstrip("/"), session or requests.Session()
        self.h = {"Authorization": f"Bearer {token}"}

    def subscriptions(self) -> list[dict]:
        r = self.s.get(f"{self.url}/subscriptions", headers=self.h, timeout=20)
        r.raise_for_status()
        return r.json()["subscriptions"]

    def delete(self, sub_id: str) -> None:
        self.s.delete(f"{self.url}/subscriptions/{sub_id}", headers=self.h, timeout=20)


def send(messages, subs, private_key, subject, webpush=None) -> dict:
    """반환: {delivered: set(post_id), gone: set(sub_id), errors: [str]}"""
    if webpush is None:
        from pywebpush import webpush
    from pywebpush import WebPushException

    delivered, gone, errors = set(), set(), []
    for m in messages:
        ok = False
        for sub in subs:
            if sub["id"] in gone:
                continue
            try:
                webpush(subscription_info=sub["subscription"], data=json.dumps(m["payload"], ensure_ascii=False),
                        vapid_private_key=private_key, vapid_claims={"sub": subject},
                        ttl=2 * 24 * 3600, headers={"Urgency": "high"}, timeout=20)
                ok = True
            except WebPushException as e:
                status = getattr(e.response, "status_code", None)
                if status in (404, 410):
                    gone.add(sub["id"])
                else:
                    errors.append(f"{sub['id']}: HTTP {status} {str(e)[:120]}")
            except Exception as e:
                errors.append(f"{sub['id']}: {type(e).__name__} {str(e)[:120]}")
        if ok:
            delivered.update(m["post_ids"])
    return {"delivered": delivered, "gone": gone, "errors": errors}


def _env(name):
    v = os.environ.get(name)
    if not v:
        raise SystemExit(f"환경변수 {name} 없음")
    return v


def main(argv=None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    settings = load_settings()
    now = now_kst()
    worker = Worker(_env("WORKER_URL"), _env("WORKER_ADMIN_TOKEN"))
    key, subject = _env("VAPID_PRIVATE_KEY"), os.environ.get("VAPID_SUBJECT", "mailto:admin@example.com")

    if "--test" in argv:
        msgs = [{"post_ids": [], "payload": {"title": "알림 테스트", "body": "알림이 잘 옵니다 👍",
                                             "url": "./", "tag": "test"}}]
        res = send(msgs, worker.subscriptions(), key, subject)
        for sid in res["gone"]:
            worker.delete(sid)
        print(f"구독 처리 완료, 만료 {len(res['gone'])}개, 오류 {res['errors']}")
        return 0 if not res["errors"] else 1

    store = Store()
    pending = store.pending_notifications(settings["notify"]["statuses"], now.date())
    if not pending:
        print("새로 알릴 공고 없음")
        return 0
    try:
        subs = worker.subscriptions()
    except Exception as e:
        mailer.send_admin("[유치원 공고] 알림 서버 접속 실패", f"{type(e).__name__}: {e}\n{mailer.run_link()}")
        print(f"Worker 접속 실패: {e}")
        return 1
    if not subs:
        mailer.send_admin("[유치원 공고] 알림 받을 폰이 없음",
                          f"새 공고 {len(pending)}건을 보내지 못했습니다. 어머니 폰에서 앱을 열고 [알림 켜기]를 다시 눌러주세요.")
        print("구독 0개")
        return 0

    msgs = build_messages(pending, settings["notify"]["summary_threshold"], now.date())
    res = send(msgs, subs, key, subject)
    for sid in res["gone"]:
        worker.delete(sid)
    for pid in res["delivered"]:
        store.jobs[pid]["notified_at"] = iso(now)
    store.save()

    alive = len(subs) - len(res["gone"])
    print(f"알림 {len(res['delivered'])}/{len(pending)}건 전달, 만료 구독 {len(res['gone'])}개, 오류 {len(res['errors'])}개")
    if alive == 0:
        mailer.send_admin("[유치원 공고] 폰 알림 구독 만료",
                          "어머니 폰의 알림 등록이 만료되었습니다. 앱을 열고 [알림 켜기]를 다시 눌러주세요.")
    if res["errors"]:
        mailer.send_admin("[유치원 공고] 알림 발송 오류", "\n".join(res["errors"]) + "\n" + mailer.run_link())
    return 0


if __name__ == "__main__":
    sys.exit(main())
