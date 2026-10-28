"""앱 아이콘 생성: 지붕 아래 종 + 별 심볼 (개발 PC에서 심볼을 바꿀 때만 실행).

필요: pillow, Google Chrome (SVG를 그림으로 바꿀 때 사용)
사용: .venv/Scripts/python scripts/make_icons.py
심볼 모양은 web/index.html의 시작 인트로(#intro)와 같게 유지한다.
"""
import shutil
import subprocess
import tempfile
from pathlib import Path

from PIL import Image

OUT = Path(__file__).resolve().parent.parent / "web" / "icons"
BG, FG, STAR = "#1F5F4A", "#FFFFFF", "#FFD45E"
CHROME = [r"C:\Program Files\Google\Chrome\Application\chrome.exe",
          r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe", "google-chrome", "chromium"]

# viewBox 0 0 100 100 기준. 지붕(꺾은선) + 꼭대기 동그라미 + 종 + 별(종의 추)
STAR_D = ("M50.00 70.50 L51.82 74.99 L56.66 75.34 L52.95 78.46 L54.11 83.16 "
          "L50.00 80.60 L45.89 83.16 L47.05 78.46 L43.34 75.34 L48.18 74.99Z")


def symbol(fg: str = FG, star: str = STAR) -> str:
    return f'''
  <path d="M17 42 L50 17 L83 42" fill="none" stroke="{fg}" stroke-width="8" stroke-linecap="round" stroke-linejoin="round"/>
  <circle cx="50" cy="15" r="5" fill="{fg}"/>
  <circle cx="50" cy="33" r="3.6" fill="{fg}"/>
  <path d="M50 34c-9.5 0-15 7.2-15 16.5v7.5c0 3.2-2.4 5.6-6.5 8.5h43c-4.1-2.9-6.5-5.3-6.5-8.5v-7.5C65 41.2 59.5 34 50 34z" fill="{fg}"/>
  <path d="{STAR_D}" fill="{star}" stroke="{star}" stroke-width="1.6" stroke-linejoin="round"/>'''


def svg(size: int, scale: float, bg: str | None, radius: float = 0, fg: str = FG, star: str = STAR) -> str:
    """scale: 심볼(100단위)이 아이콘 한 변에서 차지하는 비율."""
    s = size * scale / 100
    off = (size - size * scale) / 2
    back = f'<rect width="{size}" height="{size}" rx="{radius * size}" fill="{bg}"/>' if bg else ""
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{size}" height="{size}" viewBox="0 0 {size} {size}">'
            f'{back}<g transform="translate({off} {off + size * 0.015}) scale({s})">{symbol(fg, star)}</g></svg>')


def chrome() -> str:
    for c in CHROME:
        if Path(c).exists() or shutil.which(c):
            return c
    raise SystemExit("Chrome을 찾지 못했습니다.")


def render(svg_text: str, path: Path, size: int) -> None:
    """Chrome 헤드리스로 1024px 그림을 만든 뒤 원하는 크기로 줄인다 (작은 크기도 선명하게)."""
    big = 1024
    with tempfile.TemporaryDirectory() as tmp:
        html = Path(tmp) / "i.html"
        png = Path(tmp) / "i.png"
        html.write_text(f'<html><body style="margin:0;background:transparent">{svg_text}</body></html>', encoding="utf-8")
        subprocess.run([chrome(), "--headless=new", "--disable-gpu", "--hide-scrollbars", f"--user-data-dir={tmp}/p",
                        "--default-background-color=00000000", f"--window-size={big},{big}",
                        f"--screenshot={png}", html.as_uri()], check=True, capture_output=True, timeout=60)
        img = Image.open(png).convert("RGBA").crop((0, 0, big, big))
    img.resize((size, size), Image.Resampling.LANCZOS).save(path)


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    rounded = svg(1024, 0.78, BG, radius=0.225)        # 안드로이드·브라우저용 (모서리 둥근 투명 배경)
    square = svg(1024, 0.78, BG)                       # 아이폰 홈 화면 (iOS가 모서리를 깎음)
    maskable = svg(1024, 0.62, BG)                     # 안드로이드 적응형 (가운데 80% 원 안에 들어가게)
    badge = svg(1024, 0.92, None, star=FG)             # 안드로이드 상태바: 흰 실루엣만 쓰인다
    render(rounded, OUT / "icon-192.png", 192)
    render(rounded, OUT / "icon-512.png", 512)
    render(square, OUT / "apple-touch-icon.png", 180)
    render(maskable, OUT / "maskable-512.png", 512)
    render(badge, OUT / "badge-96.png", 96)
    (OUT / "symbol.svg").write_text(svg(100, 1.0, None), encoding="utf-8")
    print("icons →", OUT)


if __name__ == "__main__":
    main()
