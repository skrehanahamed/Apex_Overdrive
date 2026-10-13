"""Loads the sprites produced by tools/build_assets.py and knows how big each is in the world.

World units: the road is 2 wide (x = -1 .. +1 are the road edges), a lane is ~0.67, a car ~0.3.
Most sprites are sized by world *width*; tall scenery is sized by world *height* so any aspect
ratio the art ends up with keeps believable proportions.
"""
import json
import os
import sys

import pygame

# name: ("w" | "h", world size). Variants listed in SAME_SCALE reuse the reference sprite's scale.
SIZES = {
    "hero_rear": ("w", 0.36),
    "traffic_sedan": ("w", 0.31), "traffic_sports": ("w", 0.32), "traffic_van": ("w", 0.34),
    "traffic_truck": ("w", 0.40), "traffic_taxi": ("w", 0.31), "traffic_suv": ("w", 0.33),
    "police_a": ("w", 0.33), "police_front": ("w", 0.33),
    "roadblock": ("w", 1.10), "traffic_cone": ("h", 0.13), "nitro_can": ("w", 0.26),
    "explosion": ("w", 1.00), "nitro_flames": ("w", 0.55),
    "lamp_post": ("h", 1.55), "palm_a": ("h", 1.40), "palm_b": ("h", 1.45),
    "building_a": ("h", 5.4), "building_b": ("h", 3.7), "building_c": ("h", 5.0), "building_d": ("h", 4.1),
    "billboard": ("w", 2.50), "highway_sign": ("w", 3.00),
}
SAME_SCALE = {
    "hero_brake": "hero_rear", "hero_left": "hero_rear", "hero_right": "hero_rear",
    "police_b": "police_a", "lamp_post_a": "lamp_post",
}
MIRRORED = {"lamp_post_l": "lamp_post", "lamp_post_a_l": "lamp_post_a"}   # lamp arms must point at the road
SKIES = ("sky_sunset", "sky_midnight", "sky_dawn", "sky_vapor")
UI = ("hud_gauge", "hud_bar", "hud_mirror", "hud_panel", "overdrive", "apex_logo")
# roadside things that wreck you if you drive into them off-road
SOLID = {"lamp_post", "lamp_post_l", "lamp_post_a", "lamp_post_a_l", "palm_a", "palm_b", "billboard"}

_WW = {}   # name -> world width, filled when Assets loads


class Assets:
    def __init__(self, folder, progress=None):
        self.folder = folder
        self.img = {}
        self.ppu = {}          # world units per source pixel
        self.sky = {}
        self.sky_meta = {}
        meta_path = os.path.join(folder, "meta.json")
        if not os.path.exists(meta_path):
            sys.exit("assets/ is empty - run `make assets` (needs the generated sheets in sheets/)")
        with open(meta_path) as fh:
            self.meta = json.load(fh)
        names = set(SIZES) | set(SAME_SCALE) | set(UI)
        todo = sorted(names)
        for i, name in enumerate(todo):
            self.img[name] = self._load(name)
            if progress:
                progress((i + 1) / (len(todo) + len(SKIES)))
        self.img["hud_mirror"] = self._punch_glass(self.img["hud_mirror"])
        for name, kind_val in SIZES.items():
            kind, val = kind_val
            w, h = self.img[name].get_size()
            self.ppu[name] = val / (w if kind == "w" else h)
        for name, ref in SAME_SCALE.items():
            self.ppu[name] = self.ppu[ref]
        for name, src in MIRRORED.items():
            self.img[name] = pygame.transform.flip(self.img[src], True, False)
            self.ppu[name] = self.ppu[src]
        # the two nitro jets are drawn separately so each can sit on its own exhaust
        fl = self.img["nitro_flames"]
        half = fl.get_width() // 2
        self.img["flame_l"] = fl.subsurface((0, 0, half, fl.get_height())).copy()
        self.img["flame_r"] = fl.subsurface((half, 0, fl.get_width() - half, fl.get_height())).copy()
        self.ppu["flame_l"] = self.ppu["flame_r"] = self.ppu["nitro_flames"]
        for name in self.img:
            if name in self.ppu:
                _WW[name] = self.ppu[name] * self.img[name].get_width()
        for sky in SKIES:
            path = os.path.join(folder, sky + ".png")
            self.sky[sky] = pygame.image.load(path).convert()
            self.sky_meta[sky] = self.meta[sky]["horizon"]
            if progress:
                progress(1.0)

    def _load(self, name):
        path = os.path.join(self.folder, name + ".png")
        if not os.path.exists(path):
            sys.exit("missing %s - run `make assets`" % path)
        return pygame.image.load(path).convert_alpha()

    def _punch_glass(self, img):
        """Make the dark mirror glass transparent so the game can draw the rear view behind the bezel.
        Also keeps the glass outline (as an alpha mask) so the view can be clipped to its exact shape."""
        w, h = img.get_size()
        dark = pygame.mask.from_threshold(img, (14, 26, 48, 255), (45, 45, 52, 255))
        glass = dark.connected_component((w // 2, int(h * 0.62)))
        rects = glass.get_bounding_rects()
        x0 = min(r.left for r in rects); y0 = min(r.top for r in rects)
        x1 = max(r.right for r in rects); y1 = max(r.bottom for r in rects)
        self.mirror_box = (x0 / w, y0 / h, x1 / w, y1 / h)
        self.mirror_glass = glass.to_surface(setcolor=(255, 255, 255, 255), unsetcolor=(255, 255, 255, 0)).convert_alpha()
        keep = glass.copy()
        keep.invert()
        return keep.to_surface(setsurface=img, unsetcolor=(0, 0, 0, 0)).convert_alpha()

    @staticmethod
    def world_w(name):
        return _WW[name]

    def world_h(self, name):
        return self.ppu[name] * self.img[name].get_height()
