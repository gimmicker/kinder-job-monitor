import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
FIX = ROOT / "tests" / "fixtures"

from app.config import load_settings  # noqa: E402


@pytest.fixture
def settings():
    return load_settings()


@pytest.fixture
def f(settings):
    return settings["filters"]


def fixture_text(name: str) -> str:
    return (FIX / name).read_text(encoding="utf-8")
