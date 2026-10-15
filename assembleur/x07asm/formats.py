"""Formats de fichiers : binaire, Intel HEX, chargeur BASIC X-07,
vidage hexadécimal (pour l'« entreur de codes » du livre), lignes DATA."""
import re

LOADER_MARK = "x07asm"
BASIC_START = 0x0553          # début des programmes BASIC


# ------------------------------------------------------------------ outils

def segments(mem):
    """Plages contiguës [(début, fin)] de la mémoire assemblée."""
    out = []
    for a in sorted(mem):
        if out and a == out[-1][1] + 1:
            out[-1][1] = a
        else:
            out.append([a, a])
    return [tuple(s) for s in out]


# ------------------------------------------------------------------ écriture

def to_bin(mem, fill=0x00):
    if not mem:
        return b""
    lo, hi = min(mem), max(mem)
    return bytes(mem.get(a, fill) for a in range(lo, hi + 1))


def to_ihex(mem, entry=None, width=16):
    lines = []
    for lo, hi in segments(mem):
        a = lo
        while a <= hi:
            n = min(width, hi - a + 1)
            rec = [n, (a >> 8) & 0xFF, a & 0xFF, 0] + [mem[a + k] for k in range(n)]
            lines.append(":" + "".join("%02X" % b for b in rec) + "%02X" % (-sum(rec) & 0xFF))
            a += n
    if entry is not None:
        rec = [4, 0, 0, 3, 0, 0, (entry >> 8) & 0xFF, entry & 0xFF]
        lines.append(":" + "".join("%02X" % b for b in rec) + "%02X" % (-sum(rec) & 0xFF))
    lines.append(":00000001FF")
    return "\n".join(lines) + "\n"


def to_hexdump(mem, width=8):
    """Vidage à recopier avec l'« entreur de codes » ; somme par ligne."""
    out = ["; adr  octets                    somme"]
    for lo, hi in segments(mem):
        a = lo
        while a <= hi:
            n = min(width, hi - a + 1)
            bs = [mem[a + k] for k in range(n)]
            out.append("%04X : %-*s ; %d" % (a, width * 3, " ".join("%02X" % b for b in bs), sum(bs)))
            a += n
    return "\n".join(out) + "\n"


def to_basic(mem, entry, name="PROG", per_line=8, first_data=1000, step=10):
    """Chargeur BASIC : DATA adresse,nombre,octets...,somme.
    Renvoie (texte, avertissements)."""
    warnings = []
    segs = segments(mem)
    lo, hi = min(mem), max(mem)
    lines = []
    ln = 10

    def add(text):
        nonlocal ln
        lines.append("%d %s" % (ln, text))
        ln += 10

    add("REM %s - chargeur %s" % (name[:12].upper(), LOADER_MARK))
    if BASIC_START < lo and hi < 0x8000:
        add("CLEAR 50,&H%X" % (lo - 1))
    add("L=%d" % first_data)
    add('READ A$:IF A$="*" THEN %d' % (ln + 60))
    loop = ln - 10
    add('A=VAL("&H"+A$):IF A<0 THEN A=A+65536')
    add("READ N:S=0:FOR J=1 TO N:READ H$:V=VAL(\"&H\"+H$)")
    add("POKE A,V:S=S+V:A=A+1:NEXT:READ C")
    add('IF C<>S THEN PRINT "ERREUR LIGNE";L:END')
    add("L=L+%d:GOTO %d" % (step, loop))
    add('PRINT "OK. EXEC &H%X":END' % entry)
    code_end = ln
    data = []
    n = first_data
    for s_lo, s_hi in segs:
        a = s_lo
        while a <= s_hi:
            k = min(per_line, s_hi - a + 1)
            bs = [mem[a + i] for i in range(k)]
            data.append("%d DATA %X,%d,%s,%d" % (n, a, k, ",".join("%X" % b for b in bs), sum(bs)))
            n += step
            a += k
    data.append("%d DATA *" % n)
    if code_end > first_data:
        raise ValueError("programme de chargement trop long")
    text = "\n".join(lines + data) + "\n"
    # taille approximative du BASIC en mémoire (tokens ≈ texte)
    size = sum(len(l) + 1 for l in lines + data)
    if BASIC_START + size + 64 > lo and lo < 0x8000 and hi >= BASIC_START:
        warnings.append(
            "le chargeur BASIC (~%d octets à partir de &H553) risque de "
            "recouvrir le code en &H%04X : implantez le code plus haut "
            "(ORG élevé + CLEAR) ou utilisez le vidage hexadécimal." % (size, lo))
    return text, warnings


