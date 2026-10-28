"""청주교육지원청 구인 게시판 수집 (학교 게시판 · 교육지원청 게시판).

청주 유치원은 충북교육청 학교구인정보 게시판에 올리지 않고 여기에만 올리는 공고가 많다.
이 게시판에는 마감일 칸이 없고 본문도 대개 비어 있어서, 첫 HWP 첨부에서 접수 마감일을 읽는다.
"""
import difflib
import re
import time
from datetime import date, timedelta
from urllib.parse import parse_qs, urlparse

import requests
from bs4 import BeautifulSoup

from . import filters
from .config import iso
from .docs import doc_text, find_deadline
from .parser import ParseError, _clean, _date

MAX_ATTACHMENT = 8 * 1024 * 1024


class CheongjuScraper:
    def __init__(self, cfg: dict, user_agent: str, session: requests.Session | None = None):
        self.cfg = cfg
        self.s = session or requests.Session()
        self.s.headers["User-Agent"] = user_agent
        self._last = 0.0

    def _get(self, url: str, params: dict | None = None) -> requests.Response:
        wait = self.cfg["request_delay_sec"] - (time.monotonic() - self._last)
        if wait > 0:
            time.sleep(wait)
        last_err = None
        for attempt in range(3):
            try:
                r = self.s.get(url, params=params, timeout=self.cfg["timeout_sec"])
                self._last = time.monotonic()
                if r.status_code == 429 or r.status_code >= 500:
                    last_err = f"HTTP {r.status_code}"
                    time.sleep(5 * (attempt + 1))
                    continue
                r.raise_for_status()
                return r
            except requests.RequestException as e:
                last_err = str(e)
                time.sleep(5 * (attempt + 1))
        raise RuntimeError(f"요청 실패 {url} {params}: {last_err}")

    def list_page(self, menukey: int, page: int) -> str:
        r = self._get(self.cfg["base"] + "/cbcje/sub.php",
                      {"menukey": menukey, "page": page, "listCnt": self.cfg["list_count"]})
        r.encoding = "utf-8"
        return r.text

    def detail_page(self, menukey: int, no: str) -> str:
        r = self._get(self.cfg["base"] + "/cbcje/sub.php", {"menukey": menukey, "mod": "view", "no": no})
        r.encoding = "utf-8"
        return r.text

    def download(self, href: str) -> bytes:
        return self._get(self.cfg["base"] + href).content[:MAX_ATTACHMENT]


def view_url(cfg: dict, menukey: int, no: str) -> str:
    return f"{cfg['base']}/cbcje/sub.php?menukey={menukey}&mod=view&no={no}"


def parse_list(html: str) -> list[dict]:
    soup = BeautifulSoup(html, "lxml")
    table = soup.select_one("table.board")
    if table is None:
        raise ParseError("청주교육지원청 목록 표를 찾지 못함")
    headers = [_clean(th.get_text()) for th in table.select("thead th")]
    if not all(h in headers for h in ("제목", "작성자", "등록일")):
        raise ParseError(f"청주교육지원청 목록 머리글이 바뀜: {headers}")
    idx = {h: headers.index(h) for h in headers}
    rows = []
    for tr in table.select("tbody tr"):
        tds = tr.find_all("td")
        a = tr.select_one("a[href*='mod=view']")
        if a is None or len(tds) < len(headers):
            continue
        no = parse_qs(urlparse(str(a["href"])).query).get("no", [""])[0]
        if not no:
            continue
        level = tds[idx["학교급"]].select_one("span") if "학교급" in idx else None
        rows.append({
            "no": no,
            "title": _clean(str(a.get("title") or a.get_text())),
            "author": _clean(tds[idx["작성자"]].get_text()),
            "posted_at": _date(tds[idx["등록일"]].get_text()),
            "level": _clean(level.get_text()) if level else None,
        })
    return rows


def parse_detail(html: str) -> dict:
    soup = BeautifulSoup(html, "lxml")
    table = soup.select_one("table.board_insert")
    if table is None:
        raise ParseError("청주교육지원청 상세 영역을 찾지 못함")
    files = []
    for a in table.select("a[href*='/base/download/bbs.php']"):
        name = _clean(a.get_text())
        # 같은 파일에 '다운로드'·'뷰어보기' 버튼 링크도 있다 → 확장자가 있는 파일 이름만
        if re.search(r"\.[A-Za-z0-9]{2,5}$", name) and not any(f["name"] == name for f in files):
            files.append({"name": name, "href": str(a["href"])})
    body_el = soup.select_one(".hwp_editor_board_content")
    return {"body": _clean(body_el.get_text(" ")) if body_el else "", "files": files}


# ---------- 중복 판단 ----------
_NOISE = re.compile(r"20\d\d\s*(학년도|년도|년|\.)|채용|모집|공고|위촉|[^가-힣0-9A-Za-z]")


def _norm(title: str) -> str:
    return _NOISE.sub("", title or "")


