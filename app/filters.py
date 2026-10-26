"""규칙 분류. 원칙: 놓치지 않기 우선 — 확실할 때만 '부적합'."""
import re

SUFFIX_RE = re.compile(
    r"([가-힣]{1,12}?)\s?(초등학교\s?병설\s?유치원|초\s?병설\s?유치원|초\s?병설유|초등학교|유치원)"
)
GENERIC = {"병설", "공립", "사립", "단설", "국립", "학년도", "년", "중", "및", "의"}


def institutions(*texts: str) -> list[tuple[str, str, str]]:
    """텍스트에서 (kind, base, 원래이름) 목록. kind: '초'(초등/병설) 또는 '유'(단설 유치원)."""
    found = []
    for text in texts:
        for m in SUFFIX_RE.finditer(text or ""):
            base, suffix = m.group(1), m.group(2).replace(" ", "")
            if base in GENERIC or len(base) < 2 and suffix == "유치원":
                continue
            kind = "유" if suffix == "유치원" else "초"
            item = (kind, base, m.group(0).replace(" ", ""))
            if item not in found:
                found.append(item)
    return found


def _any(words, text):
    return next((w for w in words if w in text), None)


def job_type(title: str, f: dict) -> str | None:
    for jt in f["job_types"]:
        if _any(jt["words"], title):
            return jt["type"]
    return None


def _starts(words, base):
    return next((w for w in words if base.startswith(w)), None)


def region(title: str, author: str, body: str, f: dict, places: dict) -> tuple[str, str]:
    """('청주' | '기타' | '미상', 근거). 순서는 settings.yaml 주석 참고."""
    r = f["region"]
    insts = institutions(title, author)
    for kind, base, name in insts:
        v = places.get(kind, {}).get(base)
        if v:
            return ("청주" if v == "청주" else "기타"), f"기관 목록: {name} → {v}"
    head = f"{title} {author}"
    w = _any(r["cheongju_words"], head)
    if w:
        return "청주", f"'{w}' 포함"
    for kind, base, name in insts:
        w = _starts(r["cheongju_towns"], base)
        if w:
            return "청주", f"{name}: 청주 {w}"
        w = _starts(r["other_towns"], base)
        if w:
            return "기타", f"{name}: {w} 지역"
    w = _any(r["other_names"], head)
    if w:
        return "기타", f"'{w}' 포함"
    w = _any(r["cheongju_words"], body or "")
    if w:
        return "청주", f"본문에 '{w}'"
    name = insts[0][2] if insts else "기관"
    return "미상", f"{name} 지역 확인 필요"


def is_kindergarten(row: dict, f: dict) -> bool:
    return row.get("category") in f["categories"] or bool(_any(f["kindergarten_words"], row.get("title", "")))


def institution_name(row: dict) -> str | None:
    insts = institutions(row.get("title", ""), row.get("author", ""))
    if insts:
        return insts[0][2]
    a = row.get("author") or ""
    return a if re.search(r"(학교|유치원)$", a) else None


def classify(row: dict, f: dict, places: dict, body: str = "") -> dict:
    title = row.get("title", "")
    jt = job_type(title, f)
    reg, reg_reason = region(title, row.get("author", ""), body, f, places)

    if not is_kindergarten(row, f):
        status, reason = "not_match", "유치원 공고 아님"
    elif jt in f["exclude_job_types"]:
        status, reason = "not_match", f"{jt} 모집"
    elif reg == "기타":
        status, reason = "not_match", f"청주 아님 ({reg_reason})"
    elif reg == "청주" and jt in f["match_job_types"]:
        status, reason = "match", f"청주({reg_reason}) · {jt}"
    elif reg == "청주":
        status, reason = "review", f"청주({reg_reason}) · 직무 확인 필요({jt or '유형 미상'})"
    else:
        status, reason = "review", f"{reg_reason} · {jt or '직무 미상'}"

    return {"match_status": status, "reason": reason, "job_type": jt, "region": reg,
            "institution": institution_name(row)}
