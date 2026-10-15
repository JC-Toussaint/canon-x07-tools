"""Table d'instructions Z80 / NSC800 (jeu documenté), partagée par
l'assembleur et le désassembleur.

Chaque instruction est décrite par un gabarit (Template) : mnémonique,
opérandes, préfixe, code opération.  Les opérandes sont soit des chaînes
littérales ("A", "(HL)", "NZ", "AF'"...), soit des entiers littéraux
(numéro de bit, mode IM, vecteur RST), soit l'un des marqueurs :

    N     octet immédiat                       LD A,n
    NN    mot immédiat                         LD HL,nn
    E     déplacement relatif (cible absolue)  JR e
    PORT  port (n)                             IN A,(n)
    MEM   adresse (nn)                         LD A,(nn)
    IXD   (IX+d)                               LD A,(IX+d)
    IYD   (IY+d)

Le NSC800 du Canon X-07 exécute le jeu d'instructions du Z80.
"""

N, NN, E, PORT, MEM, IXD, IYD = "n", "nn", "e", "(n)", "(nn)", "(IX+d)", "(IY+d)"
PLACEHOLDERS = (N, NN, E, PORT, MEM, IXD, IYD)

R = ["B", "C", "D", "E", "H", "L", "(HL)", "A"]
RP = ["BC", "DE", "HL", "SP"]
RP2 = ["BC", "DE", "HL", "AF"]
CC = ["NZ", "Z", "NC", "C", "PO", "PE", "P", "M"]
ALU = [("ADD", "A"), ("ADC", "A"), ("SUB", None), ("SBC", "A"),
       ("AND", None), ("XOR", None), ("OR", None), ("CP", None)]
ROT = ["RLC", "RRC", "RL", "RR", "SLA", "SRA", None, "SRL"]  # SLL non documentée
BLI = {(4, 0): "LDI", (4, 1): "CPI", (4, 2): "INI", (4, 3): "OUTI",
       (5, 0): "LDD", (5, 1): "CPD", (5, 2): "IND", (5, 3): "OUTD",
       (6, 0): "LDIR", (6, 1): "CPIR", (6, 2): "INIR", (6, 3): "OTIR",
       (7, 0): "LDDR", (7, 1): "CPDR", (7, 2): "INDR", (7, 3): "OTDR"}


class Template:
    __slots__ = ("mnem", "ops", "prefix", "opcode", "size", "flow")

    def __init__(self, mnem, ops, prefix, opcode):
        self.mnem = mnem
        self.ops = tuple(ops)
        self.prefix = tuple(prefix)
        self.opcode = opcode
        size = len(self.prefix) + 1
        for o in self.ops:
            if o in (N, E, PORT, IXD, IYD):
                size += 1
            elif o in (NN, MEM):
                size += 2
        self.size = size
        self.flow = _flow(mnem, self.ops)

    @property
    def ddcb(self):
        return len(self.prefix) == 2 and self.prefix[1] == 0xCB

    def encode(self, values):
        """values : dict marqueur -> entier (déjà vérifié)."""
        out = list(self.prefix)
        d = values.get(IXD, values.get(IYD))
        if self.ddcb:
            out += [d & 0xFF, self.opcode]
            return out
        out.append(self.opcode)
        if d is not None:
            out.append(d & 0xFF)
        for o in self.ops:
            if o in (N, PORT):
                out.append(values[o] & 0xFF)
            elif o == E:
                out.append(values[o] & 0xFF)
            elif o in (NN, MEM):
                v = values[o] & 0xFFFF
                out += [v & 0xFF, v >> 8]
        return out

    def __repr__(self):
        return "<%s %s>" % (self.mnem, ",".join(map(str, self.ops)))


def _flow(mnem, ops):
    """Nature de l'instruction pour le suivi du flot de contrôle :
    'jump' (saut inconditionnel), 'cjump' (conditionnel), 'call',
    'ret' (fin de flot), 'cret' (retour conditionnel), 'rst', None."""
    if mnem in ("JP", "JR"):
        if len(ops) == 1:
            return "jump" if ops[0] in (NN, E) else "ret"   # JP (HL) : cible inconnue
        return "cjump"
    if mnem == "DJNZ":
        return "cjump"
    if mnem == "CALL":
        return "call"
    if mnem in ("RET", "RETI", "RETN"):
        return "cret" if ops else "ret"
    if mnem == "RST":
        return "rst"
    if mnem == "HALT":
        return None
    return None


