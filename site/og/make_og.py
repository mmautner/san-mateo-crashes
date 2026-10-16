"""Open Graph preview images (1200×630) for every intersection page, plus one
for the landing page. Reads the default-settings numbers the build wrote to
dist/<base>/prerender.json, so the image always matches the page headline.

    python site/og/make_og.py
"""
import json
import sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

HERE = Path(__file__).parent
ROOT = HERE.parent.parent
CFG = json.loads((ROOT / "site" / "config.json").read_text())
OUT = ROOT / "dist" / CFG["base"].strip("/")
W, H, PAD = 1200, 630, 72

# maxmautner.com dark tokens, and the map's validated mode colors (dark steps)
BG, SURFACE = "#211e1b", "#2c2925"
TEXT, TEXT2, TEXT3, ACCENT = "#f1efe9", "#aaa39a", "#8a847b", "#c79045"
MODE_COLORS = {"walk": "#d95926", "bike": "#3987e5", "scooter": "#199e70"}


def font(name, size, weight, extra=None):
    f = ImageFont.truetype(str(HERE / "fonts" / name), size)
    # axes: Newsreader [wght, opsz]; IBM Plex Sans [wght, wdth]
    f.set_variation_by_axes([weight, extra if extra is not None else (min(72, size) if "Newsreader" in name else 100)])
    return f


def wrap(draw, text, f, width):
    lines, cur = [], ""
    for w in text.split():
        t = f"{cur} {w}".strip()
        if draw.textlength(t, font=f) <= width or not cur:
            cur = t
        else:
            lines.append(cur)
            cur = w
    return lines + [cur]


def base_image():
    img = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(img)
    d.rectangle([0, H - 10, W, H], fill=ACCENT)
    d.text((PAD, PAD - 6), "SAN MATEO CRASH LOOKUP", font=font("IBMPlexSans.ttf", 22, 600), fill=TEXT3,
           spacing=0, features=["-kern"])
    return img, d


def footer(d, text):
    d.text((PAD, H - PAD - 10), text, font=font("IBMPlexSans.ttf", 24, 400), fill=TEXT3, anchor="ls")


def intersection_image(args):
    id_, p = args
    img, d = base_image()
    n = p["n"]
    # label: one line if it fits at >= 46px, else two balanced lines
    for size in range(64, 45, -2):
        lab = font("Newsreader.ttf", size, 600)
        if d.textlength(p["label"], font=lab) <= W - 2 * PAD:
            lines = [p["label"]]
            break
    else:
        size = 54
        lab = font("Newsreader.ttf", size, 600)
        a, b = p["label"].split(" & ", 1)
        lines = [f"{a} &", b] if max(d.textlength(f"{a} &", font=lab), d.textlength(b, font=lab)) <= W - 2 * PAD \
            else wrap(d, p["label"], lab, W - 2 * PAD)[:2]
    # lay out bottom-up: footer, breakdown, label, number
    y_break = H - PAD - 10 - 62
    y_last = y_break - 54
    y_first = y_last - int(size * 1.12) * (len(lines) - 1)
    for k, line in enumerate(lines):
        d.text((PAD, y_first + k * int(size * 1.12)), line, font=lab, fill=TEXT, anchor="ls")
    y_num = y_first - size - 26
    big = font("Newsreader.ttf", 200 if len(lines) == 1 else 176, 600)
    num = f"{n:,}"
    d.text((PAD - 6, y_num), num, font=big, fill=ACCENT, anchor="ls")
    x = PAD + d.textlength(num, font=big) + 26
    who = "person was hurt in a crash" if n == 1 else "people were hurt in crashes"
    sub = font("IBMPlexSans.ttf", 34, 500)
    d.text((x, y_num - 68), who, font=sub, fill=TEXT, anchor="ls")
    d.text((x, y_num - 20), "within a quarter mile of", font=sub, fill=TEXT, anchor="ls")

    # breakdown with the map's key marks
    parts = [("walk", p["walk"], "walking"), ("bike", p["bike"], "on a bike" if p["bike"] == 1 else "on bikes"),
             ("scooter", p["scooter"], "on a scooter" if p["scooter"] == 1 else "on scooters"),
             ("vehicle", p["vehicle"], "in a vehicle" if p["vehicle"] == 1 else "in vehicles")]
    parts = [t for t in parts if t[1] > 0]
    if p["killed"]:
        parts.append(("killed", p["killed"], "killed"))
    small = font("IBMPlexSans.ttf", 28, 400)
    cx, cy = PAD, y_break
    for kind, k, words in parts:
        r = 9
        if kind == "vehicle":
            d.ellipse([cx, cy - r, cx + 2 * r, cy + r], outline=TEXT2, width=3)
        elif kind == "killed":
            d.polygon([(cx + r, cy - r - 2), (cx + 2 * r + 2, cy), (cx + r, cy + r + 2), (cx - 2, cy)], fill=TEXT)
        else:
            d.ellipse([cx, cy - r, cx + 2 * r, cy + r], fill=MODE_COLORS[kind])
        t = f"{k:,} {words}"
        d.text((cx + 2 * r + 10, cy), t, font=small, fill=TEXT2, anchor="lm")
        cx += 2 * r + 10 + d.textlength(t, font=small) + 30

    footer(d, f"{p['years']} · police reports · maxmautner.com{CFG['base'].rstrip('/')}")
    img = img.quantize(colors=64, method=Image.Quantize.MEDIANCUT, dither=Image.Dither.NONE)
    img.save(OUT / "og" / f"{id_}.png", optimize=True)


def landing_image():
    img, d = base_image()
    f = font("Newsreader.ttf", 76, 600)
    y = 220
    for line in wrap(d, "How many people were hurt in crashes near you?", f, W - 2 * PAD):
        d.text((PAD, y), line, font=f, fill=TEXT, anchor="ls")
        y += 86
    d.text((PAD, y + 20), "Look up any San Mateo intersection, from police reports.", font=font("IBMPlexSans.ttf", 32, 400), fill=TEXT2, anchor="ls")
    footer(d, f"maxmautner.com{CFG['base'].rstrip('/')}")
    img.quantize(colors=64, method=Image.Quantize.MEDIANCUT, dither=Image.Dither.NONE).save(OUT / "og" / "index.png", optimize=True)


def main():
    pre = json.loads((OUT / "prerender.json").read_text())
    (OUT / "og").mkdir(exist_ok=True)
    landing_image()
    items = list(pre.items())
    if len(sys.argv) > 1:
        items = [(k, v) for k, v in items if k in sys.argv[1:]]
    with ProcessPoolExecutor() as ex:
        list(ex.map(intersection_image, items, chunksize=32))
    print(f"wrote {len(items) + 1} images to {OUT / 'og'}", file=sys.stderr)


if __name__ == "__main__":
    main()
