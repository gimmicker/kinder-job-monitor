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
from .kinders import load_kinders
from .prefs import default_prefs, is_mine, job_city, sanitize
from .store import Store

WEEKDAY = "월화수목금토일"


def deadline_text(deadline: str | None, today: date) -> str:
    if not deadline:
        return "마감일 확인 필요"
    d = date.fromisoformat(deadline)
    left = (d - today).days
    dday = "오늘 마감" if left == 0 else (f"D-{left}" if left > 0 else "마감됨")
    return f"마감 {d.month}/{d.day}({WEEKDAY[d.weekday()]}) · {dday}"


def _type_name(t: str | None) -> str:
    return (t[:-2] + " " + t[-2:]) if t and t[-2:] in ("강사", "교사") else (t or "")


def headline(j: dict) -> str:
    """알림 첫 줄: '주중초병설유치원 · 방과후 강사'. 기관을 모르면 원래 제목."""
    inst, jt = j.get("institution"), _type_name(j.get("job_type"))
    if inst:
        return f"{inst} · {jt}" if jt else inst
    return j["title"][:70]


def build_messages(pending: list[dict], threshold: int, today: date) -> list[dict]:
    """반환: [{payload, post_ids}]"""
    if not pending:
        return []
    if len(pending) > threshold:
        lines = [f"· {headline(j)}" for j in pending[:3]]
        if len(pending) > 3:
            lines.append(f"그 외 {len(pending) - 3}건")
        return [{"post_ids": [j["post_id"] for j in pending],
                 "payload": {"title": f"새 유치원 공고 {len(pending)}건", "body": "\n".join(lines),
                             "url": "./?tab=open", "tag": "summary"}}]
    out = []
    for j in pending:
        out.append({"post_ids": [j["post_id"]],
                    "payload": {"title": headline(j),
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


def plan(pending: list[dict], subs: list[dict], settings: dict, kinders: dict) -> dict:
    """폰(구독)마다 그 폰의 조건에 맞는 공고만 고른다. 반환: {sub_id: [공고]}.

    조건을 저장하지 않은 폰은 기본 조건(청주 + 설정의 직무)을 쓴다.
    """
    default = default_prefs(settings)
    cities = {j["post_id"]: job_city(j, kinders) for j in pending}
    out = {}
    for sub in subs:
        prefs = sanitize(sub.get("prefs"), settings) or default
        mine = [j for j in pending if is_mine(j, cities[j["post_id"]], prefs)]
        out[sub["id"]] = sorted(mine, key=lambda j: j.get("deadline") or "9999")
    return out


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
    # 폰마다 조건이 달라서 모든 상태를 후보로 두고, 폰별로 고른다
    pending = store.pending_notifications(["match", "review", "not_match"], now.date())
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

    per_sub = plan(pending, subs, settings, load_kinders())
    res = {"delivered": set(), "gone": set(), "errors": []}
    failed = set()  # 보내려다 실패한 공고 → 다음 실행에서 다시 시도
    for sub in subs:
        mine = per_sub[sub["id"]]
        if not mine:
            continue
        r = send(build_messages(mine, settings["notify"]["summary_threshold"], now.date()), [sub], key, subject)
        res["delivered"] |= r["delivered"]
        res["gone"] |= r["gone"]
        res["errors"] += r["errors"]
        if not r["gone"]:
            failed |= {j["post_id"] for j in mine} - r["delivered"]
    for sid in res["gone"]:
        worker.delete(sid)
    # 어느 폰에도 실패하지 않은 공고는 처리 완료 (보냈거나, 원하는 폰이 없었음)
    for j in pending:
        if j["post_id"] not in failed:
            store.jobs[j["post_id"]]["notified_at"] = iso(now)
    store.save()

    alive = len(subs) - len(res["gone"])
    print(f"알림 {len(res['delivered'])}건 전달 (후보 {len(pending)}건), 만료 구독 {len(res['gone'])}개, 오류 {len(res['errors'])}개")
    if alive == 0:
        mailer.send_admin("[유치원 공고] 폰 알림 구독 만료",
                          "어머니 폰의 알림 등록이 만료되었습니다. 앱을 열고 [알림 켜기]를 다시 눌러주세요.")
    if res["errors"]:
        mailer.send_admin("[유치원 공고] 알림 발송 오류", "\n".join(res["errors"]) + "\n" + mailer.run_link())
    return 0


if __name__ == "__main__":
    sys.exit(main())
