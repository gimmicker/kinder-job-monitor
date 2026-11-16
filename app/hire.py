"""충북교육청 기간제교사인력풀 '기간제 채용공고' 게시판 수집.

학교구인정보 게시판(bbsId 1798)과 다른 글이 올라온다. 지역·구분 칸은 있지만 마감일 칸이 없어서
본문이나 첫 HWP 첨부에서 접수 마감일을 읽는다.
"""
import re
import time
from datetime import date, timedelta

from bs4 import BeautifulSoup

from . import filters
from .cheongju import MAX_ATTACHMENT, find_same
from .config import iso
from .docs import doc_text, find_deadline
from .parser import ParseError, _clean, _date
from .parser import parse_detail as parse_pool_detail
from .scraper import Scraper


class HireScraper(Scraper):
    def __init__(self, cfg: dict, user_agent: str, session=None):
        super().__init__({**cfg, "user_agent": user_agent}, session)

    def download(self, file_key: str) -> bytes:
        """첨부는 POST로만 내려받을 수 있다 (게시판의 goFileDown)."""
        wait = self.src["request_delay_sec"] - (time.monotonic() - self._last)
        if wait > 0:
            time.sleep(wait)
        r = self.s.post(self.src["base"] + self.src["download_path"], params={"fileKey": file_key},
                        timeout=self.src["timeout_sec"])
        self._last = time.monotonic()
        r.raise_for_status()
        return r.content[:MAX_ATTACHMENT]


def detail_url(cfg: dict, post_id: str) -> str:
    return f"{cfg['base']}{cfg['detail_path']}?bbsId={cfg['bbs_id']}&nttSn={post_id}&mi={cfg['mi']}"


def parse_list(html: str) -> list[dict]:
    soup = BeautifulSoup(html, "lxml")
    table = soup.select_one("div.bbs_ListA table") or soup.find("table")
    if table is None:
        raise ParseError("기간제 채용공고 목록 표를 찾지 못함")
    headers = [_clean(th.get_text()) for th in table.select("thead th")]
    want = ["지역", "구분", "제목", "작성자", "등록일"]
    if not all(h in headers for h in want):
        raise ParseError(f"기간제 채용공고 목록 머리글이 바뀜: {headers}")
    idx = {h: headers.index(h) for h in want}
    rows = []
    for tr in table.select("tbody tr"):
        tds = tr.find_all("td")
        a = tr.select_one("a.nttInfoBtn[data-id]")
        if a is None or len(tds) < len(headers):
            continue
        title = re.sub(r"^(새글\s*)?N\s+", "", _clean(a.get("title") or a.get_text()))
        rows.append({
            "post_id": a["data-id"].strip(),
            "region": _clean(tds[idx["지역"]].get_text()),
            "levels": [x.strip() for x in tds[idx["구분"]].get_text().split(",") if x.strip()],
            "title": title,
            "author": _clean(tds[idx["작성자"]].get_text()),
            "posted_at": _date(tds[idx["등록일"]].get_text()),
        })
    return rows


def parse_detail(html: str) -> dict:
    """본문·첨부 이름은 학교구인정보 게시판과 같은 모양. 첨부 내려받기 열쇠를 더한다."""
    out = parse_pool_detail(html)
    keys = []
    for a in BeautifulSoup(html, "lxml").select("div.bbs_ViewA .bbsV_atchmnfl a.fileName"):
        m = re.search(r"goFileDown\('([0-9a-f]+)'\)", str(a.get("href") or ""))
        name = _clean(a.get_text())
        if m and name and not any(k["name"] == name for k in keys):
            keys.append({"name": name, "key": m.group(1)})
    out["files"] = keys
    return out


def _wanted(row: dict, f: dict, exclude: list[str]) -> bool:
    if any(w in row["title"] for w in exclude):
        return False
    return "유치원" in row["levels"] or filters.is_kindergarten({"title": row["title"]}, f)


def collect_hire(scraper, store, settings: dict, now, stats: dict) -> None:
    cfg, f = settings["hire"], settings["filters"]
    oldest = (now.date() - timedelta(days=cfg["bootstrap_days"])).isoformat()
    seen = store.seen.setdefault("hire", [])
    first_time = not seen
    for page in range(1, cfg["max_pages"] + 1):
        rows = parse_list(scraper.list_page(page))
        if not rows:
            if page == 1:
                raise ParseError("기간제 채용공고 목록 0건 — 게시판 구조나 주소가 바뀌었을 수 있음")
            break
        stats["kj_list_count"] = stats.get("kj_list_count", 0) + len(rows)
        reached_seen = False
        for row in rows:
            if row["post_id"] in seen:
                reached_seen = True
                continue
            seen.append(row["post_id"])
            if (row.get("posted_at") or "") < oldest or not _wanted(row, f, cfg["exclude_words"]):
                continue
            pid = f"kj{row['post_id']}"
            job = {"post_id": pid, "title": row["title"], "posted_at": row.get("posted_at")}
            dup = find_same(store, job)
            if dup and not dup.startswith(("cj", "kj")):
                stats["kj_duplicates"] = stats.get("kj_duplicates", 0) + 1
                continue  # 학교구인정보 게시판에 이미 있음 (마감일 칸이 있는 쪽을 쓴다)
            _add(scraper, store, cfg, row, pid, now, stats)
        if reached_seen and not first_time:
            break  # 이미 본 글에 닿음
    store.seen["hire"] = seen[-3000:]


def _add(scraper, store, cfg, row, pid, now, stats) -> None:
    detail = {"body": "", "files": [], "image_count": 0, "content_hash": None}
    err, deadline, src = None, None, None
    try:
        detail = parse_detail(scraper.detail_page(row["post_id"]))
        posted = date.fromisoformat(row["posted_at"]) if row.get("posted_at") else now.date()
        deadline = find_deadline(detail["body"], posted)
        src = "본문" if deadline else None
        for fdesc in detail["files"]:
            if deadline or not re.search(r"\.(hwp|hwpx)$", fdesc["name"], re.I):
                continue
            deadline = find_deadline(doc_text(fdesc["name"], scraper.download(fdesc["key"])), posted)
            src = "첨부 공고문" if deadline else None
            break  # 첫 공고문만 읽는다
    except Exception as e:
        err = str(e)[:200]
        stats["detail_errors"] = stats.get("detail_errors", 0) + 1
    author = row.get("author") or ""
    store.jobs[pid] = {
        "post_id": pid,
        "source": "충북교육청 기간제 채용공고",
        "url": detail_url(cfg, row["post_id"]),
        "title": row["title"],
        "category": "유치원" if "유치원" in row["levels"] else ", ".join(row["levels"]),
        "board_region": row.get("region") or None,
        # 작성자 칸은 담당자 개인 이름일 때가 많다. 학교 이름으로 끝날 때만 남긴다
        "author": author if re.search(r"(유치원|초|중|고|학교|교육지원청)$", author) else None,
        "posted_at": row.get("posted_at"),
        "deadline": deadline,
        "deadline_source": src,
        "deadline_detail": None,
        "body": detail["body"][:1500],
        "image_count": detail.get("image_count", 0),
        "attachments": [x["name"] for x in detail["files"]],
        "content_hash": detail.get("content_hash"),
        "detail_error": err,
        "first_seen_at": iso(now),
        "last_seen_at": iso(now),
        "notified_at": "bootstrap" if deadline and deadline < now.date().isoformat() else None,
    }
    stats["kj_new_count"] = stats.get("kj_new_count", 0) + 1
