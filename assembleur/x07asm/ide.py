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

from . import debug, emu, syntaxe
from .afficheur import Cadence, connect_speaker
from .sim import EXIT

TEMPLATES = {   # point de départ d'un nouveau programme
    ".bas": '10 REM NOUVEAU PROGRAMME\n20 CLS\n30 INPUT "NOM";N$\n40 PRINT "BONJOUR ";N$\n',
    ".qbas": ("' Nouveau programme QuickBASIC pour le Canon X-07\n"
              "DEFINT A-Z                      ' variables entières par défaut\n"
              "CLS\n"
              "INPUT \"Nom\"; nom$\n"
              "PRINT \"Bonjour \"; nom$\n"
              "END\n"),
    ".asm": ("; Nouveau programme en assembleur pour le Canon X-07\n"
             "; Chargement : CLEAR 50,&H1BFF  puis  EXEC &H1C00\n"
             "\n"
             "        ORG  $1C00\n"
             "\n"
             "DEBUT:  CALL LCDCLS          ; efface l'écran\n"
             "        LD   HL,MSG\n"
             "        CALL PRTMSG          ; affiche (HL) jusqu'à 00\n"
             ".ATT:   XOR  A\n"
             "        CALL INKEY           ; Z=1 si aucune touche\n"
             "        JR   Z,.ATT\n"
             "        RET                  ; retour au BASIC\n"
             "\n"
             "MSG:    DZ   \"BONJOUR X-07 !\"\n"),
}
KINDS = ((".bas", "BASIC du X-07"), (".qbas", "QuickBASIC"), (".asm", "Assembleur Z80"))

# registres affichés en cases : (nom, chiffres hexadécimaux), par rangée
REG_ROWS = ((("A", 2), ("F", 2), ("BC", 4), ("DE", 4), ("HL", 4)),
            (("IX", 4), ("IY", 4), ("SP", 4), ("PC", 4)),
            (("AF'", 4), ("BC'", 4), ("DE'", 4), ("HL'", 4)))
FLAG_NAMES = {"S": "S : signe (résultat négatif)", "Z": "Z : zéro", "H": "H : demi-retenue",
              "P": "P/V : parité ou dépassement", "N": "N : soustraction", "C": "C : retenue"}

# onglet « Registres » : registres 8 bits, 16 bits, secondaires, mémoire pointée
DETAIL_GROUPES = (("A", "F", "B", "C", "D", "E", "H", "L"),
                  ("BC", "DE", "HL", "IX", "IY", "SP", "PC"),
                  ("AF'", "BC'", "DE'", "HL'"))
POINTEURS = ("HL", "DE", "BC", "IX", "IY")


def octets(vals):
    """Valeurs des registres, avec les registres 8 bits tirés des paires."""
    v = dict(vals)
    for p in ("BC", "DE", "HL"):
        v[p[0]], v[p[1]] = vals[p] >> 8, vals[p] & 0xFF
    return v


def taille(name):
    return 8 if len(name) == 1 else 16


def binaire(v, bits):
    """Binaire groupé par 4 bits : 0000 1001."""
    s = format(v, "0%db" % bits)
    return " ".join(s[k:k + 4] for k in range(0, bits, 4))


def signe(v, bits):
    return v - (1 << bits) if v >> (bits - 1) & 1 else v


def caractere(v):
    return chr(v) if 32 <= v < 127 else "·"


def detail_valeur(name, v):
    """Bulle d'un registre : hexadécimal, décimal, signé, binaire (caractère)."""
    bits = taille(name)
    text = "%s = %0*X : %d (signé %d)\n%s" % (name, bits // 4, v, v, signe(v, bits),
                                              binaire(v, bits))
    if bits == 8:
        text += "   « %s »" % caractere(v)
    return text


INTERNAL = re.compile(r"(V_|S_|A[IFDS]_)(Q[TAOR]_|FNP_|FN_)")   # variables du compilateur


