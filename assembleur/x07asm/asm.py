"""Assembleur Z80 / NSC800 pour le Canon X-07 (deux passes).

Syntaxe d'une ligne :   [étiquette[:]]  [instruction|directive  opérandes]  [; commentaire]

Directives :
  ORG expr                     adresse d'implantation
  nom EQU expr  /  nom = expr  constante
  DB / DEFB / BYTE  e1,"texte",...      octets
  DW / DEFW / WORD  e1,e2,...           mots (poids faible d'abord)
  DM / DEFM / TEXT  "texte",...         chaîne
  DZ / DEFZ / ASCIZ "texte"             chaîne terminée par 00
  DS / DEFS / BLOCK n[,remplissage]     réserve n octets
  ALIGN n                               aligne sur un multiple de n
  ENTRY expr                            adresse de lancement (EXEC)
  INCLUDE "fichier"   INCBIN "fichier"
  IF expr / ELSE / ENDIF                assemblage conditionnel
  ASSERT expr[,"message"]
  END

Étiquettes locales : un nom commençant par « . » est rattaché à la
dernière étiquette globale (BOUCLE.1 ...).
Les symboles du X-07 (x07sym) sont prédéfinis, sauf avec x07=False.
"""
import os
import re

from . import z80
from .expr import evaluate, ExprError, Undefined
from . import x07sym


class AsmError(Exception):
    def __init__(self, msg, src=None):
        self.msg, self.src = msg, src
        loc = "%s:%d: " % (src[0], src[1]) if src else ""
        super().__init__(loc + msg)


DIRECTIVES = {"ORG", "EQU", "=", "DB", "DEFB", "BYTE", "DW", "DEFW", "WORD",
              "DM", "DEFM", "TEXT", "DZ", "DEFZ", "ASCIZ", "DS", "DEFS", "BLOCK",
              "ALIGN", "ENTRY", "INCLUDE", "INCBIN", "IF", "ELSE", "ENDIF",
              "ASSERT", "END"}

_ALU1 = {"SUB", "AND", "XOR", "OR", "CP"}      # forme officielle sans « A, »
_ALU2 = {"ADD", "ADC", "SBC"}                  # forme officielle avec « A, »


# ---------------------------------------------------------------- lecture

def _strip_comment(line):
    """Retire le commentaire (;) hors des chaînes.  Gère AF'."""
    out, i, q = [], 0, None
    while i < len(line):
        c = line[i]
        if q:
            out.append(c)
            if c == q:
                q = None
        elif c == ";":
            break
        elif c == '"':
            q = c
            out.append(c)
        elif c == "'":
            if line[max(0, i - 2):i].upper() == "AF" and not (i >= 3 and line[i - 3].isalnum()):
                out.append(c)                      # AF'
            elif i + 2 < len(line) and line[i + 2] == "'":
                out.append(line[i:i + 3])          # 'x'
                i += 2
            else:
                q = c
                out.append(c)
        else:
            out.append(c)
        i += 1
    return "".join(out).rstrip()


def split_operands(s):
    """Découpe aux virgules hors chaînes et parenthèses."""
    ops, cur, depth, q, i = [], [], 0, None, 0
    while i < len(s):
        c = s[i]
        if q:
            cur.append(c)
            if c == q:
                q = None
        elif c == '"':
            q = c
            cur.append(c)
        elif c == "'":
            prev = "".join(cur).strip().upper()
            if prev.endswith("AF") and not prev[:-2][-1:].isalnum():
                cur.append(c)
            elif i + 2 < len(s) and s[i + 2] == "'":
                cur.append(s[i:i + 3])
                i += 2
            else:
                q = c
                cur.append(c)
        elif c == "(":
            depth += 1
            cur.append(c)
        elif c == ")":
            depth -= 1
            cur.append(c)
        elif c == "," and depth == 0:
            ops.append("".join(cur).strip())
            cur = []
        else:
            cur.append(c)
        i += 1
    last = "".join(cur).strip()
    if last or ops:
        ops.append(last)
    return ops


_EQU_RE = re.compile(r"^\s*([A-Za-z_.@?][\w.@?]*)\s*:?\s*(?:=|[Ee][Qq][Uu]\b)(.*)$")


