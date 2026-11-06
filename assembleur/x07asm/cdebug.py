"""Variables d'un programme C ou Quick C pendant le débogage.

SDCC, avec --debug, écrit dans le fichier .adb la place et le type de chaque
variable :
    S:G$compte$0_0$0({2}SI:S),E,0,0              globale (adresse : son symbole)
    S:Lprog.main$x$1_0$4({8}ST__00000000:S),B,1,-12   locale, sur la pile, IX-12
    S:Lprog.main$i$1_0$4({2}SI:S),R,0,0,[c,b]   locale, dans les registres BC
    T:Fprog$__00000000[({0}S:S$b$0_0$0({8}DA8d,SC:U),Z,0,0)]   structure
Les locales se lisent par rapport à IX, le cadre de pile que la fonction pose
en entrant (PUSH IX / LD IX,0 / ADD IX,SP).  Le type real de x07.h, une
structure d'un seul champ b de 8 octets, est affiché comme un nombre : le réel
en double précision du X-07, en BCD.
"""
import re

_SYM = re.compile(r"S:(G|F[\w.]+|L[\w.]+)\$(\w+)\$\d+_\d+\$\d+\((\{\d+\}[^)]*)\),(\w),(\d+),(-?\d+)"
                  r"(?:,\[([^\]]*)\])?")
_FUNC = re.compile(r"F:(?:G|F[\w.]+)\$(\w+)\$")
_STRUCT = re.compile(r"T:F[\w.]+\$(\w+)\[(.*)\]")
PROLOGUE = bytes([0xDD, 0xE5, 0xDD, 0x21, 0x00, 0x00, 0xDD, 0x39])   # cadre IX
REGS = {"c,b": "BC", "e,d": "DE", "l,h": "HL", "iyl,iyh": "IY"}


def decode_real(b):
    """Texte du réel en double précision du X-07 (8 octets BCD) : bit 7 du premier
    octet = signe, ses 7 autres bits = exposant + $40, puis 14 chiffres :
    valeur = 0,d1d2...d14 x 10^exposant."""
    if not b[0]:
        return "0"
    digits = "".join("%02X" % x for x in b[1:8])
    if not digits.isdigit():
        return "?? " + " ".join("%02X" % x for x in b)
    d = digits.rstrip("0") or "0"
    e = (b[0] & 0x7F) - 0x40                  # valeur = 0,d x 10^e
    if 0 < e <= 14:
        whole, frac = (d + "0" * e)[:e], d[e:]
        text = whole + ("." + frac if frac else "")
    elif -8 < e <= 0:
        text = "0." + "0" * -e + d
    else:
        text = d[0] + ("." + d[1:] if d[1:] else "") + "E%+d" % (e - 1)
    return ("-" if b[0] & 0x80 else "") + text


class Var:
    __slots__ = ("name", "size", "chain", "signed", "space", "offset", "regs")

    def __init__(self, name, typ, space, offset, regs):
        m = re.fullmatch(r"\{(\d+)\}(.*?)(?::([SU]))?", typ)
        self.name = name
        self.size = int(m.group(1))
        self.chain = m.group(2).split(",")
        self.signed = m.group(3) != "U"
        self.space, self.offset = space, int(offset)
        self.regs = regs


