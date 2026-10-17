"""Débogueur des programmes machine du X-07, dans l'émulateur (vraie ROM).

Points d'arrêt, pas à pas (en entrant ou non dans les CALL), sortie de
routine, surveillance d'octets, registres, mémoire, pile, désassemblage.
Les adresses s'écrivent en hexadécimal ou par leur nom : étiquette du
programme, symbole de la ROM (x07sym), ligne BASIC (« ligne 40 »).
"""
import bisect
import re

from . import x07sym, z80
from .dis import Disassembler
from .sim import EXIT, SimError

FLAGS = (("S", 0x80), ("Z", 0x40), ("H", 0x10), ("P", 0x04), ("N", 0x02), ("C", 0x01))
REG8 = ("A", "F", "B", "C", "D", "E", "H", "L", "I", "R")
REG16 = ("AF", "BC", "DE", "HL", "IX", "IY", "SP", "PC")
RETS = ("RET", "RETI", "RETN")

AIDE = """\
Commandes (adresse : 3C40, $3C40, &H3C40, ÉTIQUETTE, ÉTIQUETTE+4, ligne 40) :
  c                 continuer jusqu'au prochain point d'arrêt
  s [n]             pas à pas : n instructions, en entrant dans les CALL
  n [n]             pas à pas en passant par-dessus CALL et RST
  f                 finir la routine en cours (jusqu'à son RET)
  j ADR             continuer jusqu'à l'adresse
  b [ADR]           poser un point d'arrêt (sans adresse : la liste)
  w ADR             surveiller un octet : arrêt quand il change
  d ADR | d tout    enlever un point d'arrêt ou une surveillance
  r                 registres ; r HL=1234, r A=#65 (# : décimal), r PC=START
  x ADR [n]         mémoire (64 octets par défaut)
  m ADR v [v...]    écrire des octets
  l [ADR] [n]       désassembler (au PC par défaut)
  p [n]             pile
  v [NOM]           variables BASIC compilées : v, v N, v A$, v T%(3)
  k TEXTE           touches pour le programme (INKEY$) ; \\r : Entrée
  e [points]        écran du X-07 (points : graphismes compris, en braille)
  sym TEXTE         chercher un symbole
  q                 quitter
Entrée seule : répète la dernière commande (pratique pour s et n).
Ctrl+C (ou F9 dans la fenêtre) : interrompt le programme."""


class DebugError(Exception):
    pass


