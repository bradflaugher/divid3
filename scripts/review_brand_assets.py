from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
ASSETS = [
    "favicon-16x16.png",
    "favicon-32x32.png",
    "favicon-48x48.png",
    "apple-touch-icon.png",
    "apple-touch-icon-light.png",
    "apple-touch-icon-tinted.png",
    "icon-maskable-192.png",
    "icon-monochrome-192.png",
    "og-image.png",
    "twitter-card.png",
]

try:
    FONT = ImageFont.truetype("/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf", 18)
except Exception:
    FONT = ImageFont.load_default()

thumb_w, thumb_h = 260, 170
pad = 24
label_h = 34
cols = 2
rows = (len(ASSETS) + cols - 1) // cols
sheet = Image.new("RGB", (cols * (thumb_w + pad) + pad, rows * (thumb_h + label_h + pad) + pad), "#f2f2f2")
d = ImageDraw.Draw(sheet)

for idx, name in enumerate(ASSETS):
    img = Image.open(ROOT / name).convert("RGBA")
    img.thumbnail((thumb_w, thumb_h), Image.Resampling.LANCZOS)
    col = idx % cols
    row = idx // cols
    x = pad + col * (thumb_w + pad)
    y = pad + row * (thumb_h + label_h + pad)
    checker = Image.new("RGB", (thumb_w, thumb_h), "#ddd")
    cd = ImageDraw.Draw(checker)
    for yy in range(0, thumb_h, 20):
        for xx in range(0, thumb_w, 20):
            if (xx // 20 + yy // 20) % 2:
                cd.rectangle((xx, yy, xx + 19, yy + 19), fill="#fff")
    px = x + (thumb_w - img.width) // 2
    py = y + (thumb_h - img.height) // 2
    sheet.paste(checker, (x, y))
    sheet.paste(img, (px, py), img)
    d.text((x, y + thumb_h + 8), name, font=FONT, fill="#111")

sheet.save(ROOT / "brand-assets-contact-sheet.png")