def parse_line(text):
    """-> (étiquette, mot-clé, texte des opérandes)."""
    line = _strip_comment(text.replace("\t", " "))
    if not line.strip():
        return None, None, ""
    m = _EQU_RE.match(line)
    if m:
        return m.group(1), "EQU", m.group(2).strip()
    label = None
    rest = line
    if line[0] not in " *":
        tok = line.split(None, 1)[0]
        if tok.endswith(":"):
            label = tok[:-1]
            rest = line[len(tok):]
        else:
            up = tok.upper()
            if up not in z80.MNEMONICS and up not in DIRECTIVES:
                label = tok
                rest = line[len(tok):]
    elif line[0] == "*":                        # ligne de commentaire
        return None, None, ""
    else:
        tok = line.split(None, 1)[0]
        if tok.endswith(":"):
            label = tok[:-1]
            rest = line.lstrip()[len(tok):]
    rest = rest.strip()
    if not rest:
        return label, None, ""
    if rest.startswith("="):
        return label, "EQU", rest[1:].strip()
    parts = rest.split(None, 1)
    return label, parts[0].upper(), parts[1].strip() if len(parts) > 1 else ""


def _string_literal(op):
    if len(op) >= 2 and op[0] in "\"'" and op[-1] == op[0] and op[0] not in op[1:-1]:
        return op[1:-1]
    return None


# ---------------------------------------------------------------- opérandes

def _outer_parens(t):
    if not (t.startswith("(") and t.endswith(")")):
        return False
    depth = 0
    for i, c in enumerate(t):
        if c == "(":
            depth += 1
        elif c == ")":
            depth -= 1
            if depth == 0 and i != len(t) - 1:
                return False
    return True


def classify(op):
    t = op.strip()
    u = t.upper().replace(" ", "")
    if u in z80.REGISTERS:
        return ("reg", u)
    if _outer_parens(t):
        inner = t[1:-1].strip()
        ui = inner.upper().replace(" ", "")
        if ui in ("HL", "BC", "DE", "SP", "C", "IX", "IY"):
            return ("reg", "(%s)" % ui)
        if ui[:2] in ("IX", "IY") and len(ui) > 2 and ui[2] in "+-":
            return ("idx", ui[:2], inner.strip()[2:])
        return ("ind", inner)
    return ("imm", t)


# ---------------------------------------------------------------- assembleur

