import json
from datetime import date, timedelta
from pathlib import Path

from .config import DATA_DIR


def _read(path: Path, default):
    if not path.exists():
        return default
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _write(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    with open(tmp, "w", encoding="utf-8", newline="
") as f:  # PC(Windows)에서 돌려도 LF로
        json.dump(data, f, ensure_ascii=False, indent=1, sort_keys=True)
        f.write("\n")
    tmp.replace(path)


class Store:
    def __init__(self, data_dir: Path = DATA_DIR):
        self.dir = Path(data_dir)
        self.jobs: dict = _read(self.dir / "jobs.json", {})
        self.runs: list = _read(self.dir / "runs.json", [])
        self.status: dict = _read(self.dir / "status.json", {})
        self.seen: dict = _read(self.dir / "seen.json", {})

    @property
    def is_empty(self) -> bool:
        return not self.jobs

    def save(self) -> None:
        _write(self.dir / "jobs.json", self.jobs)
        _write(self.dir / "runs.json", self.runs)
        _write(self.dir / "status.json", self.status)
        _write(self.dir / "seen.json", self.seen)

    def add_run(self, run: dict, keep: int) -> None:
        self.runs.append(run)
        self.runs = self.runs[-keep:]

    def prune(self, today: date, days: int) -> int:
        """마감 후 오래 지난 부적합 공고 삭제."""
        cutoff = (today - timedelta(days=days)).isoformat()
        drop = [k for k, j in self.jobs.items()
                if j.get("match_status") == "not_match" and (j.get("deadline") or j.get("posted_at") or "9999") < cutoff]
        for k in drop:
            del self.jobs[k]
        return len(drop)

    def pending_notifications(self, statuses: list[str], today: date) -> list[dict]:
        out = []
        for j in self.jobs.values():
            if j.get("notified_at") or j.get("match_status") not in statuses:
                continue
            if j.get("deadline") and j["deadline"] < today.isoformat():
                continue
            if not j.get("deadline") and (j.get("posted_at") or "9999") < (today - timedelta(days=30)).isoformat():
                continue  # 마감일을 모르는데 한 달 넘은 공고
            out.append(j)
        order = {s: i for i, s in enumerate(statuses)}
        return sorted(out, key=lambda j: (order[j["match_status"]], j.get("deadline") or "9999"))
