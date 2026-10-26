from pathlib import Path
from datetime import datetime, timedelta, timezone

import yaml

ROOT = Path(__file__).resolve().parent.parent
CONFIG_DIR = ROOT / "config"
DATA_DIR = ROOT / "data"
KST = timezone(timedelta(hours=9))


def load_yaml(path: Path) -> dict:
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def load_settings() -> dict:
    return load_yaml(CONFIG_DIR / "settings.yaml")


def load_places() -> dict:
    p = CONFIG_DIR / "places.yaml"
    data = load_yaml(p) if p.exists() else {}
    return {"초": data.get("초") or {}, "유": data.get("유") or {}}


def now_kst() -> datetime:
    return datetime.now(KST)


def iso(dt: datetime) -> str:
    return dt.isoformat(timespec="seconds")