def _unprefixed():
    t = []
    for op in range(256):
        x, y, z = op >> 6, (op >> 3) & 7, op & 7
        p, q = y >> 1, y & 1
        if x == 0:
            if z == 0:
                if y < 4:
                    t.append((op, ["NOP", "EX", "DJNZ", "JR"][y],
                              [[], ["AF", "AF'"], [E], [E]][y]))
                else:
                    t.append((op, "JR", [CC[y - 4], E]))
            elif z == 1:
                t.append((op, "LD", [RP[p], NN]) if q == 0 else (op, "ADD", ["HL", RP[p]]))
            elif z == 2:
                if q == 0:
                    t.append((op, "LD", [["(BC)", "A"], ["(DE)", "A"], [MEM, "HL"], [MEM, "A"]][p]))
                else:
                    t.append((op, "LD", [["A", "(BC)"], ["A", "(DE)"], ["HL", MEM], ["A", MEM]][p]))
            elif z == 3:
                t.append((op, "INC" if q == 0 else "DEC", [RP[p]]))
            elif z == 4:
                t.append((op, "INC", [R[y]]))
            elif z == 5:
                t.append((op, "DEC", [R[y]]))
            elif z == 6:
                t.append((op, "LD", [R[y], N]))
            else:
                t.append((op, ["RLCA", "RRCA", "RLA", "RRA", "DAA", "CPL", "SCF", "CCF"][y], []))
        elif x == 1:
            if op == 0x76:
                t.append((op, "HALT", []))
            else:
                t.append((op, "LD", [R[y], R[z]]))
        elif x == 2:
            m, a = ALU[y]
            t.append((op, m, ([a] if a else []) + [R[z]]))
        else:
            if z == 0:
                t.append((op, "RET", [CC[y]]))
            elif z == 1:
                if q == 0:
                    t.append((op, "POP", [RP2[p]]))
                else:
                    t.append((op, ["RET", "EXX", "JP", "LD"][p],
                              [[], [], ["(HL)"], ["SP", "HL"]][p]))
            elif z == 2:
                t.append((op, "JP", [CC[y], NN]))
            elif z == 3:
                if y == 1:
                    continue                                  # préfixe CB
                t.append((op, ["JP", None, "OUT", "IN", "EX", "EX", "DI", "EI"][y],
                          [[NN], None, [PORT, "A"], ["A", PORT], ["(SP)", "HL"],
                           ["DE", "HL"], [], []][y]))
            elif z == 4:
                t.append((op, "CALL", [CC[y], NN]))
            elif z == 5:
                if q == 0:
                    t.append((op, "PUSH", [RP2[p]]))
                elif p == 0:
                    t.append((op, "CALL", [NN]))
                # p = 1, 2, 3 : préfixes DD, ED, FD
            elif z == 6:
                m, a = ALU[y]
                t.append((op, m, ([a] if a else []) + [N]))
            else:
                t.append((op, "RST", [y * 8]))
    return t


def _cb():
    t = []
    for op in range(256):
        x, y, z = op >> 6, (op >> 3) & 7, op & 7
        if x == 0:
            if ROT[y]:
                t.append((op, ROT[y], [R[z]]))
        else:
            t.append((op, ["", "BIT", "RES", "SET"][x], [y, R[z]]))
    return t


def _ed():
    t = []
    for op in range(256):
        x, y, z = op >> 6, (op >> 3) & 7, op & 7
        p, q = y >> 1, y & 1
        if x == 1:
            if z == 0 and y != 6:
                t.append((op, "IN", [R[y], "(C)"]))
            elif z == 1 and y != 6:
                t.append((op, "OUT", ["(C)", R[y]]))
            elif z == 2:
                t.append((op, "SBC" if q == 0 else "ADC", ["HL", RP[p]]))
            elif z == 3:
                t.append((op, "LD", [MEM, RP[p]] if q == 0 else [RP[p], MEM]))
            elif z == 4 and y == 0:
                t.append((op, "NEG", []))
            elif z == 5 and y in (0, 1):
                t.append((op, "RETN" if y == 0 else "RETI", []))
            elif z == 6 and y in (0, 2, 3):
                t.append((op, "IM", [{0: 0, 2: 1, 3: 2}[y]]))
            elif z == 7 and y < 6:
                t.append((op, ["LD", "LD", "LD", "LD", "RRD", "RLD"][y],
                          [["I", "A"], ["R", "A"], ["A", "I"], ["A", "R"], [], []][y]))
        elif x == 2 and z <= 3 and y >= 4:
            t.append((op, BLI[(y, z)], []))
    return t


