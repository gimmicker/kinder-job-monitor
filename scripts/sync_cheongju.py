"""청주교육지원청 게시판을 이 PC(한국 인터넷)에서 수집해 저장소에 올린다.

그 사이트는 해외 접속을 막아서 GitHub Actions에서는 수집할 수 없다.
새 공고가 있으면 GitHub Actions를 실행해 사이트 배포와 알림까지 이어서 한다.

사용: .venv/Scripts/python scripts/sync_cheongju.py
      .venv/Scripts/pythonw scripts/sync_cheongju.py --log   (예약 작업용: 창 없이, .local/sync_cheongju.log에 기록)
- 예약 작업 등록: scripts/install_sync_task.ps1 (로그온할 때 + 매일 12:00, 18:00)
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
LOG = ROOT / ".local" / "sync_cheongju.log"
NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)  # 예약 작업에서 git 창이 깜빡이지 않게


def run(*cmd, cwd=WT, check=True, capture=False) -> subprocess.CompletedProcess:
    print("$", " ".join(cmd), flush=True)
    r = subprocess.run(cmd, cwd=cwd, text=True, encoding="utf-8", errors="replace", capture_output=True,
                       creationflags=NO_WINDOW, env={**os.environ, "PYTHONUTF8": "1"})
    if not capture and (r.stdout or r.stderr):
        print((r.stdout or "") + (r.stderr or ""), end="", flush=True)
    if check and r.returncode:
        raise subprocess.CalledProcessError(r.returncode, cmd, r.stdout, r.stderr)
    return r


def open_log():
    """로그는 최근 것만 남긴다 (약 200KB)."""
    LOG.parent.mkdir(parents=True, exist_ok=True)
    if LOG.exists() and LOG.stat().st_size > 200_000:
        LOG.write_text(LOG.read_text(encoding="utf-8", errors="replace")[-100_000:], encoding="utf-8")
    f = open(LOG, "a", encoding="utf-8")
    sys.stdout = sys.stderr = f
    print(f"\n===== {datetime.now():%Y-%m-%d %H:%M:%S} =====", flush=True)


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
    failed = r.returncode != 0 or "오류:" in out  # 예약 작업이 잠시 뒤 다시 시도하도록 실패 코드를 돌려준다

    run("git", "add", "data")
    if run("git", "diff", "--cached", "--quiet", check=False).returncode == 0:
        print("바뀐 데이터 없음")
        return 2 if failed else 0
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
    return 2 if failed else 0


if __name__ == "__main__":
    if "--log" in sys.argv:
        open_log()
    try:
        code = main()
    except Exception as e:  # 인터넷이 아직 안 붙었을 때 등
        print(f"실패: {type(e).__name__}: {e}", flush=True)
        code = 1
    print(f"종료 코드 {code}", flush=True)
    sys.exit(code)
