from __future__ import annotations

from pathlib import Path
from PIL import Image, ImageDraw, ImageFont, ImageFilter
import math
import os

ROOT = Path(__file__).resolve().parents[1]

BLACK = (0, 0, 0, 255)
WHITE = (255, 255, 255, 255)
TRANSPARENT = (0, 0, 0, 0)
MUTED = (148, 148, 148, 255)

SVG_ICON = '''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1024 1024" role="img" aria-labelledby="title desc">
  <title id="title">divid3 icon</title>
  <desc id="desc">A minimal diagonal slash dividing a square field.</desc>
  <rect width="1024" height="1024" rx="224" fill="#000"/>
  <path d="M631 128 346 896" fill="none" stroke="#fff" stroke-width="132" stroke-linecap="round"/>
</svg>
'''

SVG_MARK = '''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1024 1024" role="img" aria-labelledby="title desc">
  <title id="title">divid3 slash mark</title>
  <desc id="desc">A standalone diagonal slash mark for divid3.</desc>
  <path d="M631 128 346 896" fill="none" stroke="currentColor" stroke-width="132" stroke-linecap="round"/>
</svg>
'''

SVG_MASK = '''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1024 1024">
  <path d="M631 128 346 896" fill="none" stroke="#000" stroke-width="132" stroke-linecap="round"/>
</svg>
'''


def save_svg_assets() -> None:
    (ROOT / "favicon.svg").write_text(SVG_ICON, encoding="utf-8")
    (ROOT / "divid3-icon.svg").write_text(SVG_ICON, encoding="utf-8")
    (ROOT / "divid3-mark.svg").write_text(SVG_MARK, encoding="utf-8")
    (ROOT / "safari-pinned-tab.svg").write_text(SVG_MASK, encoding="utf-8")


def rounded_rect(draw: ImageDraw.ImageDraw, xy, radius, fill):
    draw.rounded_rectangle(xy, radius=radius, fill=fill)


def slash_bbox(size: int):
    # Coordinates are proportional to SVG source path M631 128 346 896.
    return (0.6162109375 * size, 0.125 * size, 0.337890625 * size, 0.875 * size)


def draw_slash(draw: ImageDraw.ImageDraw, size: int, fill=WHITE, scale: float = 1.0):
    x1, y1, x2, y2 = slash_bbox(size)
    cx = cy = size / 2
    x1 = cx + (x1 - cx) * scale
    y1 = cy + (y1 - cy) * scale
    x2 = cx + (x2 - cx) * scale
    y2 = cy + (y2 - cy) * scale
    width = max(1, int(size * 0.129 * scale))
    draw.line((x1, y1, x2, y2), fill=fill, width=width)
    r = width / 2
    draw.ellipse((x1-r, y1-r, x1+r, y1+r), fill=fill)
    draw.ellipse((x2-r, y2-r, x2+r, y2+r), fill=fill)


def icon(size: int, bg=BLACK, fg=WHITE, radius_ratio=0.21875, transparent_bg=False, slash_scale=1.0) -> Image.Image:
    img = Image.new("RGBA", (size, size), TRANSPARENT if transparent_bg else bg)
    draw = ImageDraw.Draw(img)
    if not transparent_bg:
        # Explicit rounded geometry for platforms that do not apply a mask.
        radius = int(size * radius_ratio)
        mask = Image.new("L", (size, size), 0)
        md = ImageDraw.Draw(mask)
        md.rounded_rectangle((0, 0, size, size), radius=radius, fill=255)
        base = Image.new("RGBA", (size, size), bg)
        base.putalpha(mask)
        img = base
        draw = ImageDraw.Draw(img)
    draw_slash(draw, size, fill=fg, scale=slash_scale)
    return img


def maskable_icon(size: int, bg=BLACK, fg=WHITE) -> Image.Image:
    # Full-bleed opaque background; slash stays comfortably inside the 80% safe zone.
    img = Image.new("RGBA", (size, size), bg)
    draw = ImageDraw.Draw(img)
    draw_slash(draw, size, fill=fg, scale=0.82)
    return img


def mono_icon(size: int, fg=WHITE) -> Image.Image:
    img = Image.new("RGBA", (size, size), TRANSPARENT)
    draw = ImageDraw.Draw(img)
    draw_slash(draw, size, fill=fg, scale=0.82)
    return img


def find_font(size: int, weight: str = "regular"):
    candidates = [
        "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
        "/usr/share/fonts/truetype/noto/NotoSans-Regular.ttf",
        "/usr/share/fonts/opentype/noto/NotoSansCJKsc-Regular.otf",
    ]
    if weight == "bold":
        candidates = [
            "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
            "/usr/share/fonts/truetype/noto/NotoSans-Bold.ttf",
            "/usr/share/fonts/opentype/noto/NotoSansCJKsc-Bold.otf",
        ] + candidates
    for path in candidates:
        if os.path.exists(path):
            return ImageFont.truetype(path, size)
    return ImageFont.load_default()


