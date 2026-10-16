"""Écran à cristaux liquides du Canon X-07 : 120 x 32 points.

Le texte (20 x 4 caractères de 6 x 8 points) et les graphismes partagent la
même mémoire, comme sur la machine : POINT voit aussi les caractères.
La police est celle du X-07 (ROM_x07/charset.rom : 256 caractères, 8 octets
par caractère, bit 7 à gauche, 6 colonnes utilisées).  Les caractères
redéfinis par un programme (commande UDC WRITE du T6834) la modifient.

Les tracés de LINE et CIRCLE suivent les algorithmes classiques
(Bresenham, point milieu) : ceux du T6834 ne sont pas dans la ROM.
"""
import os
import struct
import zlib

WIDTH, HEIGHT = 120, 32
COLS, ROWS = 20, 4
CW, CH = 6, 8

FONT_PATHS = (os.path.join(os.path.dirname(__file__), "..", "..", "ROM_x07", "charset.rom"),)


def load_font():
    env = os.environ.get("X07_CHARSET")
    for p in ((env,) if env else ()) + FONT_PATHS:
        if p and os.path.exists(p):
            with open(p, "rb") as f:
                data = f.read()
            if len(data) >= 2048:
                return bytearray(data[:2048])
    return bytearray(2048)                     # sans police : caractères vides


class LCD:
    def __init__(self, font=None):
        self.font0 = bytes(font if font is not None else load_font())
        self.font = bytearray(self.font0)
        self.px = bytearray(WIDTH * HEIGHT)     # 1 = point allumé
        self.version = 0                        # change à chaque modification
        self.cursor = None                      # (col, ligne) du curseur affiché, ou None

    # -------------------------------------------------- points
    def _touch(self):
        self.version += 1

    def get(self, x, y):
        return 0 <= x < WIDTH and 0 <= y < HEIGHT and self.px[y * WIDTH + x]

    def set(self, x, y, on=1):
        if 0 <= x < WIDTH and 0 <= y < HEIGHT:
            self.px[y * WIDTH + x] = 1 if on else 0

    def pset(self, x, y):
        self.set(x, y, 1)
        self._touch()

    def preset(self, x, y):
        self.set(x, y, 0)
        self._touch()

    def peor(self, x, y):
        self.set(x, y, not self.get(x, y))
        self._touch()

    def line(self, x0, y0, x1, y1):
        dx, dy = abs(x1 - x0), -abs(y1 - y0)
        sx, sy = (1 if x0 < x1 else -1), (1 if y0 < y1 else -1)
        err = dx + dy
        while True:
            self.set(x0, y0)
            if x0 == x1 and y0 == y1:
                break
            e2 = 2 * err
            if e2 >= dy:
                err += dy
                x0 += sx
            if e2 <= dx:
                err += dx
                y0 += sy
        self._touch()

    def circle(self, cx, cy, r):
        x, y, err = r, 0, 1 - r
        while x >= y:
            for px, py in ((x, y), (y, x), (-y, x), (-x, y), (-x, -y), (-y, -x), (y, -x), (x, -y)):
                self.set(cx + px, cy + py)
            y += 1
            if err < 0:
                err += 2 * y + 1
            else:
                x -= 1
                err += 2 * (y - x) + 1
        self._touch()

    # -------------------------------------------------- texte
    def put_char(self, col, row, code):
        """Dessine le caractère code dans la case (col, row)."""
        if not (0 <= col < COLS and 0 <= row < ROWS):
            return
        g = self.font[code * 8:code * 8 + 8]
        x0, y0 = col * CW, row * CH
        for dy in range(CH):
            b = g[dy]
            base = (y0 + dy) * WIDTH + x0
            for dx in range(CW):
                self.px[base + dx] = 1 if b & (0x80 >> dx) else 0
        self._touch()

    def put_pattern(self, col, row, pattern):
        """Motif de 8 octets à la place d'un caractère (CHAR WRITE)."""
        saved = self.font[0:8]
        self.font[0:8] = bytes(pattern[:8]).ljust(8, b"\0")
        self.put_char(col, row, 0)
        self.font[0:8] = saved

    def clear_row(self, row):
        if 0 <= row < ROWS:
            self.px[row * CH * WIDTH:(row + 1) * CH * WIDTH] = bytes(CH * WIDTH)
            self._touch()

    def scroll(self, first=0, last=ROWS - 1):
        """Fait remonter d'une ligne de texte les lignes first..last."""
        a, b = first * CH * WIDTH, (last + 1) * CH * WIDTH
        self.px[a:b] = self.px[a + CH * WIDTH:b] + bytes(CH * WIDTH)
        self._touch()

    def clear(self):
        self.px = bytearray(WIDTH * HEIGHT)
        self._touch()

    def udc_write(self, code, pattern):
        self.font[code * 8:code * 8 + 8] = bytes(pattern[:8]).ljust(8, b"\0")

    def udc_init(self):
        self.font = bytearray(self.font0)

    # -------------------------------------------------- sorties
    def rows_bits(self, cursor=True):
        """Lignes de points (listes de 0/1), curseur souligné compris."""
        rows = [list(self.px[y * WIDTH:(y + 1) * WIDTH]) for y in range(HEIGHT)]
        if cursor and self.cursor is not None:
            c, r = self.cursor
            if 0 <= c < COLS and 0 <= r < ROWS:
                for dx in range(CW - 1):
                    rows[r * CH + CH - 1][c * CW + dx] = 1
        return rows

    def braille(self, cursor=False):
        """Rendu en caractères braille Unicode (2 x 4 points par caractère) : 60 x 8."""
        rows = self.rows_bits(cursor)
        dots = ((0, 0, 0x01), (0, 1, 0x02), (0, 2, 0x04), (1, 0, 0x08), (1, 1, 0x10),
                (1, 2, 0x20), (0, 3, 0x40), (1, 3, 0x80))
        out = []
        for by in range(0, HEIGHT, 4):
            line = []
            for bx in range(0, WIDTH, 2):
                v = 0
                for dx, dy, bit in dots:
                    if rows[by + dy][bx + dx]:
                        v |= bit
                line.append(chr(0x2800 + v))
            out.append("".join(line))
        return "\n".join(out)

    def png(self, path, zoom=4, border=4, on=(0x1B, 0x2A, 0x1B), off=(0x9A, 0xA9, 0x8C)):
        """Image PNG de l'écran (sans bibliothèque), aspect LCD vert."""
        rows = self.rows_bits(cursor=False)
        w, h = (WIDTH + 2 * border) * zoom, (HEIGHT + 2 * border) * zoom
        raw = bytearray()
        for y in range(h):
            raw.append(0)                               # filtre « aucun »
            py = y // zoom - border
            for x in range(w):
                px = x // zoom - border
                lit = 0 <= px < WIDTH and 0 <= py < HEIGHT and rows[py][px]
                raw += bytes(on if lit else off)

        def chunk(kind, data):
            c = struct.pack(">I", len(data)) + kind + data
            return c + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)

        data = (b"\x89PNG\r\n\x1a\n"
                + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0))
                + chunk(b"IDAT", zlib.compress(bytes(raw), 9))
                + chunk(b"IEND", b""))
        with open(path, "wb") as f:
            f.write(data)
        return path