# ------------------------------------------------------------------ lecture

def from_ihex(text):
    mem = {}
    base = 0
    for n, line in enumerate(text.splitlines(), 1):
        line = line.strip()
        if not line:
            continue
        if not line.startswith(":"):
            raise ValueError("ligne %d : enregistrement Intel HEX attendu" % n)
        rec = bytes.fromhex(line[1:])
        if sum(rec) & 0xFF:
            raise ValueError("ligne %d : somme de contrôle incorrecte" % n)
        cnt, addr, typ = rec[0], (rec[1] << 8) | rec[2], rec[3]
        data = rec[4:4 + cnt]
        if typ == 0:
            for i, b in enumerate(data):
                mem[(base + addr + i) & 0xFFFF] = b
        elif typ == 1:
            break
        elif typ == 2:
            base = ((data[0] << 8) | data[1]) << 4
        elif typ == 4:
            base = ((data[0] << 8) | data[1]) << 16
    return mem


def from_bin(data, org=0):
    return {(org + i) & 0xFFFF: b for i, b in enumerate(data)}


_ADDR_RE = re.compile(r"^\s*([0-9A-Fa-f]{4})\s*[:=]?\s+(.*)$")
_DATA_RE = re.compile(r"\bDATA\b(.*)$", re.I)


def from_text(text, org=0, base=16):
    """Lit des octets écrits en texte :
      - chargeur produit par x07asm (DATA adresse,n,octets,somme) ;
      - lignes BASIC « DATA 11,96,E7,... » (hexadécimal ou décimal) ;
      - vidage « 1C00 : 11 96 E7 ... » ou simples suites d'octets."""
    mem = {}
    if LOADER_MARK in text:
        for n, line in enumerate(text.splitlines(), 1):
            m = _DATA_RE.search(line)
            if not m or m.group(1).strip() == "*":
                continue
            f = [x.strip() for x in m.group(1).split(",")]
            a, k = int(f[0], 16), int(f[1])
            bs = [int(x, 16) for x in f[2:2 + k]]
            if len(f) > 2 + k and sum(bs) != int(f[2 + k]):
                raise ValueError("ligne %d : somme de contrôle incorrecte" % n)
            for i, b in enumerate(bs):
                mem[(a + i) & 0xFFFF] = b
        return mem
    a = org
    for n, line in enumerate(text.splitlines(), 1):
        line = line.split(";")[0].split("'")[0]
        m = _DATA_RE.search(line)
        if m:
            body = m.group(1)
        else:
            m = _ADDR_RE.match(line)
            if m and len(m.group(2).split()) > 0 and ":" in line[:8]:
                a = int(m.group(1), 16)
                body = m.group(2)
            else:
                body = line
        for tok in re.split(r"[\s,]+", body.strip()):
            if not tok:
                continue
            tok = tok.lstrip("$").replace("&H", "").replace("&h", "")
            try:
                v = int(tok, base)
            except ValueError:
                raise ValueError("ligne %d : octet incorrect %r" % (n, tok))
            if not 0 <= v <= 255:
                raise ValueError("ligne %d : valeur hors octet %r" % (n, tok))
            mem[a & 0xFFFF] = v
            a += 1
    return mem


def load_any(path, org=None, base=16):
    """Charge un fichier selon son contenu : Intel HEX, texte ou binaire."""
    with open(path, "rb") as f:
        raw = f.read()
    try:
        text = raw.decode("ascii")
        is_text = all(c.isprintable() or c in "\r\n\t" for c in text)
    except UnicodeDecodeError:
        is_text = False
    if is_text and text.lstrip().startswith(":"):
        return from_ihex(text)
    if is_text and not path.lower().endswith((".bin", ".rom")):
        return from_text(text, org or 0, base)
    return from_bin(raw, org or 0)