def text_size(draw, text, font):
    box = draw.textbbox((0, 0), text, font=font)
    return box[2] - box[0], box[3] - box[1]


def make_social(width: int, height: int, out: str, twitter: bool = False) -> None:
    img = Image.new("RGBA", (width, height), BLACK)
    draw = ImageDraw.Draw(img)

    # Subtle orbital dividers / echoes of the slash to keep it simple but distinctive.
    overlay = Image.new("RGBA", (width, height), TRANSPARENT)
    od = ImageDraw.Draw(overlay)
    for i, alpha in enumerate([30, 22, 16, 10]):
        x = int(width * (0.15 + i * 0.18))
        od.line((x + 280, -80, x - 80, height + 80), fill=(255, 255, 255, alpha), width=3)
    img = Image.alpha_composite(img, overlay)
    draw = ImageDraw.Draw(img)

    # Icon block.
    block = int(min(width, height) * 0.36)
    bx = int(width * 0.09)
    by = int((height - block) / 2)
    badge = icon(block, bg=BLACK, fg=WHITE, radius_ratio=0.22, slash_scale=0.95)
    # Add crisp white outline for social contexts.
    outline = Image.new("RGBA", (block, block), TRANSPARENT)
    od = ImageDraw.Draw(outline)
    od.rounded_rectangle((2, 2, block-2, block-2), radius=int(block*0.22), outline=(255,255,255,48), width=max(2, block//96))
    badge = Image.alpha_composite(badge, outline)
    img.alpha_composite(badge, (bx, by))

    # Wordmark and short proposition.
    title_font = find_font(int(height * 0.19), "bold")
    desc_font = find_font(int(height * 0.058))
    small_font = find_font(int(height * 0.036), "bold")
    tx = bx + block + int(width * 0.06)
    title = "divid3"
    desc = "private search routing, on device"
    kicker = "divide the query · route the result"
    draw.text((tx, int(height * 0.23)), title, font=title_font, fill=WHITE)
    draw.text((tx + 6, int(height * 0.50)), desc, font=desc_font, fill=(221, 221, 221, 255))
    draw.text((tx + 7, int(height * 0.65)), kicker.upper(), font=small_font, fill=(145, 145, 145, 255))

    # A tiny slash at the far right as a finishing cue.
    dd = ImageDraw.Draw(img)
    sx = width - int(width * 0.11)
    sy = int(height * 0.23)
    dd.line((sx + 52, sy, sx, height - sy), fill=(255, 255, 255, 92), width=14)
    dd.ellipse((sx + 45, sy-7, sx+59, sy+7), fill=(255, 255, 255, 92))
    dd.ellipse((sx-7, height-sy-7, sx+7, height-sy+7), fill=(255, 255, 255, 92))

    img.convert("RGB").save(ROOT / out, optimize=True, quality=94)


def generate() -> None:
    save_svg_assets()

    for size in [16, 32, 48, 96, 144, 180, 192, 256, 384, 512, 1024]:
        icon(size).save(ROOT / f"favicon-{size}x{size}.png") if size in [16, 32, 48, 96, 144] else None
        icon(size).save(ROOT / f"icon-{size}.png")

    # Apple touch icons and variants. iOS rounds the icon itself; these are full-bleed and legible.
    for size in [120, 152, 167, 180, 192, 512, 1024]:
        icon(size).save(ROOT / f"apple-touch-icon-{size}x{size}.png")
    icon(180).save(ROOT / "apple-touch-icon.png")
    icon(180, bg=WHITE, fg=BLACK).save(ROOT / "apple-touch-icon-light.png")
    maskable_icon(180, bg=BLACK, fg=WHITE).save(ROOT / "apple-touch-icon-dark.png")
    mono_icon(180, fg=WHITE).save(ROOT / "apple-touch-icon-tinted.png")

    # PWA adaptive purposes.
    for size in [192, 512, 1024]:
        maskable_icon(size).save(ROOT / f"icon-maskable-{size}.png")
        mono_icon(size, fg=WHITE).save(ROOT / f"icon-monochrome-{size}.png")

    # Microsoft tiles / legacy pinned surfaces.
    icon(70).save(ROOT / "mstile-70x70.png")
    icon(150).save(ROOT / "mstile-150x150.png")
    icon(310).save(ROOT / "mstile-310x310.png")
    Image.new("RGBA", (310, 150), BLACK).save(ROOT / "mstile-310x150.png")
    tile = Image.open(ROOT / "mstile-310x150.png")
    tile.alpha_composite(icon(112), (99, 19))
    tile.save(ROOT / "mstile-310x150.png")

    # ICO with multiple embedded bitmap sizes.
    ico_sizes = [16, 32, 48, 64, 128, 256]
    base = icon(256)
    base.save(ROOT / "favicon.ico", sizes=[(s, s) for s in ico_sizes])

    make_social(1200, 630, "og-image.png")
    make_social(1200, 628, "twitter-card.png", twitter=True)
    make_social(1200, 1200, "og-image-square.png")


if __name__ == "__main__":
    generate()
