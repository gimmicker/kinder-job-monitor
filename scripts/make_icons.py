"""앱 아이콘 생성 (개발 PC에서 1회). 필요: pip install pillow, Windows 맑은 고딕."""
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

OUT = Path(__file__).resolve().parent.parent / "web" / "icons"
FONT = "C:/Windows/Fonts/malgunbd.ttf"
BG, FG = (31, 95, 74), (255, 255, 255)


def icon(size: int, pad_ratio: float, path: Path, rounded: bool = True):
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0) if rounded else BG)
    d = ImageDraw.Draw(img)
    if rounded:
        d.rounded_rectangle([0, 0, size - 1, size - 1], radius=int(size * 0.22), fill=BG)
    inner = size * (1 - 2 * pad_ratio)
    font = ImageFont.truetype(FONT, int(inner * 0.5))
    d.text((size / 2, size / 2 - inner * 0.12), "유", font=font, fill=FG, anchor="mm")
    small = ImageFont.truetype(FONT, int(inner * 0.17))
    d.text((size / 2, size / 2 + inner * 0.33), "공고", font=small, fill=(255, 230, 160), anchor="mm")
    img.save(path)


def badge(size: int, path: Path):
    """안드로이드 상태바용: 흰색 실루엣만 쓰인다."""
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    font = ImageFont.truetype(FONT, int(size * 0.8))
    d.text((size / 2, size / 2), "유", font=font, fill=(255, 255, 255, 255), anchor="mm")
    img.save(path)


if __name__ == "__main__":
    OUT.mkdir(parents=True, exist_ok=True)
    icon(192, 0.08, OUT / "icon-192.png")
    icon(512, 0.08, OUT / "icon-512.png")
    icon(512, 0.2, OUT / "maskable-512.png", rounded=False)
    badge(96, OUT / "badge-96.png")
    print("icons →", OUT)
