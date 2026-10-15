"""Désassembleur Z80 / NSC800 pour le Canon X-07.

Deux stratégies :
  - balayage linéaire (par défaut) : tout ce qui n'est pas déclaré comme
    données est décodé comme du code ;
  - suivi du flot (trace=True) : seul le code atteint depuis les points
    d'entrée est décodé ; le reste devient des données (DB / DM).

Le texte produit se réassemble à l'identique avec l'assembleur.
Particularité du X-07 : RST 08 (SYNCHR) est suivi d'un octet en ligne.
"""
from . import z80
from . import x07sym

# instructions dont l'opérande NN est une adresse de code
_CODE_NN = {"JP", "CALL"}


class DataRange:
    def __init__(self, start, end, kind="b"):
        self.start, self.end, self.kind = start, end, kind

    def __contains__(self, a):
        return self.start <= a <= self.end


def parse_range(text):
    """« 1C61-1C67 », « 1C61-1C67:w », « t:1C61-1C67 » (hexadécimal)."""
    kind = "b"
    if ":" in text:
        a, b = text.split(":", 1)
        if a.lower() in ("b", "w", "t"):
            kind, text = a.lower(), b
        else:
            text, kind = a, b.lower()
    if kind not in ("b", "w", "t"):
        raise ValueError("type de données inconnu : %s (b, w ou t)" % kind)
    lo, _, hi = text.partition("-")
    lo = int(lo.lstrip("$&Hh"), 16)
    hi = int(hi.lstrip("$&Hh"), 16) if hi else lo
    return DataRange(lo, hi, kind)


class Item:
    """Ligne produite : instruction ou données."""
    __slots__ = ("addr", "size", "text", "comment", "kind")

    def __init__(self, addr, size, text, comment="", kind="code"):
        self.addr, self.size, self.text, self.comment, self.kind = addr, size, text, comment, kind