class CDebugInfo:
    """Globales et locales d'un programme C, lues dans le .adb de SDCC."""

    def __init__(self, adb_text, symbols, prog_range):
        self.symbols = symbols                    # nom C -> adresse
        self.prog_range = prog_range
        self.globals, self.locals, self.functions = [], {}, []
        self.reals = set()                        # structures qui sont le type real
        for line in adb_text.splitlines():
            m = _STRUCT.match(line)
            if m and re.fullmatch(r"\(\{0\}S:S\$b\$\d+_\d+\$\d+\(\{8\}DA8d,SC:U\),Z,0,0\)",
                                  m.group(2)):
                self.reals.add("ST" + m.group(1))
                continue
            m = _FUNC.match(line)
            if m:
                self.functions.append(m.group(1))
                continue
            m = _SYM.match(line)
            if not m:
                continue
            scope, name, typ, space, _, offset, regs = m.groups()
            if typ.startswith("{2}DF") or "DF," in typ:        # une fonction
                continue
            v = Var(name, typ, space, offset, regs)
            if scope.startswith("L"):
                func = scope.split(".", 1)[1] if "." in scope else scope[1:]
                self.locals.setdefault(func, []).append(v)
            elif name in symbols:
                self.globals.append(v)

    # ------------------------------------------------ valeurs
    def text(self, rd, addr, size, chain, signed):
        head = chain[0] if chain else ""
        if head.startswith("DA"):                 # tableau : les premiers éléments
            n = int(re.match(r"DA(\d+)", head).group(1)) or 1
            esz = max(1, size // n)
            items = [self.text(rd, addr + k * esz, esz, chain[1:], signed)
                     for k in range(min(n, 8))]
            return "{%s%s}" % (", ".join(items), ", …" if n > 8 else "")
        if head.startswith("D"):                  # pointeur
            return "$%04X" % (rd(addr) | rd(addr + 1) << 8)
        if head in self.reals:
            return decode_real([rd(addr + k) for k in range(8)])
        if head in ("SC", "SI", "SS", "SL", "SB") or size in (1, 2, 4):
            v = sum(rd(addr + k) << 8 * k for k in range(size))
            if signed and v >= 1 << (8 * size - 1):
                v -= 1 << 8 * size
            if size == 1 and 32 <= (v & 0xFF) < 127:
                return "%d '%s'" % (v, chr(v & 0xFF))
            return str(v)
        return " ".join("%02X" % rd(addr + k) for k in range(min(size, 16)))

    def current_function(self, m):
        """(nom, adresse) de la fonction du programme qui contient PC, ou None."""
        pc = m.pc
        lo, hi = self.prog_range
        if not lo <= pc <= hi:
            return None
        starts = sorted((a, n) for n, a in self.symbols.items() if n in self.functions)
        others = sorted(a for n, a in self.symbols.items()
                        if not n.startswith("LN_") and n != "VARS_END")
        for k, (a, n) in enumerate(starts):
            end = next((b for b in others if b > a), hi + 1)
            if a <= pc < end:
                return n, a
        return None

    def lines(self, m):
        """« nom = valeur » : globales, puis locales de la fonction en cours."""
        rd = m.rd
        out = []
        for v in sorted(self.globals, key=lambda v: v.name):
            a = self.symbols[v.name]
            out.append("%s = %s   ($%04X)" % (v.name, self.text(rd, a, v.size, v.chain,
                                                                v.signed), a))
        cur = self.current_function(m)
        if cur is None:
            return out
        name, start = cur
        local = [v for v in self.locals.get(name, [])
                 if not v.name.startswith(("_qc_", "sloc"))]     # temporaires du traducteur, de SDCC
        if not local:
            return out
        out.append("— %s —" % name)
        framed = bytes(rd(start + k) for k in range(len(PROLOGUE))) == PROLOGUE
        if framed and m.pc < start + len(PROLOGUE):
            out.append("(entrée de %s : variables pas encore créées)" % name)
            return out
        ix = m.get16("IX")
        for v in local:
            if v.space == "B":                    # sur la pile, par rapport à IX
                if not framed:
                    out.append("%s : (pile, sans cadre IX)" % v.name)
                    continue
                a = (ix + v.offset) & 0xFFFF
                out.append("%s = %s   (IX%+d)" % (v.name, self.text(rd, a, v.size, v.chain,
                                                                    v.signed), v.offset))
            elif v.space == "R" and v.regs:       # dans des registres : valeur actuelle
                pair = REGS.get(v.regs)
                if pair and v.size == 2:
                    val = m.get16(pair)
                    if v.signed and val >= 0x8000:
                        val -= 0x10000
                    out.append("%s = %d   (registre %s)" % (v.name, val, pair))
                elif v.size == 1 and len(v.regs) == 1:
                    val = m.r[v.regs.upper()]
                    if v.signed and val >= 0x80:
                        val -= 0x100
                    out.append("%s = %d   (registre %s)" % (v.name, val, v.regs.upper()))
                else:
                    out.append("%s : (registres %s)" % (v.name, v.regs))
            else:
                out.append("%s : (optimisée par SDCC, sans place fixe)" % v.name)
        return out
