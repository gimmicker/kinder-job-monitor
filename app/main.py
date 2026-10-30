"""수집 → 분류 → 저장. 알림은 사이트 배포 후 app.push가 따로 보낸다.

사용: python -m app.main                  두 출처 모두 (GitHub Actions에서는 충북교육청만)
      python -m app.main --only-cheongju   청주교육지원청만 (한국 인터넷에서, scripts/sync_cheongju.py가 부른다)
종료 코드: 0 성공/부분 성공, 1 실패(데이터는 저장됨)
"""
import os
import re
import sys
import traceback
from datetime import date

from . import filters, mailer
from .config import iso, load_places, load_settings, now_kst
from .kinders import load_kinders, merge_places
from .cheongju import CheongjuScraper, collect_cheongju, find_same, same_post
from .docs import find_deadline
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
            board = {**job, "deadline": job.get("deadline_board") or job.get("deadline")}
            changed = [k for k in TRACKED if row.get(k) != board.get(k)]
            if changed:
                job.update({k: row.get(k) for k in TRACKED})
                job.pop("deadline_board", None)  # 아래 reclassify에서 본문과 다시 비교
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
        dup = find_same(store, job, prefix="cj")
        if dup:  # 청주교육지원청에서 먼저 받은 같은 공고 → 마감일 칸이 있는 이쪽으로 바꾼다
            job["notified_at"] = job["notified_at"] or store.jobs[dup].get("notified_at")
            del store.jobs[dup]
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
        apply_body_deadline(job)
        board = job.get("deadline_board") or job.get("deadline")
        if job.get("deadline_detail") and board and job["deadline_detail"] != board:
            if cls["match_status"] == "match":
                cls["match_status"] = "review"
            cls["reason"] += f" · 마감일 불일치(목록 {board}, 본문 {job['deadline_detail']})"
        job.update(cls)


def apply_body_deadline(job: dict) -> None:
    """충북교육청 게시판 마감일 칸보다 공고 본문의 접수 마감일이 이르면 본문 날짜를 쓴다.
    (게시 기간을 마감일 칸에 넣는 학교가 있다. 늦게 알면 지원을 놓친다.)"""
    if job.get("source"):
        return  # 청주교육지원청 공고는 처음부터 본문·첨부에서 읽는다
    board = job.get("deadline_board") or job.get("deadline")
    body_dl = None
    if board and job.get("posted_at") and job.get("body"):
        body_dl = find_deadline(job["body"], date.fromisoformat(job["posted_at"]))
    if body_dl and body_dl < board:
        job.update({"deadline": body_dl, "deadline_board": board, "deadline_source": "본문"})
    elif job.get("deadline_board"):
        job["deadline"] = job.pop("deadline_board")
        job.pop("deadline_source", None)


def merge_duplicates(store: Store) -> int:
    """두 게시판에 같이 올라온 공고는 충북교육청 쪽 하나만 남긴다 (이미 알렸으면 그 기록을 옮긴다)."""
    pool = [j for k, j in store.jobs.items() if not k.startswith("cj")]
    drop = []
    for k, cj in store.jobs.items():
        if not k.startswith("cj"):
            continue
        same = next((p for p in pool if same_post(cj, p)), None)
        if same:
            same["notified_at"] = same.get("notified_at") or cj.get("notified_at")
            drop.append(k)
    for k in drop:
        del store.jobs[k]
    return len(drop)


class _Skip(Exception):
    pass


def settings_skip_cj() -> bool:
    return bool(load_settings().get("cheongju", {}).get("skip_on_github", True))


def record_check(status: dict, result: str, at: str) -> None:
    """충북교육청 확인 결과 기록. 화면에는 하루치(3번) 연속 실패일 때만 알린다."""
    status.update({"last_checked_at": at, "last_status": result})
    if result != "failed":
        status["last_success_at"] = at
        status["fail_streak"] = 0
    else:
        status["fail_streak"] = status.get("fail_streak", 0) + 1


def main(argv=None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    only_cj = "--only-cheongju" in argv
    # 청주교육지원청 사이트는 해외 접속을 막는다 → GitHub Actions(미국)에서는 건너뛰고 한국 PC에서 따로 돌린다
    skip_cj = os.environ.get("GITHUB_ACTIONS") == "true" and settings_skip_cj()
    settings, places = load_settings(), merge_places(load_places(), load_kinders())
    store = Store()
    now = now_kst()
    run = {"started_at": iso(now), "status": "success"}
    if only_cj:
        run["source"] = "cheongju"
    code = 0
    if not only_cj:
        try:
            stats = collect(Scraper(settings["source"]), store, settings, places, now)
            run.update(stats)
            run["status"] = "partial" if stats["detail_errors"] else "success"
        except Exception as e:
            run["status"] = "failed"
            run["error"] = f"{type(e).__name__}: {e}"[:500]
            traceback.print_exc()
            code = 1
    # 두 번째 출처: 청주교육지원청. 한쪽이 실패해도 다른 쪽은 계속한다
    cj = {}
    try:
        if skip_cj:
            raise _Skip()
        collect_cheongju(CheongjuScraper(settings["cheongju"], settings["source"]["user_agent"]),
                         store, settings, now, cj)
        run.update(cj)
        if cj.get("detail_errors") and run["status"] == "success":
            run["status"] = "partial"
    except _Skip:
        run["cheongju"] = "skipped (해외 접속 차단, PC에서 수집)"
    except Exception as e:
        run["cheongju_error"] = f"{type(e).__name__}: {e}"[:500]
        traceback.print_exc()
        if run["status"] == "success":
            run["status"] = "partial"
    run["merged"] = merge_duplicates(store)
    reclassify(store, settings["filters"], places)  # 게시판이 안 열려도 분류 기준 변경은 반영
    finish = now_kst()
    run["finished_at"] = iso(finish)
    dropped = store.prune(finish.date(), settings["retention"]["drop_after_deadline_days"])
    run["pruned"] = dropped
    store.add_run(run, settings["retention"]["runs_keep"])
    if only_cj:
        store.status["cheongju_checked_at"] = iso(finish)
    else:
        record_check(store.status, run["status"], iso(finish))
    store.save()

    summary = (f"[{run['status']}] 목록 {run.get('list_count', 0)}건, 유치원 {run.get('kinder_count', 0)}건, "
               f"신규 {run.get('new_count', 0)}건, 변경 {run.get('changed_count', 0)}건 / "
               f"청주교육지원청 신규 {run.get('cj_new_count', 0)}건, 중복 {run.get('cj_duplicates', 0)}건"
               + (f", 오류: {run['cheongju_error']}" if run.get("cheongju_error") else ""))
    print(summary)
    if os.environ.get("GITHUB_STEP_SUMMARY"):
        with open(os.environ["GITHUB_STEP_SUMMARY"], "a", encoding="utf-8") as fh:
            fh.write(summary + "\n")
    if run["status"] == "failed":
        mailer.send_admin("[유치원 공고] 수집 실패", f"{summary}\n\n{run.get('error')}\n\n{mailer.run_link()}")
    return code


if __name__ == "__main__":
    sys.exit(main())
