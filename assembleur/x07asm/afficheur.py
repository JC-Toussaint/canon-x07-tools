"""Fenêtre affichant l'écran du X-07 en direct (tkinter).

L'émulation tourne dans un fil d'exécution séparé ; la fenêtre redessine
l'écran de 120 x 32 points dès qu'il change et transmet les touches :
  lettres     majuscules par défaut, comme le X-07 (Maj : minuscules)
  Entrée      RETURN
  flèches     déplacent le curseur (éditeur plein écran de la ROM)
  Suppr, Inser, Origine   DEL, INS, HOME
  Échap       BREAK
  F9          interrompt le programme (débogueur)

Le pavé de flèches du X-07 (quatre flèches et un bouton au milieu) est
dessiné à côté de l'écran ; on le manie à la souris ou au clavier :
  flèches du PC, ou pavé numérique verrou éteint : flèches du X-07,
      tenues tant qu'on appuie (STICK) et tapées (éditeur, INKEY$)
  5 du pavé numérique (verrou éteint) : bouton du milieu (STRIG(1))
  barre d'espace : espace tapé, barre d'espace (STRIG(0)) et bouton du milieu
"""
import threading
import time

from .lcd import WIDTH, HEIGHT
from .sim import SimError

ON, OFF = "#1b2a1b", "#9aa98c"            # points allumés / fond, aspect LCD
BEZEL = "#2b2b2e"
# DEL : la ROM change $7F en $16 ($C88A) avant l'éditeur ; on envoie directement $16
KEYMAP = {"Return": "\r", "KP_Enter": "\r", "BackSpace": "\x08", "Left": "\x1d",
          "Right": "\x1c", "Up": "\x1e", "Down": "\x1f", "Delete": "\x16",
          "Insert": "\x12", "Home": "\x0b"}


class Ecran:
    """L'écran du X-07 (120 x 32 points) dans un widget tkinter, avec le
    curseur clignotant ; sert à la fenêtre de l'émulateur et à l'éditeur."""

    def __init__(self, parent, zoom=5):
        import tkinter as tk
        self.tk = tk
        self.zoom = zoom
        self.pad = 4 * zoom
        self.canvas = tk.Canvas(parent, width=WIDTH * zoom + 2 * self.pad,
                                height=HEIGHT * zoom + 2 * self.pad, bg=OFF,
                                highlightthickness=3, highlightbackground="#111",
                                highlightcolor="#2c9a3c")   # vert : l'écran a le clavier
        self.img_item = None
        self._img = None
        self._last = None
        self._blink = True
        self._blink_t = 0

    def refresh(self, lcd):
        """Redessine si l'écran (ou le clignotement du curseur) a changé."""
        now = time.time()
        if now - self._blink_t > 0.4:
            self._blink, self._blink_t = not self._blink, now
        key = (lcd.version, lcd.cursor is not None and self._blink)
        if key != self._last:
            self._last = key
            self.draw(lcd.rows_bits(cursor=lcd.cursor is not None and self._blink))

    def draw(self, rows):
        tk = self.tk
        img = tk.PhotoImage(width=WIDTH, height=HEIGHT)
        img.put(" ".join("{" + " ".join(ON if b else OFF for b in r) + "}" for r in rows))
        img = img.zoom(self.zoom, self.zoom)
        if self.img_item is None:
            self.img_item = self.canvas.create_image(self.pad, self.pad, image=img, anchor="nw")
        else:
            self.canvas.itemconfigure(self.img_item, image=img)
        self._img = img                         # garder une référence


# touches tenues : nom pour STICK / STRIG (sim.X07.held), caractère tapé
HELD_KEYS = {"Up": (("haut",), "\x1e"), "KP_Up": (("haut",), "\x1e"),
             "Down": (("bas",), "\x1f"), "KP_Down": (("bas",), "\x1f"),
             "Left": (("gauche",), "\x1d"), "KP_Left": (("gauche",), "\x1d"),
             "Right": (("droite",), "\x1c"), "KP_Right": (("droite",), "\x1c"),
             "KP_Begin": (("milieu",), None),
             "space": (("espace", "milieu"), " ")}
ARROWS = {"haut": "\x1e", "bas": "\x1f", "gauche": "\x1d", "droite": "\x1c"}
RELEASE_DELAY = 80        # ms : la répétition automatique envoie appui et relâchement


