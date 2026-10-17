"""Éditeur-débogueur visuel du X-07 (tkinter).

À gauche, le source (.asm, .bas, .qbas) : un clic dans la marge pose ou
enlève un point d'arrêt, la ligne en cours d'exécution est surlignée.
À droite, l'écran du X-07 émulé (il reçoit le clavier), les registres, les
variables, la pile et le code machine autour du PC.

Le programme tourne dans l'émulateur (vraie ROM), comme pour la commande
debug ; un .qbas est compilé directement (lignes du source QuickBASIC).

Session : toute la logique, sans interface (testée par tests/test_ide.py).
Editeur : la fenêtre.
"""
import bisect
import os
import re
import threading

from . import debug, emu
from .sim import EXIT

INTERNAL = re.compile(r"(V_|S_|A[IFDS]_)(Q[TAOR]_|FNP_|FN_)")   # variables du compilateur


class Session:
    """Un programme en cours de débogage, repéré par les lignes de son source."""

    def __init__(self, path, ram=16):
        self.path = path
        self.ram = ram
        self.kind = os.path.splitext(path)[1].lower().lstrip(".")
        self.break_lines = set()           # points d'arrêt : lignes du source (1, 2...)
        self.m = self.dbg = None
        self.messages = []
        self.line_addr = {}                # ligne -> adresse de sa première instruction
        self.addrs, self.addr_lines = [], []
        self.reason = None

    # -------------------------------------------------- compilation
    def build(self):
        """Compile le fichier et prépare la machine ; rend les avertissements."""
        from .cli import load_for_debug
        mem, entry, symbols, listing, prog_range, warns = load_for_debug(
            self.path, self.ram, direct=True)
        m = emu.prepare_binary(mem, entry, ram=self.ram, real_display=True)
        m.interactive = True               # clavier : l'écran de la fenêtre
        self.messages = []
        self.dbg = debug.Debugger(m, symbols, listing, prog_range, out=self.messages.append)
        self.m = m
        self.symbols = {n.upper(): a for n, a in symbols.items()}
        self.prog_range = prog_range
        self._map_lines(listing, symbols)
        kept = set()
        for line in self.break_lines:     # les points d'arrêt suivent la recompilation
            if line in self.line_addr:
                kept.add(line)
                self.dbg.breaks.add(self.line_addr[line])
        self.break_lines = kept
        self.reason = "départ"
        return warns

    def _map_lines(self, listing, symbols):
        pairs = []
        if self.kind == "asm":
            name = os.path.basename(self.path)
            for addr, data, src, text in listing:
                code = text.split(";")[0]
                if re.search(r"\b(DB|DW|DZ|DS|DEFB|DEFW|DEFS|DEFM|DM)\b", code, re.I):
                    continue                        # données : pas de point d'arrêt
                if addr is not None and data and os.path.basename(str(src[0])) == name:
                    pairs.append((addr & 0xFFFF, src[1]))
        else:
            lab = {int(n[3:]): a for n, a in symbols.items() if re.fullmatch(r"LN_\d+", n)}
            if self.kind == "qbas":                 # LN_n : ligne n du fichier
                pairs = [(a, n) for n, a in lab.items()]
            else:                                   # BASIC du X-07 : numéro en tête de ligne
                with open(self.path, encoding="utf-8", errors="replace") as f:
                    for k, text in enumerate(f.read().splitlines(), 1):
                        mm = re.match(r"\s*(\d+)", text)
                        if mm and int(mm.group(1)) in lab:
                            pairs.append((lab[int(mm.group(1))], k))
        self.line_addr = {}
        for a, line in sorted(pairs):
            self.line_addr.setdefault(line, a)
        pairs = sorted((a, l) for l, a in self.line_addr.items())
        self.addrs = [a for a, _ in pairs]
        self.addr_lines = [l for _, l in pairs]

    # -------------------------------------------------- lignes
    def line_of(self, a):
        """Ligne du source contenant l'adresse a (None hors du programme)."""
        lo, hi = self.prog_range
        if not self.addrs or not lo <= a <= hi:
            return None
        k = bisect.bisect_right(self.addrs, a) - 1
        return self.addr_lines[k] if k >= 0 else None

    def current_line(self):
        if self.m is None or self.m.pc == EXIT:
            return None
        return self.line_of(self.m.pc)

    def code_line(self, line):
        """Première ligne avec du code, à partir de line (None s'il n'y en a pas)."""
        later = [l for l in self.line_addr if l >= line]
        return min(later) if later else None

    def toggle_break(self, line):
        """Pose ou enlève un point d'arrêt ; rend (ligne effective, posé ?)."""
        if line in self.break_lines:
            self.break_lines.discard(line)
            if self.dbg and line in self.line_addr:
                self.dbg.breaks.discard(self.line_addr[line])
            return line, False
        if self.dbg is not None:
            line = self.code_line(line)
            if line is None:
                return None, False
            self.dbg.breaks.add(self.line_addr[line])
        self.break_lines.add(line)
        return line, True

    # -------------------------------------------------- exécution
    @property
    def finished(self):
        return self.m is None or self.m.pc == EXIT

    def run(self):
        self.reason = self.dbg.go()
        return self.reason

    def step_instruction(self):
        self.reason = self.dbg.go(count=1)
        return self.reason

    def step_line(self, over=True):
        """Jusqu'au début d'une autre ligne du source ; over : sans entrer dans
        les procédures appelées (la pile ne doit pas être plus basse)."""
        m = self.m
        start, sp0 = self.current_line(), m.sp

        def until(pc0, _):
            line = self.line_of(m.pc)
            if line is None or self.line_addr.get(line) != m.pc:
                return False                    # dans la ROM, ou au milieu d'une ligne
            if over and m.sp < sp0:
                return False
            return line != start or m.sp > sp0  # autre ligne, ou retour de procédure
        self.reason = self.dbg.go(until=until)
        return self.reason

    def finish(self):
        self.reason = self.dbg.finish() or "retour de la routine"
        return self.reason

    def pause(self):
        if self.m is not None:
            self.m.debug_pause = True

    # -------------------------------------------------- état
    def registers(self):
        m, r = self.m, self.m.r
        flags = "".join(n if r["F"] & b else "-" for n, b in debug.FLAGS)
        al = m.alt
        return ("A=%02X  F=%02X %s     PC=%04X  SP=%04X\n"
                "BC=%04X  DE=%04X  HL=%04X    IX=%04X  IY=%04X\n"
                "AF'=%02X%02X BC'=%02X%02X DE'=%02X%02X HL'=%02X%02X  %d instructions"
                % (r["A"], r["F"], flags, m.pc, m.sp, m.get16("BC"), m.get16("DE"),
                   m.get16("HL"), m.ix, m.iy, al["A"], al["F"], al["B"], al["C"],
                   al["D"], al["E"], al["H"], al["L"], m.steps))

    def disassembly(self, n=12):
        m, out, a = self.m, [], self.m.pc
        if a == EXIT:
            return "programme terminé : retour au BASIC"
        for _ in range(n):
            size, text = self.dbg.line(a, ">" if a == m.pc else
                                       ("*" if a in self.dbg.breaks else " "))
            out.append(text)
            a = (a + size) & 0xFFFF
        return "\n".join(out)

    def stack(self, n=10):
        m, out = self.m, []
        for k in range(n):
            a = (m.sp + 2 * k) & 0xFFFF
            v = m.rd16(a)
            note = "retour au BASIC" if v == EXIT else self.dbg.where(v)
            out.append("%04X: %04X  %s" % (a, v, note))
        return "\n".join(out)

    def variables(self):
        """Lignes « NOM = valeur » : variables du programme compilé, ou
        étiquettes de données d'un programme assembleur."""
        if self.kind in ("bas", "qbas"):
            return self._basic_variables()
        code = set(self.addrs)
        lo, hi = self.prog_range
        out = []
        for n, a in sorted(self.symbols.items(), key=lambda kv: kv[1]):
            if lo <= a <= hi and a not in code and not n.startswith(("LN_", ".")):
                data = [self.m.rd(a + k) for k in range(8)]
                text = "".join(chr(c) if 32 <= c < 127 else "." for c in data)
                out.append("%s = %s  %s   ($%04X)" % (n, " ".join("%02X" % c for c in data),
                                                     text, a))
        return out

    def _basic_variables(self):
        out = []
        simple = sorted(n for n in self.symbols
                        if re.fullmatch(r"(V_\w+_[IFD]|S_\w+)", n) and not INTERNAL.match(n))
        descs = {a: n[3:] for n, a in self.symbols.items() if n.startswith("QD_")}
        arrays_at = {a: n for n, a in self.symbols.items() if re.fullmatch(r"A[IFDS]_\w+", n)}
        for n in simple:
            text = self.dbg.var_text(n).split("   ($")[0]
            name, _, val = text.partition(" = ")
            if re.search(r"\.[A-Z0-9]+\.P%$", name):      # paramètre tableau : pointeur
                target = descs.get(self.m.rd16(self.symbols[n]))
                arr = self.dbg.var_text(target, 0).split("(", 1)[0] if target else "?"
                text = "%s() -> %s()" % (name[:-3], arr)
            elif re.search(r"\.RESULTAT[%!#$]$", name):    # résultat d'une FUNCTION
                text = "%s%s (résultat) = %s" % (name.split(".")[0], name[-1], val)
            out.append(text)
        arrays = sorted((a, n) for n, a in self.symbols.items()
                        if re.fullmatch(r"A[IFDS]_\w+", n) and not INTERNAL.match(n))
        ends = sorted(a for a in self.symbols.values())
        for a, n in arrays:
            t = n[1]
            size = {"I": 2, "F": 4, "D": 8}.get(t, self.symbols.get("STRCAP", 80) + 1)
            nxt = next((e for e in ends if e > a), a + size)
            count = max(1, (nxt - a) // size)
            vals = []
            for k in range(min(count, 12)):
                vals.append(self.dbg.var_text(n, k).split(" = ", 1)[1].split("   ($")[0])
            name = self.dbg.var_text(n, 0).split("(", 1)[0]
            out.append("%s(0..%d) = %s%s" % (name, count - 1, " ".join(vals),
                                              " ..." if count > 12 else ""))
        return out


class Editeur:
    """La fenêtre de l'éditeur-débogueur."""

    BG_LINE, BG_BREAK = "#fff3a8", "#ffd6d6"

    def __init__(self, path=None, ram=16, zoom=3):
        import tkinter as tk
        from tkinter import ttk
        from .afficheur import Ecran
        self.tk = tk
        self.ram = ram
        self.session = None
        self.path = None
        self.worker = None
        self.root = tk.Tk()
        self.root.title("Canon X-07 : éditeur-débogueur")
        self.root.geometry("1250x760")
        mono = ("DejaVu Sans Mono", 10)
        self.mono = mono

        bar = tk.Frame(self.root)
        bar.pack(fill="x", padx=4, pady=3)
        self.buttons = {}
        for key, text, cmd in (
                ("ouvrir", "Ouvrir…", self.open_dialog),
                ("enregistrer", "Enregistrer", self.save),
                ("compiler", "Compiler", self.compile),
                ("continuer", "▶ Continuer (F5)", self.do_run),
                ("pause", "⏸ Pause", self.do_pause),
                ("ligne", "Ligne suivante (F10)", lambda: self.do_step("over")),
                ("entrer", "Entrer (F11)", lambda: self.do_step("into")),
                ("sortir", "Sortir (Maj+F11)", lambda: self.do_step("out")),
                ("instr", "Instruction", lambda: self.do_step("instr")),
                ("reinit", "↺ Recommencer", self.restart)):
            b = tk.Button(bar, text=text, command=cmd)
            b.pack(side="left", padx=2)
            self.buttons[key] = b
        self.status = tk.Label(self.root, text="", anchor="w", fg="#222", relief="sunken",
                               padx=6)
        self.status.pack(side="bottom", fill="x")

        panes = tk.PanedWindow(self.root, orient="horizontal", sashwidth=5)
        panes.pack(fill="both", expand=True)

        left = tk.Frame(panes)
        self.gutter = tk.Canvas(left, width=58, bg="#eeeeee", highlightthickness=0)
        self.gutter.pack(side="left", fill="y")
        scroll = tk.Scrollbar(left)
        scroll.pack(side="right", fill="y")
        self.text = tk.Text(left, font=mono, undo=True, wrap="none",
                            yscrollcommand=lambda *a: (scroll.set(*a), self.draw_gutter()))
        self.text.pack(side="left", fill="both", expand=True)
        scroll.configure(command=lambda *a: (self.text.yview(*a), self.draw_gutter()))
        self.text.tag_configure("courante", background=self.BG_LINE)
        self.text.tag_configure("arret", background=self.BG_BREAK)
        self.text.tag_raise("courante")
        self.gutter.bind("<Button-1>", self.gutter_click)
        self.text.bind("<<Modified>>", self.on_modified)
        self.text.bind("<Configure>", lambda e: self.draw_gutter())
        panes.add(left, stretch="always", minsize=420)

        right = tk.Frame(panes)
        self.screen_hint = tk.Label(right, anchor="w")
        self.screen_hint.pack(fill="x")
        self.ecran = Ecran(right, zoom)
        self.ecran.canvas.pack(anchor="w", pady=2)
        c = self.ecran.canvas
        c.bind("<Button-1>", lambda e: c.focus_set())
        c.bind("<Key>", self.screen_key)
        c.bind("<FocusIn>", lambda e: self.show_focus(True))
        c.bind("<FocusOut>", lambda e: self.show_focus(False))
        line = tk.Frame(right)                   # saisie sûre : une ligne, puis Entrée
        line.pack(fill="x", pady=(0, 4))
        tk.Label(line, text="Taper pour le X-07 :").pack(side="left")
        self.entry = tk.Entry(line, font=mono, width=22)
        self.entry.pack(side="left", padx=4)
        self.entry.bind("<Return>", lambda e: self.send_line())
        tk.Button(line, text="Envoyer ⏎", command=self.send_line).pack(side="left")
        self.show_focus(False)
        tk.Label(right, text="Registres", anchor="w", font=("Helvetica", 9, "bold")).pack(fill="x")
        self.regs = tk.Label(right, font=mono, justify="left", anchor="w", bg="white",
                             relief="sunken")
        self.regs.pack(fill="x", pady=2)
        tabs = ttk.Notebook(right)
        tabs.pack(fill="both", expand=True)
        self.panels = {}
        for key, title in (("variables", "Variables"), ("code", "Code machine"),
                           ("pile", "Pile"), ("messages", "Messages")):
            t = tk.Text(tabs, font=mono, height=12, wrap="none")
            t.tag_configure("change", foreground="#c00000")
            tabs.add(t, text=title)
            self.panels[key] = t
        self.previous = {}                       # variable -> valeur à l'arrêt précédent
        self.tabs = tabs
        panes.add(right, minsize=430)

        r = self.root
        r.bind("<F5>", lambda e: self.do_run())
        r.bind("<F10>", lambda e: self.do_step("over"))
        r.bind("<F11>", lambda e: self.do_step("into"))
        r.bind("<Shift-F11>", lambda e: self.do_step("out"))
        r.bind("<F9>", self.f9)
        r.bind("<Control-s>", lambda e: self.save())
        r.protocol("WM_DELETE_WINDOW", self.close)
        if path:
            self.load(path)
        self.update_buttons()
        self.root.after(40, self.tick)

    # -------------------------------------------------- fichier
    def open_dialog(self):
        from tkinter import filedialog
        p = filedialog.askopenfilename(filetypes=[("Programmes X-07", "*.asm *.bas *.qbas"),
                                                  ("Tous", "*")])
        if p:
            self.load(p)

    def load(self, path):
        with open(path, encoding="utf-8", errors="replace") as f:
            content = f.read()
        self.path = path
        self.session = Session(path, self.ram)
        self.text.delete("1.0", "end")
        self.text.insert("1.0", content)
        self.text.edit_modified(False)
        self.text.edit_reset()
        self.root.title("Canon X-07 : %s" % os.path.basename(path))
        self.set_status("%s ouvert : Compiler, puis ▶" % os.path.basename(path))
        self.refresh()

    def save(self):
        if not self.path:
            return False
        with open(self.path, "w", encoding="utf-8") as f:
            f.write(self.text.get("1.0", "end-1c"))
        self.text.edit_modified(False)
        self.dirty = True                   # à recompiler
        self.set_status("enregistré")
        return True

    def on_modified(self, event=None):
        if self.text.edit_modified():
            self.root.title("Canon X-07 : %s *" % os.path.basename(self.path or "?"))
            self.dirty = True
            if self.session:
                self.sync_breaks_from_text()
        self.draw_gutter()

    # -------------------------------------------------- compilation
    def compile(self):
        if not self.path or self.busy():
            return False
        if self.text.edit_modified():
            self.save()
        self.root.title("Canon X-07 : %s" % os.path.basename(self.path))
        self.sync_breaks_from_text()              # après d'éventuelles modifications
        try:
            warns = self.session.build()
        except Exception as e:                       # erreur de compilation : on l'affiche
            self.session.m = None
            self.set_status("erreur : %s" % e)
            self.show_text("messages", "erreur : %s" % e)
            self.tabs.select(self.panels["messages"])
            self.refresh()
            return False
        self.dirty = False
        self.previous = {}
        self.sync_text_from_breaks()              # déplacés sur une ligne avec du code
        self.show_text("messages", "\n".join("attention : %s" % w for w in warns)
                       or "compilé sans avertissement")
        self.set_status("compilé : %d point(s) d'arrêt ; ▶ pour lancer"
                        % len(self.session.break_lines))
        self.refresh()
        return True

    def restart(self):
        if self.busy():
            self.do_pause()
            return
        self.compile()

    def ready(self):
        """Compile si nécessaire ; rend True si l'on peut exécuter."""
        if self.session is None:
            return False
        if self.session.m is None or getattr(self, "dirty", False):
            return self.compile()
        return True

    # -------------------------------------------------- exécution (fil séparé)
    def busy(self):
        return self.worker is not None and self.worker.is_alive()

    def start(self, action, label):
        if self.busy() or not self.ready():
            return
        if self.session.finished:
            self.set_status("programme terminé : ↺ pour recommencer")
            return
        self.set_status(label)
        self.text.tag_remove("courante", "1.0", "end")
        self.ecran.canvas.focus_set()               # le clavier va au X-07

        def work():
            try:
                action()
            except Exception as e:                  # erreur inattendue : affichée
                self.session.reason = "erreur : %s" % e
        self.worker = threading.Thread(target=work, daemon=True)
        self.worker.start()
        self.update_buttons()

    def do_run(self):
        self.start(lambda: self.session.run(), "en cours… (⏸ ou F9 pour arrêter)")

    def do_step(self, how):
        s = self.session
        actions = {"over": lambda: s.step_line(True), "into": lambda: s.step_line(False),
                   "out": s.finish, "instr": s.step_instruction}
        self.start(actions[how], "pas à pas…")

    def do_pause(self):
        if self.session:
            self.session.pause()

    def f9(self, event):
        if self.root.focus_get() is self.text:      # F9 dans le source : point d'arrêt
            line = int(self.text.index("insert").split(".")[0])
            self.toggle(line)
            return "break"
        self.do_pause()

    # -------------------------------------------------- points d'arrêt
    def gutter_click(self, event):
        if self.session is None:
            return
        index = self.text.index("@0,%d" % event.y)
        self.toggle(int(index.split(".")[0]))

    def sync_breaks_from_text(self):
        """Les points d'arrêt suivent le texte édité (marques tkinter)."""
        lines = set()
        for mark in self.text.mark_names():
            if mark.startswith("bp_"):
                lines.add(int(self.text.index(mark).split(".")[0]))
        self.session.break_lines = lines

    def sync_text_from_breaks(self):
        for mark in [m for m in self.text.mark_names() if m.startswith("bp_")]:
            self.text.mark_unset(mark)
        for line in self.session.break_lines:
            mark = "bp_%d" % line
            self.text.mark_set(mark, "%d.0" % line)
            self.text.mark_gravity(mark, "left")

    def toggle(self, line):
        if self.session.m is None or getattr(self, "dirty", False):
            self.sync_breaks_from_text()          # pas encore compilé : ligne telle quelle
        got, on = self.session.toggle_break(line)
        self.sync_text_from_breaks()
        if got is None:
            self.set_status("pas de code à partir de la ligne %d" % line)
        elif got != line and on:
            self.set_status("point d'arrêt sur la ligne %d (première ligne avec du code)" % got)
        self.refresh()

    # -------------------------------------------------- affichage
    def set_status(self, text):
        self.status.configure(text=text)

    def show_text(self, key, text):
        t = self.panels[key]
        t.configure(state="normal")
        t.delete("1.0", "end")
        t.insert("1.0", text)
        t.configure(state="disabled")

    def show_variables(self, lines):
        """Variables ; en rouge, celles qui ont changé depuis l'arrêt précédent."""
        self.show_text("variables", "\n".join(lines) or "(aucune)")
        t = self.panels["variables"]
        now = {}
        for k, line in enumerate(lines, 1):
            name, _, val = line.partition(" = ")
            now[name] = val
            if name in self.previous and self.previous[name] != val:
                t.tag_add("change", "%d.0" % k, "%d.end" % k)
        self.previous = now

    def draw_gutter(self):
        g = self.gutter
        g.delete("all")
        s = self.session
        current = s.current_line() if (s and s.m and not self.busy()) else None
        idx = self.text.index("@0,0")
        while True:
            info = self.text.dlineinfo(idx)
            if info is None:
                break
            y, h = info[1], info[3]
            line = int(idx.split(".")[0])
            g.create_text(54, y + h // 2, anchor="e", text=str(line), fill="#888",
                          font=("DejaVu Sans Mono", 9))
            if s and line in s.break_lines:
                g.create_oval(4, y + h // 2 - 5, 14, y + h // 2 + 5, fill="#d22", outline="#900")
            if line == current:
                g.create_text(22, y + h // 2, text="▶", fill="#c80", font=("DejaVu Sans", 10))
            nxt = self.text.index("%s+1line" % idx)
            if nxt == idx:
                break
            idx = nxt

    def refresh(self):
        """Met à jour la source, les registres et les onglets (machine arrêtée)."""
        s = self.session
        t = self.text
        t.tag_remove("arret", "1.0", "end")
        t.tag_remove("courante", "1.0", "end")
        if s:
            if getattr(self, "dirty", False):
                self.sync_breaks_from_text()
            for line in s.break_lines:
                t.tag_add("arret", "%d.0" % line, "%d.0+1line" % line)
        if s and s.m and not self.busy():
            cur = s.current_line()
            if cur:
                t.tag_add("courante", "%d.0" % cur, "%d.0+1line" % cur)
                t.see("%d.0" % cur)
            self.regs.configure(text=s.registers())
            self.show_variables(s.variables())
            self.show_text("code", s.disassembly())
            self.show_text("pile", s.stack())
        elif not (s and s.m):
            self.regs.configure(text="(programme non compilé)")
        self.draw_gutter()
        self.update_buttons()

    def update_buttons(self):
        run = self.busy()
        has = self.session is not None
        for k, b in self.buttons.items():
            if k == "pause":
                b.configure(state="normal" if run else "disabled")
            elif k in ("ouvrir",):
                b.configure(state="disabled" if run else "normal")
            else:
                b.configure(state="normal" if has and not run else "disabled")

    def tick(self):
        s = self.session
        if s and s.m:
            self.ecran.refresh(s.m.lcd)
        if self.worker is not None and not self.worker.is_alive():
            self.worker = None
            reason = s.reason
            if s.finished:
                self.set_status("programme terminé (%s) : ↺ pour recommencer" % (reason or "fin"))
            else:
                line = s.current_line()
                self.set_status("arrêt%s%s" % (" : %s" % reason if reason else "",
                                               ", ligne %d" % line if line else ""))
            if s.messages:
                self.show_text("messages", "\n".join(s.messages[-50:]))
            self.refresh()
        elif self.busy() and s and s.m:
            if s.m.lcd.cursor is not None:
                self.set_status("le X-07 attend une touche : cliquez sur l'écran et tapez")
        self.root.after(40, self.tick)

    def show_focus(self, on):
        self.screen_hint.configure(
            text=("Écran du X-07 : le clavier va au X-07 (Échap = BREAK)" if on else
                  "Écran du X-07 : cliquez dessus pour taper, ou utilisez le champ dessous"),
            fg="#1f7a2e" if on else "#555")

    def screen_key(self, event):
        """Touche tapée sur l'écran.  Programme arrêté : la touche est gardée,
        le programme la lira en repartant (elle n'est plus perdue)."""
        s = self.session
        if s and s.m and not s.finished:
            from .afficheur import send_key
            before = len(s.m.keys)
            send_key(s.m, event)
            if not self.busy() and len(s.m.keys) > before:
                self.set_status("touches gardées pour le programme : %r ; ▶ pour continuer"
                                % "".join(s.m.keys))
        elif s and s.finished:
            self.set_status("programme terminé : ↺ pour recommencer, puis tapez")
        return "break"

    def send_line(self):
        """Champ « Taper pour le X-07 » : le texte tel quel, puis Entrée."""
        s = self.session
        text = self.entry.get()
        if not (s and s.m) or s.finished:
            self.set_status("lancez d'abord le programme (▶)")
            return
        s.m.keys += list(text) + ["\r"]
        self.entry.delete(0, "end")
        if not self.busy():
            self.set_status("ligne gardée pour le programme : %r ; ▶ pour continuer" % text)

    def close(self):
        if self.session and self.session.m:
            self.session.m.stop_requested = True
        self.root.destroy()

    def mainloop(self):
        self.root.mainloop()
