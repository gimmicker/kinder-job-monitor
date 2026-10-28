"""유치원알리미 '일반현황' 공시 자료로 config/kinders.json을 만든다.

필요: 유치원알리미 OPEN API 인증키 (e-childschoolinfo.moe.go.kr → 자료실 → OPEN API)
사용: CHILD_KEY=... python scripts/build_kinders.py
공시는 1년에 몇 번만 바뀌므로 그때 한 번씩 다시 실행해서 커밋한다.
"""
import json
import os
import sys
from datetime import date
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app.kinders import KINDERS_PATH, key_for  # noqa: E402

URL = "https://e-childschoolinfo.moe.go.kr/api/notice/basicInfo2.do"
SIDO = 43  # 충청북도
SGG = [43111, 43112, 43113, 43114, 43130, 43150, 43720, 43730, 43740, 43745, 43750, 43760, 43770, 43800]


def num(v) -> int:
    try:
        return int(v)
    except (TypeError, ValueError):
        return 0


def slim(k: dict) -> dict:
    parts = (k.get("addr") or "").split()
    city = parts[1][:-1] if len(parts) > 1 and parts[1][-1] in "시군" else None
    area = parts[2] if len(parts) > 2 and parts[2][-1] in "구읍면" else None
    return {
        "name": k["kindername"], "establish": k.get("establish"), "addr": k.get("addr"),
        "tel": k.get("telno"), "city": city, "area": area,
        "classes": sum(num(k.get(f)) for f in ["clcnt3", "clcnt4", "clcnt5", "mixclcnt", "shclcnt"]),
        "kids": sum(num(k.get(f)) for f in ["ppcnt3", "ppcnt4", "ppcnt5", "mixppcnt", "shppcnt"]),
        "special_classes": num(k.get("shclcnt")), "timing": k.get("pbnttmng"),
    }


def main():
    key = os.environ.get("CHILD_KEY")
    if not key:
        sys.exit("CHILD_KEY 환경변수가 필요합니다.")
    out, dup = {}, set()
    for sgg in SGG:
        r = requests.get(URL, params={"key": key, "sidoCode": SIDO, "sggCode": sgg}, timeout=30)
        d = r.json()
        if d.get("status") != "SUCCESS":
            sys.exit(f"{sgg}: {d.get('status')} {d.get('message')}")
        for k in d.get("kinderInfo") or []:
            kk = key_for(k["kindername"])
            if not kk:
                continue
            if kk in out and out[kk]["city"] != slim(k)["city"]:
                dup.add(kk)  # 다른 지역에 같은 이름 → 어느 쪽인지 알 수 없으니 뺀다
            out[kk] = slim(k)
    for kk in dup:
        out.pop(kk, None)
    KINDERS_PATH.write_text(json.dumps({"updated": date.today().isoformat(), "kinders": dict(sorted(out.items()))},
                                       ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"유치원 {len(out)}곳 저장, 이름이 겹쳐 뺀 곳 {len(dup)}곳: {sorted(dup)}")


if __name__ == "__main__":
    main()
