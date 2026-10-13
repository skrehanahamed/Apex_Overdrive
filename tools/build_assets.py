#!/usr/bin/env python3
"""Cut the generated sheets in sheets/ into trimmed transparent sprites in assets/.

    python tools/build_assets.py            # or: make assets

The background is the flat magenta ChatGPT painted. Only magenta connected to the sheet border is
removed (plus big enclosed patches of near-exact magenta), so hot-pink neon *inside* sprites survives.
Edge fringe (anti-aliasing blended with magenta) is eaten back and despilled.
"""
import json
import os
import sys

import numpy as np
import pygame
from PIL import Image, ImageChops, ImageFilter

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SHEETS = os.path.join(ROOT, "sheets")
OUT = os.path.join(ROOT, "assets")

# file, cols, rows, names (row-major)
LAYOUTS = [
    ("hero.png", 2, 2, ["hero_rear", "hero_brake", "hero_left", "hero_right"]),
    ("traffic.png", 3, 2, ["traffic_sedan", "traffic_sports", "traffic_van", "traffic_truck", "traffic_taxi", "traffic_suv"]),
    ("police.png", 3, 2, ["police_a", "police_b", "police_front", "traffic_cone", "nitro_can", "nitro_flames"]),
    ("wide.png", 2, 2, ["roadblock", "billboard", "highway_sign", "explosion"]),
    ("tall_a.png", 4, 1, ["lamp_post_a", "palm_a", "building_a", "building_b"]),
    ("tall_b.png", 4, 1, ["lamp_post", "palm_b", "building_c", "building_d"]),
    ("hud.png", 2, 2, ["hud_gauge", "hud_bar", "hud_mirror", "hud_panel"]),
    ("overdrive.png", 1, 1, ["overdrive"]),
]
SKIES = ["sky_sunset", "sky_midnight", "sky_dawn", "sky_vapor"]


def ring_points(w, h, step, d):
    """Points on a rectangle `d` px inside the border (the very edge can carry a white frame line)."""
    xs, ys = range(d, w - d, step), range(d, h - d, step)
    return [(x, d) for x in xs] + [(x, h - 1 - d) for x in xs] + [(d, y) for y in ys] + [(w - 1 - d, y) for y in ys]


