"""HUD text: a bold condensed system font with a dark outline (falls back to pygame's built-in font)."""
import pygame

CANDIDATES = ("dinalternate", "dincondensed", "avenirnextcondensed", "bahnschrift", "helveticaneue",
              "arialnarrow", "arial")


class UIFont:
    def __init__(self):
        self.path = None
        for name in CANDIDATES:
            path = pygame.font.match_font(name, bold=True)
            if path:
                self.path = path
                break
        self._fonts = {}
        self._text = {}

    def font(self, size):
        f = self._fonts.get(size)
        if f is None:
            f = self._fonts[size] = pygame.font.Font(self.path, size)
        return f

    def render(self, text, size, color=(255, 255, 255), outline=(8, 6, 24), ow=2):
        key = (text, size, color, outline, ow)
        surf = self._text.get(key)
        if surf is None:
            f = self.font(size)
            base = f.render(text, True, color)
            if ow:
                edge = f.render(text, True, outline)
                w, h = base.get_size()
                surf = pygame.Surface((w + 2 * ow, h + 2 * ow), pygame.SRCALPHA)
                for dx in range(-ow, ow + 1):
                    for dy in range(-ow, ow + 1):
                        if dx * dx + dy * dy <= ow * ow + 1:
                            surf.blit(edge, (ow + dx, ow + dy))
                surf.blit(base, (ow, ow))
            else:
                surf = base
            if len(self._text) > 600:
                self._text.clear()
            self._text[key] = surf
        return surf

    def width(self, text, size):
        return self.font(size).size(text)[0]

    def draw(self, dst, text, x, y, size, color=(255, 255, 255), anchor="l", outline=(8, 6, 24), ow=2):
        s = self.render(text, size, color, outline, ow)
        if anchor == "c":
            x -= s.get_width() // 2
        elif anchor == "r":
            x -= s.get_width()
        dst.blit(s, (x, y))
        return s.get_size()