class Debugger:
    def __init__(self, m, symbols=None, listing=None, prog_range=None, out=None):
        self.m = m
        self.out = out or (lambda s: print(s, flush=True))
        self.symbols = {n.upper(): a for n, a in x07sym.all_symbols().items()}
        lo, hi = prog_range or (0, -1)
        names = {}                                       # adresse -> nom (programme)

        def rank(n):                                     # ligne BASIC, puis étiquettes
            return (0 if n.startswith("LN_") else 2 if re.fullmatch(r"G_\d+(_X)?", n) else 1, n)
        for n, a in sorted((symbols or {}).items(), key=lambda kv: rank(kv[0].upper())):
            n, a = n.upper(), a & 0xFFFF
            self.symbols[n] = a
            if lo <= a <= hi and a not in names:
                names[a] = n
        for a, (n, _) in x07sym.ROUTINE_AT.items():
            names.setdefault(a, n)
        self.names = names
        self.places = sorted(names)
        self.src = {}                                    # adresse -> ligne du source
        for addr, data, _, text in listing or []:
            if addr is not None and data:
                self.src.setdefault(addr & 0xFFFF, text.strip())
        self.basic = sorted((a, int(n[3:])) for n, a in (symbols or {}).items()
                            if re.fullmatch(r"LN_\d+", n.upper()))
        self.prog_range = (lo, hi)
        self.dis = Disassembler({}, labels=names)
        self.dis.labels, self.dis.used = dict(names), set()
        self.breaks = set()
        self.watches = {}                                # adresse -> dernière valeur
        self.pause = False                               # Ctrl+C, F9
        self.last = ""
        self.finished = False

    # -------------------------------------------------- adresses
    def addr(self, text):
        t = text.strip().upper()
        m = re.fullmatch(r"(?:LIGNE|LN_)\s*(\d+)", t)
        if m:
            n = int(m.group(1))
            for a, num in self.basic:
                if num == n:
                    return a
            raise DebugError("ligne BASIC %d introuvable" % n)
        m = re.fullmatch(r"(.+?)\s*([+-])\s*(\S+)", t)
        if m and not t.startswith(("$", "&", "0X", "#")):
            base = self.addr(m.group(1))
            off = self.number(m.group(3))
            return (base + off if m.group(2) == "+" else base - off) & 0xFFFF
        if t in self.symbols:
            return self.symbols[t] & 0xFFFF
        try:
            return self.number(t) & 0xFFFF
        except DebugError:
            raise DebugError("adresse inconnue : %s" % text.strip())

    def number(self, t):
        t = t.strip().upper()
        try:
            if t.startswith("#"):
                return int(t[1:])
            if t.startswith("$"):
                return int(t[1:], 16)
            if t.startswith("&H"):
                return int(t[2:], 16)
            if t.startswith("0X"):
                return int(t[2:], 16)
            return int(t, 16)
        except ValueError:
            raise DebugError("nombre invalide : %s" % t)

    def value(self, t):
        """Valeur : nombre, ou adresse d'un symbole."""
        try:
            return self.number(t)
        except DebugError:
            return self.addr(t)

    def where(self, a):
        """« ÉTIQUETTE+n » pour l'adresse a."""
        if a in self.names:
            return self.names[a]
        k = bisect.bisect_right(self.places, a) - 1
        if k >= 0 and a - self.places[k] < 0x200:
            return "%s+%d" % (self.names[self.places[k]], a - self.places[k])
        return ""

    def basic_line(self, a):
        lo, hi = self.prog_range
        if not self.basic or not lo <= a <= hi:
            return None
        k = bisect.bisect_right([x for x, _ in self.basic], a) - 1
        return self.basic[k][1] if k >= 0 else None

    # -------------------------------------------------- affichage
    def insn(self, a):
        """(taille, texte, commentaire) de l'instruction en a."""
        d = z80.decode(self.m.rd, a)
        if d is None:
            return 1, "DB    $%02X" % self.m.rd(a), "instruction invalide"
        t, vals, size = d
        text, comment = self.dis.format(a, t, vals)
        if t.mnem == "RST" and t.ops[0] in (0x08, 0x38):     # octet en ligne
            text += " / DB $%02X" % self.m.rd(a + 1)
            size += 1
        return size, text, comment

    def line(self, a, mark=" "):
        size, text, comment = self.insn(a)
        lab = self.where(a)
        note = comment or ""
        src = self.src.get(a)
        if src:                                      # source : seulement s'il apporte du neuf
            code, _, scomment = src.partition(";")
            code = re.sub(r"^\s*[A-Za-z_.][\w.]*:", "", code).strip()
            if re.sub(r"\s+", "", code).upper() != re.sub(r"\s+", "", text).upper():
                note = (note + " | " if note else "") + code
            if scomment.strip():
                note = (note + " ; " if note else "") + scomment.strip()
        return size, "%s %04X  %-14s %-24s%s" % (mark, a, lab[:14], text,
                                                   ("; " + note) if note else "")

    def regs_text(self, full=False):
        m, r = self.m, self.m.r
        flags = "".join(n if r["F"] & b else "-" for n, b in FLAGS)
        s = ("A=%02X F=%02X %s  BC=%04X DE=%04X HL=%04X  IX=%04X IY=%04X SP=%04X PC=%04X"
             % (r["A"], r["F"], flags, m.get16("BC"), m.get16("DE"), m.get16("HL"),
                m.ix, m.iy, m.sp, m.pc))
        if full:
            al = m.alt
            s += ("\nAF'=%02X%02X BC'=%02X%02X DE'=%02X%02X HL'=%02X%02X  I=%02X R=%02X  "
                  "interruptions %s  instructions %d"
                  % (al["A"], al["F"], al["B"], al["C"], al["D"], al["E"], al["H"], al["L"],
                     r["I"], r["R"], "permises" if m.iff else "masquées", m.steps))
        return s

    def show(self, reason=None):
        m = self.m
        head = "[%s]" % reason if reason else ""
        n = self.basic_line(m.pc)
        if n is not None:
            head += "%sligne BASIC %d" % ("  " if head else "", n)
        if head:
            self.out(head)
        if m.pc == EXIT:
            self.out("programme terminé : retour au BASIC (EXEC)")
            return
        self.out(self.regs_text())
        self.out(self.line(m.pc, ">")[1])

    # -------------------------------------------------- exécution
    def _decode_mnem(self, a):
        d = z80.decode(self.m.rd, a)
        return d[0].mnem if d else None

    def go(self, count=None, until=None):
        """Exécute jusqu'à un arrêt ; rend la raison (ou None après count pas)."""
        m = self.m
        if m.pc == EXIT:
            self.finished = True
            return "le programme est terminé"
        n = 0
        try:
            while True:
                if n and m.pc in self.breaks:
                    return "point d'arrêt"
                if self.pause or getattr(m, "debug_pause", False):
                    self.pause = m.debug_pause = False
                    return "interrompu"
                pc0, sp0 = m.pc, m.sp
                try:
                    m.step()
                except SimError as e:
                    m.pc = pc0
                    if "arrêt demandé" in str(e):
                        raise
                    if "interrompu" in str(e):
                        m.debug_pause = False
                        return "interrompu pendant l'attente d'une touche"
                    return "erreur : %s" % e
                n += 1
                for a, old in self.watches.items():
                    new = m.mem[a]
                    if new != old:
                        self.watches[a] = new
                        return "surveillance $%04X : %02X -> %02X (par l'instruction en %04X)" % (
                            a, old, new, pc0)
                if m.pc == EXIT:
                    self.finished = True
                    return "fin"
                if until is not None:
                    r = until(pc0, sp0)
                    if r:
                        return r if isinstance(r, str) else None
                if count is not None and n >= count:
                    return None
        except KeyboardInterrupt:
            return "interrompu (Ctrl+C)"

    def step_over(self):
        a = self.m.pc
        mnem = self._decode_mnem(a)
        if mnem not in ("CALL", "RST"):
            return self.go(count=1)
        size = self.insn(a)[0]
        after, sp = (a + size) & 0xFFFF, self.m.sp
        return self.go(until=lambda pc0, sp0: self.m.pc == after and self.m.sp >= sp)

    def finish(self):
        top = self.m.sp

        def returned(pc0, sp0):
            return self._decode_mnem(pc0) in RETS and self.m.sp == sp0 + 2 and sp0 >= top
        return self.go(until=returned)

    # -------------------------------------------------- commandes
    def command(self, line):
        """Exécute une commande ; rend False pour quitter."""
        line = line.strip()
        if not line:
            line = self.last
            if not line:
                return True
        self.last = line if line.split()[0] in ("s", "n", "l", "x") else ""
        parts = line.split()
        cmd, args = parts[0].lower(), parts[1:]
        rest = line[len(parts[0]):].strip()
        try:
            return self._command(cmd, args, rest)
        except DebugError as e:
            self.out("erreur : %s" % e)
            return True

    def _count(self, args):
        return self.number("#" + args[0]) if args else 1

    def _command(self, cmd, args, rest):
        m = self.m
        if cmd in ("q", "quitter"):
            return False
        if cmd in ("h", "?", "aide"):
            self.out(AIDE)
        elif cmd in ("c", "continuer"):
            self.show(self.go())
        elif cmd in ("s", "pas"):
            reason = None
            for _ in range(self._count(args)):
                reason = self.go(count=1)
                if reason:
                    break
            self.show(reason)
        elif cmd in ("n", "suivant"):
            reason = None
            for _ in range(self._count(args)):
                reason = self.step_over()
                if reason:
                    break
            self.show(reason)
        elif cmd in ("f", "finir"):
            self.show(self.finish() or "retour de la routine")
        elif cmd in ("j", "jusqua"):
            target = self.addr(rest)
            self.show(self.go(until=lambda pc0, sp0: m.pc == target) or "adresse atteinte")
        elif cmd in ("b", "arret"):
            if not rest:
                if not self.breaks:
                    self.out("aucun point d'arrêt")
                for a in sorted(self.breaks):
                    self.out(self.line(a, "*")[1])
            else:
                a = self.addr(rest)
                self.breaks.add(a)
                self.out("point d'arrêt en %04X %s" % (a, self.where(a)))
        elif cmd in ("w", "surveiller"):
            if not rest:
                for a, v in sorted(self.watches.items()):
                    self.out("$%04X = %02X %s" % (a, v, self.where(a)))
                if not self.watches:
                    self.out("aucune surveillance")
            else:
                a = self.addr(rest)
                self.watches[a] = m.mem[a]
                self.out("surveillance de $%04X (valeur %02X)" % (a, m.mem[a]))
        elif cmd in ("d", "enlever"):
            if rest.lower() == "tout":
                self.breaks.clear()
                self.watches.clear()
            else:
                a = self.addr(rest)
                if a not in self.breaks and a not in self.watches:
                    raise DebugError("rien en %04X" % a)
                self.breaks.discard(a)
                self.watches.pop(a, None)
        elif cmd in ("r", "registres"):
            if rest:
                for item in rest.replace(",", " ").split():
                    self.set_reg(item)
            self.out(self.regs_text(full=True))
        elif cmd in ("x", "memoire"):
            a = self.addr(args[0]) if args else m.pc
            n = self.number("#" + args[1]) if len(args) > 1 else 64
            self.dump(a, n)
            self.last = "x %X %d" % ((a + n) & 0xFFFF, n)
        elif cmd in ("m", "ecrire"):
            if len(args) < 2:
                raise DebugError("m ADR valeur [valeur...]")
            a = self.addr(args[0])
            for k, v in enumerate(args[1:]):
                m.wr(a + k, self.number(v) & 0xFF)
            m.cache.clear()
        elif cmd in ("l", "liste"):
            a = self.addr(args[0]) if args else m.pc
            n = self.number("#" + args[1]) if len(args) > 1 else 8
            for _ in range(n):
                size, text = self.line(a, ">" if a == m.pc else ("*" if a in self.breaks else " "))
                self.out(text)
                a = (a + size) & 0xFFFF
            self.last = "l %X %d" % (a, n)
        elif cmd in ("p", "pile"):
            n = self.number("#" + args[0]) if args else 8
            for k in range(n):
                a = (m.sp + 2 * k) & 0xFFFF
                v = m.rd16(a)
                note = "retour au BASIC" if v == EXIT else self.where(v)
                self.out("  %04X: %04X  %s" % (a, v, note))
        elif cmd in ("e", "ecran"):
            if rest.lower().startswith("p"):             # e points : graphismes compris
                self.out(m.lcd.braille())
            elif getattr(m, "real_display", False):      # la ROM dessine : texte lu à l'écran
                rows = m.lcd.text()
                self.out("\n".join(["+" + "-" * 20 + "+"] + ["|%s|" % r for r in rows]
                                    + ["+" + "-" * 20 + "+"]))
            else:
                self.out(m.screen_text())
        elif cmd in ("k", "touches"):
            if not rest:
                raise DebugError('k TEXTE : touches pour INKEY$ (\\r : Entrée), ex. k O\\r')
            m.keys += list(rest.encode().decode("unicode_escape"))
            self.out("touches en attente : %r" % "".join(m.keys))
        elif cmd in ("v", "variable"):
            self.show_vars(rest)
        elif cmd == "sym":
            key = rest.upper()
            found = sorted((a, n) for n, a in self.symbols.items() if key in n)
            for a, n in found[:40]:
                self.out("  %-20s $%04X" % (n, a))
            if len(found) > 40:
                self.out("  ... (%d en tout)" % len(found))
            if not found:
                self.out("aucun symbole ne contient « %s »" % rest)
        else:
            raise DebugError("commande inconnue : %s (aide : h)" % cmd)
        return True

    # -------------------------------------------------- variables BASIC compilées
    TAGS = {"%": "I", "!": "F", "#": "D"}

    def show_vars(self, rest):
        """v : toutes les variables simples ; v NOM, v NOM$, v T(3) : une seule."""
        if not rest:
            found = sorted(n for n in self.symbols if re.fullmatch(r"(V_\w+_[IFD]|S_\w+)", n))
            if not found:
                raise DebugError("pas de variables BASIC (programme assembleur ?)")
            for n in found:
                self.out("  %s" % self.var_text(n))
            return
        m = re.fullmatch(r"\s*([A-Za-z][A-Za-z0-9]*)([%!#$]?)\s*(?:\(\s*(\S+?)\s*\))?\s*", rest)
        if not m:
            raise DebugError("v NOM, v NOM$, v NOM%(3)")
        name, suf, idx = m.group(1).upper(), m.group(2), m.group(3)
        tags = [self.TAGS[suf]] if suf in self.TAGS else (["$"] if suf == "$" else ["I", "F", "D", "$"])
        shown = False
        for t in tags:
            if idx is None:
                lab = ("S_%s" % name) if t == "$" else "V_%s_%s" % (name, t)
            else:
                lab = ("AS_%s" % name) if t == "$" else "A%s_%s" % (t, name)
            if lab in self.symbols:
                self.out("  " + self.var_text(lab, None if idx is None else self.number("#" + idx)))
                shown = True
        if not shown:
            raise DebugError("variable %s%s introuvable" % (name, suf))

    def var_text(self, lab, index=None):
        a = self.symbols[lab]
        t = "$" if lab.startswith(("S_", "AS_")) else lab[1] if lab.startswith("A") else lab[-1]
        size = {"I": 2, "F": 4, "D": 8}.get(t, self.symbols.get("STRCAP", 80) + 1)
        if index is not None:
            a += index * size
        data = bytes(self.m.rd(a + k) for k in range(size))
        if t == "$":
            n = data[0]
            val = '"%s" (longueur %d)' % ("".join(chr(c) if 32 <= c < 127 else "." for c in
                                                   data[1:1 + n]), n)
        elif t == "I":
            val = str(int.from_bytes(data, "little", signed=True))
        else:
            val = self.float_text(data)
        name = lab.split("_", 1)[1]
        if t != "$":
            name = name.rsplit("_", 1)[0] if not lab.startswith("A") else name
        suffix = {"I": "%", "F": "!", "D": "#", "$": "$"}[t]
        idx = "(%d)" % index if index is not None else ""
        return "%s%s%s = %s   ($%04X)" % (name, suffix, idx, val, a)

    def float_text(self, data):
        """Nombre BCD du X-07, converti par la ROM (FOUT) sur une machine annexe."""
        from . import emu
        sym = x07sym.all_symbols()
        m2 = emu.boot(16)
        m2.mem[sym["FAC"]:sym["FAC"] + len(data)] = data
        m2.mem[sym["VALTYP"]] = len(data)
        m2.push(EXIT)
        m2.pc = sym["FOUT"]
        try:
            m2.run(m2.steps + 200_000)
        except SimError as e:
            return "? (%s)" % e
        a, out = m2.get16("HL"), []
        while m2.mem[a] and len(out) < 30:
            out.append(chr(m2.mem[a]))
            a += 1
        return "".join(out).strip()

    def set_reg(self, item):
        if "=" not in item:
            raise DebugError("écrire REG=valeur, par exemple HL=3C40")
        name, val = item.split("=", 1)
        name = name.strip().upper()
        v = self.value(val)
        m = self.m
        if name == "PC":
            m.pc = v & 0xFFFF
        elif name in REG16:
            m.set16(name, v)
        elif name in REG8:
            m.r[name] = v & 0xFF
        else:
            raise DebugError("registre inconnu : %s" % name)

    def dump(self, a, n):
        for row in range(0, n, 16):
            base = (a + row) & 0xFFFF
            data = [self.m.rd((base + k) & 0xFFFF) for k in range(min(16, n - row))]
            hexs = " ".join("%02X" % b for b in data)
            text = "".join(chr(b) if 32 <= b < 127 else "." for b in data)
            self.out("  %04X  %-47s  %s" % (base, hexs, text))

    # -------------------------------------------------- boucle
    def repl(self, read=input, script=()):
        """Boucle de commandes : d'abord script, puis read (None : fin)."""
        self.out("Débogueur X-07 : h pour l'aide, q pour quitter.")
        self.show("départ")
        pending = list(script)
        while True:
            if pending:
                line = pending.pop(0)
                self.out("(x07) %s" % line)
            elif read is None:
                return
            else:
                try:
                    line = read("(x07) ")
                except EOFError:
                    self.out("")
                    return
                except KeyboardInterrupt:
                    self.out("\n(q pour quitter)")
                    continue
            if not self.command(line):
                return
