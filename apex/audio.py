"""Procedural racing-game audio (numpy synthesis, no audio files):
layered engine with gears, wind, tyre screech, gravel, nitro turbo, police siren, crash/explosion
impacts, pickups and a synthwave soundtrack per theme."""
import numpy as np
import pygame

SR = 44100
ENGINE_F0 = (44, 64, 92, 132, 188, 268, 376)       # multiples of 4 so every layer loops seamlessly in 0.5 s
CH_WIND, CH_TIRE, CH_GRAVEL, CH_TURBO, CH_SIREN, CH_MUSIC = 7, 8, 9, 10, 11, 12
RESERVED = 13


# ---- synthesis helpers --------------------------------------------------------------------
CHANNELS = 1   # set from the real mixer format in Audio.__init__


def snd(x, peak=0.95):
    x = np.asarray(x, dtype=np.float64)
    m = np.max(np.abs(x)) or 1.0
    pcm = (x / m * peak * 32767).astype(np.int16)
    if CHANNELS == 2:
        pcm = np.repeat(pcm, 2)          # interleaved L/R
    return pygame.mixer.Sound(buffer=pcm.tobytes())


def tvec(n):
    return np.arange(n) / SR


def noise(n, lo=0.0, hi=0.0, seed=1):
    """Band-limited noise. Shaped in the frequency domain, so it loops seamlessly."""
    rng = np.random.default_rng(seed)
    spec = np.fft.rfft(rng.standard_normal(n))
    f = np.fft.rfftfreq(n, 1 / SR)
    resp = np.ones_like(f)
    if lo:
        resp /= np.sqrt(1 + (lo / np.maximum(f, 1.0)) ** 4)
    if hi:
        resp /= np.sqrt(1 + (f / hi) ** 4)
    x = np.fft.irfft(spec * resp, n)
    return x / (np.max(np.abs(x)) or 1.0)


def whoosh(secs, f0, f1, seed=3, width=0.5):
    """Noise whose band sweeps f0 -> f1 (a pass-by / nitro rush)."""
    n = int(SR * secs)
    win = 2048
    hop = win // 2
    base = noise(n + 2 * win, 0, 0, seed)
    out = np.zeros(n + 2 * win)
    f = np.fft.rfftfreq(win, 1 / SR)
    hann = np.hanning(win)
    for i in range(0, n, hop):
        fc = f0 * (f1 / f0) ** (i / n)
        resp = np.exp(-(np.log(np.maximum(f, 1.0) / fc) ** 2) / (2 * width ** 2))
        out[i:i + win] += np.fft.irfft(np.fft.rfft(base[i:i + win] * hann) * resp, win)
    out = out[:n]
    return out * np.sin(np.pi * np.linspace(0, 1, n)) ** 1.4


def engine_loop(f0, seed):
    n = SR // 2
    k = tvec(n)
    rng = np.random.default_rng(seed)
    x = np.zeros(n)
    for h in range(1, 30):
        fh = f0 * h
        if fh > 9000:
            break
        amp = h ** -1.0 * (1 + 1.6 * np.exp(-((fh - 420) / 280) ** 2) + 1.0 * np.exp(-((fh - 1500) / 600) ** 2))
        x += amp * np.sin(2 * np.pi * fh * k + rng.uniform(0, 2 * np.pi))
    x *= 1 + 0.2 * np.sin(2 * np.pi * (f0 / 2) * k)          # uneven firing, gives the burble
    x /= np.max(np.abs(x))
    x += 0.12 * noise(n, 90, 2200, seed + 50)                 # intake hiss
    return np.tanh(2.0 * x)


def siren_wail(T=3.0):
    n = int(SR * T)
    t = tvec(n)
    f = 640 + 430 * (0.5 - 0.5 * np.cos(2 * np.pi * t / T))
    ph = 2 * np.pi * np.cumsum(f) / SR
    ph += (np.round(ph[-1] / (2 * np.pi)) * 2 * np.pi - ph[-1]) * (t / T)   # close the loop on a whole cycle
    return np.tanh(2.4 * np.sin(ph)) + 0.35 * np.sin(2 * ph + 0.5)


