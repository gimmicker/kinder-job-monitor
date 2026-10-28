"""수집 → 분류 → 저장. 알림은 사이트 배포 후 app.push가 따로 보낸다.

사용: python -m app.main
종료 코드: 0 성공/부분 성공, 1 실패(데이터는 저장됨)
"""
import os
import re
import sys
import traceback

from . import filters, mailer
from .config import iso, load_places, load_settings, now_kst
from .kinders import load_kinders, merge_places
from .parser import ParseError, parse_detail, parse_list
from .scraper import Scraper, detail_url
from .store import Store

TRACKED = ("title", "category", "deadline", "posted_at")


def _public_author(author: str) -> str | None:
    """담당자 개인 이름은 저장하지 않는다(공개 저장소). 기관명만 남김."""
    return author if re.search(r"(학교|유치원|교육지원청|교육청)$", author or "") else None


def collect(scraper, store: Store, settings: dict, places: dict, now) -> dict:
    src, f = settings["source"], settings["filters"]
    bootstrap = store.is_empty
    today = now.date().isoformat()
    stats = {"list_count": 0, "kinder_count": 0, "new_count": 0, "changed_count": 0,
             "detail_errors": 0, "pages": 0}

    rows = []
    for page in range(1, src["max_pages"] + 1):
        page_rows = parse_list(scraper.list_page(page))
        stats["pages"] = page
        if not page_rows:
            if page == 1:
                raise ParseError("목록 0건 — 게시판 구조나 주소가 바뀌었을 수 있음")
            break
        rows += page_rows
        if not bootstrap and any(r["post_id"] in store.jobs for r in page_rows):
            break  # 이미 본 글에 닿음 → 더 오래된 페이지는 볼 필요 없음
    stats["list_count"] = len(rows)

    for row in rows:
        if not filters.is_kindergarten(row, f):
            continue
        stats["kinder_count"] += 1
        pid = row["post_id"]
        job = store.jobs.get(pid)
        if job:
            job["last_seen_at"] = iso(now)
            changed = [k for k in TRACKED if row.get(k) != job.get(k)]
            if changed:
                job.update({k: row.get(k) for k in TRACKED})
                job["changed_at"] = iso(now)
                stats["changed_count"] += 1
            continue

        detail, err = {}, None
        try:
            detail = parse_detail(scraper.detail_page(pid))
        except Exception as e:  # 상세 실패는 그 건만 '확인 필요'로 남기고 계속
            err = str(e)[:200]
            stats["detail_errors"] += 1
        job = {
            "post_id": pid,
            "url": detail_url(src, pid),
            "title": row["title"],
            "category": row["category"],
            "author": _public_author(row.get("author")),
            "posted_at": row.get("posted_at"),
            "deadline": row.get("deadline"),
            "deadline_detail": detail.get("deadline_detail"),
            "body": detail.get("body", "")[:1500],
            "image_count": detail.get("image_count", 0),
            "attachments": detail.get("attachments", []),
            "content_hash": detail.get("content_hash"),
            "detail_error": err,
            "first_seen_at": iso(now),
            "last_seen_at": iso(now),
            "notified_at": None,
        }
        if bootstrap and job["deadline"] and job["deadline"] < today:
            job["notified_at"] = "bootstrap"
        store.jobs[pid] = job
        stats["new_count"] += 1

    reclassify(store, f, places)
    return stats


def reclassify(store: Store, f: dict, places: dict) -> None:
    """설정·기관 목록이 바뀌어도 반영되도록 저장된 공고 전체를 다시 분류 (네트워크 없음)."""
    for job in store.jobs.values():
        row = {"title": job["title"], "category": job["category"], "author": job.get("author") or ""}
        cls = filters.classify(row, f, places, job.get("body", ""))
        if job.get("detail_error") and cls["match_status"] == "not_match" and cls["region"] == "미상":
            cls["match_status"] = "review"
        if job.get("deadline_detail") and job.get("deadline") and job["deadline_detail"] != job["deadline"]:
            if cls["match_status"] == "match":
                cls["match_status"] = "review"
            cls["reason"] += f" · 마감일 불일치(목록 {job['deadline']}, 본문 {job['deadline_detail']})"
        job.update(cls)


def main() -> int:
    settings, places = load_settings(), merge_places(load_places(), load_kinders())
    store = Store()
    now = now_kst()
    run = {"started_at": iso(now)}
    code = 0
    try:
        stats = collect(Scraper(settings["source"]), store, settings, places, now)
        run.update(stats)
        run["status"] = "partial" if stats["detail_errors"] else "success"
    except Exception as e:
        reclassify(store, settings["filters"], places)  # 게시판이 안 열려도 분류 기준 변경은 반영
        run["status"] = "failed"
        run["error"] = f"{type(e).__name__}: {e}"[:500]
        traceback.print_exc()
        code = 1
    finish = now_kst()
    run["finished_at"] = iso(finish)
    dropped = store.prune(finish.date(), settings["retention"]["drop_after_deadline_days"])
    run["pruned"] = dropped
    store.add_run(run, settings["retention"]["runs_keep"])
    store.status.update({"last_checked_at": iso(finish), "last_status": run["status"]})
    if run["status"] != "failed":
        store.status["last_success_at"] = iso(finish)
    store.save()

    summary = (f"[{run['status']}] 목록 {run.get('list_count', 0)}건, 유치원 {run.get('kinder_count', 0)}건, "
               f"신규 {run.get('new_count', 0)}건, 변경 {run.get('changed_count', 0)}건")
    print(summary)
    if os.environ.get("GITHUB_STEP_SUMMARY"):
        with open(os.environ["GITHUB_STEP_SUMMARY"], "a", encoding="utf-8") as fh:
            fh.write(summary + "\n")
    if run["status"] == "failed":
        mailer.send_admin("[유치원 공고] 수집 실패", f"{summary}\n\n{run.get('error')}\n\n{mailer.run_link()}")
    return code


if __name__ == "__main__":
    sys.exit(main())
