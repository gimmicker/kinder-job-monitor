"""청주교육지원청 게시판을 이 PC(한국 인터넷)에서 수집해 저장소에 올린다.

그 사이트는 해외 접속을 막아서 GitHub Actions에서는 수집할 수 없다.
새 공고가 있으면 GitHub Actions를 실행해 사이트 배포와 알림까지 이어서 한다.

사용: .venv/Scripts/python scripts/sync_cheongju.py
- 작업 중인 브랜치(dev)를 건드리지 않도록 main을 .local/main-sync 폴더에 따로 두고 거기서 돌린다.
- 필요: git, gh(로그인된 상태)
"""
import os
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WT = ROOT / ".local" / "main-sync"


def run(*cmd, cwd=WT, check=True, capture=False) -> subprocess.CompletedProcess:
    print("$", " ".join(cmd), flush=True)
    return subprocess.run(cmd, cwd=cwd, check=check, text=True, encoding="utf-8",
                          capture_output=capture, env={**os.environ, "PYTHONUTF8": "1"})


def main() -> int:
    if not WT.exists():
        run("git", "fetch", "-q", "origin", "main", cwd=ROOT)
        run("git", "worktree", "add", "-q", "--detach", str(WT), "origin/main", cwd=ROOT)
    run("git", "fetch", "-q", "origin", "main")
    run("git", "checkout", "-q", "-B", "main-sync", "origin/main")

    r = run(sys.executable, "-m", "app.main", "--only-cheongju", capture=True, check=False)
    out = (r.stdout or "") + (r.stderr or "")
    print(out)
    m = re.search(r"청주교육지원청 신규 (\d+)건", out or "")
    new = int(m.group(1)) if m else 0

    run("git", "add", "data")
    if run("git", "diff", "--cached", "--quiet", check=False).returncode == 0:
        print("바뀐 데이터 없음")
        return 0
    stamp = datetime.now().strftime("%m/%d %H:%M")
    run("git", "commit", "-q", "-m", f"data: 청주교육지원청 수집 {stamp} (PC)")
    for _ in range(3):  # GitHub Actions가 그 사이 데이터를 올렸으면 위에 다시 얹는다
        run("git", "pull", "-q", "--rebase", "origin", "main", check=False)
        if run("git", "push", "-q", "origin", "HEAD:main", check=False).returncode == 0:
            break
    else:
        print("올리기 실패: 잠시 뒤 다시 실행해 주세요.")
        return 1

    if new:
        # 사이트 배포 + 알림 (수집 단계는 충북교육청만 다시 확인한다)
        run("gh", "workflow", "run", "monitor.yml", cwd=ROOT, check=False)
        print(f"새 공고 {new}건 → 사이트 배포와 알림을 시작했어요.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
