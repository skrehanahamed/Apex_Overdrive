"""Window, input, game states (title / play / pause) and the fixed-timestep main loop."""
import os
import sys

import pygame

from .assets import Assets
from .audio import Audio
from .font import UIFont
from .render import Renderer
from .track import THEMES
from .world import H, S, Input, W, World

ROOT = getattr(sys, "_MEIPASS", os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
HI_PATH = os.path.join(ROOT, ".highscore")
STEP = 1 / 60


def load_hi():
    try:
        with open(HI_PATH) as fh:
            return int(fh.read().strip())
    except (OSError, ValueError):
        return 0


def save_hi(v):
    try:
        with open(HI_PATH, "w") as fh:
            fh.write(str(int(v)))
    except OSError:
        pass


class Game:
    def __init__(self, bot=False, mute=False):
        pygame.init()
        pygame.display.set_caption("APEX OVERDRIVE")
        pygame.mouse.set_visible(False)
        self.screen = pygame.display.set_mode(self.window_size(), pygame.RESIZABLE)
        self.present = pygame.Surface((W, H))
        self.clock = pygame.time.Clock()
        self.ui_font = UIFont()
        self.splash = None
        self.load_label, self.load_frac = "STARTING", 0.0
        self.progress(0.0, "STARTING")
        # everything is loaded and warmed up front, so nothing pops in or hitches once you're driving
        self.assets = Assets(os.path.join(ROOT, "assets"), lambda f: self.progress(0.02 + 0.28 * f, "LOADING SPRITES"))
        self.renderer = Renderer(self.assets, lambda f: self.progress(0.30 + 0.15 * f, "BUILDING SCENERY"))
        self.audio = Audio(mute=mute, progress=lambda f: self.progress(0.45 + 0.35 * f, "TUNING ENGINES"))
        self.throttle = False
        self.world = World()
        self.hi = load_hi()
        self.new_hi = False
        self.bot = bot
        self.mode = "play" if bot else "title"
        self.t = 0.0
        self.acc = 0.0
        self.running = True
        self.warm_up()
        self.progress(1.0, "READY")

    # ---- loading screen ----------------------------------------------------------------
    def progress(self, frac, label):
        self.load_frac, self.load_label = frac, label
        c = self.present
        c.fill((6, 6, 20))
        if self.splash is None:
            path = os.path.join(ROOT, "assets", "apex_logo.png")
            if os.path.exists(path):
                img = pygame.image.load(path).convert_alpha()
                self.splash = pygame.transform.smoothscale(img, (560, int(560 * img.get_height() / img.get_width())))
            else:
                self.splash = False
        if self.splash:
            c.blit(self.splash, (W // 2 - self.splash.get_width() // 2, H // 2 - 110))
        self.ui_font.draw(c, "O V E R D R I V E", W // 2, H // 2 - 10, 34, (200, 215, 240), "c", ow=2)
        bw, bh = 520, 14
        x0, y0 = W // 2 - bw // 2, H // 2 + 70
        pygame.draw.rect(c, (24, 30, 60), (x0 - 3, y0 - 3, bw + 6, bh + 6), border_radius=8)
        pygame.draw.rect(c, (60, 190, 255), (x0, y0, max(4, int(bw * frac)), bh), border_radius=6)
        self.ui_font.draw(c, "%s  %d%%" % (label, int(frac * 100)), W // 2, y0 + 26, 18, (150, 175, 215), "c", ow=1)
        self.blit_to_window(c)
        pygame.event.pump()

    def warm_up(self):
        """Render every theme once (and touch every font size) so the first real frames are already cheap."""
        w = self.world
        for size in (14, 15, 16, 17, 18, 22, 24, 26, 28, 30, 34, 40, 44, 46, 62, 96, 110, 120, 140, 150, 190, 250):
            self.ui_font.font(size)
            self.renderer.ui.font(size)
        for i in range(len(THEMES)):
            w.theme_idx = i
            for mode in ("title", "play"):
                self.renderer.draw(w, {"mode": mode, "t": 0.0, "hi": 0, "new_hi": False})
            self.progress(0.80 + 0.2 * (i + 1) / len(THEMES), "WARMING UP")
        w.new_run()

    @staticmethod
    def window_size():
        """Up to 1920x1080, but never bigger than the desktop; always 16:9."""
        try:
            dw, dh = pygame.display.get_desktop_sizes()[0]
        except (pygame.error, IndexError):
            dw, dh = 1920, 1080
        k = min(2.0, dw * 0.94 / W, dh * 0.88 / H)
        return int(W * k), int(H * k)

    # ---- state transitions -------------------------------------------------------------
    def start_run(self):
        self.world.new_run()
        self.new_hi = False
        self.mode = "play"
        self.audio.play("start")

    def read_input(self):
        k = pygame.key.get_pressed()
        inp = Input()
        inp.left = k[pygame.K_LEFT] or k[pygame.K_a]
        inp.right = k[pygame.K_RIGHT] or k[pygame.K_d]
        inp.up = k[pygame.K_UP] or k[pygame.K_w]
        inp.down = k[pygame.K_DOWN] or k[pygame.K_s]
        inp.nitro = k[pygame.K_SPACE] or k[pygame.K_LSHIFT] or k[pygame.K_RSHIFT]
        return inp

    def handle_events(self):
        w = self.world
        for e in pygame.event.get():
            if e.type == pygame.QUIT:
                self.running = False
            elif e.type == pygame.KEYDOWN:
                if e.key == pygame.K_ESCAPE:
                    if self.mode == "play":
                        self.mode = "paused"
                    else:
                        self.running = False
                elif e.key == pygame.K_p and self.mode in ("play", "paused"):
                    self.mode = "paused" if self.mode == "play" else "play"
                elif e.key in (pygame.K_RETURN, pygame.K_KP_ENTER):
                    if self.mode == "title" or (w.state == "busted" and w.state_t > 1.0):
                        self.start_run()
                elif e.key == pygame.K_m:
                    self.audio.toggle_mute()
                elif e.key == pygame.K_c:
                    self.renderer.crt = not self.renderer.crt
                elif e.key in (pygame.K_f, pygame.K_F11):
                    pygame.display.toggle_fullscreen()

    # ---- simulation --------------------------------------------------------------------
    def update(self, dt):
        w = self.world
        if self.mode == "paused":
            return
        if self.mode == "title":
            w.pursuit, w.gap, w.free_t, w.countdown = False, 100.0, 99.0, 0.0      # attract mode: no police
            if w.state != "play":
                w.new_run()
            w.step(dt, None, ai=True)
            self.throttle = True
        else:
            inp = None if self.bot else self.read_input()
            w.step(dt, inp, ai=self.bot)
            self.throttle = True if inp is None else bool(inp.up or inp.nitro)
            if w.state == "busted" and self.bot and w.state_t > 1.5:
                w.new_run()
        for ev in w.events:
            if ev in self.audio.fx:
                self.audio.play(ev)
        w.events.clear()
        if w.state == "busted" and int(w.score) > self.hi:
            self.hi = int(w.score)
            self.new_hi = True
            save_hi(self.hi)

    def update_audio(self, dt):
        w = self.world
        active = self.mode == "play" and w.state in ("play", "escaped")
        if self.audio.music_want != w.theme_idx:
            self.audio.set_music(w.theme_idx)
        self.audio.update({
            "speed_pct": w.speed_pct, "throttle": self.throttle, "braking": w.braking, "steer": w.steer,
            "offroad": abs(w.x) > 1.0 and w.speed > 1500, "boosting": w.boosting, "gap": w.gap,
            "pursuit": w.pursuit and w.state == "play", "active": active, "paused": self.mode == "paused",
        }, dt)

    # ---- main loop ---------------------------------------------------------------------
    def frame(self, dt):
        self.t += dt
        self.handle_events()
        self.acc += min(dt, 0.1)
        while self.acc >= STEP:
            self.update(STEP)
            self.acc -= STEP
        self.update_audio(dt)
        ui = {"mode": self.mode, "t": self.t, "hi": self.hi, "new_hi": self.new_hi}
        canvas = self.renderer.draw(self.world, ui)
        sh = int(self.world.shake)
        if sh and self.mode == "play":
            self.present.fill((0, 0, 0))
            self.present.blit(canvas, (self.world.rng.randint(-sh, sh) * S, self.world.rng.randint(-sh, sh) * S))
            canvas = self.present
        self.blit_to_window(canvas)

    def blit_to_window(self, canvas):
        sw, sh_ = self.screen.get_size()
        k = min(sw / W, sh_ / H)
        tw, th = int(W * k), int(H * k)
        ox, oy = (sw - tw) // 2, (sh_ - th) // 2
        if ox or oy:
            self.screen.fill((0, 0, 0))
        dest = self.screen.subsurface((ox, oy, tw, th))
        if (tw, th) == (W, H):
            dest.blit(canvas, (0, 0))
        elif tw % W == 0 and th % H == 0:
            pygame.transform.scale(canvas, (tw, th), dest)          # exact multiple: crisp pixels
        else:
            pygame.transform.smoothscale(canvas, (tw, th), dest)
        pygame.display.flip()

    def run(self):
        while self.running:
            self.frame(self.clock.tick(60) / 1000)
        pygame.quit()

    def screenshot(self, path, frames):
        """Headless helper: autopilot for `frames` ticks, then save the frame."""
        for _ in range(frames):
            self.frame(STEP)
        pygame.image.save(self.renderer.canvas, path)
        pygame.quit()
