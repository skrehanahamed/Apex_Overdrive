"""Game simulation: pseudo-3D driving physics, traffic AI, police pursuit and pickups."""
import math
import random

from .assets import SOLID, Assets
from .track import SEG_LEN, THEMES, build_track, dress

W, H = 960, 540
S = W // 320          # pixel-scale vs. the original 320x180 tuning of effects
HORIZON = int(H * 0.46)
ROAD_W = 1400.0
CAM_H = 900.0
CAM_DEPTH = 1 / math.tan(math.radians(50))
PLAYER_Z = CAM_H * CAM_DEPTH
DRAW = 110

MAX_SPEED = SEG_LEN * 60
NITRO_SPEED = MAX_SPEED * 1.4
ACCEL = MAX_SPEED / 4.5
BRAKE = -MAX_SPEED * 0.9
DECEL = -MAX_SPEED / 5
OFFROAD_DECEL = -MAX_SPEED / 2
OFFROAD_LIMIT = MAX_SPEED / 4
COUNTDOWN = 3.0
FIRST_FREE = 14.0      # seconds of free driving before the police show up on a new run
NEXT_FREE = 7.0       # ... and after escaping to the next heat level
START_GAP = 55.0      # how far behind you the police are when they join
LANES = (-0.667, 0.0, 0.667)
PLAYER_W = 0.30
M_PER_UNIT = 0.0051
KMH = 225.0

TRAFFIC = ("sedan", "sedan", "sports", "van", "truck", "taxi", "suv")
TRAFFIC_SPEED = {"sedan": (0.30, 0.62), "sports": (0.5, 0.78), "van": (0.28, 0.5), "truck": (0.2, 0.4),
                 "taxi": (0.3, 0.55), "suv": (0.3, 0.6)}


def overlap(x1, w1, x2, w2, pct=1.0):
    return abs(x1 - x2) < (w1 + w2) / 2 * pct


class Input:
    up = down = left = right = nitro = False


class Car:
    __slots__ = ("z", "offset", "speed", "name", "ww", "kind", "seg", "rel", "hit", "life")

    def __init__(self, z, offset, speed, name, ww, kind="traffic", life=0.0):
        self.z, self.offset, self.speed, self.name, self.ww, self.kind = z, offset, speed, name, ww, kind
        self.seg = None
        self.rel = 1.0
        self.hit = False
        self.life = life