class Touches:
    """Touches tenues du pavé de flèches (souris ou clavier), pour STICK et
    STRIG.  Un relâchement n'est pris en compte qu'après un court délai sans
    nouvel appui : la répétition automatique du système ne fait pas clignoter
    la direction."""

    def __init__(self, widget, get_machine):
        self.widget, self.get_m = widget, get_machine
        self.pending = {}
        self.on_change = None

    def press(self, names, char=None):
        m = self.get_m()
        if m is None:
            return
        for n in names:
            self.pending.pop(n, None)
            m.held.add(n)
        if char:
            m.keys.append(char)
        self.changed()

    def release(self, names):
        for n in names:
            token = object()
            self.pending[n] = token
            self.widget.after(RELEASE_DELAY, lambda n=n, t=token: self._release(n, t))

    def _release(self, name, token):
        if self.pending.get(name) is not token:
            return                                # appuyée de nouveau entre-temps
        del self.pending[name]
        m = self.get_m()
        if m is not None:
            m.held.discard(name)
        self.changed()

    def changed(self):
        if self.on_change:
            self.on_change()


def release_key(ev, touches):
    if touches is not None and ev.keysym in HELD_KEYS:
        touches.release(HELD_KEYS[ev.keysym][0])


def send_key(m, ev, touches=None):
    """Touche du PC -> X-07 (m.keys) ; Échap : BREAK ; F9 : arrêt (débogueur) ;
    flèches et barre d'espace : aussi tenues pour STICK / STRIG (touches)."""
    if touches is not None and ev.keysym in HELD_KEYS:
        names, char = HELD_KEYS[ev.keysym]
        touches.press(names, char)
        return
    if ev.keysym == "F9":
        m.debug_pause = True
        return
    if ev.keysym == "Escape":
        if m.lcd.cursor is not None:            # en saisie : BREAK de la saisie
            m.keys.append("\x1b")
        else:                                   # programme en cours : touche BREAK
            m.mem[0x2B] |= 0x01
        return
    k = KEYMAP.get(ev.keysym)
    if k is None and ev.char and len(ev.char) == 1 and ord(ev.char) < 256:
        k = ev.char.swapcase() if ev.char.isalpha() else ev.char
    if k:
        m.keys.append(k)