def _index(base, reg):
    """Instructions documentées préfixées DD (IX) ou FD (IY)."""
    xd = IXD if reg == "IX" else IYD
    t = []
    for op, m, ops in base:
        if op == 0xEB:                        # EX DE,HL : pas d'équivalent indexé
            continue
        if "(HL)" in ops:
            if op == 0xE9:                    # JP (HL) -> JP (IX)
                t.append((op, m, ["(%s)" % reg]))
            elif op != 0x76:
                t.append((op, m, [xd if o == "(HL)" else o for o in ops]))
        elif "HL" in ops and not any(o in ("H", "L") for o in ops):
            t.append((op, m, [reg if o == "HL" else o for o in ops]))
    return t


def _index_cb(cb, reg):
    xd = IXD if reg == "IX" else IYD
    return [(op, m, [xd if o == "(HL)" else o for o in ops])
            for op, m, ops in cb if (op & 7) == 6]


def build():
    base = _unprefixed()
    cb = _cb()
    tpls = []
    tpls += [Template(m, o, (), op) for op, m, o in base]
    tpls += [Template(m, o, (0xCB,), op) for op, m, o in cb]
    tpls += [Template(m, o, (0xED,), op) for op, m, o in _ed()]
    for pfx, reg in ((0xDD, "IX"), (0xFD, "IY")):
        tpls += [Template(m, o, (pfx,), op) for op, m, o in _index(base, reg)]
        tpls += [Template(m, o, (pfx, 0xCB), op) for op, m, o in _index_cb(cb, reg)]
    return tpls


TEMPLATES = build()

# Décodage : (préfixe, opcode) -> gabarit
DECODE = {(t.prefix, t.opcode): t for t in TEMPLATES}

# Assemblage : (mnémonique, nombre d'opérandes) -> gabarits, les plus courts d'abord
ENCODE = {}
for _t in sorted(TEMPLATES, key=lambda t: t.size):
    ENCODE.setdefault((_t.mnem, len(_t.ops)), []).append(_t)

MNEMONICS = {t.mnem for t in TEMPLATES}

# Mots réservés en position d'opérande
REGISTERS = {"A", "B", "C", "D", "E", "H", "L", "I", "R", "AF", "AF'", "BC", "DE",
             "HL", "SP", "IX", "IY", "NZ", "Z", "NC", "PO", "PE", "P", "M"}


def decode(read, addr):
    """Décode l'instruction à `addr`.  `read(a)` renvoie l'octet en a
    (ou None hors des données).  Renvoie (gabarit, valeurs, taille) ou
    None si la séquence n'est pas une instruction documentée."""
    b0 = read(addr)
    if b0 is None:
        return None
    if b0 in (0xDD, 0xFD):
        b1 = read(addr + 1)
        if b1 is None:
            return None
        if b1 == 0xCB:
            d, op = read(addr + 2), read(addr + 3)
            if d is None or op is None:
                return None
            t = DECODE.get(((b0, 0xCB), op))
            if t is None:
                return None
            return t, {t.ops[-1]: _s8(d)}, 4
        t = DECODE.get(((b0,), b1))
        pos = addr + 2
    elif b0 in (0xCB, 0xED):
        b1 = read(addr + 1)
        if b1 is None:
            return None
        t = DECODE.get(((b0,), b1))
        pos = addr + 2
    else:
        t = DECODE.get(((), b0))
        pos = addr + 1
    if t is None:
        return None
    vals = {}
    for o in t.ops:                       # (IX+d) précède toujours n
        if o in (IXD, IYD):
            v = read(pos)
            if v is None:
                return None
            vals[o] = _s8(v)
            pos += 1
    for o in t.ops:
        if o in (N, PORT, E):
            v = read(pos)
            if v is None:
                return None
            vals[o] = (addr + t.size + _s8(v)) & 0xFFFF if o == E else v
            pos += 1
        elif o in (NN, MEM):
            lo, hi = read(pos), read(pos + 1)
            if lo is None or hi is None:
                return None
            vals[o] = lo | (hi << 8)
            pos += 2
    return t, vals, t.size


def _s8(v):
    return v - 256 if v >= 128 else v
