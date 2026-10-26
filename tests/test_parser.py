import pytest

from app.parser import ParseError, _date, parse_detail, parse_list
from tests.conftest import fixture_text


def test_list_parses_all_rows_with_required_fields():
    rows = parse_list(fixture_text("list_100.html"))
    assert len(rows) == 100
    for r in rows:
        assert r["post_id"].isdigit()
        assert r["title"] and r["category"]
        assert r["posted_at"] and len(r["posted_at"]) == 10


def test_list_first_row_values():
    r = parse_list(fixture_text("list_100.html"))[0]
    assert r == {
        "post_id": "1581252", "category": "유치원",
        "title": "2026. 주중초병설유치원 겨울방학 중 방과후과정 강사 채용 공고",
        "author": "이민애", "posted_at": "2026-10-26", "deadline": "2026-11-02",
    }


def test_list_structure_change_raises():
    with pytest.raises(ParseError):
        parse_list("<html><body><p>점검 중</p></body></html>")
    with pytest.raises(ParseError):
        parse_list("<table><thead><tr><th>번호</th><th>제목</th></tr></thead><tbody></tbody></table>")


def test_list_empty_table_returns_empty():
    html = ("<div class='bbs_ListA'><table><thead><tr>" + "".join(f"<th>{h}</th>" for h in
            ["번호", "분류", "제목", "작성자", "등록일", "마감일", "조회수"]) +
            "</tr></thead><tbody><tr><td colspan=7>게시물이 없습니다.</td></tr></tbody></table></div>")
    assert parse_list(html) == []


def test_detail():
    d = parse_detail(fixture_text("detail_1581252.html"))
    assert d["image_count"] == 2
    assert len(d["attachments"]) == 2 and d["attachments"][0].endswith(".pdf")
    assert d["deadline_detail"] == "2026-11-02"
    assert "주중초등학교병설유치원" in d["body"]
    assert len(d["content_hash"]) == 16


@pytest.mark.parametrize("s,want", [
    ("2026.10.26.", "2026-10-26"), ("2026/11/02", "2026-11-02"), ("2026-1-5", "2026-01-05"),
    ("", None), ("미정", None), ("2026.13.01", None),
])
def test_date(s, want):
    assert _date(s) == want