class World:
    def __init__(self, seed=None):
        self.rng = random.Random(seed)
        self.segs = build_track()
        self.n = len(self.segs)
        self.length = self.n * SEG_LEN
        self.cars = []
        self.particles = []   # [x, y, vx, vy, life, max_life, color, size]
        self.floaters = []    # [text, color, age]
        self.sky_off = 0.0
        self.time = 0.0
        self.events = []      # one-shot strings for the audio/UI layer
        self.new_run()

    # ---- setup -------------------------------------------------------------------------
    def new_run(self):
        self.heat = 1
        self.score = 0
        self.dist = 0.0
        self.hi_run = 0
        self.start_level(first=True)

    def start_level(self, first=False):
        self.theme_idx = (self.heat - 1) % len(THEMES)
        dress(self.segs, self.theme_idx, self.rng)
        if first:                            # a fresh run starts on the grid; later levels carry straight on
            self.position = 0.0
            self.x = 0.0
            self.speed = 0.0
        self.steer = 0.0
        self.nitro = 45.0 if first else min(100.0, self.nitro + 30)
        self.pursuit = False                 # police are not on you yet
        self.free_t = FIRST_FREE if first else NEXT_FREE
        self.gap = 100.0
        self.combo = 0
        self.combo_t = 0.0
        self.invul = 0.0
        self.shake = 0.0
        self.flash = 0.0
        self.state = "play"
        self.state_t = 0.0
        self.boosting = False
        self.braking = False
        self.booms = []                      # [x, y, scale, age] fireballs in screen space
        self.recenter = 0.0
        self.was_boost = False
        self.countdown = COUNTDOWN if first else 0.0     # 3-2-1-GO on a fresh run
        self.cd_last = None
        self.go_t = 0.0
        self.director_t = 7.0                # first scripted road event, seconds after GO
        self.event_i = 0
        self.near_count = 0
        self.spawn_traffic()

    def spawn_traffic(self):
        for s in self.segs:
            s.cars = []
        self.cars = []
        count = min(60 + 8 * self.heat, 130)
        for _ in range(count):
            name = self.rng.choice(TRAFFIC)
            lo, hi = TRAFFIC_SPEED[name]
            z = (self.position + self.rng.uniform(45, self.n - 35) * SEG_LEN) % self.length
            self.add_car(Car(z, self.rng.choice(LANES) + self.rng.uniform(-0.08, 0.08),
                             MAX_SPEED * self.rng.uniform(lo, hi), "traffic_" + name,
                             Assets.world_w("traffic_" + name)))

    def add_car(self, car):
        car.seg = self.find(car.z)
        car.seg.cars.append(car)
        self.cars.append(car)

    def remove_car(self, car):
        if car.seg and car in car.seg.cars:
            car.seg.cars.remove(car)
        if car in self.cars:
            self.cars.remove(car)

    def find(self, z):
        return self.segs[int(z // SEG_LEN) % self.n]

    def rel(self, z):
        """Signed distance of world z ahead of the player's contact point (wrap-aware)."""
        return (z - (self.position + PLAYER_Z) + self.length / 2) % self.length - self.length / 2

    # ---- helpers -----------------------------------------------------------------------
    @property
    def speed_pct(self):
        return self.speed / MAX_SPEED

    @property
    def kmh(self):
        return int(self.speed / MAX_SPEED * KMH)

    @property
    def police_speed(self):
        return MAX_SPEED * min(0.80 + 0.05 * self.heat, 1.12)   # from heat 7 on, plain full throttle loses ground

    def floater(self, text, color=(255, 255, 255)):
        key = text.split(" x")[0]
        if self.floaters and self.floaters[-1][0].split(" x")[0] == key and self.floaters[-1][2] < 1.2:
            self.floaters[-1][:] = [text, color, 0.0]        # repeated message: update in place
            return
        self.floaters.append([text, color, 0.0])
        del self.floaters[:-3]

    def burst(self, x, y, n, colors, speed=60, life=0.5, size=1):
        for _ in range(n):
            a = self.rng.uniform(0, math.tau)
            v = self.rng.uniform(0.3, 1.0) * speed
            self.particles.append([x, y, math.cos(a) * v, math.sin(a) * v - 20, life * self.rng.uniform(0.6, 1.0),
                                   life, self.rng.choice(colors), size])

    def other_x(self, offset):
        """Screen x where a car at road offset `offset` is when it meets the player."""
        return max(W * 0.12, min(W * 0.88, W / 2 + (offset - self.x) * ROAD_W * (W / 2) / CAM_H))

    def wreck(self, gap_loss, shake, speed_keep, boom=0.0, others=()):
        """Any crash: lose ground on the police, shake, slow down, blast (you AND what you hit), and get
        put back in the middle of the road."""
        self.gap -= gap_loss
        self.shake = max(self.shake, shake)
        self.speed *= speed_keep
        self.combo = 0
        if boom:
            self.booms.append([W / 2, H * 0.80, boom, 0.0])
            for ox in others:
                self.booms.append([ox, H * 0.64, boom * 0.9, 0.06])
            self.events.append("crash")
        self.burst(W / 2, H * 0.84, 26, [(255, 240, 120), (255, 160, 40), (255, 255, 255)], 110 * S, 0.5, S)
        self.events.append("hit")
        if not self.pursuit:
            self.free_t = min(self.free_t, 2.0)        # the noise brings the police
        self.recover()

    def recover(self):
        """Back to the middle of the road, with traffic just ahead cleared so you don't crash again."""
        self.recenter = 1.5
        self.steer = 0.0
        self.invul = 2.4
        for car in list(self.cars):
            if car.kind in ("traffic", "block", "cone") and 0 < self.rel(car.z) < SEG_LEN * 30 and abs(car.offset) < 0.8:
                self.remove_car(car)

    # ---- per-frame update --------------------------------------------------------------
    def step(self, dt, inp, ai=False):
        self.time += dt
        if self.countdown > 0 and self.state == "play":
            self.countdown -= dt
            self.speed = 0.0
            self.steer = 0.0
            n = math.ceil(max(self.countdown, 0.0))
            if n != self.cd_last:
                self.cd_last = n
                self.events.append("beep" if n > 0 else "go")
            if self.countdown <= 0:
                self.countdown, self.go_t = 0.0, 0.9
            self.tick_fx(dt)
            return
        if self.state in ("busted", "title_idle"):
            self.speed = max(0.0, self.speed - MAX_SPEED * 0.9 * dt)
            self.advance(dt)
            self.tick_fx(dt)
            self.state_t += dt
            return
        if ai:
            inp = self.autopilot()
        pseg = self.find(self.position + PLAYER_Z)
        pct = self.speed_pct

        # throttle / brake / nitro
        self.boosting = bool(inp.nitro and self.nitro > 0 and self.speed > MAX_SPEED * 0.3)
        if self.boosting and not self.was_boost:
            self.events.append("nitro")
        self.was_boost = self.boosting
        self.braking = bool(inp.down and self.speed > MAX_SPEED * 0.05) or self.invul > 0.5
        if self.boosting:
            self.speed += ACCEL * 2.4 * dt
            self.nitro = max(0.0, self.nitro - 22 * dt)
            if self.rng.random() < 0.5:
                self.burst(W / 2 + self.rng.uniform(-30, 30) * S, H * 0.93, 2, [(80, 200, 255), (255, 200, 80), (255, 255, 255)], 60 * S, 0.35, S)
        elif inp.up:
            self.speed += ACCEL * dt
        elif inp.down:
            self.speed += BRAKE * dt
        else:
            self.speed += DECEL * dt
        if not self.boosting and self.speed > MAX_SPEED:
            self.speed = max(MAX_SPEED, self.speed - MAX_SPEED * 0.4 * dt)

        # steering
        target = (inp.right - inp.left) * 1.0
        self.steer += (target - self.steer) * min(1.0, 9 * dt)
        dx = dt * 2.0 * min(pct, 1.2)
        self.x += self.steer * dx * 1.4
        self.x -= dx * pct * pseg.curve * 0.2
        if abs(self.x) > 1 and self.speed > OFFROAD_LIMIT:
            self.speed += OFFROAD_DECEL * dt
            self.shake = max(self.shake, 1.2)
            if self.rng.random() < 0.6:
                self.burst(W / 2 + self.rng.uniform(-60, 60) * S // 2, H * 0.95, 1, [(150, 120, 80), (110, 90, 60)], 50 * S, 0.5, 2 * S)
        if self.recenter > 0:
            self.recenter -= dt
            self.x += (0.0 - self.x) * min(1.0, 3.0 * dt)       # a slow glide, not a snap
            self.steer *= 0.8
        self.x = max(-2.4, min(2.4, self.x))
        self.speed = max(0.0, min(NITRO_SPEED, self.speed))

        self.advance(dt)
        pseg = self.find(self.position + PLAYER_Z)
        self.sky_off = (self.sky_off + pseg.curve * pct * dt * 60) % 100000

        self.check_collisions(pseg)
        self.update_cars(dt, pseg)
        self.update_pursuit(dt)
        self.spawn_dynamic(dt)
        self.tick_fx(dt)

        # engine / smoke
        if self.speed > 1 and self.rng.random() < 0.25 * (1 + pct):
            self.burst(W / 2 + self.rng.choice((-1, 1)) * 26 * S, H * 0.96, 1, [(90, 90, 110), (60, 60, 80)], 14 * S, 0.5, S)

    def advance(self, dt):
        self.position = (self.position + dt * self.speed) % self.length
        self.dist += dt * self.speed * M_PER_UNIT
        if self.state == "play" or self.state == "escaped":
            self.score += dt * self.speed_pct * 40 * self.heat

    def tick_fx(self, dt):
        self.invul = max(0.0, self.invul - dt)
        self.shake = max(0.0, self.shake - 14 * dt)
        self.flash = max(0.0, self.flash - 2.5 * dt)
        self.go_t = max(0.0, self.go_t - dt)
        for b in self.booms:
            b[3] += dt
        self.booms = [b for b in self.booms if b[3] < 0.95]
        self.combo_t = max(0.0, self.combo_t - dt)
        if self.combo_t == 0:
            self.combo = 0
        for p in self.particles:
            p[0] += p[2] * dt
            p[1] += p[3] * dt
            p[3] += 60 * S * dt
            p[4] -= dt
        self.particles = [p for p in self.particles if p[4] > 0]
        for f in self.floaters:
            f[2] += dt
        self.floaters = [f for f in self.floaters if f[2] < 1.6]

    # ---- collisions --------------------------------------------------------------------
    def check_collisions(self, pseg):
        # roadside obstacles (only reachable when off-road)
        if abs(self.x) > 1.0 and self.invul <= 0:
            for seg in (pseg, self.segs[(pseg.index + 1) % self.n]):
                for name, off in seg.sprites:
                    if name in SOLID:
                        ww = Assets.world_w(name)
                        center = off + (ww / 2 if off > 0 else -ww / 2)
                        if overlap(self.x, PLAYER_W, center, ww * 0.45):
                            self.wreck(16, 9, 0.2, boom=0.9)
                            self.floater("CRASH!", (255, 110, 80))
                            return
        for seg in (pseg, self.segs[(pseg.index + 1) % self.n]):
            for car in list(seg.cars):
                if self.speed <= car.speed:
                    continue
                if car.kind in ("traffic", "block") and self.invul > 0:
                    continue                                   # ghosting through after a crash
                if not overlap(self.x, PLAYER_W, car.offset, car.ww, 0.8):
                    continue
                if car.kind == "pickup":
                    self.nitro = min(100.0, self.nitro + 35)
                    self.score += 50
                    self.floater("NITRO +35", (90, 200, 255))
                    self.events.append("pickup")
                    self.remove_car(car)
                elif car.kind == "cone":
                    self.speed *= 0.82
                    self.gap -= 2
                    self.events.append("hit")
                    self.burst(W / 2, H * 0.84, 8, [(255, 120, 30), (255, 255, 255)], 80 * S, 0.4, S)
                    self.remove_car(car)
                elif car.kind == "block":
                    self.wreck(28, 12, 0.25, boom=1.1, others=(self.other_x(car.offset - 0.3), self.other_x(car.offset + 0.3)))
                    self.floater("ROADBLOCK!", (255, 80, 70))
                    self.flash = 0.8
                    self.remove_car(car)
                else:
                    self.remove_car(car)                       # the car you hit is blown away
                    self.wreck(9, 7, 0.45, boom=0.85, others=(self.other_x(car.offset),))
                    self.floater("CRASH!", (255, 190, 80))
                return

    # ---- traffic -----------------------------------------------------------------------
    def update_cars(self, dt, pseg):
        for car in list(self.cars):
            if car.speed:
                car.offset += self.avoid(car, pseg) * dt * 60
                car.offset = max(-0.85, min(0.85, car.offset))
                car.z = (car.z + dt * car.speed) % self.length
                seg = self.find(car.z)
                if seg is not car.seg:
                    car.seg.cars.remove(car)
                    seg.cars.append(car)
                    car.seg = seg
            rel = self.rel(car.z)
            if car.kind in ("traffic", "block") and car.rel > 0 >= rel and not car.hit:
                lat = abs(car.offset - self.x)
                if lat < 0.58 and self.speed > 0.5 * MAX_SPEED and self.invul <= 0 and self.state in ("play", "escaped"):
                    self.near_miss()
            car.rel = rel
            if car.kind in ("cone", "pickup", "block") and rel < -SEG_LEN * 8:
                self.remove_car(car)

    def near_miss(self):
        self.combo = min(self.combo + 1, 8)
        self.combo_t = 3.0
        self.near_count += 1
        self.score += 100 * self.combo * self.heat
        self.nitro = min(100.0, self.nitro + 7)
        self.gap = min(100.0, self.gap + 1.5)
        self.floater("NEAR MISS x%d" % self.combo, (255, 235, 90))
        self.events.append("near")

    def avoid(self, car, pseg):
        base = car.seg.index
        for i in range(1, 21):
            seg = self.segs[(base + i) % self.n]
            if seg is pseg and car.speed > self.speed and overlap(self.x, PLAYER_W, car.offset, car.ww, 1.2):
                d = -1 if self.x > 0.5 else 1 if self.x < -0.5 else (1 if car.offset > self.x else -1)
                return d / i * (car.speed - self.speed) / MAX_SPEED
            for other in seg.cars:
                if other.kind in ("traffic", "block") and car.speed > other.speed and \
                        overlap(car.offset, car.ww, other.offset, other.ww, 1.2):
                    d = -1 if other.offset > 0.5 else 1 if other.offset < -0.5 else (1 if car.offset > other.offset else -1)
                    return d / i * (car.speed - other.speed) / MAX_SPEED
        return 0.0

    # ---- police pursuit ----------------------------------------------------------------
    def begin_pursuit(self):
        self.pursuit = True
        self.gap = START_GAP
        self.floater("POLICE PURSUIT!", (255, 90, 90))
        self.events.append("alert")

    def update_pursuit(self, dt):
        if self.state == "play":
            if not self.pursuit:
                self.free_t -= dt
                self.gap = 100.0
                if self.free_t <= 0:
                    self.begin_pursuit()
                return
            self.gap += (self.speed - self.police_speed) / MAX_SPEED * 11.0 * dt
            self.gap = min(self.gap, 100.0)
            if self.gap <= 0:
                self.gap = 0.0
                self.state, self.state_t = "busted", 0.0
                self.events.append("busted")
            elif self.gap >= 100:
                self.state, self.state_t = "escaped", 0.0
                bonus = 1000 * self.heat
                self.score += bonus
                self.floater("ESCAPED +%d" % bonus, (120, 255, 150))
                self.events.append("escape")
        elif self.state == "escaped":
            self.gap = 100.0
            self.state_t += dt
            self.flash = max(self.flash, (self.state_t - 2.2) / 0.6)     # fade out, swap under the white, fade in
            if self.state_t > 2.8:
                self.heat += 1
                self.flash = 1.0
                self.start_level()
                self.floater("HEAT %d" % self.heat, (255, 120, 90))

    def spawn_dynamic(self, dt):
        """Scripted road events on a steady rhythm instead of random spawns: nitro lines, cone lanes,
        chicanes and (once the police are on you) roadblocks."""
        if self.countdown > 0:
            return
        self.director_t -= dt
        if self.director_t > 0:
            return
        script = ["nitro", "cones", "nitro", "chicane"]
        if self.pursuit:
            script = ["nitro", "roadblock", "cones", "nitro", "chicane", "roadblock"]
            if self.heat >= 3:
                script += ["nitro", "double"]
        kind = script[self.event_i % len(script)]
        self.event_i += 1
        self.director_t = max(6.0, 10.5 - 0.5 * self.heat)
        ahead = self.position + PLAYER_Z + SEG_LEN * (DRAW - 12)
        self.run_event(kind, ahead)

    def run_event(self, kind, ahead):
        rng = self.rng
        add = self.add_car
        side = rng.choice((-1, 1))
        if kind == "nitro":                                  # a line of canisters to thread
            lane = rng.choice(LANES)
            for i in range(5):
                add(Car((ahead + i * SEG_LEN * 3) % self.length, lane, 0.0, "nitro_can", Assets.world_w("nitro_can"), "pickup"))
        elif kind == "cones":                                # a lane closure that tapers in
            lane = rng.choice(LANES)
            for i in range(8):
                add(Car((ahead + i * SEG_LEN * 2) % self.length, lane + (i - 3.5) * 0.04, 0.0,
                        "traffic_cone", Assets.world_w("traffic_cone"), "cone"))
        elif kind == "chicane":                              # alternating cone gates to weave through
            for i in range(5):
                centre = -0.42 if i % 2 == 0 else 0.42
                for dx in (-0.12, 0.0, 0.12):
                    add(Car((ahead + i * SEG_LEN * 6) % self.length, centre + dx, 0.0,
                            "traffic_cone", Assets.world_w("traffic_cone"), "cone"))
        else:                                                # roadblock(s) with one clear side
            self.floater("ROADBLOCK AHEAD", (255, 90, 90))
            self.events.append("alert")
            add(Car(ahead % self.length, side * 0.48, 0.0, "roadblock", Assets.world_w("roadblock"), "block"))
            if kind == "double":
                add(Car((ahead + SEG_LEN * 16) % self.length, -side * 0.48, 0.0, "roadblock", Assets.world_w("roadblock"), "block"))

    # ---- autopilot (title screen + --bot) ----------------------------------------------
    def autopilot(self):
        inp = Input()
        base = self.find(self.position + PLAYER_Z).index
        best, best_lane = -1, 0.0
        clear_now = 40
        for lane in LANES:
            d = 40
            for i in range(1, 40):
                seg = self.segs[(base + i) % self.n]
                if any(abs(c.offset - lane) < c.ww * 0.5 + 0.27 and c.kind in ("traffic", "block", "cone") and c.speed < self.speed + 1
                       for c in seg.cars):
                    d = i
                    break
            bonus = 6 if abs(lane - self.x) < 0.3 else 0
            if d + bonus > best:
                best, best_lane = d + bonus, lane
            if abs(lane - self.x) < 0.35:
                clear_now = d
        inp.up = True
        inp.left = self.x > best_lane + 0.08
        inp.right = self.x < best_lane - 0.08
        inp.nitro = self.nitro > 55 and clear_now > 25 and self.gap < 90
        return inp
