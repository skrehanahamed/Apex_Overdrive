"""Track geometry (curves + hills as a list of segments), visual themes and roadside dressing."""
import math
from dataclasses import dataclass

SEG_LEN = 200.0
RUMBLE = 3  # segments per colour band


class Segment:
    __slots__ = ("index", "z1", "z2", "y1", "y2", "curve", "dark", "sprites", "cars",
                 "sx1", "sy1", "sw1", "sx2", "sy2", "sw2", "sc1", "sc2", "cz1", "clip", "looped")

    def __init__(self, index, y1, y2, curve):
        self.index = index
        self.z1 = index * SEG_LEN
        self.z2 = (index + 1) * SEG_LEN
        self.y1, self.y2, self.curve = y1, y2, curve
        self.dark = (index // RUMBLE) % 2
        self.sprites = []   # (name, road-relative x offset)
        self.cars = []
        self.sx1 = self.sy1 = self.sw1 = self.sx2 = self.sy2 = self.sw2 = 0
        self.sc1 = self.sc2 = self.cz1 = self.clip = 0
        self.looped = False


@dataclass(frozen=True)
class Theme:
    name: str
    sky: str          # backdrop key in Assets.sky
    top: float        # fraction of the backdrop image height shown at the very top of the screen
    grass: tuple      # (light, dark)
    road: tuple
    rumble: tuple
    lane: tuple
    decor: tuple      # relative weights: palm, building, billboard, gantry
    night: bool = False


THEMES = [
    Theme("SUNSET STRIP", "sky_sunset", 0.16, ((62, 22, 96), (52, 18, 84)), ((98, 72, 112), (88, 64, 102)),
          ((250, 240, 232), (222, 48, 62)), (255, 232, 170), (3, 1, 1, 1)),
    Theme("MIDNIGHT CITY", "sky_midnight", 0.05, ((26, 12, 66), (20, 8, 54)), ((54, 50, 90), (46, 42, 80)),
          ((0, 226, 255), (255, 60, 190)), (255, 226, 96), (0.5, 4, 1, 1), True),
    Theme("BRIDGE DAWN", "sky_dawn", 0.12, ((22, 86, 120), (16, 74, 106)), ((100, 110, 140), (90, 100, 130)),
          ((255, 255, 255), (255, 112, 96)), (255, 255, 255), (2, 2, 1, 1)),
    Theme("VAPORWAVE BAY", "sky_vapor", 0.10, ((20, 68, 158), (14, 58, 144)), ((80, 90, 142), (72, 80, 132)),
          ((255, 110, 210), (90, 225, 255)), (255, 244, 210), (3, 2, 1, 1)),
]


def _ease_in(a, b, p):
    return a + (b - a) * p * p


def _ease_io(a, b, p):
    return a + (b - a) * (-math.cos(p * math.pi) / 2 + 0.5)


def build_track():
    segs = []

    def last_y():
        return segs[-1].y2 if segs else 0.0

    def add(curve, y):
        segs.append(Segment(len(segs), last_y(), y, curve))

    def road(enter, hold, leave, curve, y):
        start, end = last_y(), last_y() + y * SEG_LEN
        total = enter + hold + leave
        for n in range(enter):
            add(_ease_in(0, curve, n / enter), _ease_io(start, end, n / total))
        for n in range(hold):
            add(curve, _ease_io(start, end, (enter + n) / total))
        for n in range(leave):
            add(_ease_io(curve, 0, n / leave), _ease_io(start, end, (enter + hold + n) / total))

    def straight(n=25):
        road(n, n, n, 0, 0)

    def hill(n, h):
        road(n, n, n, 0, h)

    def curve(n, c, h=0):
        road(n, n, n, c, h)

    def s_curves():
        road(25, 25, 25, -2, 0); road(25, 25, 25, 4, 15); road(25, 25, 25, -3, -10)
        road(25, 25, 25, 2, 0); road(25, 25, 25, -5, 10)

    straight(40)
    hill(25, 20); curve(30, 3); straight(15)
    curve(30, -4, 25); hill(25, -20); s_curves()
    straight(20); curve(40, 6, 20); hill(30, 40); curve(25, -6, -30)
    straight(15); road(20, 30, 20, 5, 15); road(20, 30, 20, -5, -15)
    hill(20, 30); curve(35, -3, 15); hill(25, -45); straight(30)
    curve(30, 4); s_curves(); curve(25, -6, 25)
    hill(30, -15); straight(25)
    road(25, 25, 25, 0, -last_y() / SEG_LEN)  # drop back to y=0 so the loop is seamless
    return segs


PALMS = ("palm_a", "palm_b")
BUILDINGS = ("building_a", "building_b", "building_c", "building_d")


def dress(segs, theme_idx, rng):
    """Re-populate roadside decoration for a theme."""
    th = THEMES[theme_idx % len(THEMES)]
    for s in segs:
        s.sprites = []
    w_palm, w_build, w_board, w_gantry = th.decor
    lamp_every = 8 if th.night else 12
    for s in segs:
        i = s.index
        if i % lamp_every == 0:
            alt = "_a" if (i // lamp_every) % 3 == 0 else ""
            s.sprites.append(("lamp_post%s_l" % alt, -1.22))
            s.sprites.append(("lamp_post%s" % alt, 1.22))
        if w_palm and rng.random() < 0.045 * w_palm:
            s.sprites.append((rng.choice(PALMS), rng.choice((-1, 1)) * rng.uniform(1.6, 2.8)))
        if w_build and i % 5 == 0:
            side = 1 if (i // 5) % 2 else -1
            s.sprites.append((rng.choice(BUILDINGS), side * rng.uniform(3.6, 5.2)))
            if rng.random() < 0.5 * w_build / 4:
                s.sprites.append((rng.choice(BUILDINGS), -side * rng.uniform(3.8, 5.6)))
        if w_board and i % 60 == 11 and rng.random() < 0.45 * w_board:
            s.sprites.append(("billboard", rng.choice((-1, 1)) * rng.uniform(1.8, 2.4)))
        if w_gantry and i % 170 == 90:
            s.sprites.append(("highway_sign", 0.0))
