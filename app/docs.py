"""첨부 공고문(HWP, HWPX)에서 글자를 뽑고, 접수 마감일을 찾는다.

청주교육지원청 게시판은 본문이 비어 있고 내용이 첨부 HWP에만 있는 경우가 많다.
"""
import io
import re
import struct
import zipfile
import zlib
from datetime import date

import olefile

PARA_TEXT = 67  # HWP 5.0 문단 글자 레코드


def hwp_text(data: bytes) -> str:
    """HWP 5.0 (OLE 복합 문서) → 글자. 표 안의 글자도 포함된다."""
    ole = olefile.OleFileIO(io.BytesIO(data))
    header = ole.openstream("FileHeader").read()
    compressed = bool(header[36] & 1)
    out = []
    i = 0
    while ole.exists(f"BodyText/Section{i}"):
        raw = ole.openstream(f"BodyText/Section{i}").read()
        if compressed:
            raw = zlib.decompress(raw, -15)
        pos = 0
        while pos + 4 <= len(raw):
            h = struct.unpack_from("<I", raw, pos)[0]
            tag, size = h & 0x3FF, (h >> 20) & 0xFFF
            pos += 4
            if size == 0xFFF:
                size = struct.unpack_from("<I", raw, pos)[0]
                pos += 4
            if tag == PARA_TEXT:
                out.append(_para(raw[pos:pos + size]))
            pos += size
        i += 1
    return "\n".join(out)


def _para(b: bytes) -> str:
    """문단 레코드의 UTF-16 글자. 0~31은 제어 문자이고, 일부는 뒤에 7글자(14바이트)가 딸려 있다."""
    chars, i = [], 0
    while i + 1 < len(b):
        c = struct.unpack_from("<H", b, i)[0]
        i += 2
        if c < 32:
            if c in (1, 2, 3, 4, 5, 6, 7, 8, 11, 12, 14, 15, 16, 17, 18, 19, 20, 21, 22, 23):
                i += 14
            elif c in (9, 10, 13, 24, 30, 31):
                chars.append(" ")
            continue
        chars.append(chr(c))
    return "".join(chars)


def hwpx_text(data: bytes) -> str:
    """HWPX (ZIP 안의 XML) → 글자."""
    out = []
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        for name in sorted(n for n in z.namelist() if re.match(r"Contents/section\d+\.xml$", n)):
            xml = z.read(name).decode("utf-8", "ignore")
            out += re.findall(r"<hp:t(?:\s[^>]*)?>([^<]*)</hp:t>", xml)
    return " ".join(out)


def doc_text(name: str, data: bytes) -> str:
    """파일 이름의 확장자로 형식을 고른다. 읽지 못하면 빈 문자열."""
    try:
        if name.lower().endswith(".hwpx") or data[:2] == b"PK":
            return hwpx_text(data)
        if name.lower().endswith(".hwp") or data[:8] == b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1":
            return hwp_text(data)
    except Exception:
        return ""
    return ""


# 접수(제출) 기간을 말하는 문구. 이 뒤 150자 안에서 날짜를 찾는다
_ANCHOR = re.compile(r"(원서\s*접수|서류\s*접수|서류\s*제출|신청서\s*접수|접수\s*(기간|기한|마감|일시|일정)|제출\s*(기간|기한)"
                     r"|지원서\s*접수|모집\s*기간|신청\s*기간|접\s*수\s*기\s*간)")
_FULL = re.compile(r"(20\d\d)\s*[.년/-]\s*(\d{1,2})\s*[.월/-]\s*(\d{1,2})")
_SHORT = re.compile(r"(?<![\d.])(\d{1,2})\s*[.월/]\s*(\d{1,2})\s*[.일]?\s*(?:\(|［|\[)|(?<!\d)(\d{1,2})\s*월\s*(\d{1,2})\s*일")


def find_deadline(text: str, posted: date) -> str | None:
    """접수 기간 문구 뒤의 날짜 중 마지막(기간의 끝)을 마감일로 본다. 연도가 없으면 등록 연도."""
    t = re.sub(r"\s+", " ", text or "")
    best = None
    for m in _ANCHOR.finditer(t):
        seg = t[m.end():m.end() + 150]
        # 다음 항목 번호(예: ' 6. ', '나.')가 나오면 거기서 자른다
        cut = re.search(r"\s(\d{1,2}\s*\.|[가-하]\s*\.)\s*[가-힣]", seg[10:])
        if cut:
            seg = seg[:10 + cut.start()]
        dates = []
        for d in _FULL.finditer(seg):
            dates.append((d.start(), int(d.group(1)), int(d.group(2)), int(d.group(3))))
        for d in _SHORT.finditer(seg):
            if not any(abs(d.start() - x[0]) < 12 for x in dates):
                mo, dd = (d.group(1), d.group(2)) if d.group(1) else (d.group(3), d.group(4))
                dates.append((d.start(), posted.year, int(mo), int(dd)))
        dates.sort()
        for _, y, mo, dd in dates:
            try:
                cand = date(y, mo, dd)
            except ValueError:
                continue
            if mo < posted.month - 6:  # 12월에 올린 공고의 1월 마감
                cand = date(y + 1, mo, dd)
            if posted <= cand <= date(posted.year + 1, 12, 31):
                best = cand  # 기간의 끝 날짜까지 계속 갱신
        if best:
            return best.isoformat()
    return None
