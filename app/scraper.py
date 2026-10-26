import time

import requests


class Scraper:
    def __init__(self, src: dict, session: requests.Session | None = None):
        self.src = src
        self.s = session or requests.Session()
        self.s.headers["User-Agent"] = src["user_agent"]
        self._last = 0.0

    def _get(self, path: str, params: dict) -> str:
        wait = self.src["request_delay_sec"] - (time.monotonic() - self._last)
        if wait > 0:
            time.sleep(wait)
        url = self.src["base"] + path
        last_err = None
        for attempt in range(3):
            try:
                r = self.s.get(url, params=params, timeout=self.src["timeout_sec"])
                self._last = time.monotonic()
                if r.status_code == 429 or r.status_code >= 500:
                    last_err = f"HTTP {r.status_code}"
                    time.sleep(5 * (attempt + 1))
                    continue
                r.raise_for_status()
                r.encoding = r.encoding or "utf-8"
                return r.text
            except requests.RequestException as e:
                last_err = str(e)
                time.sleep(5 * (attempt + 1))
        raise RuntimeError(f"요청 실패 {url} {params}: {last_err}")

    def list_page(self, page: int) -> str:
        return self._get(self.src["list_path"], {
            "bbsId": self.src["bbs_id"], "mi": self.src["mi"],
            "currPage": page, "listCo": self.src["list_count"],
        })

    def detail_page(self, post_id: str) -> str:
        return self._get(self.src["detail_path"], {
            "bbsId": self.src["bbs_id"], "nttSn": post_id, "mi": self.src["mi"],
        })


def detail_url(src: dict, post_id: str) -> str:
    return (f"{src['base']}{src['detail_path']}"
            f"?bbsId={src['bbs_id']}&nttSn={post_id}&mi={src['mi']}")