def border_color(img):
    px = img.load()
    pts = [px[p] for p in ring_points(*img.size, 8, 10)]
    return tuple(sorted(p[c] for p in pts)[len(pts) // 2] for c in range(3))


def background_mask(img):
    """L image, 255 where the magenta background is."""
    surf = pygame.image.frombytes(img.convert("RGB").tobytes(), img.size, "RGB")
    bg = border_color(img)
    loose = pygame.mask.from_threshold(surf, bg, (85, 85, 85, 255))
    tight = pygame.mask.from_threshold(surf, bg, (30, 30, 30, 255))
    w, h = img.size
    out = pygame.mask.Mask((w, h))
    seeds = ring_points(w, h, 24, 10) + ring_points(w, h, 24, 14)
    for s in seeds:
        if loose.get_at(s) and not out.get_at(s):
            out.draw(loose.connected_component(s), (0, 0))
    for comp in tight.connected_components(25):   # enclosed holes of pure magenta
        out.draw(comp, (0, 0))
    vis = out.to_surface(setcolor=(255, 255, 255), unsetcolor=(0, 0, 0))
    return Image.frombytes("RGB", img.size, pygame.image.tobytes(vis, "RGB")).convert("L")


def magenta_excess(img):
    r, g, b = img.convert("RGB").split()
    return ImageChops.subtract(ImageChops.darker(r, b), g)


def key_out(img):
    img = img.convert("RGB")
    bg = background_mask(img)
    excess = magenta_excess(img)
    for _ in range(3):  # eat the magenta-tinted fringe, one pixel ring at a time
        ring = ImageChops.subtract(bg.filter(ImageFilter.MaxFilter(3)), bg)
        bad = ImageChops.darker(ring, excess.point(lambda v: 255 if v > 38 else 0))
        bg = ImageChops.lighter(bg, bad)
    # despill what is left right at the edge
    zone = ImageChops.subtract(bg.filter(ImageFilter.MaxFilter(5)), bg)
    r, g, b = img.split()
    cut = excess.point(lambda v: int(v * 0.65))
    r2, b2 = ImageChops.subtract(r, cut), ImageChops.subtract(b, cut)
    r = Image.composite(r2, r, zone)
    b = Image.composite(b2, b, zone)
    out = Image.merge("RGB", (r, g, b)).convert("RGBA")
    alpha = ImageChops.invert(bg)
    # divider lines the generator sometimes draws: rows/columns that are opaque almost edge to edge
    w, h = alpha.size
    rows = alpha.resize((1, h), Image.BOX).point(lambda v: 0 if v > 230 else 255).resize((w, h), Image.NEAREST)
    cols = alpha.resize((w, 1), Image.BOX).point(lambda v: 0 if v > 230 else 255).resize((w, h), Image.NEAREST)
    alpha = ImageChops.darker(ImageChops.darker(alpha, rows), cols)
    out.putalpha(alpha)
    return out


def bleed_colors(img, passes=14):
    """Give transparent pixels the colour of their nearest opaque neighbours (instead of magenta).
    Scaling blends RGB across transparent pixels; with magenta underneath that makes pink halos."""
    arr = np.array(img.convert("RGBA"))
    rgb = arr[..., :3].astype(np.float32)
    known = arr[..., 3] > 8
    rgb[~known] = 0
    for _ in range(passes):
        k = known.astype(np.float32)
        acc = np.zeros_like(rgb)
        cnt = np.zeros(k.shape, np.float32)
        for dy in (-1, 0, 1):
            for dx in (-1, 0, 1):
                if dx or dy:
                    acc += np.roll(np.roll(rgb * k[..., None], dy, 0), dx, 1)
                    cnt += np.roll(np.roll(k, dy, 0), dx, 1)
        fill = (~known) & (cnt > 0)
        if not fill.any():
            break
        rgb[fill] = acc[fill] / cnt[fill][:, None]
        known |= fill
    out = arr.copy()
    solid = arr[..., 3] > 8
    out[..., :3] = np.where(solid[..., None], arr[..., :3], np.clip(rgb, 0, 255).astype(np.uint8))
    return Image.fromarray(out, "RGBA")


def to_mask(l_img):
    surf = pygame.image.frombytes(l_img.convert("RGB").tobytes(), l_img.size, "RGB")
    return pygame.mask.from_threshold(surf, (255, 255, 255), (40, 40, 40, 255))


def split_sprites(sheet, cols, rows, pad=2):
    """Assign each connected blob of pixels to the grid cell holding its centre. Blobs that merely
    cross a cell border stay with their owner; specks and the thin divider lines are dropped."""
    alpha = sheet.getchannel("A").point(lambda v: 255 if v > 24 else 0)
    amask = to_mask(alpha)
    dmask = to_mask(alpha.filter(ImageFilter.MaxFilter(15)))   # bridge small gaps (sparkles, struts)
    cw, ch = sheet.width / cols, sheet.height / rows
    cells = {}
    for comp in dmask.connected_components():
        bits = amask.overlap_mask(comp, (0, 0))
        if bits.count() < 80:
            continue
        rects = bits.get_bounding_rects()
        x0 = min(r.left for r in rects); y0 = min(r.top for r in rects)
        x1 = max(r.right for r in rects); y1 = max(r.bottom for r in rects)
        if min(x1 - x0, y1 - y0) <= 5 and max(x1 - x0, y1 - y0) > 150:
            continue                                           # divider line
        cx, cy = comp.centroid()
        key = (min(rows - 1, int(cy / ch)), min(cols - 1, int(cx / cw)))
        cells.setdefault(key, []).append((bits, (x0, y0, x1, y1)))
    out = {}
    for key, blobs in cells.items():
        union = pygame.mask.Mask(sheet.size)
        for bits, _ in blobs:
            union.draw(bits, (0, 0))
        box = (min(b[1][0] for b in blobs), min(b[1][1] for b in blobs),
               max(b[1][2] for b in blobs), max(b[1][3] for b in blobs))
        box = (max(0, box[0] - pad), max(0, box[1] - pad), min(sheet.width, box[2] + pad), min(sheet.height, box[3] + pad))
        sprite = sheet.crop(box)
        keep = Image.frombytes("RGB", sheet.size, pygame.image.tobytes(
            union.to_surface(setcolor=(255, 255, 255), unsetcolor=(0, 0, 0)), "RGB")).convert("L").crop(box)
        sprite.putalpha(ImageChops.darker(sprite.getchannel("A"), keep))
        out[key] = bleed_colors(sprite)
    return out


def horizon_row(img):
    """Lowest row (fraction of height) that still has skyline detail."""
    g = img.convert("L")
    w, h = g.size
    px = g.load()
    for y in range(h - 2, int(h * 0.4), -1):
        row = [px[x, y] for x in range(0, w, 3)]
        mean = sum(row) / len(row)
        std = (sum((v - mean) ** 2 for v in row) / len(row)) ** 0.5
        if std > 11:
            return (y + 1) / h
    return 0.7


def main():
    pygame.init()
    os.makedirs(OUT, exist_ok=True)
    meta = {}
    for fname, cols, rows, names in LAYOUTS:
        path = os.path.join(SHEETS, fname)
        if not os.path.exists(path):
            print("  ! missing", path)
            continue
        print(fname)
        sheet = key_out(Image.open(path))
        found = split_sprites(sheet, cols, rows)
        for i, name in enumerate(names):
            sprite = found.get((i // cols, i % cols))
            if sprite is None:
                print("  ! %-14s empty cell" % name)
                continue
            sprite.save(os.path.join(OUT, name + ".png"))
            meta[name] = [sprite.width, sprite.height]
            print("  ok %-14s %dx%d" % (name, sprite.width, sprite.height))
    for sky in SKIES:
        path = os.path.join(SHEETS, sky + ".png")
        if not os.path.exists(path):
            print("  ! missing", path)
            continue
        img = Image.open(path).convert("RGB")
        img.save(os.path.join(OUT, sky + ".png"))
        meta[sky] = {"horizon": round(horizon_row(img), 3), "size": list(img.size)}
        print("  ok %-14s horizon at %.1f%%" % (sky, meta[sky]["horizon"] * 100))
    logo = os.path.join(ROOT, "brand", "apex_logo.png")
    if os.path.exists(logo):
        bleed_colors(Image.open(logo)).save(os.path.join(OUT, "apex_logo.png"))
    with open(os.path.join(OUT, "meta.json"), "w") as fh:
        json.dump(meta, fh, indent=1)
    print("done ->", OUT)


if __name__ == "__main__":
    sys.exit(main())