def same_post(a: dict, b: dict) -> bool:
    """제목이 거의 같고 등록일이 열흘 안이면 같은 공고. 차수(2차·3차)가 다르면 다른 공고."""
    ta, tb = _norm(a.get("title") or ""), _norm(b.get("title") or "")
    if not ta or not tb:
        return False
    if re.findall(r"(\d+)차", a.get("title") or "") != re.findall(r"(\d+)차", b.get("title") or ""):
        return False
    pa, pb = a.get("posted_at"), b.get("posted_at")
    if pa and pb and abs((date.fromisoformat(pa) - date.fromisoformat(pb)).days) > 10:
        return False
    return ta == tb or difflib.SequenceMatcher(None, ta, tb).ratio() >= 0.9


def find_same(store, job: dict, prefix: str | None = None) -> str | None:
    for pid, other in store.jobs.items():
        if pid == job.get("post_id") or (prefix and not pid.startswith(prefix)):
            continue
        if same_post(job, other):
            return pid
    return None


# ---------- 수집 ----------
def _wanted(board: dict, row: dict, f: dict, exclude: list[str]) -> bool:
    if any(w in row["title"] for w in exclude):
        return False
    if board["kind"] == "school":
        return row.get("level") == "유치원" or filters.is_kindergarten({"title": row["title"]}, f)
    # 교육지원청 게시판: 직무를 알아볼 수 있는 채용만 (소방기사·운동부지도자 같은 글 제외)
    return filters.job_type(row["title"], f) is not None


def collect_cheongju(scraper, store, settings: dict, now, stats: dict) -> None:
    cfg, f = settings["cheongju"], settings["filters"]
    today = now.date()
    oldest = (today - timedelta(days=cfg["bootstrap_days"])).isoformat()
    seen = store.seen.setdefault("cheongju", [])
    first_time = not seen
    for board in cfg["boards"]:
        mk = board["menukey"]
        for page in range(1, cfg["max_pages"] + 1):
            rows = parse_list(scraper.list_page(mk, page))
            if not rows:
                if page == 1:
                    raise ParseError(f"청주교육지원청 목록 0건 (menukey {mk})")
                break
            stats["cj_list_count"] = stats.get("cj_list_count", 0) + len(rows)
            reached_seen = False
            for row in rows:
                key = f"{mk}-{row['no']}"
                if key in seen:
                    reached_seen = True
                    continue
                seen.append(key)
                if (row.get("posted_at") or "") < oldest or not _wanted(board, row, f, cfg["exclude_words"]):
                    continue
                pid = f"cj{key}"
                job = {"post_id": pid, "title": row["title"], "posted_at": row.get("posted_at")}
                if find_same(store, job):
                    stats["cj_duplicates"] = stats.get("cj_duplicates", 0) + 1
                    continue  # 충북교육청 게시판에 이미 있음 (마감일 칸이 있는 쪽을 쓴다)
                _add(scraper, store, cfg, board, row, pid, now, stats)
            if reached_seen and not first_time:
                break  # 이미 본 글에 닿음
    store.seen["cheongju"] = seen[-3000:]


def _add(scraper, store, cfg, board, row, pid, now, stats) -> None:
    mk = board["menukey"]
    detail, err, deadline, src = {"body": "", "files": []}, None, None, None
    try:
        detail = parse_detail(scraper.detail_page(mk, row["no"]))
        posted = date.fromisoformat(row["posted_at"]) if row.get("posted_at") else now.date()
        deadline = find_deadline(detail["body"], posted)
        src = "본문" if deadline else None
        for fdesc in detail["files"]:
            if deadline or not re.search(r"\.(hwp|hwpx)$", fdesc["name"], re.I):
                continue
            deadline = find_deadline(doc_text(fdesc["name"], scraper.download(fdesc["href"])), posted)
            src = "첨부 공고문" if deadline else None
            break  # 첫 공고문만 읽는다
    except Exception as e:
        err = str(e)[:200]
        stats["detail_errors"] = stats.get("detail_errors", 0) + 1
    author = row.get("author") or ""
    store.jobs[pid] = {
        "post_id": pid,
        "source": "청주교육지원청",
        "url": view_url(cfg, mk, row["no"]),
        "title": row["title"],
        "category": "유치원" if board["kind"] == "school" else "교육지원청",
        # 학교 이름은 '창신유치원', '각리초'처럼 쓰여 있다. 사람 이름일 수 있는 짧은 값은 저장하지 않는다
        "author": author if re.search(r"(유치원|초|중|고|학교|교육지원청|과)$", author) else None,
        "posted_at": row.get("posted_at"),
        "deadline": deadline,
        "deadline_source": src,
        "deadline_detail": None,
        "body": detail["body"][:1500],
        "image_count": 0,
        "attachments": [x["name"] for x in detail["files"]],
        "content_hash": None,
        "detail_error": err,
        "first_seen_at": iso(now),
        "last_seen_at": iso(now),
        "notified_at": "bootstrap" if deadline and deadline < now.date().isoformat() else None,
    }
    stats["cj_new_count"] = stats.get("cj_new_count", 0) + 1
