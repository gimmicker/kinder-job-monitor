"""개발 중인 화면 미리보기: 사이트를 _site에 만들고 PC·같은 와이파이의 폰에서 볼 수 있게 띄운다.

사용: .venv/Scripts/python scripts/preview.py [포트] [--lan]   (기본 8090, 끝내려면 Ctrl+C)
- 기본: 이 PC에서만 열림 → http://localhost:포트
- --lan: 같은 네트워크의 폰에서도 열림 → http://PC의IP:포트
  PC가 공인 IP를 쓰는 망이면 인터넷 전체에 열리니, 확인할 때만 잠깐 쓴다.
  폰에서는 https가 아니라서 알림 켜기·위치 저장은 동작하지 않는다. 화면 확인용.
"""
import functools
import http.server
import socket
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app.build_site import build  # noqa: E402
from app.config import ROOT  # noqa: E402


def lan_ip() -> str:
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("8.8.8.8", 80))  # 실제로 보내지는 않음. 내 IP 확인용
            return s.getsockname()[0]
    except OSError:
        return "PC의IP"


class NoCache(http.server.SimpleHTTPRequestHandler):
    def end_headers(self):
        self.send_header("Cache-Control", "no-store")  # 고친 내용이 바로 보이게
        super().end_headers()


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    lan = "--lan" in sys.argv
    port = int(args[0]) if args else 8090
    out = ROOT / "_site"
    build(out)
    handler = functools.partial(NoCache, directory=str(out))
    with http.server.ThreadingHTTPServer(("0.0.0.0" if lan else "127.0.0.1", port), handler) as httpd:
        print(f"PC:  http://localhost:{port}" + (f"\n폰:  http://{lan_ip()}:{port}" if lan else ""), flush=True)
        httpd.serve_forever()


if __name__ == "__main__":
    main()
