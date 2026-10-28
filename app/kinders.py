"""유치원알리미 공시 자료(config/kinders.json) 읽기와 공고 기관 이름 매칭.

자료는 scripts/build_kinders.py로 만든다 (인증키 필요, 공시 갱신 때만 다시 실행).
"""
import json

from . import filters
from .config import CONFIG_DIR

KINDERS_PATH = CONFIG_DIR / "kinders.json"


def key_for(name: str) -> str | None:
    """'주중초병설유치원'·'주중초등학교병설유치원' → '초:주중', '비봉유치원' → '유:비봉'."""
    insts = filters.institutions(name or "")
    return f"{insts[0][0]}:{insts[0][1]}" if insts else None


def load_kinders() -> dict:
    if not KINDERS_PATH.exists():
        return {}
    return json.loads(KINDERS_PATH.read_text(encoding="utf-8")).get("kinders", {})


def find(job: dict, kinders: dict) -> dict | None:
    """공고의 제목·작성자에 나온 기관 중 공시 자료에 있는 첫 유치원."""
    for kind, base, _ in filters.institutions(job.get("title", ""), job.get("author") or ""):
        info = kinders.get(f"{kind}:{base}")
        if info:
            return info
    return None


def merge_places(places: dict, kinders: dict) -> dict:
    """places.yaml에 없는 기관만 공시 자료의 시·군으로 채운다 (손으로 넣은 값이 우선)."""
    out = {"초": dict(places.get("초") or {}), "유": dict(places.get("유") or {})}
    for key, info in kinders.items():
        kind, base = key.split(":", 1)
        if info.get("city") and base not in out.setdefault(kind, {}):
            out[kind][base] = info["city"]
    return out