def explosion():
    n = int(SR * 1.8)
    t = tvec(n)
    boom = noise(n, 0, 1100, 11) * np.exp(-t * 2.6)
    sub = np.sin(2 * np.pi * (28 * t + 70 * (1 - np.exp(-5 * t)) / 5)) * np.exp(-t * 1.8)
    crackle = noise(n, 700, 6000, 12) * np.exp(-t * 6) * 0.55
    rubble = noise(n, 200, 2500, 13) * np.exp(-((t - 0.45) / 0.35) ** 2) * 0.35
    attack = np.minimum(1, t * 400)
    return (1.0 * boom + 1.1 * sub + crackle + rubble) * attack


def crunch():
    n = int(SR * 0.8)
    t = tvec(n)
    thump = np.sin(2 * np.pi * (45 + 100 * np.exp(-t * 20)) * t) * np.exp(-t * 9)
    body = noise(n, 0, 3500, 21) * np.exp(-t * 13)
    metal = sum(np.sin(2 * np.pi * f * t) for f in (720, 1110, 1630, 2290)) * np.exp(-t * 16) * 0.16
    rng = np.random.default_rng(5)
    glass = noise(n, 4500, 0, 22) * np.exp(-t * 8) * (rng.random(n // 220 + 1).repeat(220)[:n] > 0.55) * 0.5
    return (1.2 * thump + body + metal + glass) * np.minimum(1, t * 600)


def chime():
    n = int(SR * 1.0)
    t = tvec(n)
    x = np.zeros(n)
    for f, d in ((880, 0.0), (1320, 0.07), (1760, 0.14), (2640, 0.21)):
        env = np.exp(-np.maximum(t - d, 0) * 6.5) * (t >= d)
        x += (np.sin(2 * np.pi * f * t) + 0.3 * np.sin(4 * np.pi * f * t)) * env
    return x + 0.25 * noise(n, 6000, 0, 31) * np.exp(-t * 9)


def fanfare():
    n = int(SR * 1.8)
    t = tvec(n)
    x = np.zeros(n)
    for f, d in ((523.25, 0.0), (659.25, 0.12), (783.99, 0.24), (1046.5, 0.36), (1318.5, 0.5)):
        env = np.exp(-np.maximum(t - d, 0) * 2.4) * (t >= d) * np.minimum(1, (t - d) * 60 + (t < d))
        x += (np.sin(2 * np.pi * f * t) + 0.4 * np.sin(4 * np.pi * f * t) + 0.2 * np.sign(np.sin(2 * np.pi * f * t))) * env
    return x


def busted():
    n = int(SR * 1.8)
    t = tvec(n)
    f = 950 * np.exp(-t * 1.1) + 120
    siren = np.tanh(2 * np.sin(2 * np.pi * np.cumsum(f) / SR)) * np.exp(-t * 1.0)
    thud = np.sin(2 * np.pi * (60 * t + 40 * (1 - np.exp(-8 * t)) / 8)) * np.exp(-t * 4) * 1.4
    return siren * 0.7 + thud + noise(n, 0, 900, 41) * np.exp(-t * 5) * 0.4


def nitro_blast():
    n = int(SR * 1.0)
    t = tvec(n)
    hiss = noise(n, 2500, 9000, 51) * (1 - np.exp(-t * 60)) * np.exp(-t * 3.2)
    low = np.sin(2 * np.pi * (50 + 120 * t) * t) * np.exp(-t * 6) * 0.6
    return 0.8 * hiss + 0.9 * whoosh(1.0, 300, 3600, 52, 0.7) + low


def alert():
    n = int(SR * 0.9)
    t = tvec(n)
    x = np.zeros(n)
    for d in (0.0, 0.16, 0.45):
        x += np.sign(np.sin(2 * np.pi * 1250 * t)) * ((t >= d) & (t < d + 0.1)) * 0.5
    x += 0.04 * noise(n, 800, 3500, 61)
    return x


def start_beep(freq=880.0, secs=0.5, decay=7.0):
    n = int(SR * secs)
    t = tvec(n)
    return (np.sin(2 * np.pi * freq * t) + 0.4 * np.sin(4 * np.pi * freq * t)) * np.exp(-t * decay) * np.minimum(1, t * 300)


def shift_pop():
    n = int(SR * 0.14)
    t = tvec(n)
    return noise(n, 200, 4500, 71) * np.exp(-t * 40) + np.sin(2 * np.pi * 85 * t) * np.exp(-t * 30) * 0.7


def midi_hz(m):
    return 440.0 * 2 ** ((m - 69) / 12)


# ---- soundtrack ---------------------------------------------------------------------------
CHORD = {"m": (0, 3, 7), "M": (0, 4, 7), "m7": (0, 3, 7, 10), "M7": (0, 4, 7, 11)}
TRACKS = [   # one per theme: sunset, midnight, dawn, vaporwave
    dict(bpm=118, prog=[(57, "m"), (53, "M"), (48, "M"), (55, "M")]),
    dict(bpm=106, prog=[(50, "m"), (46, "M"), (53, "M"), (48, "M")]),
    dict(bpm=124, prog=[(48, "M"), (55, "M"), (57, "m"), (53, "M")]),
    dict(bpm=100, prog=[(53, "M7"), (52, "m7"), (50, "m7"), (48, "M7")]),
]


def make_track(idx):
    cfg = TRACKS[idx % len(TRACKS)]
    beat = 60.0 / cfg["bpm"]
    spb = int(SR * beat)
    bars = 8
    N = spb * 4 * bars
    tail = int(SR * 1.5)
    prog = cfg["prog"]
    rng = np.random.default_rng(idx + 7)

    def buf():
        return np.zeros(N + tail)

    def put(dst, i, x):
        x = x[: len(dst) - i]
        dst[i:i + len(x)] += x

    kt = tvec(int(SR * 0.34))
    kick = np.sin(2 * np.pi * np.cumsum(45 + 120 * np.exp(-kt * 30)) / SR) * np.exp(-kt * 9) + 0.25 * noise(len(kt), 0, 5000, 81) * np.exp(-kt * 90)
    st = tvec(int(SR * 0.26))
    snare = noise(len(st), 900, 7500, 82) * np.exp(-st * 17) * 0.8 + np.sin(2 * np.pi * 185 * st) * np.exp(-st * 24) * 0.5
    hat = noise(int(SR * 0.07), 6500, 0, 83) * np.exp(-tvec(int(SR * 0.07)) * 70) * 0.45
    ohat = noise(int(SR * 0.3), 6000, 0, 84) * np.exp(-tvec(int(SR * 0.3)) * 13) * 0.4

    drums, bass, pad, arp = buf(), buf(), buf(), buf()
    for b in range(bars * 4):
        i = b * spb
        put(drums, i, kick)
        if b % 2 == 1:
            put(drums, i, snare)
        put(drums, i + spb // 2, ohat if b % 4 == 3 else hat)
        if b % 4 == 1:
            put(drums, i + int(spb * 0.75), hat * 0.6)

    # bass: pumping eighths
    pattern = (0, 0, 12, 0, 0, 12, 0, 7)
    bl = int(spb / 2 * 0.95)
    bt = tvec(bl)
    for e in range(bars * 8):
        root = prog[(e // 16) % 4][0] - 24 + pattern[e % 8]
        f = midi_hz(root)
        w = sum(np.sin(2 * np.pi * h * f * bt) / h for h in range(1, 9))
        put(bass, e * (spb // 2), w * np.exp(-bt * 7) * np.minimum(1, bt * 400))

    # pads: detuned saw-ish chords, slow attack
    for c in range(bars // 2):
        root, q = prog[c % 4]
        length = spb * 8
        t = tvec(length + int(SR * 0.6))
        env = np.minimum(1, t / 0.5) * np.minimum(1, (length / SR + 0.5 - t) / 0.5).clip(0)
        for semi in CHORD[q] + (12,):
            for det in (0.996, 1.004):
                f = midi_hz(root + semi) * det
                pad_note = sum(np.sin(2 * np.pi * h * f * t + rng.uniform(0, 6.28)) / h for h in range(1, 7))
                put(pad, c * length, pad_note * env * 0.18)

    # arpeggio: 16th-note plucks, then a ping-pong echo
    arp_pat = (0, 1, 2, 3, 2, 1, 2, 3)
    al = int(SR * 0.2)
    at = tvec(al)
    for s in range(bars * 16):
        root, q = prog[(s // 32) % 4]
        tones = CHORD[q] + (12,)
        semi = tones[arp_pat[s % 8] % len(tones)] + (12 if (s // 8) % 2 else 0)
        f = midi_hz(root + 12 + semi)
        w = sum(np.sin(2 * np.pi * h * f * at) / h for h in (1, 3, 5, 7, 9))
        put(arp, s * (spb // 4), w * np.exp(-at * 14) * np.minimum(1, at * 500) * (0.75 + 0.25 * (s % 4 == 0)))

    for part in (drums, bass, pad, arp):
        part[:tail] += part[N:]
    drums, bass, pad, arp = (p[:N] for p in (drums, bass, pad, arp))
    arp = arp + 0.42 * np.roll(arp, int(spb * 0.75)) + 0.2 * np.roll(arp, int(spb * 1.5))
    duck = 1 - 0.55 * np.exp(-8 * (np.arange(N) % spb) / SR)      # sidechain pump on every kick
    mix = drums * 0.85 + bass * 0.8 * duck + pad * 0.5 * duck + arp * 0.42 * (0.6 + 0.4 * duck)
    mix = np.tanh(1.25 * mix / (np.max(np.abs(mix)) or 1))
    return mix


# ---- the audio engine ---------------------------------------------------------------------
def clamp(v, lo=0.0, hi=1.0):
    return max(lo, min(hi, v))


class Audio:
    def __init__(self, mute=False, progress=None):
        self.ok = False
        self.muted = mute
        global CHANNELS
        try:
            pygame.mixer.quit()          # pygame.init() already opened a default stereo mixer
            pygame.mixer.init(frequency=SR, size=-16, channels=1, buffer=512, allowedchanges=0)
            pygame.mixer.set_num_channels(24)
            pygame.mixer.set_reserved(RESERVED)
        except pygame.error:
            return
        fmt = pygame.mixer.get_init()
        if not fmt or fmt[1] != -16:
            return
        CHANNELS = fmt[2]
        self.ok = True
        self.fx = {
            "hit": snd(crunch()), "crash": snd(explosion()), "near": snd(whoosh(0.55, 3600, 500, 4), 0.7),
            "pickup": snd(chime(), 0.8), "escape": snd(fanfare(), 0.85), "busted": snd(busted()),
            "nitro": snd(nitro_blast(), 0.9), "alert": snd(alert(), 0.7), "start": snd(start_beep(), 0.7), "beep": snd(start_beep(660, 0.35, 9), 0.8),
            "go": snd(start_beep(1320, 0.9, 3.5), 0.9),
            "shift": snd(shift_pop(), 0.5),
        }
        if progress:
            progress(0.15)
        self.engine = [snd(engine_loop(f, i), 0.9) for i, f in enumerate(ENGINE_F0)]
        if progress:
            progress(0.25)
        self.engine_ch = [pygame.mixer.Channel(i) for i in range(len(self.engine))]
        loops = {
            CH_WIND: snd(noise(SR * 2, 150, 3200, 91), 0.8),
            CH_TIRE: self._screech(),
            CH_GRAVEL: self._gravel(),
            CH_TURBO: self._turbo(),
            CH_SIREN: snd(siren_wail(), 0.8),
        }
        self.loop_ch = {}
        for ch_id, sound in loops.items():
            ch = pygame.mixer.Channel(ch_id)
            ch.play(sound, loops=-1)
            ch.set_volume(0)
            self.loop_ch[ch_id] = ch
        for ch, s in zip(self.engine_ch, self.engine):
            ch.play(s, loops=-1)
            ch.set_volume(0)
        self.music_ch = pygame.mixer.Channel(CH_MUSIC)
        self.music = {}
        self.music_want = None
        self.music_now = None
        self.vol = {}
        self.rpm, self.gear, self.throttle = 0.2, 0, 0.0
        for i in range(len(TRACKS)):                       # all four soundtracks are ready before the game starts
            self.music[i] = snd(make_track(i), 0.9)
            if progress:
                progress(0.25 + 0.75 * (i + 1) / len(TRACKS))

    # -- loop sounds
    @staticmethod
    def _screech():
        n = SR
        t = tvec(n)
        tone = np.sin(2 * np.pi * 2160 * t) * (1 + 0.35 * np.sin(2 * np.pi * 5 * t)) + 0.5 * np.sin(2 * np.pi * 3240 * t)
        return snd(0.55 * noise(n, 1500, 4200, 101) + 0.45 * tone / 1.5, 0.8)

    @staticmethod
    def _gravel():
        n = SR
        rng = np.random.default_rng(9)
        clicks = (rng.random(n) > 0.9985) * rng.uniform(0.4, 1.0, n)
        return snd(0.8 * noise(n, 60, 650, 111) + 0.9 * noise(n, 600, 3500, 112) * (np.convolve(clicks, np.hanning(40), "same") * 3 + 0.15), 0.8)

    @staticmethod
    def _turbo():
        n = SR
        t = tvec(n)
        whine = np.sin(2 * np.pi * 1900 * t + 3 * np.sin(2 * np.pi * 6 * t)) + 0.4 * np.sin(2 * np.pi * 3800 * t)
        return snd(0.5 * whine / 1.4 + 0.6 * noise(n, 2500, 7000, 121) + 0.5 * noise(n, 0, 400, 122), 0.8)

    # -- public API
    def play(self, name, vol=1.0):
        if self.ok and not self.muted and name in self.fx:
            s = self.fx[name]
            s.set_volume(clamp(vol))
            s.play()

    def set_music(self, idx):
        if self.ok:
            self.music_want = idx

    def toggle_mute(self):
        self.muted = not self.muted

    def _v(self, key, target, dt, rate=10.0):
        cur = self.vol.get(key, 0.0)
        cur += (target - cur) * min(1.0, rate * dt)
        self.vol[key] = cur
        return cur

    def update(self, s, dt):
        """s: speed_pct, throttle(0/1), braking, steer, offroad, boosting, gap, pursuit, active, paused."""
        if not self.ok:
            return
        m = 0.0 if self.muted else 1.0
        active = s["active"]
        sp = s["speed_pct"]
        # --- engine: gears + rpm, crossfaded between pitch layers
        bounds = (0.14, 0.28, 0.45, 0.64, 0.85, 9.0)
        g = next(i for i, b in enumerate(bounds) if sp <= b)
        lo = bounds[g - 1] if g else 0.0
        hi = min(bounds[g], 1.5)
        target = 0.2 + 0.8 * clamp((sp - lo) / (hi - lo))
        if g > self.gear and s["throttle"] and active:
            self.play("shift", 0.35)
        self.gear = g
        self.rpm += (target - self.rpm) * min(1.0, (14 if target > self.rpm else 5) * dt)
        thr = self._v("thr", 1.0 if s["throttle"] else 0.0, dt, 6)
        pos = clamp(self.rpm) * (len(self.engine_ch) - 1)
        base = (0.42 + 0.4 * thr) * m * (1.0 if active else 0.0)
        for i, ch in enumerate(self.engine_ch):
            ch.set_volume(max(0.0, 1 - abs(pos - i)) * base)
        # --- ambience
        gain = m * (1.0 if active else 0.0)
        self.loop_ch[CH_WIND].set_volume(self._v("wind", clamp(sp, 0, 1.4) ** 2 * 0.42, dt) * gain)
        lateral = abs(s["steer"]) * sp
        screech = clamp((lateral - 0.5) / 0.4) if sp > 0.4 else 0.0
        if s["braking"] and sp > 0.5:
            screech = max(screech, 0.55)
        self.loop_ch[CH_TIRE].set_volume(self._v("tire", screech * 0.5, dt, 14) * gain)
        self.loop_ch[CH_GRAVEL].set_volume(self._v("gravel", (0.55 * clamp(sp * 1.4)) if s["offroad"] else 0.0, dt, 12) * gain)
        self.loop_ch[CH_TURBO].set_volume(self._v("turbo", 0.5 if s["boosting"] else 0.0, dt, 9) * gain)
        siren = clamp((75 - s["gap"]) / 55) * 0.34 if s["pursuit"] else 0.0
        self.loop_ch[CH_SIREN].set_volume(self._v("siren", siren, dt, 3) * gain)
        # --- music
        want = self.music_want
        if want in self.music and self.music_now != want:
            self.music_ch.play(self.music[want], loops=-1, fade_ms=900)
            self.music_now = want
        base_music = 0.34 if active else 0.42
        self.music_ch.set_volume(self._v("music", base_music * (0.4 if s["paused"] else 1.0), dt, 4) * m)
