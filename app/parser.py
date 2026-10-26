"""게시판 HTML → dict. 네트워크와 무관하게 테스트할 수 있도록 순수 함수로 둔다."""
import hashlib
import re

from bs4 import BeautifulSoup


class ParseError(Exception):
    pass


def _date(text: str) -> str | None:
    """'2026.10.26.' / '2026/11/02' / '2026-11-02' → '2026-11-02'"""
    m = re.search(r"(\d{4})\s*[./-]\s*(\d{1,2})\s*[./-]\s*(\d{1,2})", text or "")
    if not m:
        return None
    y, mo, d = (int(x) for x in m.groups())
    if not (1 <= mo <= 12 and 1 <= d <= 31):
        return None
    return f"{y:04d}-{mo:02d}-{d:02d}"


def _clean(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").replace("\xa0", " ")).strip()


def parse_list(html: str) -> list[dict]:
    """목록 페이지의 게시글 행. 필수 필드가 하나도 안 잡히면 ParseError."""
    soup = BeautifulSoup(html, "lxml")
    table = soup.select_one("div.bbs_ListA table") or soup.find("table")
    if table is None:
        raise ParseError("목록 표를 찾지 못함")
    headers = [_clean(th.get_text()) for th in table.select("thead th")]
    want = ["번호", "분류", "제목", "작성자", "등록일", "마감일"]
    if not all(h in headers for h in want):
        raise ParseError(f"목록 머리글이 바뀜: {headers}")
    idx = {h: headers.index(h) for h in want}

    rows = []
    for tr in table.select("tbody tr"):
        tds = tr.find_all("td")
        a = tr.select_one("a.nttInfoBtn[data-id]")
        if a is None or len(tds) < len(headers):
            continue  # '게시물이 없습니다' 같은 행
        title = _clean(a.get("title") or a.get_text())
        title = re.sub(r"^(새글\s*)?N\s+", "", title)
        rows.append({
            "post_id": a["data-id"].strip(),
            "category": _clean(tds[idx["분류"]].get_text()),
            "title": title,
            "author": _clean(tds[idx["작성자"]].get_text()),
            "posted_at": _date(tds[idx["등록일"]].get_text()),
            "deadline": _date(tds[idx["마감일"]].get_text()),
        })
    return rows


def parse_detail(html: str) -> dict:
    soup = BeautifulSoup(html, "lxml")
    view = soup.select_one("div.bbs_ViewA")
    if view is None:
        raise ParseError("상세 영역을 찾지 못함")
    cont = view.select_one(".bbsV_cont")
    body = _clean(cont.get_text(" ")) if cont else ""
    images = len(cont.find_all("img")) if cont else 0
    files = []
    for a in view.select(".bbsV_atchmnfl a.fileName"):
        name = _clean(a.get_text())
        if name and name not in files:
            files.append(name)
    meta = {}
    for li in view.select("ul.bbsV_data li"):
        strong = li.find("strong")
        if strong:
            key = _clean(strong.get_text())
            meta[key] = _clean(li.get_text().replace(strong.get_text(), "", 1))
    digest = hashlib.sha256((body + "|" + "|".join(files)).encode("utf-8")).hexdigest()[:16]
    return {
        "body": body[:4000],
        "image_count": images,
        "attachments": files,
        "deadline_detail": _date(meta.get("마감일", "")),
        "content_hash": digest,
    }
