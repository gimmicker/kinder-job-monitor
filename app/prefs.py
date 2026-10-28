"""폰마다 고른 '받을 공고 조건'에 공고가 맞는지 판단한다.

앱(web/index.html의 isMine)과 같은 규칙이다. 한쪽을 바꾸면 다른 쪽도 같이 바꾼다.
  - 직무를 알고, 고른 직무가 아니면 → 내 조건 아님
  - 지역을 알고, 고른 지역이 아니면 → 내 조건 아님
  - 나머지 → 내 조건 (지역·직무를 자동으로 알아내지 못한 공고도 놓치지 않게 포함)
"""
from .kinders import find

CITIES = ["청주", "충주", "제천", "보은", "옥천", "영동", "증평", "진천", "괴산", "음성", "단양"]


def job_types(settings: dict) -> list[str]:
    return [jt["type"] for jt in settings["filters"]["job_types"]]


def default_prefs(settings: dict) -> dict:
    return {"cities": ["청주"], "types": list(settings["filters"]["match_job_types"])}


def sanitize(prefs, settings: dict) -> dict | None:
    """Worker에 저장된 값은 폰이 보낸 것이므로 아는 값만 남긴다. 쓸 수 없으면 None."""
    if not isinstance(prefs, dict):
        return None
    cities = [c for c in prefs.get("cities") or [] if c in CITIES]
    types = [t for t in prefs.get("types") or [] if t in job_types(settings)]
    return {"cities": cities, "types": types}


def job_city(job: dict, kinders: dict) -> str | None:
    """유치원알리미 주소의 시·군. 없으면 분류 결과로 '청주'/'기타', 모르면 None."""
    k = find(job, kinders)
    if k and k.get("city"):
        return k["city"]
    return {"청주": "청주", "기타": "기타"}.get(job.get("region") or "")


def is_mine(job: dict, city: str | None, prefs: dict) -> bool:
    jt = job.get("job_type")
    if jt and jt not in prefs["types"]:
        return False
    if city and city not in prefs["cities"]:
        return False
    return True
