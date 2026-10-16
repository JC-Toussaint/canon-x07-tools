"""Fenêtre affichant l'écran du X-07 en direct (tkinter).

L'émulation tourne dans un fil d'exécution séparé ; la fenêtre redessine
l'écran de 120 x 32 points dès qu'il change et transmet les touches :
  lettres     majuscules par défaut, comme le X-07 (Maj : minuscules)
  Entrée      RETURN
  flèches     déplacent le curseur (éditeur plein écran de la ROM)
  Suppr, Inser, Origine   DEL, INS, HOME
  Échap       BREAK
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
        pad = 4 * zoom
        self.canvas = tk.Canvas(self.root, width=WIDTH * zoom + 2 * pad,
                                height=HEIGHT * zoom + 2 * pad, bg=OFF,
                                highlightthickness=3, highlightbackground="#111")
        self.canvas.pack(padx=18, pady=4)
        self.pad = pad
        self.img_item = None
        self.info = tk.Label(self.root, text="", fg="#d0d0d0", bg=BEZEL, anchor="w",
                             font=("Helvetica", 9))
        self.info.pack(fill="x", padx=18)
        tk.Label(self.root, text="Échap = BREAK   ·   flèches : édition plein écran   ·   "
                                 "Maj = minuscules", fg="#8a8a8a", bg=BEZEL,
                 font=("Helvetica", 8)).pack(pady=(0, 8))
        self.root.bind("<Key>", self._key)
        self.root.protocol("WM_DELETE_WINDOW", self._close)
        self._last = None
        self._blink = True
        self._blink_t = 0

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
        m = self.m
        now = time.time()
        if now - self._blink_t > 0.4:
            self._blink, self._blink_t = not self._blink, now
        if m is not None:
            lcd = m.lcd
            key = (lcd.version, lcd.cursor is not None and self._blink)
            if key != self._last:
                self._last = key
                self._draw(lcd.rows_bits(cursor=lcd.cursor is not None and self._blink))
            waiting = lcd.cursor is not None
            state = "attente du clavier" if waiting and not self.done else self.status
            self.info.configure(text="%s   ·   %s instructions" % (state, format(m.steps, ",")
                                                                  .replace(",", " ")))
        self.root.after(40, self._refresh)

    def _draw(self, rows):
        tk = self.tk
        img = tk.PhotoImage(width=WIDTH, height=HEIGHT)
        img.put(" ".join("{" + " ".join(ON if b else OFF for b in r) + "}" for r in rows))
        img = img.zoom(self.zoom, self.zoom)
        if self.img_item is None:
            self.img_item = self.canvas.create_image(self.pad, self.pad, image=img, anchor="nw")
        else:
            self.canvas.itemconfigure(self.img_item, image=img)
        self._img = img                         # garder une référence

    # -------------------------------------------------- clavier
    def _key(self, ev):
        m = self.m
        if m is None or self.done:
            return
        if ev.keysym == "Escape":
            if m.lcd.cursor is not None:        # en saisie : BREAK de la saisie
                m.keys.append("\x1b")
            else:                               # programme en cours : touche BREAK
                m.mem[0x2B] |= 0x01
            return
        k = KEYMAP.get(ev.keysym)
        if k is None and ev.char and len(ev.char) == 1 and ord(ev.char) < 256:
            k = ev.char.swapcase() if ev.char.isalpha() else ev.char
        if k:
            m.keys.append(k)

    def _close(self):
        if self.m is not None:
            self.m.stop_requested = True
        self.root.destroy()
