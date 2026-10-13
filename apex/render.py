"""Pseudo-3D road renderer, backdrops, sprites, effects and HUD. Everything draws at 960x540."""
import math
import random

import pygame

from .font import UIFont
from .track import SEG_LEN, THEMES
from .world import CAM_DEPTH, CAM_H, DRAW, H, HORIZON, PLAYER_Z, ROAD_W, S, W

CENTERED = {"highway_sign"}     # decor drawn centred on the road instead of beside it
GAUGE_MAX = 320.0


def mix(a, b, t):
    return (int(a[0] + (b[0] - a[0]) * t), int(a[1] + (b[1] - a[1]) * t), int(a[2] + (b[2] - a[2]) * t))


def lerp(a, b, t):
    return a + (b - a) * t


class Renderer:
    def __init__(self, assets, progress=None):
        self.a = assets
        self.ui = UIFont()
        self.canvas = pygame.Surface((W, H))
        self.cache = {}
        self.shadows = {}
        self.frames = {}
        self.logos = {}
        self.fades, self.tints, self.strips = {}, {}, {}
        self.mips = {}
        names = sorted(self.a.img)
        for i, name in enumerate(names):                      # pre-shrunk copies: scaling never starts from a huge image
            self.mips[name] = self._mip_chain(self.a.img[name])
            if progress:
                progress(0.6 * (i + 1) / len(names))
        self.themes = []
        for i in range(len(THEMES)):
            self.themes.append(self._build_theme(i))
            if progress:
                progress(0.6 + 0.4 * (i + 1) / len(THEMES))
        self.vignette = self._vignette()
        self.scan = self._scanlines()
        self.crt = False

    # ---- precomputation ----------------------------------------------------------------
    @staticmethod
    def _mip_chain(src):
        chain = [src]
        w, h = src.get_size()
        while w > 12:
            w, h = max(1, int(w * 0.7)), max(1, int(h * 0.7))
            chain.append(pygame.transform.smoothscale(chain[-1], (w, h)))
        return chain

    def _build_theme(self, idx):
        th = THEMES[idx]
        img = self.a.sky[th.sky]
        hr = self.a.sky_meta[th.sky]
        iw, ih = img.get_size()
        y0, y1 = int(th.top * ih), int(hr * ih)
        crop = img.subsurface((0, y0, iw, y1 - y0))
        sw = int(iw * HORIZON / (y1 - y0))
        strip = pygame.Surface((sw, H))
        strip.blit(pygame.transform.smoothscale(crop, (sw, HORIZON)), (0, 0))
        ground = img.subsurface((0, y1, iw, ih - y1))                  # the backdrop's misty band below the skyline
        strip.blit(pygame.transform.smoothscale(ground, (sw, H - HORIZON)), (0, HORIZON))
        pair = pygame.Surface((sw * 2, H))                              # mirrored so the wrap has no seam
        pair.blit(strip, (0, 0))
        pair.blit(pygame.transform.flip(strip, True, False), (sw, 0))
        row = min(ih - 1, y1 + 6)
        pts = [img.get_at((x, row))[:3] for x in range(0, iw, 16)]
        fog = tuple(sum(p[k] for p in pts) // len(pts) for k in range(3))     # haze colour just under the skyline
        table = []
        for n in range(DRAW):
            f = min(1.0, (n / DRAW) ** 2.0 * 0.9)
            table.append([(mix(th.grass[d], fog, f), mix(th.rumble[d], fog, f), mix(th.road[d], fog, f),
                           mix(th.lane, fog, f)) for d in (0, 1)])
        hh_ = int(H * 0.22)
        up = 18 * S                                                    # haze rises above the horizon, peaks on it
        haze = pygame.Surface((W, hh_), pygame.SRCALPHA)
        for y in range(hh_):
            f = (y / up) ** 1.4 if y < up else (1 - (y - up) / (hh_ - up)) ** 1.6
            pygame.draw.line(haze, (*fog, int(140 * f)), (0, y), (W, y))
        return {"pair": pair, "period": sw * 2, "fog": fog, "table": table, "haze": haze, "th": th}

    @staticmethod
    def _vignette():
        v = pygame.Surface((W, H), pygame.SRCALPHA)
        for i in range(70):
            a = int(110 * (1 - i / 70) ** 2.2)
            pygame.draw.rect(v, (0, 0, 0, a), (i, i, W - 2 * i, H - 2 * i), 1)
        return v

    @staticmethod
    def _scanlines():
        s = pygame.Surface((W, H), pygame.SRCALPHA)
        for y in range(1, H, 2):
            pygame.draw.line(s, (0, 0, 0, 26), (0, y), (W, y))
        return s

    # ---- alpha helpers -----------------------------------------------------------------
    # Surface.set_alpha() on a per-pixel-alpha surface is not reliable on every pygame build (the
    # transparent pixels' raw colour shows through), so fades are baked into cached copies instead.
    def faded(self, surf, key, a):
        """Copy of `surf` with its per-pixel alpha multiplied by a (0..1), cached in 16 steps."""
        level = int(max(0.0, min(1.0, a)) * 15 + 0.5)
        if level >= 15:
            return surf
        k = (key, level)
        out = self.fades.get(k)
        if out is None:
            if len(self.fades) > 900:
                self.fades.clear()
            out = surf.copy()
            out.fill((255, 255, 255, level * 17), special_flags=pygame.BLEND_RGBA_MULT)
            self.fades[k] = out
        return out

    def overlay(self, c, rgb, a):
        """Flat tint over the whole canvas (drawn with per-pixel alpha, never set_alpha)."""
        a = int(max(0, min(255, a))) // 4 * 4
        if a <= 0:
            return
        s = self.tints.get((rgb, a))
        if s is None:
            s = pygame.Surface((W, H), pygame.SRCALPHA)
            s.fill((*rgb, a))
            if len(self.tints) > 80:
                self.tints.clear()
            self.tints[(rgb, a)] = s
        c.blit(s, (0, 0))

    def edge_glow(self, c, color, level, side="both"):
        """Additive coloured light along the left/right screen edges (plain RGB, no alpha involved)."""
        lv = int(max(0.0, min(1.0, level)) * 12)
        if lv <= 0:
            return
        key = (color, lv)
        strip = self.strips.get(key)
        if strip is None:
            strip = pygame.Surface((190, H))
            for x in range(190):
                f = lv / 12 * (1 - x / 190) ** 2
                pygame.draw.line(strip, tuple(int(v * f) for v in color), (x, 0), (x, H))
            self.strips[key] = strip
        if side in ("both", "L"):
            c.blit(strip, (0, 0), special_flags=pygame.BLEND_RGB_ADD)
        if side in ("both", "R"):
            c.blit(pygame.transform.flip(strip, True, False), (W - 190, 0), special_flags=pygame.BLEND_RGB_ADD)

    # ---- sprite helpers ----------------------------------------------------------------
    def scaled(self, name, dw, fade=1.0):
        key = (name, dw)
        sp = self.cache.get(key)
        if sp is None:
            if len(self.cache) > 1400:
                self.cache.clear()
            src = self.a.img[name]
            dh = max(1, dw * src.get_height() // src.get_width())
            if dw >= src.get_width():
                sp = pygame.transform.scale(src, (dw, dh))
            else:
                base = src
                for m in self.mips[name]:               # smallest pre-shrunk copy that is still >= target
                    if m.get_width() >= dw:
                        base = m
                if base.get_width() == dw:
                    sp = base
                elif dw > 320:
                    sp = pygame.transform.scale(base, (dw, dh))         # big & near: fast, still crisp
                else:
                    sp = pygame.transform.smoothscale(base, (dw, dh))
            self.cache[key] = sp
        return self.faded(sp, key, fade) if fade < 1.0 else sp

    def frame(self, name, width):
        key = (name, width)
        sp = self.frames.get(key)
        if sp is None:
            src = self.a.img[name]
            sp = self.frames[key] = pygame.transform.smoothscale(src, (width, width * src.get_height() // src.get_width()))
        return sp

    def shadow(self, dw):
        sp = self.shadows.get(dw)
        if sp is None:
            h = max(2, dw // 6)
            sp = pygame.Surface((dw, h), pygame.SRCALPHA)
            pygame.draw.ellipse(sp, (0, 0, 0, 105), (0, 0, dw, h))
            self.shadows[dw] = sp
        return sp

    def dest_w(self, name, scale, wmul=1.0):
        src = self.a.img[name]
        return int(scale * self.a.ppu[name] * src.get_width() * ROAD_W * (W / 2) * wmul)

    def blit_sprite(self, c, name, scale, sx, sy, clip=9999, anchor=-0.5, wmul=1.0, max_w=W * 2, shadow=False, fade=1.0):
        dw = self.dest_w(name, scale, wmul)
        if dw < 2 or dw > max_w:
            return
        if dw > 360:
            dw = dw // 8 * 8                                    # coarser steps for big sprites: far fewer rescales
        if sx + dw * anchor > W or sx + dw * (anchor + 1) < 0:
            return                                              # completely off-screen: don't even scale it
        sp = self.scaled(name, dw, fade)
        dh = sp.get_height()
        x = int(sx + dw * anchor)
        y = int(sy - dh)
        if shadow and dw > 8:
            sh = self.shadow(int(dw * 0.92))
            c.blit(sh, (int(sx - sh.get_width() / 2), int(sy - sh.get_height() / 2)))
        cut = max(0, int(y + dh - clip))
        if cut >= dh:
            return
        if cut:
            c.blit(sp, (x, y), (0, 0, dw, dh - cut))
        else:
            c.blit(sp, (x, y))

    # ---- main entry --------------------------------------------------------------------
    def draw(self, w, ui):
        c = self.canvas
        td = self.themes[w.theme_idx]
        title = ui["mode"] == "title"
        self.draw_sky(c, w, td)
        vis = self.draw_road(c, w, td)
        self.draw_sprites(c, w, vis)
        c.blit(td["haze"], (0, HORIZON - 18 * S))
        if w.pursuit and w.gap < 35 and w.state == "play" and not title:   # siren light on the edges, behind the car
            lvl = min(1.0, (35 - w.gap) / 35 * 1.35)
            red, blue = (255, 40, 50), (50, 100, 255)
            left, right = (red, blue) if int(w.time * 5) % 2 == 0 else (blue, red)
            self.edge_glow(c, left, lvl, "L")
            self.edge_glow(c, right, lvl, "R")
        self.draw_speed_lines(c, w)
        self.draw_booms(c, w)                                 # blasts sit behind the car, which stays visible
        if w.state == "busted":
            self.overlay(c, (70, 0, 10), 150 * min(1.0, w.state_t / 0.6))
        self.draw_player(c, w)
        if w.state == "busted":
            self.draw_busted_cops(c, w)
        self.draw_particles(c, w)
        c.blit(self.vignette, (0, 0))
        if w.boosting:
            self.edge_glow(c, (60, 150, 255), 0.7)
        if w.flash > 0:
            self.overlay(c, (255, 255, 255), 255 * min(1, w.flash))
        if not title:
            self.draw_hud(c, w, td)
        self.draw_overlay(c, w, ui)
        if self.crt:
            c.blit(self.scan, (0, 0))
        return c

    # ---- sky ---------------------------------------------------------------------------
    def draw_sky(self, c, w, td):
        pair, period = td["pair"], td["period"]
        x = -int(w.sky_off) % period
        c.blit(pair, (x - period, 0))
        c.blit(pair, (x, 0))

    # ---- road --------------------------------------------------------------------------
    def draw_road(self, c, w, td):
        segs, n_segs = w.segs, w.n
        base = w.find(w.position)
        base_pct = (w.position % SEG_LEN) / SEG_LEN
        pseg = w.find(w.position + PLAYER_Z)
        pp = ((w.position + PLAYER_Z) % SEG_LEN) / SEG_LEN
        cam_y = lerp(pseg.y1, pseg.y2, pp) + CAM_H
        fog = td["table"]
        x = 0.0
        dx = -(base.curve * base_pct)
        maxy = H
        vis = []
        hw, hh = W / 2, H / 2
        poly = pygame.draw.polygon
        for n in range(DRAW):
            seg = segs[(base.index + n) % n_segs]
            looped = seg.index < base.index
            seg.clip = maxy
            camz = w.position - (w.length if looped else 0)
            cx1 = w.x * ROAD_W - x
            x += dx
            cx2 = w.x * ROAD_W - x
            dx += seg.curve
            tz1 = seg.z1 - camz
            if tz1 <= CAM_DEPTH:
                continue
            tz2 = seg.z2 - camz
            s1 = CAM_DEPTH / tz1
            s2 = CAM_DEPTH / tz2
            sx1 = hw - s1 * cx1 * hw
            sx2 = hw - s2 * cx2 * hw
            sy1 = HORIZON + s1 * (cam_y - seg.y1) * hh
            sy2 = HORIZON + s2 * (cam_y - seg.y2) * hh
            if sy2 >= sy1 or sy2 >= maxy:
                continue
            sw1 = s1 * ROAD_W * hw
            sw2 = s2 * ROAD_W * hw
            seg.sx1, seg.sy1, seg.sw1, seg.sc1 = sx1, sy1, sw1, s1
            seg.sx2, seg.sy2, seg.sw2, seg.sc2 = sx2, sy2, sw2, s2
            vis.append((n, seg))
            grass, rumble, road, lane = fog[n][seg.dark]
            iy1, iy2 = int(sy1), int(sy2)
            c.fill(grass, (0, iy2, W, iy1 - iy2 + 1))
            r1, r2 = sw1 / 10, sw2 / 10
            poly(c, rumble, ((sx1 - sw1 - r1, iy1), (sx1 - sw1, iy1), (sx2 - sw2, iy2), (sx2 - sw2 - r2, iy2)))
            poly(c, rumble, ((sx1 + sw1 + r1, iy1), (sx1 + sw1, iy1), (sx2 + sw2, iy2), (sx2 + sw2 + r2, iy2)))
            poly(c, road, ((sx1 - sw1, iy1), (sx1 + sw1, iy1), (sx2 + sw2, iy2), (sx2 - sw2, iy2)))
            if not seg.dark:
                l1, l2 = max(1.0, sw1 / 70), max(1.0, sw2 / 70)
                for k in (-1 / 3, 1 / 3):
                    a1, a2 = sx1 + sw1 * k, sx2 + sw2 * k
                    poly(c, lane, ((a1 - l1, iy1), (a1 + l1, iy1), (a2 + l2, iy2), (a2 - l2, iy2)))
            maxy = sy1
        return vis

    # ---- sprites -----------------------------------------------------------------------
    def draw_sprites(self, c, w, vis):
        hw = W / 2
        t = w.time
        for n, seg in reversed(vis):
            fade = min(1.0, (DRAW - n) / 20.0)          # scenery fades in at the horizon instead of popping
            for car in seg.cars:
                pct = (car.z % SEG_LEN) / SEG_LEN
                scale = lerp(seg.sc1, seg.sc2, pct)
                sx = lerp(seg.sx1, seg.sx2, pct) + scale * car.offset * ROAD_W * hw
                sy = lerp(seg.sy1, seg.sy2, pct)
                wmul = 1.0
                shadow = car.kind in ("traffic", "block", "cone")
                if car.kind == "pickup":
                    unit = scale * ROAD_W * hw
                    sy -= math.sin(t * 4 + car.z * 0.01) * unit * 0.025 + unit * 0.04
                self.blit_sprite(c, car.name, scale, sx, sy, seg.clip, -0.5, wmul, shadow=shadow and fade >= 1.0, fade=fade)
            for name, off in seg.sprites:
                scale = seg.sc1
                sx = seg.sx1 + scale * off * ROAD_W * hw
                anchor = -0.5 if name in CENTERED else (-1 if off < 0 else 0)
                self.blit_sprite(c, name, scale, sx, seg.sy1, seg.clip, anchor, max_w=W * 2.4, fade=fade)

    def draw_player(self, c, w):
        name = "hero_rear"
        if w.steer > 0.4:
            name = "hero_right"
        elif w.steer < -0.4:
            name = "hero_left"
        elif w.braking:
            name = "hero_brake"
        bounce = S // 2 if (int(w.time * (6 + 10 * w.speed_pct)) % 2 and w.speed > 1000) else 0
        if abs(w.x) > 1:
            bounce += (int(w.time * 40) % 2) * S
        scale = 1 / CAM_H
        cx, base_y = W // 2 + int(w.steer * 6 * S), H - 22 - bounce
        car_w = self.dest_w("hero_rear", scale)
        sh = self.shadow(int(car_w * 1.05))
        c.blit(sh, (cx - sh.get_width() // 2, base_y - sh.get_height() // 2 + 2 * S))
        ghost = 0 < w.invul < 1.5 and int(w.time * 14) % 2      # after a crash: flicker translucent, never vanish
        self.blit_sprite(c, name, scale, cx, base_y, 9999, -0.5, fade=0.65 if ghost else 1.0)
        if w.boosting:
            sp = self.scaled(name, self.dest_w(name, scale))
            ch = sp.get_height()
            top = base_y - ch
            fl = 0.85 + 0.3 * math.sin(w.time * 70) + 0.1 * math.sin(w.time * 113)
            fw = int(car_w * 0.30 * fl)
            if fw > 4:
                for rel in (0.22, 0.78):
                    jx = cx - sp.get_width() // 2 + int(sp.get_width() * rel)
                    spr = self.scaled("flame_l" if rel < 0.5 else "flame_r", fw)
                    c.blit(spr, (jx - fw // 2, top + int(ch * 0.84)))

    def draw_speed_lines(self, c, w):
        if w.speed_pct < 0.85 and not w.boosting:
            return
        rnd = random.Random(int(w.time * 30))
        count = 34 if w.boosting else 10
        for _ in range(count):
            a = rnd.uniform(0, math.tau)
            if math.sin(a) < -0.35:
                continue
            r0 = rnd.uniform(110, 280)
            r1 = r0 + rnd.uniform(40, 140)
            col = (230, 245, 255) if w.boosting else (170, 170, 210)
            pygame.draw.line(c, col, (W / 2 + math.cos(a) * r0, HORIZON + 14 * S + math.sin(a) * r0 * 0.62),
                             (W / 2 + math.cos(a) * r1, HORIZON + 14 * S + math.sin(a) * r1 * 0.62), 2)

    def draw_booms(self, c, w):
        """Fireballs on every car involved in a crash (yours and the other one)."""
        for x, y, s, age in w.booms:
            if age < 0:
                continue
            dw = int(W * 0.30 * s * (0.35 + 1.0 * min(1.0, age / 0.3)))
            fade = 1.0 if age < 0.35 else 1 - (age - 0.35) / 0.55
            if dw > 4 and fade > 0:
                sp = self.scaled("explosion", dw, fade)
                c.blit(sp, (int(x - sp.get_width() / 2), int(y - sp.get_height() / 2)))

    def draw_busted_cops(self, c, w):
        """Two cruisers slide in on either side of your (still visible) car."""
        ease = 1 - (1 - min(1.0, w.state_t / 0.7)) ** 3
        flip = int(w.time * 6) % 2
        for side, x_end in ((-1, 0.15), (1, 0.85)):
            name = "police_a" if (flip if side < 0 else not flip) else "police_b"
            x = W * x_end + side * (1 - ease) * 420
            sp = self.scaled(name, 400)
            c.blit(sp, (int(x - sp.get_width() / 2), H + 24 - sp.get_height()))

    def draw_particles(self, c, w):
        for p in w.particles:
            s = max(1, int(p[7]))
            c.fill(p[6], (int(p[0]), int(p[1]), s, s))

    # ---- HUD ---------------------------------------------------------------------------
    def draw_hud(self, c, w, td):
        u = self.ui
        white, dim = (255, 255, 255), (150, 190, 230)
        M = 16

        # score panel (top-left)
        pan = self.frame("hud_panel", 310)
        c.blit(pan, (M, M))
        ph = pan.get_height()
        u.draw(c, "SCORE", M + 30, M + 10, 15, dim, ow=1)
        u.draw(c, "%07d" % int(w.score), M + 30, M + 24, 44, white, ow=2)

        # heat / distance panel (top-right)
        pw2 = 270
        c.blit(self.frame("hud_panel", pw2), (W - M - pw2, M))
        x2 = W - M - pw2
        u.draw(c, "HEAT", x2 + 26, M + 9, 15, dim, ow=1)
        for i in range(min(w.heat, 9)):
            self.star(c, x2 + 36 + i * 22, M + 44, 9)
        u.draw(c, "%.1f KM" % (w.dist / 1000), x2 + pw2 - 26, M + 8, 26, white, "r", ow=2)

        self.draw_mirror(c, w, td)
        self.draw_gap(c, w)

        # nitro bar (bottom-left)
        bw = 330
        bar = self.frame("hud_bar", bw)
        bh = bar.get_height()
        by = H - M - bh
        u.draw(c, "NITRO", M + 8, by - 24, 18, (110, 210, 255), ow=2)
        c.blit(bar, (M, by))
        ix, iy, iw, ih = M + int(bw * 0.075), by + int(bh * 0.27), int(bw * 0.85), int(bh * 0.46)
        pygame.draw.rect(c, (4, 14, 30), (ix, iy, iw, ih))
        n_seg = 20
        sw_ = iw / n_seg
        for i in range(n_seg):
            on = w.nitro >= (i + 1) * 100 / n_seg - 2.5
            col = (70, 190, 255) if on else (18, 36, 62)
            if on and w.boosting:
                col = (255, 255, 255) if int(w.time * 24) % 2 else (150, 225, 255)
            c.fill(col, (int(ix + i * sw_) + 1, iy + 1, max(1, int(sw_) - 2), ih - 2))

        # speed gauge (bottom-right)
        gw = 260
        g = self.frame("hud_gauge", gw)
        gx, gy = W - M - gw, H - M - g.get_height()
        c.blit(g, (gx, gy))
        gcx, gcy = gx + gw // 2, gy + g.get_height() // 2
        kmh = w.kmh
        frac = max(0.0, min(1.0, kmh / GAUGE_MAX))
        ang = math.radians(225 - 270 * frac)
        r1, r2 = gw * 0.315, gw * 0.425
        p1 = (gcx + math.cos(ang) * r1, gcy - math.sin(ang) * r1)
        p2 = (gcx + math.cos(ang) * r2, gcy - math.sin(ang) * r2)
        hot = kmh > 270 or w.boosting
        pygame.draw.line(c, (255, 120, 40) if hot else (70, 230, 255), p1, p2, 9)
        pygame.draw.line(c, (255, 255, 255), p1, p2, 3)
        u.draw(c, "%d" % kmh, gcx, gcy - 34, 62, (255, 150, 90) if hot else white, "c", ow=3)
        u.draw(c, "KM/H", gcx, gcy + 26, 16, dim, "c", ow=1)

        if w.combo > 1:
            u.draw(c, "COMBO x%d" % w.combo, M + 8, M + ph + 6, 24, (255, 235, 90), ow=2)
        for i, (text, color, age) in enumerate(reversed(w.floaters)):
            if age < 0.12 and int(age * 40) % 2:
                continue
            fade = 1 - max(0, (age - 1.0) / 0.6)
            s = u.render(text, 44 if i == 0 else 26, color, (8, 6, 24), 3)
            if fade < 1.0:
                s = s.copy()
                s.fill((255, 255, 255, int(255 * fade)), special_flags=pygame.BLEND_RGBA_MULT)
            c.blit(s, (W // 2 - s.get_width() // 2, 296 + i * 34 - int(age * 14)))

    @staticmethod
    def star(c, x, y, r):
        pts = []
        for k in range(10):
            rr = r if k % 2 == 0 else r * 0.42
            a = -math.pi / 2 + k * math.pi / 5
            pts.append((x + math.cos(a) * rr, y + math.sin(a) * rr))
        pygame.draw.polygon(c, (20, 14, 10), [(px + 1, py + 1) for px, py in pts])
        pygame.draw.polygon(c, (255, 214, 60), pts)

    def draw_mirror(self, c, w, td):
        mw = 300
        fr = self.frame("hud_mirror", mw)
        mh = fr.get_height()
        mx, my = W // 2 - mw // 2, 6
        key = ("glassmask", mw)
        mask = self.frames.get(key)
        if mask is None:
            src = self.a.mirror_glass
            mask = self.frames[key] = pygame.transform.smoothscale(src, (mw, mh))
        gx0, gy0, gx1, gy1 = self.a.mirror_box
        gl = pygame.Rect(int(gx0 * mw), int(gy0 * mh), int((gx1 - gx0) * mw), int((gy1 - gy0) * mh))
        th, fog = td["th"], td["fog"]
        view = pygame.Surface((mw, mh), pygame.SRCALPHA)
        view.fill(mix(fog, (10, 10, 30), 0.6), gl)
        hz = gl.top + int(gl.height * 0.42)
        view.fill(mix(th.grass[0], fog, 0.15), (gl.left, hz, gl.width, gl.bottom - hz))
        mid = gl.centerx
        pygame.draw.polygon(view, th.road[0], ((mid - 8, hz), (mid + 8, hz), (gl.right - 10, gl.bottom), (gl.left + 10, gl.bottom)))
        pygame.draw.line(view, th.lane, (mid, hz), (mid, gl.bottom), 2)
        if w.pursuit and w.gap < 98:
            f = 1 - w.gap / 100
            dw = int(10 + 120 * f ** 1.1)
            sp = self.scaled("police_front", dw)
            px = mid - dw // 2 + int(math.sin(w.time * 2) * 3)
            py = gl.bottom - sp.get_height() + int((1 - f) * 10) + 4
            view.blit(sp, (px, py))
            lit = int(w.time * 8) % 2
            glow = pygame.Surface((dw, max(4, dw // 3)), pygame.SRCALPHA)
            glow.fill((255, 40, 40, 110) if lit else (60, 100, 255, 110), (0, 0, dw // 2, glow.get_height()))
            glow.fill((60, 100, 255, 110) if lit else (255, 40, 40, 110), (dw // 2, 0, dw - dw // 2, glow.get_height()))
            view.blit(glow, (px, py - glow.get_height() // 3))
        view.blit(mask, (0, 0), special_flags=pygame.BLEND_RGBA_MIN)      # cut to the bezel's glass shape
        c.blit(view, (mx, my))
        c.blit(fr, (mx, my))

    def draw_gap(self, c, w):
        u = self.ui
        bw = 250
        bar = self.frame("hud_bar", bw)
        bh = bar.get_height()
        x0, y0 = W // 2 - bw // 2, 6 + 125
        c.blit(bar, (x0, y0))
        ix, iy, iw, ih = x0 + int(bw * 0.075), y0 + int(bh * 0.27), int(bw * 0.85), int(bh * 0.46)
        pygame.draw.rect(c, (4, 14, 30), (ix, iy, iw, ih))
        if not w.pursuit:
            u.draw(c, "NO POLICE IN AREA", x0 + bw // 2, y0 + bh * 0.5 - 8, 15, (120, 200, 160), "c", ow=1)
            return
        col = (230, 50, 60) if w.gap < 30 else (240, 200, 60) if w.gap < 65 else (80, 225, 130)
        if w.gap < 18 and int(w.time * 8) % 2:
            col = (255, 255, 255)
        c.fill(col, (ix + 1, iy + 1, max(0, int((iw - 2) * w.gap / 100)), ih - 2))
        u.draw(c, "BUSTED", x0 + 6, y0 + bh + 1, 14, (255, 110, 110), ow=1)
        u.draw(c, "ESCAPE", x0 + bw - 6, y0 + bh + 1, 14, (120, 255, 160), "r", ow=1)

    # ---- overlays / screens ------------------------------------------------------------
    def logo(self, name, width):
        key = (name, width)
        sp = self.logos.get(key)
        if sp is None:
            src = self.a.img[name]
            sp = self.logos[key] = pygame.transform.smoothscale(src, (width, int(width * src.get_height() / src.get_width())))
        return sp

    @staticmethod
    def glow_of(surf, color):
        """Soft coloured halo: the logo's silhouette, tinted, stamped around in rings."""
        w, h = surf.get_size()
        sil = surf.copy()
        sil.fill((0, 0, 0, 255), special_flags=pygame.BLEND_RGBA_MULT)
        sil.fill(color + (0,), special_flags=pygame.BLEND_RGBA_ADD)
        sil.fill((255, 255, 255, 26), special_flags=pygame.BLEND_RGBA_MULT)
        out = pygame.Surface((w + 60, h + 60), pygame.SRCALPHA)
        for r in (4, 9, 15, 22):
            for k in range(14):
                a = k * math.tau / 14
                out.blit(sil, (30 + int(math.cos(a) * r), 30 + int(math.sin(a) * r)))
        return out

    @staticmethod
    def shine(surf, t, period=3.4):
        out = surf.copy()
        w, h = out.get_size()
        u = (t % period) / period
        if u < 0.35:
            x = int(u / 0.35 * (w + h * 2)) - h
            band = pygame.Surface((w, h))
            for k, br in ((h * 0.55, 40), (h * 0.35, 80), (h * 0.15, 120)):
                pygame.draw.polygon(band, (br, br, br + 10), ((x - k + h * 0.5, 0), (x + k + h * 0.5, 0), (x + k, h), (x - k, h)))
            out.blit(band, (0, 0), special_flags=pygame.BLEND_RGB_ADD)
        return out

    def draw_title_logo(self, c, t, y):
        apex = self.logo("apex_logo", 540)
        over = self.logo("overdrive", 780)
        for i, (img, color, yy) in enumerate(((apex, (0, 200, 255), y), (over, (255, 60, 190), y + apex.get_height() + 26))):
            key = ("glow", i)
            glow = self.logos.get(key)
            if glow is None:
                glow = self.logos[key] = self.glow_of(img, color)
            x = W // 2 - img.get_width() // 2
            c.blit(self.faded(glow, key, 0.75 + 0.2 * math.sin(t * 3)), (x - 30, yy - 30))
            c.blit(self.shine(img, t + 0.5 * i), (x, yy))
        return y + apex.get_height() + over.get_height() + 26

    def dim(self, c, alpha, color=(0, 0, 0)):
        self.overlay(c, color, alpha)

    def draw_overlay(self, c, w, ui):
        u = self.ui
        mode = ui["mode"]
        blink = int(ui["t"] * 2.5) % 2
        if mode == "title":
            self.dim(c, 110, (4, 2, 24))
            yb = self.draw_title_logo(c, ui["t"], 70)
            u.draw(c, "S T R E E T   P U R S U I T", W // 2, yb + 22, 28, (220, 235, 255), "c", ow=2)
            if blink:
                u.draw(c, "PRESS ENTER", W // 2, yb + 82, 44, (120, 255, 160), "c", ow=3)
            u.draw(c, "ARROWS / WASD  STEER   -   UP  GAS   -   DOWN  BRAKE   -   SPACE  NITRO", W // 2, H - 66, 17, (170, 190, 230), "c", ow=2)
            u.draw(c, "HI SCORE %07d     P PAUSE   M MUTE   C CRT   F FULLSCREEN" % ui["hi"], W // 2, H - 40, 17, (130, 150, 200), "c", ow=2)
        elif mode == "paused":
            self.dim(c, 140)
            u.draw(c, "PAUSED", W // 2, 190, 110, (255, 255, 255), "c", ow=4)
            u.draw(c, "P  RESUME      ESC  QUIT", W // 2, 320, 24, (170, 190, 230), "c", ow=2)
        elif w.state == "busted":
            if w.state_t > 0.2:
                col = (255, 70, 80) if int(ui["t"] * 6) % 2 else (255, 255, 255)
                u.draw(c, "BUSTED", W // 2, 40, 140, col, "c", ow=5)
                u.draw(c, "SCORE  %07d" % int(w.score), W // 2, 200, 46, (255, 255, 255), "c", ow=3)
                u.draw(c, "%.1f KM    HEAT %d" % (w.dist / 1000, w.heat), W // 2, 254, 24, (200, 215, 245), "c", ow=2)
                best = "NEW HIGH SCORE!" if ui["new_hi"] else "HI SCORE  %07d" % ui["hi"]
                u.draw(c, best, W // 2, 286, 26, (255, 214, 60), "c", ow=2)
                if w.state_t > 1.0 and blink:
                    u.draw(c, "PRESS ENTER", W // 2, 322, 40, (120, 255, 160), "c", ow=3)
        elif w.state == "escaped":
            u.draw(c, "ESCAPED!", W // 2, 160, 96, (120, 255, 160), "c", ow=5)
            u.draw(c, "HEAT RISING...", W // 2, 250, 26, (255, 214, 60), "c", ow=2)
        if mode == "play" and w.state == "play" and w.countdown > 0:       # 3 - 2 - 1
            n = int(w.countdown) + 1
            pulse = 1.0 - (w.countdown % 1.0)
            u.draw(c, str(n), W // 2, 120 - int(pulse * 14), int(190 + 60 * (1 - pulse)), (255, 214, 60), "c", ow=6)
            u.draw(c, "GET READY", W // 2, 96, 28, (200, 220, 255), "c", ow=2)
        elif mode == "play" and w.go_t > 0:
            u.draw(c, "GO!", W // 2, 120, int(230 - w.go_t * 40), (120, 255, 160), "c", ow=6)