class Assembler:
    def __init__(self, x07=True, defines=None):
        self.predef = x07sym.all_symbols() if x07 else {}
        self.defines = {k.upper(): v for k, v in (defines or {}).items()}
        self.errors = []
        self.warnings = []

    # -- symboles
    def _fullname(self, name):
        name = name.upper()
        if name.startswith("."):
            return (self.last_global or "") + name
        return name

    def lookup(self, name):
        name = self._fullname(name)
        if name in self.symbols:
            return self.symbols[name]
        if name in self.defines:
            return self.defines[name]
        if name in self.predef:
            self.used_predef.add(name)
            return self.predef[name]
        if self.lenient:
            self.undefined = True
            return 0
        raise Undefined(name)

    def eval(self, text, strict=False):
        self.undefined = False
        saved = self.lenient
        if strict:
            self.lenient = False
        try:
            return evaluate(text, self.lookup, self.pc)
        finally:
            self.lenient = saved

    def define(self, name, value, src):
        if name.upper() in z80.REGISTERS or name.upper() in z80.MNEMONICS:
            raise AsmError("nom réservé : %s" % name, src)
        if not name.startswith("."):
            self.last_global = name.upper()
        full = self._fullname(name)
        if self.passno == 1:
            if full in self.symbols:
                raise AsmError("symbole défini deux fois : %s" % full, src)
            self.symbols[full] = value
        elif self.symbols.get(full) != value and not self.errors:
            # (après une première erreur, les décalages qui en découlent sont tus)
            raise AsmError("erreur de phase sur %s" % full, src)

    # -- sources
    def load(self, path, depth=0, src=None):
        if depth > 16:
            raise AsmError("INCLUDE trop imbriqués", src)
        try:
            with open(path, "rb") as f:
                raw = f.read()
            try:
                text = raw.decode("utf-8")
            except UnicodeDecodeError:
                text = raw.decode("latin-1")
        except OSError as e:
            raise AsmError("lecture impossible de %s : %s" % (path, e.strerror), src)
        return self.expand(text, path, depth)

    def expand(self, text, name, depth=0):
        lines = []
        for n, line in enumerate(text.splitlines(), 1):
            src = (name, n)
            label, kw, ops = parse_line(line)
            if kw == "INCLUDE":
                fn = _string_literal(ops) or ops
                base = os.path.dirname(name) if os.path.exists(name) else ""
                if label:
                    lines.append((src, line.split(None, 1)[0]))
                lines += self.load(os.path.join(base, fn), depth + 1, src)
            else:
                lines.append((src, line))
        return lines

    # -- assemblage
    def assemble_file(self, path):
        return self.assemble_lines(self.load(path))

    def assemble_text(self, text, name="<source>"):
        return self.assemble_lines(self.expand(text, name))

    def assemble_lines(self, lines):
        self.symbols = {}
        self.used_predef = set()
        for self.passno in (1, 2):
            self.lenient = self.passno == 1
            self.mem = {}
            self.listing = []
            self.entry = None
            self.first = None
            self.pc = 0
            self.last_global = None
            self.errors = []
            self.warnings = []
            cond = []
            for src, text in lines:
                active = all(cond)
                try:
                    label, kw, ops = parse_line(text)
                    if kw in ("IF", "ELSE", "ENDIF"):
                        self._cond(kw, ops, cond, active, src)
                        self.listing.append((None, [], src, text))
                        continue
                    if not active:
                        self.listing.append((None, [], src, text))
                        continue
                    if kw == "END":
                        self.listing.append((None, [], src, text))
                        break
                    self._line(label, kw, ops, src, text)
                except AsmError as e:
                    self.errors.append(e)
                    self.listing.append((None, [], src, text))
                except ExprError as e:
                    self.errors.append(AsmError(str(e), src))
                    self.listing.append((None, [], src, text))
            if cond:
                self.errors.append(AsmError("IF sans ENDIF"))
            if self.errors and self.passno == 1:
                break
        if self.entry is None:
            self.entry = self.first if self.first is not None else 0
        return self.mem

    def _cond(self, kw, ops, cond, active, src):
        if kw == "IF":
            v = self.eval(ops, strict=True) if active else 0
            cond.append(bool(v))
        elif not cond:
            raise AsmError("%s sans IF" % kw, src)
        elif kw == "ELSE":
            cond[-1] = not cond[-1]
        else:
            cond.pop()

    def emit(self, data, src):
        for b in data:
            a = self.pc & 0xFFFF
            if a in self.mem and self.passno == 2:
                raise AsmError("chevauchement en $%04X" % a, src)
            self.mem[a] = b & 0xFF
            self.pc += 1
        if self.pc > 0x10000:
            raise AsmError("dépassement de l'espace mémoire", src)

    def _line(self, label, kw, ops, src, text):
        start = self.pc
        if kw == "EQU":
            if not label:
                raise AsmError("EQU sans nom", src)
            v = self.eval(ops)
            if self.passno == 1 and self.undefined:
                raise AsmError("EQU : symbole non défini à cet endroit", src)
            self.define(label, v, src)
            self.listing.append((v, [], src, text))
            return
        if label:
            self.define(label, self.pc, src)
        if kw is None:
            self.listing.append((self.pc if label else None, [], src, text))
            return
        if kw in DIRECTIVES:
            data = self._directive(kw, ops, src)
        else:
            data = self._instruction(kw, ops, src)
        if data:
            if self.first is None:
                self.first = start
            self.emit(data, src)
        shown = start if (data or label or kw in z80.MNEMONICS) else None
        if kw in ("ORG", "DS", "DEFS", "BLOCK", "ALIGN"):
            shown = self.pc if kw == "ORG" else start
        self.listing.append((shown, data or [], src, text))

    def _directive(self, kw, ops, src):
        if kw == "ORG":
            self.pc = self._word(self.eval(ops, strict=True), src)
            return []
        if kw == "ENTRY":
            self.entry = self._word(self.eval(ops), src)
            return []
        if kw in ("DB", "DEFB", "BYTE", "DM", "DEFM", "TEXT", "DZ", "DEFZ", "ASCIZ"):
            out = []
            for op in split_operands(ops):
                s = _string_literal(op)
                if s is not None:
                    if any(ord(c) > 255 for c in s):
                        raise AsmError("caractère hors du jeu 8 bits dans %s" % op, src)
                    out += [ord(c) for c in s]
                else:
                    out.append(self._byte(self.eval(op), src))
            if kw in ("DZ", "DEFZ", "ASCIZ"):
                out.append(0)
            return out
        if kw in ("DW", "DEFW", "WORD"):
            out = []
            for op in split_operands(ops):
                v = self._word(self.eval(op), src)
                out += [v & 0xFF, v >> 8]
            return out
        if kw in ("DS", "DEFS", "BLOCK"):
            parts = split_operands(ops)
            n = self.eval(parts[0], strict=True)
            fill = self._byte(self.eval(parts[1]), src) if len(parts) > 1 else 0
            if n < 0:
                raise AsmError("taille négative", src)
            if len(parts) > 1:
                return [fill] * n
            self.pc += n                         # réservation sans remplissage
            return []
        if kw == "ALIGN":
            n = self.eval(ops, strict=True)
            if n > 0:
                self.pc += (-self.pc) % n
            return []
        if kw == "INCBIN":
            fn = _string_literal(ops) or ops
            base = os.path.dirname(src[0]) if os.path.exists(src[0]) else ""
            try:
                with open(os.path.join(base, fn), "rb") as f:
                    return list(f.read())
            except OSError as e:
                raise AsmError("INCBIN : %s" % e.strerror, src)
        if kw == "ASSERT":
            parts = split_operands(ops)
            if self.passno == 2 and not self.eval(parts[0], strict=True):
                msg = _string_literal(parts[1]) if len(parts) > 1 else parts[0]
                raise AsmError("ASSERT : %s" % msg, src)
            return []
        raise AsmError("directive inattendue : %s" % kw, src)

    def _byte(self, v, src):
        if not -128 <= v <= 255:
            raise AsmError("valeur hors octet : %d" % v, src)
        return v & 0xFF

    def _word(self, v, src):
        if not -32768 <= v <= 65535:
            raise AsmError("valeur hors mot : %d" % v, src)
        return v & 0xFFFF

    # -- instructions
    def _instruction(self, mnem, ops_text, src):
        if mnem not in z80.MNEMONICS:
            raise AsmError("instruction inconnue : %s" % mnem, src)
        ops = split_operands(ops_text)
        cls = [classify(o) for o in ops]
        r = self._match(mnem, cls, src)
        if r is None and mnem in _ALU2 and len(cls) == 1:
            r = self._match(mnem, [("reg", "A")] + cls, src)
        if r is None and mnem in _ALU1 and len(cls) == 2 and cls[0] == ("reg", "A"):
            r = self._match(mnem, cls[1:], src)
        if r is None:
            raise AsmError("opérandes incorrects : %s %s" % (mnem, ops_text), src)
        tpl, vals = r
        return tpl.encode(vals)

    def _match(self, mnem, cls, src):
        for tpl in z80.ENCODE.get((mnem, len(cls)), ()):
            vals = {}
            ok = True
            for top, c in zip(tpl.ops, cls):
                if not self._match_op(top, c, vals, tpl, src):
                    ok = False
                    break
            if ok:
                return tpl, vals
        return None

    def _match_op(self, top, c, vals, tpl, src):
        kind = c[0]
        if isinstance(top, int):                         # BIT n, IM n, RST n
            if kind != "imm":
                return False
            v = self.eval(c[1])
            if self.undefined:
                if self.passno == 2:
                    raise AsmError("valeur indéfinie", src)
                return True
            if tpl.mnem == "RST" and 1 <= v <= 7:
                v *= 8
            return v == top
        if isinstance(top, str) and top not in z80.PLACEHOLDERS:
            return kind == "reg" and c[1] == top
        if top in (z80.N, z80.NN, z80.E):
            if kind != "imm":
                return False
            v = self.eval(c[1])
            if top == z80.N:
                vals[top] = self._byte(v, src)
            elif top == z80.NN:
                vals[top] = self._word(v, src)
            else:
                d = (v - (self.pc + tpl.size)) & 0xFFFF   # le PC reboucle en $FFFF
                if d >= 0x8000:
                    d -= 0x10000
                if self.passno == 2 and not -128 <= d <= 127:
                    raise AsmError("saut relatif hors de portée (%+d)" % d, src)
                vals[top] = d if -128 <= d <= 127 else 0
            return True
        if top in (z80.PORT, z80.MEM):
            if kind != "ind":
                return False
            v = self.eval(c[1])
            vals[top] = self._byte(v, src) if top == z80.PORT else self._word(v, src)
            return True
        if top in (z80.IXD, z80.IYD):
            reg = "IX" if top == z80.IXD else "IY"
            if kind == "reg" and c[1] == "(%s)" % reg:
                vals[top] = 0
                return True
            if kind == "idx" and c[1] == reg:
                d = self.eval(c[2])
                if not -128 <= d <= 127:
                    raise AsmError("déplacement hors de portée : %d" % d, src)
                vals[top] = d
                return True
            return False
        return False

    # -- sorties
    def listing_text(self):
        out = []
        for addr, data, src, text in self.listing:
            a = "%04X" % (addr & 0xFFFF) if addr is not None else "    "
            chunks = [data[i:i + 4] for i in range(0, len(data), 4)] or [[]]
            for k, ch in enumerate(chunks):
                hexs = " ".join("%02X" % b for b in ch)
                if k == 0:
                    out.append("%s  %-11s %5d  %s" % (a, hexs, src[1], text.rstrip()))
                else:
                    out.append("%04X  %-11s" % ((addr + 4 * k) & 0xFFFF, hexs))
        out.append("")
        out.append("Symboles :")
        for name in sorted(self.symbols):
            out.append("  %-20s $%04X" % (name, self.symbols[name] & 0xFFFF))
        if self.used_predef:
            out.append("")
            out.append("Symboles X-07 utilisés :")
            for name in sorted(self.used_predef):
                out.append("  %-20s $%04X" % (name, self.predef[name]))
        return "\n".join(out) + "\n"


def assemble(text, x07=True, name="<source>"):
    """Raccourci : assemble un texte -> (Assembler, mémoire)."""
    a = Assembler(x07=x07)
    mem = a.assemble_text(text, name)
    return a, mem
