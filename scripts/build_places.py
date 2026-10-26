"""NEIS 학교 정보로 config/places.yaml의 '초' 목록을 채운다 (병설유치원 지역 판단용).

필요: NEIS 오픈API 인증키 (https://open.neis.go.kr → 인증키 신청, 무료·즉시 발급)
사용: NEIS_KEY=... python scripts/build_places.py
이미 손으로 넣은 항목은 덮어쓰지 않는다.
"""
import os
import re
import sys
from pathlib import Path

import requests
import yaml

PLACES = Path(__file__).resolve().parent.parent / "config" / "places.yaml"
CITIES = ["청주", "충주", "제천", "보은", "옥천", "영동", "증평", "진천", "괴산", "음성", "단양"]


def fetch(key: str) -> list[dict]:
    rows, page = [], 1
    while True:
        r = requests.get("https://open.neis.go.kr/hub/schoolInfo", timeout=30, params={
            "KEY": key, "Type": "json", "ATPT_OFCDC_SC_CODE": "M10", "SCHUL_KND_SC_NM": "초등학교",
            "pIndex": page, "pSize": 1000})
        data = r.json().get("schoolInfo")
        if not data:
            break
        rows += data[1]["row"]
        if len(rows) >= data[0]["head"][0]["list_total_count"]:
            break
        page += 1
    return rows


def main():
    key = os.environ.get("NEIS_KEY")
    if not key:
        sys.exit("NEIS_KEY 환경변수가 필요합니다.")
    places = yaml.safe_load(PLACES.read_text(encoding="utf-8")) or {}
    cho = places.get("초") or {}
    added = 0
    for s in fetch(key):
        m = re.match(r"^(.+?)초등학교$", s["SCHUL_NM"])
        if not m or m.group(1).startswith("(가칭)"):
            continue
        addr = s.get("ORG_RDNMA") or ""
        city = next((c for c in CITIES if c in addr), None)
        if city and m.group(1) not in cho:
            cho[m.group(1)] = "청주" if city == "청주" else city
            added += 1
    places["초"] = dict(sorted(cho.items()))
    places.setdefault("유", {})
    header = "".join(l + "\n" for l in PLACES.read_text(encoding="utf-8").splitlines() if l.startswith("#"))
    PLACES.write_text(header + "\n" + yaml.safe_dump(places, allow_unicode=True, sort_keys=False), encoding="utf-8")
    print(f"초등학교 {added}곳 추가 (전체 {len(cho)}곳)")


if __name__ == "__main__":
    main()