# polices à chasse fixe, par ordre de préférence (Linux, Windows, macOS) ; une
# police absente serait remplacée par Tk par une police proportionnelle
POLICES_FIXES = ("DejaVu Sans Mono", "Consolas", "Menlo", "Courier New", "Liberation Mono")


def police_fixe(root):
    """Première police à chasse fixe installée, sinon celle du système (TkFixedFont)."""
    import tkinter.font as tkfont
    installees = set(tkfont.families(root))
    for nom in POLICES_FIXES:
        if nom in installees:
            return nom
    return tkfont.nametofont("TkFixedFont").actual("family")


class Session:
    """Un programme en cours de débogage, repéré par les lignes de son source."""

    def __init__(self, path, ram=16, memoire=None, image=None):
        self.path = path
        self.ram = ram
        self.memoire = memoire             # fichier : mémoire gardée d'une session à l'autre
        self.image = image                 # RAM du X-07 à la fin du dernier programme :
        self.saved = False                 # le suivant repart d'elle, comme sur la machine
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
        machine = None
        image = self.image
        if image is None and self.memoire and os.path.exists(self.memoire):
            with open(self.memoire, "rb") as f:
                image = f.read()
        if image is not None:
            if len(image) != emu.RAM_TOP[self.ram] + 1:
                raise ValueError("mémoire de %d Ko, pas de %d Ko"
                                 % (len(image) // 1024, self.ram))
            machine = emu.power_on(image, self.ram, real_display=True)
        m = emu.prepare_binary(mem, entry, ram=self.ram, real_display=True, machine=machine)
        self.saved = False
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
        # programme revenu au BASIC, ou X-07 déjà éteint par OFF à sa fin
        return self.m is None or self.m.pc == EXIT or self.saved

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

    def save_memory(self):
        """Programme terminé : X-07 éteint par OFF ; sa mémoire (programmes,
        fichiers en RAM) sert au lancement suivant, et va dans le fichier
        --memoire s'il y en a un.  Rend True si elle a été gardée."""
        if self.saved or not self.finished or self.m is None:
            return False
        self.image = emu.power_off(self.m)
        if self.memoire:
            with open(self.memoire, "wb") as f:
                f.write(self.image)
        self.saved = True
        return True

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

    def register_values(self):
        """Registres par nom (REG_ROWS), et « steps » : instructions exécutées."""
        m, r, al = self.m, self.m.r, self.m.alt
        v = {"A": r["A"], "F": r["F"], "BC": m.get16("BC"), "DE": m.get16("DE"),
             "HL": m.get16("HL"), "IX": m.ix, "IY": m.iy, "SP": m.sp, "PC": m.pc,
             "steps": m.steps}
        for name in ("AF", "BC", "DE", "HL"):
            v[name + "'"] = al[name[0]] << 8 | al[name[1]]
        return v

    def registres_detail(self, base=None):
        """Lignes de l'onglet « Registres » : listes de (texte, style), style
        None, "titre", "nom", "change" ou "note".  base : valeurs de l'arrêt
        précédent (register_values) ; valeurs et bits changés en "change"."""
        vals = octets(self.register_values())
        old = octets(base) if base else None
        out = [[("%-5s%6s%7s%7s   %-22s%s" % ("", "hexa", "déc.", "signé", "binaire", "car."),
                 "titre")]]
        for groupe in DETAIL_GROUPES:
            for name in groupe:
                bits, v = taille(name), vals[name]
                o = v if old is None else old[name]
                hexa = "%0*X" % (bits // 4, v)
                segs = [("%-5s" % name, "nom"), (" " * (6 - len(hexa)), None),
                        (hexa, "change" if o != v else None),
                        ("%7d%7d   " % (v, signe(v, bits)), None)]
                for k in range(bits - 1, -1, -1):
                    segs.append(("1" if v >> k & 1 else "0", "change" if (o ^ v) >> k & 1 else None))
                    if k % 4 == 0 and k:
                        segs.append((" ", None))
                if bits == 8:
                    segs.append(("%14s" % caractere(v), None))
                out.append(segs)
                if name == "F":                     # le nom de chaque indicateur sous son bit
                    out.append([("%28s%s" % ("", "SZ·H ·PNC"), "note")])
            out.append([])
        out.append([("Mémoire pointée", "titre")])
        m = self.m
        for name in POINTEURS:
            a = vals[name]
            data = [m.rd((a + k) & 0xFFFF) for k in range(8)]
            out.append([("%-6s" % ("(%s)" % name), "nom"),
                        ("%04X : %s   " % (a, " ".join("%02X" % b for b in data)), None),
                        ("".join(caractere(b) for b in data), "note")])
        words = " ".join("%04X" % m.rd16((vals["SP"] + 2 * k) & 0xFFFF) for k in range(6))
        out.append([("%-6s" % "(SP)", "nom"), ("%04X : %s   " % (vals["SP"], words), None),
                    ("sommet de pile", "note")])
        return out

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


# barre d'outils : clé, symbole, bulle d'aide, (méthode, arguments...)
TOOLBAR = (
    ("compiler", "⚙", "Compiler", ("compile",)),
    ("continuer", "▶", "Continuer (F5)", ("do_run",)),
    ("pause", "‖", "Pause (F9)", ("do_pause",)),       # (⏸ s'afficherait en émoji, non grisé)
    (None, None, None, None),
    ("ligne", "⤼", "Ligne suivante (F10)", ("do_step", "over")),
    ("entrer", "↓", "Entrer dans la procédure (F11)", ("do_step", "into")),
    ("sortir", "↑", "Sortir de la procédure (Maj+F11)", ("do_step", "out")),
    ("instr", "·", "Une instruction machine", ("do_step", "instr")),
    (None, None, None, None),
    ("reinit", "↺", "Recommencer : recompiler et repartir du début", ("restart",)),
)

AIDE = """Éditeur-débogueur du Canon X-07

Points d'arrêt : clic dans la marge, ou F9 sur la ligne du curseur.
Continuer F5 · Ligne suivante F10 · Entrer F11 · Sortir Maj+F11
Pause : bouton ‖ ou F9 (hors du source).

Écran du X-07 : cliquez dessus pour lui donner le clavier (cadre vert),
ou tapez une valeur dans le champ « Taper pour le X-07 », puis Entrée.
Échap = BREAK.  Sur un clavier AZERTY, les chiffres demandent Maj.

La mémoire du X-07 (fichiers en RAM) est gardée d'un lancement à
l'autre ; --memoire FICHIER la garde d'une session à l'autre."""


class SuiviRegistres:
    """Registres changés depuis l'arrêt précédent.  La référence ne change
    qu'à un nouvel arrêt (autre nombre d'instructions), pas à un simple
    rafraîchissement de la fenêtre pendant le même arrêt."""

    def __init__(self):
        self.reset()

    def reset(self):
        self.last = self.base = None

    def changed(self, vals):
        if self.last is not None and self.last["steps"] != vals["steps"]:
            self.base = self.last
        self.last = vals
        b = self.base
        return set() if b is None else {k for k in vals if k != "steps" and vals[k] != b[k]}


class Bulle:
    """Bulle d'aide qui apparaît au survol d'un widget."""

    def __init__(self, widget, text):
        self.widget, self.text, self.win = widget, text, None     # text : ou une fonction
        widget.bind("<Enter>", self.show)
        widget.bind("<Leave>", self.hide)
        widget.bind("<ButtonPress>", self.hide)

    def show(self, event=None):
        import tkinter as tk
        if self.win is not None:
            return
        x = self.widget.winfo_rootx() + 4
        y = self.widget.winfo_rooty() + self.widget.winfo_height() + 4
        self.win = tk.Toplevel(self.widget)
        self.win.wm_overrideredirect(True)
        self.win.wm_geometry("+%d+%d" % (x, y))
        text = self.text() if callable(self.text) else self.text
        tk.Label(self.win, text=text, bg="#ffffe0", relief="solid", bd=1, justify="left",
                 padx=5, pady=2, font=("Helvetica", 9)).pack()

    def hide(self, event=None):
        if self.win is not None:
            self.win.destroy()
            self.win = None


class Registres:
    """Les registres du Z80 en cases (nom en petit, valeur en gros), en
    couleur s'ils ont changé depuis l'arrêt précédent ; les indicateurs en
    pastilles allumées ou éteintes, expliquées au survol."""

    FOND, NOM, VALEUR, GRIS = "white", "black", "#1a1a1a", "#888888"
    CHANGE, FOND_CHANGE = "#c45a00", "#fff1d6"
    ALLUME, ETEINT = ("#2c9a3c", "white"), ("#eeeeee", "#aaaaaa")

    def __init__(self, parent, mono):
        import tkinter as tk
        self.frame = tk.Frame(parent, bg=self.FOND, relief="sunken", bd=1, padx=6, pady=4)
        self.suivi = SuiviRegistres()
        self.values, self.flags = {}, {}
        petit = ("Helvetica", 8)
        for r, row in enumerate(REG_ROWS):
            for c, (name, _) in enumerate(row):
                cell = tk.Frame(self.frame, bg=self.FOND, padx=9, pady=1)
                cell.grid(row=r, column=c, sticky="w")
                tk.Label(cell, text=name, font=("Helvetica", 9), fg=self.NOM,
                         bg=self.FOND).pack(anchor="w")
                v = tk.Label(cell, font=(mono[0], 12, "bold"), bg=self.FOND, padx=2)
                v.pack(anchor="w")
                Bulle(v, lambda n=name: self.bulle(n))
                self.values[name] = v
        flags = tk.Frame(self.frame, bg=self.FOND)
        flags.grid(row=len(REG_ROWS), column=0, columnspan=5, sticky="w", padx=5, pady=(4, 0))
        for n, _ in debug.FLAGS:
            lab = tk.Label(flags, text=n, width=2, font=(mono[0], 10, "bold"), bd=1,
                           relief="groove")
            lab.pack(side="left", padx=2)
            Bulle(lab, FLAG_NAMES[n])
            self.flags[n] = lab
        self.steps = tk.Label(flags, font=petit, fg=self.GRIS, bg=self.FOND)
        self.steps.pack(side="left", padx=10)
        self.show(None)

    def bulle(self, name):
        """Décimal, signé, binaire : au survol d'une case."""
        if self.vals is None:
            return "(programme non compilé)"
        return detail_valeur(name, self.vals[name])

    def show(self, vals):
        """vals : Session.register_values(), ou None (programme non compilé)."""
        self.vals = vals
        changed = self.suivi.changed(vals) if vals else set()
        digits = {n: d for row in REG_ROWS for n, d in row}
        for name, lab in self.values.items():
            text = "-" * digits[name] if vals is None else "%0*X" % (digits[name], vals[name])
            hot = name in changed
            lab.configure(text=text, fg=self.CHANGE if hot else self.VALEUR,
                          bg=self.FOND_CHANGE if hot else self.FOND)
        f = vals["F"] if vals else 0
        for n, bit in debug.FLAGS:
            bg, fg = self.ALLUME if f & bit else self.ETEINT
            self.flags[n].configure(bg=bg, fg=fg)
        self.steps.configure(text="(programme non compilé)" if vals is None
                             else "%s instructions" % format(vals["steps"], ",").replace(",", " "))


class Editeur:
    """La fenêtre de l'éditeur-débogueur."""

    BG_LINE, BG_BREAK = "#fff3a8", "#ffd6d6"
    STYLES = {"titre": {"foreground": "#888888"}, "note": {"foreground": "#888888"},   # onglet
              "change": {"foreground": "#c45a00", "background": "#fff1d6"}}       # Registres
    COLORS = {"motcle": "#0033b3", "fonction": "#871094", "chaine": "#a31515",
              "commentaire": "#4f7f4f", "numero": "#8a8a8a", "directive": "#00777a",
              "registre": "#a35a00", "etiquette": "#6b3f00"}

    def __init__(self, path=None, ram=16, zoom=3, memoire=None, muet=False):
        self.memoire = memoire
        import tkinter as tk
        from tkinter import ttk
        from .afficheur import Ecran, Pave, Touches
        from .son import HautParleur
        self.tk = tk
        self.hp = HautParleur(muet)
        self.ram = ram
        self.session = None
        self.path = None
        self.worker = None
        self.root = tk.Tk()
        self.root.title("Canon X-07 : éditeur-débogueur")
        self.root.geometry("1250x760")
        mono = (police_fixe(self.root), 10)
        self.mono = mono

        self.build_menus()
        bar = tk.Frame(self.root)
        bar.pack(fill="x", padx=4, pady=2)
        self.buttons = {}
        for key, symbol, tip, cmd in TOOLBAR:
            if key is None:                       # séparateur
                tk.Frame(bar, width=2, bd=1, relief="sunken").pack(side="left", fill="y",
                                                                   padx=6, pady=2)
                continue
            b = tk.Button(bar, text=symbol, width=2, font=("DejaVu Sans", 13),
                          command=lambda c=cmd: getattr(self, c[0])(*c[1:]))
            b.pack(side="left", padx=1)
            Bulle(b, tip)
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
        for tag, color in self.COLORS.items():           # coloration syntaxique
            self.text.tag_configure(tag, foreground=color)
        self.text.tag_configure("commentaire", font=mono + ("italic",))
        self.text.tag_configure("etiquette", font=mono + ("bold",))
        self.text.tag_configure("courante", background=self.BG_LINE)
        self.text.tag_configure("arret", background=self.BG_BREAK)
        self.text.tag_raise("courante")
        self.gutter.bind("<Button-1>", self.gutter_click)
        self.text.bind("<<Modified>>", self.on_modified)
        self.recolor_pending = None
        for ev in ("<KeyRelease>", "<<Paste>>", "<<Cut>>", "<<Undo>>", "<<Redo>>"):
            self.text.bind(ev, self.schedule_colors, add="+")
        self.text.bind("<Configure>", lambda e: self.draw_gutter())
        panes.add(left, stretch="always", minsize=420)

        right = tk.Frame(panes)
        self.screen_hint = tk.Label(right, anchor="w")
        self.screen_hint.pack(fill="x")
        row = tk.Frame(right)                    # l'écran, et le pavé de flèches du X-07
        row.pack(anchor="w", pady=2)
        self.ecran = Ecran(row, zoom)
        self.ecran.canvas.pack(side="left")
        self.touches = Touches(self.root, self.running_machine)
        self.pave = Pave(row, self.touches, size=int(self.ecran.canvas["height"]),
                         bg=row["bg"])                  # aussi haut que l'écran
        self.pave.canvas.pack(side="left", padx=(14, 0))
        c = self.ecran.canvas
        c.bind("<Button-1>", lambda e: c.focus_set())
        c.bind("<Key>", self.screen_key)
        c.bind("<KeyRelease>", self.screen_key_release)
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
        self.regs = Registres(right, mono)
        self.regs.frame.pack(fill="x", pady=2)
        tabs = ttk.Notebook(right)
        tabs.pack(fill="both", expand=True)
        self.panels = {}
        for key, title in (("variables", "Variables"), ("registres", "Registres"),
                           ("code", "Code machine"), ("pile", "Pile"), ("messages", "Messages")):
            t = tk.Text(tabs, font=mono, height=12, wrap="none")
            t.tag_configure("change", foreground="#c00000")
            for style, opts in self.STYLES.items():      # onglet « Registres »
                t.tag_configure("s_" + style, **opts)
            t.tag_configure("s_nom", font=mono + ("bold",))
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
        r.bind("<Control-S>", lambda e: self.save_as_dialog())       # Ctrl+Maj+S
        r.bind("<Control-o>", lambda e: self.open_dialog())
        r.protocol("WM_DELETE_WINDOW", self.close)
        if path:
            self.load(path)
        self.update_buttons()
        self.cadence = Cadence(self.root, self.tick)

    # -------------------------------------------------- menus
    def build_menus(self):
        tk = self.tk
        bar = tk.Menu(self.root)
        self.menu_items = []                      # (menu, libellé, clé d'état)

        def add(menu, label, cmd, key, accel=None):
            menu.add_command(label=label, command=cmd, accelerator=accel)
            self.menu_items.append((menu, label, key))

        fichier = tk.Menu(bar, tearoff=False)
        nouveau = tk.Menu(fichier, tearoff=False)
        for ext, label in KINDS:
            nouveau.add_command(label="%s (%s)" % (label, ext),
                                command=lambda e=ext: self.new_dialog(e))
        fichier.add_cascade(label="Nouveau", menu=nouveau)
        self.menu_items.append((fichier, "Nouveau", "nouveau"))
        add(fichier, "Ouvrir…", self.open_dialog, "ouvrir", "Ctrl+O")
        add(fichier, "Enregistrer", self.save, "enregistrer", "Ctrl+S")
        add(fichier, "Enregistrer sous…", self.save_as_dialog, "enregistrer_sous",
            "Ctrl+Maj+S")
        fichier.add_separator()
        fichier.add_command(label="Quitter", command=self.close)
        bar.add_cascade(label="Fichier", menu=fichier)

        execution = tk.Menu(bar, tearoff=False)
        add(execution, "Compiler", self.compile, "compiler")
        add(execution, "Continuer", self.do_run, "continuer", "F5")
        add(execution, "Pause", self.do_pause, "pause", "F9")
        execution.add_separator()
        add(execution, "Ligne suivante", lambda: self.do_step("over"), "ligne", "F10")
        add(execution, "Entrer dans la procédure", lambda: self.do_step("into"), "entrer",
            "F11")
        add(execution, "Sortir de la procédure", lambda: self.do_step("out"), "sortir",
            "Maj+F11")
        add(execution, "Une instruction machine", lambda: self.do_step("instr"), "instr")
        execution.add_separator()
        add(execution, "Recommencer", self.restart, "reinit")
        add(execution, "Enlever tous les points d'arrêt", self.clear_breaks, "reinit")
        bar.add_cascade(label="Exécution", menu=execution)

        aide = tk.Menu(bar, tearoff=False)
        aide.add_command(label="Utilisation…", command=self.show_help)
        bar.add_cascade(label="Aide", menu=aide)
        self.root.configure(menu=bar)
        self.menubar = bar

    def show_help(self):
        from tkinter import messagebox
        messagebox.showinfo("Aide", AIDE, parent=self.root)

    def clear_breaks(self):
        if self.session is None:
            return
        for line in list(self.session.break_lines):
            self.session.toggle_break(line)
        self.sync_text_from_breaks()
        self.refresh()

    # -------------------------------------------------- fichier
    FILETYPES = [("Programmes X-07", "*.bas *.qbas *.asm"), ("BASIC du X-07", "*.bas"),
                 ("QuickBASIC", "*.qbas"), ("Assembleur", "*.asm"), ("Tous", "*")]

    def open_dialog(self):
        from tkinter import filedialog
        if self.busy() or not self.confirm_discard():
            return
        p = filedialog.askopenfilename(filetypes=self.FILETYPES)
        if p:
            self.load(p)

    def confirm_discard(self):
        """Modifications non enregistrées : proposer de les enregistrer.
        Rend False si l'utilisateur annule."""
        if not (self.path and self.text.edit_modified()):
            return True
        from tkinter import messagebox
        answer = messagebox.askyesnocancel(
            "Modifications", "Enregistrer les modifications de %s ?"
            % os.path.basename(self.path), parent=self.root)
        if answer is None:
            return False
        if answer:
            self.save()
        return True

    def new_dialog(self, ext):
        from tkinter import filedialog
        if self.busy() or not self.confirm_discard():
            return
        label = dict(KINDS)[ext]
        p = filedialog.asksaveasfilename(
            title="Nouveau programme : %s" % label, defaultextension=ext,
            initialfile="nouveau" + ext, filetypes=[(label, "*" + ext), ("Tous", "*")])
        if p:
            self.new_file(p)

    def new_file(self, path):
        """Crée le programme (modèle selon l'extension) et l'ouvre."""
        ext = os.path.splitext(path)[1].lower()
        if ext not in TEMPLATES:
            self.set_status("extension inconnue : .bas, .qbas ou .asm")
            return False
        with open(path, "w", encoding="utf-8") as f:
            f.write(TEMPLATES[ext])
        self.load(path)
        self.set_status("nouveau programme %s : modifiez-le, puis ▶"
                        % os.path.basename(path))
        return True

    def save_as_dialog(self):
        from tkinter import filedialog
        if not self.path or self.busy():
            return
        ext = os.path.splitext(self.path)[1].lower()
        p = filedialog.asksaveasfilename(
            title="Enregistrer sous", defaultextension=ext,
            initialdir=os.path.dirname(os.path.abspath(self.path)),
            initialfile=os.path.basename(self.path), filetypes=self.FILETYPES)
        if p:
            self.save_as(p)

    def save_as(self, path):
        """Enregistre le texte sous un autre nom, qui devient le fichier ouvert
        (les points d'arrêt sont gardés ; à recompiler)."""
        if os.path.splitext(path)[1].lower() not in TEMPLATES:
            self.set_status("extension inconnue : .bas, .qbas ou .asm")
            return False
        if self.session is not None:
            self.sync_breaks_from_text()
            breaks = set(self.session.break_lines)
        else:
            breaks = set()
        with open(path, "w", encoding="utf-8") as f:
            f.write(self.text.get("1.0", "end-1c"))
        self.path = path
        self.session = Session(path, self.ram, self.memoire,
                               self.session.image if self.session else None)
        self.session.break_lines = breaks
        self.text.edit_modified(False)
        self.dirty = True
        self.root.title("Canon X-07 : %s" % os.path.basename(path))
        self.set_status("enregistré sous %s" % path)
        self.refresh()
        return True

    def load(self, path):
        with open(path, encoding="utf-8", errors="replace") as f:
            content = f.read()
        self.path = path
        self.session = Session(path, self.ram, self.memoire,
                               self.session.image if self.session else None)
        self.text.delete("1.0", "end")
        self.text.insert("1.0", content)
        self.text.edit_modified(False)
        self.text.edit_reset()
        self.colorize()
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

    def schedule_colors(self, event=None):
        if self.recolor_pending is None:
            self.recolor_pending = self.root.after(60, self.colorize)

    def colorize(self):
        """Mots-clés, fonctions, chaînes, commentaires et numéros de ligne en
        couleur (BASIC X-07 et QuickBASIC) ; instructions, directives, registres
        et étiquettes en assembleur."""
        self.recolor_pending = None
        t = self.text
        for tag in syntaxe.CATEGORIES:
            t.tag_remove(tag, "1.0", "end")
        kind = os.path.splitext(self.path or "")[1].lower().lstrip(".")
        for tag, line, a, b in syntaxe.zones(t.get("1.0", "end-1c"), kind):
            t.tag_add(tag, "%d.%d" % (line, a), "%d.%d" % (line, b))

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
            connect_speaker(self.session.m, self.hp)
        except Exception as e:                       # erreur de compilation : on l'affiche
            self.session.m = None
            self.set_status("erreur : %s" % e)
            self.show_text("messages", "erreur : %s" % e)
            self.tabs.select(self.panels["messages"])
            self.refresh()
            return False
        self.dirty = False
        self.previous = {}
        self.regs.suivi.reset()
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

        # le fil ne tient que la session, jamais la fenêtre : s'il en gardait la
        # dernière référence, Tcl (ou Qt) serait détruit hors du fil principal
        # (« Tcl_AsyncDelete: async handler deleted by the wrong thread »)
        session = self.session

        def work():
            try:
                action()
            except Exception as e:                  # erreur inattendue : affichée
                session.reason = "erreur : %s" % e
        self.worker = threading.Thread(target=work, daemon=True)
        self.worker.start()
        self.update_buttons()

    def do_run(self):
        self.start(self.session.run if self.session else None,
                   "en cours… (⏸ ou F9 pour arrêter)")

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

    def show_segments(self, key, lines):
        """Lignes de (texte, style) : Session.registres_detail()."""
        t = self.panels[key]
        t.configure(state="normal")
        t.delete("1.0", "end")
        for k, segs in enumerate(lines):
            for text, style in segs:
                t.insert("end", text, ("s_" + style,) if style else ())
            if k < len(lines) - 1:
                t.insert("end", "\n")
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
                          font=(self.mono[0], 9))
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
            self.regs.show(s.register_values())
            self.show_segments("registres", s.registres_detail(self.regs.suivi.base))
            self.show_variables(s.variables())
            self.show_text("code", s.disassembly())
            self.show_text("pile", s.stack())
        elif not (s and s.m):
            self.regs.show(None)
            self.show_text("registres", "(programme non compilé)")
        self.draw_gutter()
        self.update_buttons()

    def state_of(self, key):
        run = self.busy()
        if key == "pause":
            return "normal" if run else "disabled"
        if key in ("ouvrir", "nouveau"):
            return "disabled" if run else "normal"
        return "normal" if self.session is not None and not run else "disabled"

    def update_buttons(self):
        for k, b in self.buttons.items():
            b.configure(state=self.state_of(k))
        for menu, label, key in getattr(self, "menu_items", []):
            menu.entryconfigure(label, state=self.state_of(key))

    def tick(self):
        self.touches.poll()
        s = self.session
        if s and s.m:
            self.ecran.refresh(s.m.lcd)
        if self.worker is not None and not self.worker.is_alive():
            self.worker = None
            reason = s.reason
            if s.finished:
                saved = s.save_memory()
                self.set_status("programme terminé (%s)%s : ↺ pour recommencer"
                                % (reason or "fin",
                                   "" if not saved else " ; mémoire enregistrée (OFF)"
                                   if s.memoire else " ; fichiers en RAM gardés"))
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
            send_key(s.m, event, self.touches)
            if not self.busy() and len(s.m.keys) > before:
                self.set_status("touches gardées pour le programme : %r ; ▶ pour continuer"
                                % "".join(s.m.keys))
        elif s and s.finished:
            self.set_status("programme terminé : ↺ pour recommencer, puis tapez")
        return "break"

    def screen_key_release(self, event):
        from .afficheur import release_key
        release_key(event, self.touches)
        return "break"

    def running_machine(self):
        """Machine du programme (pour le pavé de flèches), None s'il n'y en a pas."""
        s = self.session
        return s.m if s is not None and s.m is not None and not s.finished else None

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
        if not self.confirm_discard():
            return
        if self.session and self.session.m:
            self.session.m.stop_requested = True
        if self.recolor_pending is not None:
            self.root.after_cancel(self.recolor_pending)
        self.cadence.stop()
        self.hp.close()
        self.root.destroy()

    def mainloop(self):
        self.root.mainloop()