class Disassembler:
    def __init__(self, mem, x07=True, rst8_inline=True, labels=None):
        self.mem = dict(mem)
        self.x07 = x07
        self.rst8 = rst8_inline and x07
        self.user_labels = {a: n.upper() for a, n in (labels or {}).items()}

    def read(self, a):
        return self.mem.get(a & 0xFFFF) if a <= 0xFFFF else None

    # ------------------------------------------------------------ analyse
    def analyse(self, entries=None, trace=False, data=()):
        self.data = list(data)
        self.starts = {}          # adresse -> (gabarit, valeurs, taille) pour le code
        self.inline = set()       # octets en ligne après RST 08
        if trace:
            self._trace(entries or [min(self.mem)])
        else:
            self._linear()
        self._collect_labels()

    def _in_data(self, a):
        return any(a in r for r in self.data)

    def _decode(self, a):
        r = z80.decode(self.read, a)
        if r is None:
            return None
        if any(self._in_data(a + k) for k in range(r[2])):
            return None
        return r

    def _linear(self):
        addrs = sorted(self.mem)
        i = 0
        covered = set()
        for a in addrs:
            if a in covered or self._in_data(a):
                continue
            r = self._decode(a)
            if r is None:
                continue
            self.starts[a] = r
            covered.update(range(a, a + r[2]))
            t = r[0]
            if (self.rst8 and t.mnem == "RST" and t.ops[0] == 8 and self.read(a + 1) is not None
                    and not self._in_data(a + 1)):
                self.inline.add(a + 1)
                covered.add(a + 1)

    def _trace(self, entries):
        owner = {}
        work = list(entries)
        while work:
            a = work.pop()
            while True:
                if a in self.starts or a not in self.mem or self._in_data(a):
                    break
                r = self._decode(a)
                if r is None or any((a + k) in owner for k in range(r[2])):
                    break
                t, vals, size = r
                self.starts[a] = r
                for k in range(size):
                    owner[a + k] = a
                nxt = a + size
                if (t.mnem == "RST" and self.rst8 and t.ops[0] == 8 and nxt in self.mem
                        and nxt not in owner and not self._in_data(nxt)):
                    self.inline.add(nxt)
                    owner[nxt] = a
                    nxt += 1
                f = t.flow
                target = vals.get(z80.E, vals.get(z80.NN))
                if f in ("jump", "cjump", "call") and target is not None:
                    work.append(target)
                if f in ("jump", "ret"):
                    break
                a = nxt

    def _collect_labels(self):
        self.labels = {}
        refs = set()
        for a, (t, vals, size) in self.starts.items():
            for key in (z80.E, z80.NN, z80.MEM):
                if key in vals:
                    refs.add((vals[key], t.mnem in _CODE_NN or key == z80.E))
        for r in self.data:                       # mots des zones DW
            if r.kind == "w":
                for a in range(r.start, r.end, 2):
                    if a in self.mem and a + 1 in self.mem:
                        refs.add((self.mem[a] | (self.mem[a + 1] << 8), False))
        # bornes des instructions : on n'étiquette qu'un début d'élément
        bounds = set(self.starts) | {a for a in self.mem if a not in self._covered()}
        for target, is_code in refs:
            if target in self.mem and target in bounds:
                self.labels[target] = self._name_for(target, is_code)
        for a, n in self.user_labels.items():
            if a in self.mem:
                self.labels[a] = n

    def _covered(self):
        if not hasattr(self, "_cov"):
            cov = set()
            for a, (t, v, size) in self.starts.items():
                cov.update(range(a + 1, a + size))
            cov.update(self.inline)
            self._cov = cov
        return self._cov

    def _name_for(self, a, is_code):
        if a in self.user_labels:
            return self.user_labels[a]
        if self.x07 and a in x07sym.ROUTINE_AT:
            return x07sym.ROUTINE_AT[a][0]
        return ("L%04X" if is_code else "D%04X") % a

    # ------------------------------------------------------------ formatage
    def _hex8(self, v):
        return "$%02X" % (v & 0xFF)

    def _hex16(self, v):
        return "$%04X" % (v & 0xFFFF)

    def _addr(self, v, kind):
        """Représentation d'une adresse : étiquette interne, symbole X-07 ou nombre."""
        if v in self.labels:
            return self.labels[v], None
        if self.x07:
            table = x07sym.ROUTINE_AT if kind == "code" else x07sym.VARIABLE_AT
            if v in table:
                name, comment = table[v]
                self.used.add(name)
                return name, comment
        return self._hex16(v), None

    def format(self, a, t, vals):
        ops, comments = [], []
        for o in t.ops:
            if isinstance(o, int):
                ops.append(self._hex8(o) if t.mnem == "RST" else str(o))
            elif o == z80.N:
                v = vals[o]
                ops.append(self._hex8(v))
                if 32 <= v < 127 and t.mnem in ("LD", "CP", "SUB", "ADD", "AND", "OR", "XOR"):
                    comments.append("'%s'" % chr(v))
            elif o == z80.NN:
                v = vals[o]
                if t.mnem in _CODE_NN:
                    s, c = self._addr(v, "code")
                    ops.append(s)
                    if c:
                        comments.append(c)
                elif v in self.labels:
                    ops.append(self.labels[v])
                else:
                    ops.append(self._hex16(v))
                    if self.x07:
                        for tab in (x07sym.VARIABLE_AT, x07sym.ROUTINE_AT):
                            if v in tab and v >= 0x9F:
                                comments.append("%s : %s" % tab[v])
                                break
            elif o == z80.E:
                v = vals[o]
                ops.append(self.labels.get(v, self._hex16(v)))
            elif o == z80.MEM:
                s, c = self._addr(vals[o], "data")
                ops.append("(%s)" % s)
                if c:
                    comments.append(c)
            elif o == z80.PORT:
                v = vals[o]
                if self.x07 and v in x07sym.PORT_AT:
                    name, c = x07sym.PORT_AT[v]
                    self.used.add(name)
                    ops.append("(%s)" % name)
                    comments.append(c)
                else:
                    ops.append("(%s)" % self._hex8(v))
            elif o in (z80.IXD, z80.IYD):
                d = vals[o]
                ops.append("(%s%s%d)" % (o[1:3], "+" if d >= 0 else "-", abs(d)))
            else:
                ops.append(o)
        if t.mnem == "RST" and self.x07:
            comments.append(x07sym.RST_COMMENT.get(t.ops[0], ""))
        text = t.mnem if not ops else "%-5s %s" % (t.mnem, ",".join(ops))
        return text, "; ".join(c for c in comments if c)

    def _data_items(self, a, end):
        """Données de a à end inclus, découpées selon les plages déclarées."""
        items = []
        while a <= end:
            r = next((r for r in self.data if a in r), None)
            kind = r.kind if r else "b"
            stop = min(end, r.end) if r else end
            # pas d'élément à cheval sur une étiquette
            nxt = [l for l in self.labels if a < l <= stop]
            if nxt:
                stop = min(nxt) - 1
            if kind == "w":
                while a + 1 <= stop:
                    words = []
                    while a + 1 <= stop and len(words) < 4:
                        v = self.mem[a] | (self.mem[a + 1] << 8)
                        s, _ = (self.labels[v], None) if v in self.labels else (self._hex16(v), None)
                        words.append(s)
                        a += 2
                    items.append(Item(a - 2 * len(words), 2 * len(words), "DW    " + ",".join(words), kind="data"))
                if a <= stop:
                    items += self._bytes(a, stop)
                    a = stop + 1
            elif kind == "t":
                items += self._text(a, stop, force=True)
                a = stop + 1
            else:
                items += self._text(a, stop)
                a = stop + 1
        return items

    def _text(self, a, stop, force=False):
        """DB avec détection des chaînes (au moins 4 caractères imprimables)."""
        items = []
        run_start = a
        k = a
        while k <= stop:
            j = k
            while j <= stop and 32 <= self.mem[j] < 127 and self.mem[j] != 34:
                j += 1
            if j - k >= (1 if force else 4):
                if run_start < k:
                    items += self._bytes(run_start, k - 1)
                for s in range(k, j, 32):
                    e = min(j, s + 32)
                    txt = "".join(chr(self.mem[x]) for x in range(s, e))
                    items.append(Item(s, e - s, 'DM    "%s"' % txt, kind="data"))
                run_start = k = j
            else:
                k = j + 1 if j == k else j
        if run_start <= stop:
            items += self._bytes(run_start, stop)
        return items

    def _bytes(self, a, stop):
        items = []
        while a <= stop:
            n = min(8, stop - a + 1)
            bs = [self.mem[a + k] for k in range(n)]
            asc = "".join(chr(b) if 32 <= b < 127 else "." for b in bs)
            items.append(Item(a, n, "DB    " + ",".join(self._hex8(b) for b in bs), asc, kind="data"))
            a += n
        return items

    def items(self):
        self.used = set()
        out = []
        addrs = sorted(self.mem)
        i = 0
        while i < len(addrs):
            a = addrs[i]
            if a in self.starts:
                t, vals, size = self.starts[a]
                text, com = self.format(a, t, vals)
                if t.prefix == (0xED,) and t.opcode in (0x63, 0x6B):
                    # forme longue de LD (nn),HL / LD HL,(nn) : l'assembleur
                    # produirait la forme courte, on garde les octets exacts
                    com = text.replace("  ", " ") + " (forme longue ED)"
                    text = "DB    " + ",".join(self._hex8(self.mem[a + k]) for k in range(size))
                out.append(Item(a, size, text, com))
                nxt = a + size
                if a + size in self.inline:
                    b = self.mem[a + size]
                    c = "'%s'" % chr(b) if 32 <= b < 127 else ""
                    out.append(Item(a + size, 1, "DB    " + self._hex8(b), c, kind="inline"))
                    nxt += 1
            else:
                # bloc de données contigu jusqu'au prochain code ou trou
                j = i
                while j + 1 < len(addrs) and addrs[j + 1] == addrs[j] + 1 \
                        and addrs[j + 1] not in self.starts:
                    j += 1
                out += self._data_items(a, addrs[j])
                nxt = addrs[j] + 1
            while i < len(addrs) and addrs[i] < nxt:
                i += 1
        return out

    # ------------------------------------------------------------ sortie
    def source(self, listing=False, title=None):
        items = self.items()
        lines = []
        if title:
            lines.append("; " + title)
        lines.append("; Désassemblage Canon X-07 (NSC800 / Z80)")
        lines.append("")
        # étiquettes hors de la zone : définies par EQU
        ext = sorted(n for n in self.used)
        if ext:
            for name in ext:
                v = x07sym.all_symbols()[name]
                fmt = "$%02X" if name.startswith("P_") else "$%04X"
                lines.append("%-12s EQU  %s" % (name, fmt % v))
            lines.append("")
        pc = None
        for it in items:
            if pc != it.addr:
                lines.append("")
                lines.append(self._line("", "ORG   " + self._hex16(it.addr), "", it, listing, False))
            lab = self.labels.get(it.addr, "")
            lines.append(self._line(lab, it.text, it.comment, it, listing, True))
            pc = it.addr + it.size
        lines.append("")
        lines.append(self._line("", "END", "", None, listing, False))
        return "\n".join(lines) + "\n"

    def _line(self, label, text, comment, it, listing, show):
        lab = (label + ":") if label else ""
        if listing:
            if show and it is not None:
                hexs = " ".join("%02X" % self.mem[it.addr + k] for k in range(min(it.size, 4)))
                pre = "%04X  %-12s" % (it.addr, hexs + ("+" if it.size > 4 else ""))
            else:
                pre = " " * 18
            body = "%-10s %s" % (lab, text)
        else:
            pre = ""
            body = "%-10s %s" % (lab, text) if len(lab) < 10 else "%s\n%-10s %s" % (lab, "", text)
        line = pre + body
        if comment:
            line = "%-50s ; %s" % (line, comment)
        return line.rstrip()


def disassemble(mem, **kw):
    entries = kw.pop("entries", None)
    trace = kw.pop("trace", False)
    data = kw.pop("data", ())
    listing = kw.pop("listing", False)
    d = Disassembler(mem, **kw)
    d.analyse(entries, trace, data)
    return d.source(listing)
