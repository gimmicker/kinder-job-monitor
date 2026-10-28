"""GitHub Pages에 올릴 _site 폴더를 만든다.

환경변수: VAPID_PUBLIC_KEY, WORKER_URL (없으면 알림 버튼이 '준비 중'으로 표시됨)
사용: python -m app.build_site [출력폴더]
"""
import json
import os
import shutil
import sys
from pathlib import Path

from .config import DATA_DIR, ROOT
from .kinders import find, load_kinders

PUBLIC_FIELDS = ["post_id", "url", "title", "category", "author", "institution", "posted_at", "deadline",
                 "deadline_detail", "attachments", "image_count", "match_status", "reason", "job_type",
                 "region", "first_seen_at", "changed_at", "detail_error"]


def build(out: Path) -> None:
    if out.exists():
        shutil.rmtree(out)
    shutil.copytree(ROOT / "web", out)
    (out / "data").mkdir()
    jobs = json.loads((DATA_DIR / "jobs.json").read_text(encoding="utf-8")) if (DATA_DIR / "jobs.json").exists() else {}
    kinders = load_kinders()
    slim = []
    for j in jobs.values():
        row = {k: j.get(k) for k in PUBLIC_FIELDS}
        row["kinder"] = find(j, kinders)  # 원아·학급 수, 주소 (유치원알리미 공시)
        slim.append(row)
    (out / "data" / "jobs.json").write_text(json.dumps(slim, ensure_ascii=False), encoding="utf-8")
    status = DATA_DIR / "status.json"
    shutil.copy(status, out / "data" / "status.json") if status.exists() else \
        (out / "data" / "status.json").write_text("{}", encoding="utf-8")
    cfg = {"vapidPublicKey": os.environ.get("VAPID_PUBLIC_KEY", ""),
           "workerUrl": os.environ.get("WORKER_URL", "").rstrip("/")}
    (out / "config.js").write_text(f"window.APP_CONFIG = {json.dumps(cfg)};\n", encoding="utf-8")
    print(f"site → {out} ({len(slim)} jobs)")


if __name__ == "__main__":
    build(Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "_site")