class Pave:
    """Le pavé de flèches du X-07 : quatre flèches et un bouton au milieu,
    actifs à la souris (tenus tant que le bouton est enfoncé)."""

    KEY, KEY_DOWN, EDGE, MARK = "#d8d8d4", "#8f8f8a", "#55554f", "#2b2b2e"
    TIPS = {"haut": "flèche haut (STICK 1)", "bas": "flèche bas (STICK 5)",
            "gauche": "flèche gauche (STICK 7)", "droite": "flèche droite (STICK 3)",
            "milieu": "bouton du milieu (STRIG(1))"}

    def __init__(self, parent, touches, size=120, bg=BEZEL):
        import tkinter as tk
        self.touches = touches
        touches.on_change = self.redraw
        self.canvas = tk.Canvas(parent, width=size, height=size, bg=bg,
                                highlightthickness=0)
        # comme sur la machine : quatre touches trapézoïdales autour d'un bouton carré
        lo, hi, gap = 3, size - 3, max(2, size // 30)
        inner = size * 0.32                                  # côté du bouton du milieu
        p, q = (size - inner) / 2, (size + inner) / 2
        self.items = {}
        c = self.canvas
        place = {"haut": lambda x, y: (x, y), "bas": lambda x, y: (x, size - y),
                 "gauche": lambda x, y: (y, x), "droite": lambda x, y: (size - y, x)}
        trap = ((lo + gap, lo), (hi - gap, lo), (q, p - gap), (p, p - gap))   # celle du haut
        cx, cy, r = size / 2, (lo + p - gap) / 2, size / 14
        tri = ((cx, cy - r), (cx - r, cy + 0.7 * r), (cx + r, cy + 0.7 * r))
        for name, f in place.items():
            key = c.create_polygon(*[f(x, y) for x, y in trap], fill=self.KEY,
                                   outline=self.EDGE, width=2, tags=(name,))
            c.create_polygon(*[f(x, y) for x, y in tri], fill=self.MARK, tags=(name,))
            self.items[name] = key
        self.items["milieu"] = c.create_rectangle(p, p, q, q, fill=self.KEY, outline=self.EDGE,
                                                  width=2, tags=("milieu",))
        self.mouse = None
        for name in self.items:
            c.tag_bind(name, "<ButtonPress-1>", lambda e, n=name: self.click(n))
        c.bind("<ButtonRelease-1>", self.unclick)

    def click(self, name):
        self.mouse = name
        self.touches.press((name,), ARROWS.get(name))

    def unclick(self, event=None):
        if self.mouse:
            self.touches.release((self.mouse,))
            self.mouse = None

    def redraw(self):
        m = self.touches.get_m()
        held = m.held if m is not None else set()
        for name, item in self.items.items():
            self.canvas.itemconfigure(item, fill=self.KEY_DOWN if name in held else self.KEY)


class Fenetre:
    def __init__(self, title="Canon X-07", zoom=5):
        import tkinter as tk
        self.tk = tk
        self.zoom = zoom
        self.m = None
        self.status = "démarrage..."
        self.done = False
        self.root = tk.Tk()
        self.root.title(title)
        self.root.configure(bg=BEZEL)
        self.root.resizable(False, False)
        tk.Label(self.root, text="CANON  X-07", fg="#c8c8c8", bg=BEZEL,
                 font=("Helvetica", 11, "bold")).pack(pady=(10, 4))
        row = tk.Frame(self.root, bg=BEZEL)
        row.pack(padx=18, pady=4)
        self.ecran = Ecran(row, zoom)
        self.ecran.canvas.pack(side="left")
        self.touches = Touches(self.root, lambda: self.m)
        self.pave = Pave(row, self.touches, size=int(self.ecran.canvas["height"]))
        self.pave.canvas.pack(side="left", padx=(16, 0))
        self.info = tk.Label(self.root, text="", fg="#d0d0d0", bg=BEZEL, anchor="w",
                             font=("Helvetica", 9))
        self.info.pack(fill="x", padx=18)
        tk.Label(self.root, text="Échap = BREAK   ·   flèches : pavé du X-07 (STICK)   ·   "
                                 "espace : bouton du milieu (STRIG(1))   ·   Maj = minuscules",
                 fg="#8a8a8a", bg=BEZEL,
                 font=("Helvetica", 8)).pack(pady=(0, 8))
        self.root.bind("<Key>", self._key)
        self.root.bind("<KeyRelease>", lambda e: release_key(e, self.touches))
        self.root.protocol("WM_DELETE_WINDOW", self._close)

    # -------------------------------------------------- émulation
    def attach(self, m):
        """À appeler (setup) avec la machine, avant son exécution."""
        m.interactive = True
        self.m = m
        self.status = "en cours"

    def start(self, target):
        """Lance target() dans un fil d'exécution ; target appelle attach()."""
        def worker():
            try:
                target()
                if not self.done:
                    self.status = "terminé — fermez la fenêtre"
            except SimError as e:
                if "arrêt demandé" not in str(e):
                    self.status = "arrêt : %s" % e
            except Exception as e:                 # erreur inattendue : on l'affiche
                self.status = "erreur : %s" % e
            finally:
                self.done = True
        threading.Thread(target=worker, daemon=True).start()
        self.root.after(40, self._refresh)
        self.root.mainloop()

    # -------------------------------------------------- dessin
    def _refresh(self):
        if getattr(self, "close_requested", False):    # demandé depuis un autre fil
            self._close()
            return
        m = self.m
        if m is not None:
            lcd = m.lcd
            self.ecran.refresh(lcd)
            waiting = lcd.cursor is not None
            state = "attente du clavier" if waiting and not self.done else self.status
            self.info.configure(text="%s   ·   %s instructions" % (state, format(m.steps, ",")
                                                                  .replace(",", " ")))
        self.root.after(40, self._refresh)

    # -------------------------------------------------- clavier
    def _key(self, ev):
        m = self.m
        if m is None or self.done:
            return
        send_key(m, ev, self.touches)

    def _close(self):
        if self.m is not None:
            self.m.stop_requested = True
        self.root.destroy()
