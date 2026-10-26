"""Simulateur Z80 minimal, avec imitation des routines de la ROM du X-07
utilisées par le compilateur BASIC (écran 20x4, clavier, INPUT, T6834).

Ce n'est PAS un émulateur du X-07 : la ROM n'est pas exécutée, ses
routines sont remplacées par des équivalents écrits en Python.  Il sert à
tester sur PC les programmes compilés.
"""
from . import z80
from . import x07sym

S, Z, H, PV, N, C = 0x80, 0x40, 0x10, 0x04, 0x02, 0x01
EXIT = 0xFFFF                  # adresse de retour fictive (« retour au BASIC ») ; $B000 sert au DIM de la ROM


REAL = "rom"                  # valeur rendue par une imitation : « exécute la vraie routine »


T6CMDV = 0xC951     # commande T6834 à réponse de longueur variable (vérifié ROM)
# Commandes écrites directement sur le port $F1 (comme les routines de la ROM,
# $C98F) : nombre de paramètres de chacune, relevé sur les appels de la ROM
# (t6log) ; les autres n'en ont pas.  UDK WRITE / UDK CONT : touche, texte, 00.
T6_PARAMS = {0x05: 2, 0x06: 3, 0x07: 2, 0x09: 1, 0x10: 2, 0x11: 2, 0x12: 2, 0x13: 2,
             0x14: 4, 0x15: 3, 0x17: 1, 0x1A: 9, 0x1B: 1, 0x24: 3, 0x41: 8}
T6_TEXT = (0x16, 0x35)

class SimError(Exception):
    pass


class PowerOff(SimError):
    """La ROM a demandé la coupure de l'alimentation (OFF) ; la RAM est gardée."""


def _parity(v):
    return bin(v & 0xFF).count("1") % 2 == 0


def _szp(v):
    v &= 0xFF
    return (v & S) | (Z if v == 0 else 0) | (PV if _parity(v) else 0)


class CPU:
    R8 = ("B", "C", "D", "E", "H", "L", "A")
    R16 = ("BC", "DE", "HL", "SP", "IX", "IY", "AF")

    def __init__(self):
        self.mem = bytearray(65536)
        self.r = dict.fromkeys(self.R8 + ("F", "I", "R"), 0)
        self.alt = dict.fromkeys(("A", "F", "B", "C", "D", "E", "H", "L"), 0)
        self.ix = self.iy = 0
        self.sp = 0xFFFF
        self.pc = 0
        self.traps = {}
        self.steps = 0
        self.cache = {}
        self.ports_out = []
        self.rom_start = 0xB000
        self.iff = False             # interruptions autorisées (EI)
        self.stop_requested = False  # mis à True de l'extérieur pour arrêter run()
        self.has_rom = False
        self.ram_top = 0xAFFF        # dernière adresse de RAM
        self.strict = True           # erreur sur écriture hors RAM (aide à la mise au point)

    # ------------------------------------------------ mémoire
    def rd(self, a):
        a &= 0xFFFF
        if self.ram_top < a < self.rom_start:
            return 0xFF                         # pas de mémoire à cette adresse
        return self.mem[a]

    def wr(self, a, v):
        a &= 0xFFFF
        if a > self.ram_top:
            if self.strict:
                raise SimError("écriture hors de la RAM à $%04X (PC=$%04X)" % (a, self.pc))
            return                              # ignorée, comme sur la machine
        self.mem[a] = v & 0xFF
        self.cache.pop(a, None)

    def rd16(self, a):
        return self.rd(a) | (self.rd(a + 1) << 8)

    def wr16(self, a, v):
        self.wr(a, v & 0xFF)
        self.wr(a + 1, (v >> 8) & 0xFF)

    def push(self, v):
        self.sp = (self.sp - 2) & 0xFFFF
        self.wr16(self.sp, v)

    def pop(self):
        v = self.rd16(self.sp)
        self.sp = (self.sp + 2) & 0xFFFF
        return v

    def load_rom(self, data):
        self._use_rom_routines()
        self._load_rom(data)

    def _use_rom_routines(self):
        """Avec la ROM, ces routines s'exécutent pour de vrai (pas d'imitation)."""
        pass

    def _load_rom(self, data):
        """Charge la ROM BASIC ($B000-$FFFF) et recopie la table des vecteurs
        en $0000, comme le démarrage à froid ($C3D8 : LDIR de $C6DB, $AE octets)."""
        self.mem[0xB000:0x10000] = bytes(data[:0x5000]).ljust(0x5000, b"\xff")
        self.mem[0:0xAE] = self.mem[0xC6DB:0xC6DB + 0xAE]
        self.has_rom = True
        self.cache.clear()

    def load(self, mem):
        for a, b in mem.items():
            self.mem[a] = b
        self.cache.clear()

    # ------------------------------------------------ registres
    def get16(self, n):
        r = self.r
        if n == "HL":
            return (r["H"] << 8) | r["L"]
        if n == "DE":
            return (r["D"] << 8) | r["E"]
        if n == "BC":
            return (r["B"] << 8) | r["C"]
        if n == "SP":
            return self.sp
        if n == "IX":
            return self.ix
        if n == "IY":
            return self.iy
        if n == "AF":
            return (r["A"] << 8) | r["F"]
        raise SimError(n)

    def set16(self, n, v):
        v &= 0xFFFF
        r = self.r
        if n in ("HL", "DE", "BC", "AF"):
            r[n[0]], r[n[1]] = v >> 8, v & 0xFF
        elif n == "SP":
            self.sp = v
        elif n == "IX":
            self.ix = v
        elif n == "IY":
            self.iy = v
        else:
            raise SimError(n)

    def flag(self, f):
        return bool(self.r["F"] & f)

    def setf(self, f, on):
        if on:
            self.r["F"] |= f
        else:
            self.r["F"] &= ~f & 0xFF

    def cond(self, c):
        f = self.r["F"]
        return {"NZ": not f & Z, "Z": bool(f & Z), "NC": not f & C, "C": bool(f & C),
                "PO": not f & PV, "PE": bool(f & PV), "P": not f & S, "M": bool(f & S)}[c]

    # ------------------------------------------------ opérandes 8 bits
    def addr_of(self, op, vals):
        if op == "(HL)":
            return self.get16("HL")
        if op == "(BC)":
            return self.get16("BC")
        if op == "(DE)":
            return self.get16("DE")
        if op == z80.IXD:
            return (self.ix + vals[op]) & 0xFFFF
        if op == z80.IYD:
            return (self.iy + vals[op]) & 0xFFFF
        if op == z80.MEM:
            return vals[op]
        return None

    def get8(self, op, vals):
        if op in self.r and op not in ("F",):
            return self.r[op]
        if op == z80.N:
            return vals[op]
        a = self.addr_of(op, vals)
        if a is None:
            raise SimError("opérande %s" % op)
        return self.rd(a)

    def set8(self, op, v, vals):
        if op in self.r:
            self.r[op] = v & 0xFF
            return
        a = self.addr_of(op, vals)
        if a is None:
            raise SimError("opérande %s" % op)
        self.wr(a, v)

    # ------------------------------------------------ arithmétique
    def add8(self, a, b, c=0):
        r = a + b + c
        f = _szp(r) & ~PV
        if (a & 0xF) + (b & 0xF) + c > 0xF:
            f |= H
        if (a ^ ~b) & (a ^ r) & 0x80:
            f |= PV
        if r > 0xFF:
            f |= C
        self.r["F"] = f & 0xFF
        return r & 0xFF

    def sub8(self, a, b, c=0):
        r = a - b - c
        f = (_szp(r) & ~PV) | N
        if (a & 0xF) - (b & 0xF) - c < 0:
            f |= H
        if (a ^ b) & (a ^ r) & 0x80:
            f |= PV
        if r < 0:
            f |= C
        self.r["F"] = f & 0xFF
        return r & 0xFF

    def logic(self, r, h):
        self.r["F"] = _szp(r) | (H if h else 0)
        return r & 0xFF

    # ------------------------------------------------ exécution
    def irq(self):
        """Vecteur d'une interruption en attente, ou None (voir X07)."""
        return None

    def step(self):
        if self.iff:
            vec = self.irq()
            if vec is not None:                # interruption acceptée (RST A/B/C du NSC800)
                self.iff = False
                self.push(self.pc)
                self.pc = vec
        pc = self.pc
        if pc in self.traps:
            if self.traps[pc](self) != REAL:  # REAL : exécuter le vrai code de la ROM
                if self.pc == pc:             # le gestionnaire n'a pas sauté : RET
                    self.pc = self.pop()
                return
        if pc >= self.rom_start and not self.has_rom:
            raise SimError("appel d'une routine ROM non simulée : $%04X" % pc)
        d = self.cache.get(pc)
        if d is None:
            d = z80.decode(self.rd, pc)
            if d is None:
                raise SimError("instruction invalide en $%04X : %02X" % (pc, self.rd(pc)))
            self.cache[pc] = d
        t, vals, size = d
        self.pc = (pc + size) & 0xFFFF
        self.steps += 1
        self.r["R"] = (self.r["R"] & 0x80) | ((self.r["R"] + 1) & 0x7F)
        getattr(self, "x_" + t.mnem)(t, t.ops, vals)

    def run(self, max_steps=20_000_000):
        while self.pc != EXIT:
            if self.stop_requested:
                raise SimError("arrêt demandé")
            if self.steps >= max_steps:
                raise SimError("limite de %d instructions atteinte (boucle sans fin ?)"
                               % max_steps)
            self.step()

    # ------------------------------------------------ instructions
    def _is16(self, ops):
        return any(o in self.R16 for o in ops)

    def x_NOP(self, t, o, v):
        pass

    def x_HALT(self, t, o, v):
        raise SimError("HALT en $%04X" % ((self.pc - 1) & 0xFFFF))

    def x_DI(self, t, o, v):
        self.iff = False

    def x_EI(self, t, o, v):
        self.iff = True

    def x_IM(self, t, o, v):
        pass

    def x_LD(self, t, o, v):
        dst, src = o
        if self._is16(o):
            if src == z80.NN:
                val = v[src]
            elif src == z80.MEM:
                val = self.rd16(v[src])
            else:
                val = self.get16(src)
            if dst == z80.MEM:
                self.wr16(v[dst], val)
            else:
                self.set16(dst, val)
            return
        if src in ("I", "R"):
            val = self.r[src]
            self.r["F"] = (self.r["F"] & C) | (_szp(val) & ~PV)
        else:
            val = self.get8(src, v)
        self.set8(dst, val, v)

    def x_PUSH(self, t, o, v):
        self.push(self.get16(o[0]))

    def x_POP(self, t, o, v):
        self.set16(o[0], self.pop())

    def x_EX(self, t, o, v):
        a, b = o
        if a == "AF":
            for k in ("A", "F"):
                self.r[k], self.alt[k] = self.alt[k], self.r[k]
        elif a == "DE":
            de, hl = self.get16("DE"), self.get16("HL")
            self.set16("DE", hl)
            self.set16("HL", de)
        else:                                       # (SP),rr
            m = self.rd16(self.sp)
            self.wr16(self.sp, self.get16(b))
            self.set16(b, m)

    def x_EXX(self, t, o, v):
        for k in "BCDEHL":
            self.r[k], self.alt[k] = self.alt[k], self.r[k]

    def _alu_src(self, o, v):
        return self.get8(o[-1], v)

    def x_ADD(self, t, o, v):
        if self._is16(o):
            a, b = self.get16(o[0]), self.get16(o[1])
            r = a + b
            f = self.r["F"] & (S | Z | PV)
            if (a & 0xFFF) + (b & 0xFFF) > 0xFFF:
                f |= H
            if r > 0xFFFF:
                f |= C
            self.r["F"] = f
            self.set16(o[0], r)
        else:
            self.r["A"] = self.add8(self.r["A"], self._alu_src(o, v))

    def x_ADC(self, t, o, v):
        c = 1 if self.flag(C) else 0
        if self._is16(o):
            a, b = self.get16("HL"), self.get16(o[1])
            r = a + b + c
            f = 0
            if (a & 0xFFF) + (b & 0xFFF) + c > 0xFFF:
                f |= H
            if (a ^ ~b) & (a ^ r) & 0x8000:
                f |= PV
            if r > 0xFFFF:
                f |= C
            r &= 0xFFFF
            f |= (S if r & 0x8000 else 0) | (Z if r == 0 else 0)
            self.r["F"] = f
            self.set16("HL", r)
        else:
            self.r["A"] = self.add8(self.r["A"], self._alu_src(o, v), c)

    def x_SUB(self, t, o, v):
        self.r["A"] = self.sub8(self.r["A"], self._alu_src(o, v))

    def x_SBC(self, t, o, v):
        c = 1 if self.flag(C) else 0
        if self._is16(o):
            a, b = self.get16("HL"), self.get16(o[1])
            r = a - b - c
            f = N
            if (a & 0xFFF) - (b & 0xFFF) - c < 0:
                f |= H
            if (a ^ b) & (a ^ r) & 0x8000:
                f |= PV
            if r < 0:
                f |= C
            r &= 0xFFFF
            f |= (S if r & 0x8000 else 0) | (Z if r == 0 else 0)
            self.r["F"] = f
            self.set16("HL", r)
        else:
            self.r["A"] = self.sub8(self.r["A"], self._alu_src(o, v), c)

    def x_CP(self, t, o, v):
        self.sub8(self.r["A"], self._alu_src(o, v))

    def x_AND(self, t, o, v):
        self.r["A"] = self.logic(self.r["A"] & self._alu_src(o, v), True)

    def x_OR(self, t, o, v):
        self.r["A"] = self.logic(self.r["A"] | self._alu_src(o, v), False)

    def x_XOR(self, t, o, v):
        self.r["A"] = self.logic(self.r["A"] ^ self._alu_src(o, v), False)

    def x_INC(self, t, o, v):
        if self._is16(o):
            self.set16(o[0], self.get16(o[0]) + 1)
            return
        a = self.get8(o[0], v)
        r = (a + 1) & 0xFF
        f = (self.r["F"] & C) | (_szp(r) & ~PV)
        if (a & 0xF) == 0xF:
            f |= H
        if r == 0x80:
            f |= PV
        self.r["F"] = f
        self.set8(o[0], r, v)

    def x_DEC(self, t, o, v):
        if self._is16(o):
            self.set16(o[0], self.get16(o[0]) - 1)
            return
        a = self.get8(o[0], v)
        r = (a - 1) & 0xFF
        f = (self.r["F"] & C) | (_szp(r) & ~PV) | N
        if (a & 0xF) == 0:
            f |= H
        if r == 0x7F:
            f |= PV
        self.r["F"] = f
        self.set8(o[0], r, v)

    def x_CPL(self, t, o, v):
        self.r["A"] ^= 0xFF
        self.r["F"] |= H | N

    def x_NEG(self, t, o, v):
        self.r["A"] = self.sub8(0, self.r["A"])

    def x_SCF(self, t, o, v):
        self.r["F"] = (self.r["F"] & (S | Z | PV)) | C

    def x_CCF(self, t, o, v):
        f = self.r["F"]
        self.r["F"] = (f & (S | Z | PV)) | (H if f & C else 0) | (0 if f & C else C)

    def x_DAA(self, t, o, v):
        a, f = self.r["A"], self.r["F"]
        corr, carry = 0, bool(f & C)
        if f & H or (a & 0xF) > 9:
            corr |= 0x06
        if carry or a > 0x99:
            corr |= 0x60
            carry = True
        if f & N:
            hf = bool(f & H) and (a & 0xF) < 6
            a = (a - corr) & 0xFF
        else:
            hf = (a & 0xF) > 9
            a = (a + corr) & 0xFF
        self.r["A"] = a
        self.r["F"] = _szp(a) | (H if hf else 0) | (f & N) | (C if carry else 0)

    # rotations sur A
    def _rota(self, r, c):
        self.r["A"] = r & 0xFF
        self.r["F"] = (self.r["F"] & (S | Z | PV)) | (C if c else 0)

    def x_RLCA(self, t, o, v):
        a = self.r["A"]
        self._rota((a << 1) | (a >> 7), a & 0x80)

    def x_RRCA(self, t, o, v):
        a = self.r["A"]
        self._rota((a >> 1) | ((a & 1) << 7), a & 1)

    def x_RLA(self, t, o, v):
        a = self.r["A"]
        self._rota((a << 1) | (1 if self.flag(C) else 0), a & 0x80)

    def x_RRA(self, t, o, v):
        a = self.r["A"]
        self._rota((a >> 1) | (0x80 if self.flag(C) else 0), a & 1)

    # rotations CB
    def _rot(self, o, v, fn):
        a = self.get8(o[0], v)
        r, c = fn(a)
        r &= 0xFF
        self.set8(o[0], r, v)
        self.r["F"] = _szp(r) | (C if c else 0)

    def x_RLC(self, t, o, v):
        self._rot(o, v, lambda a: ((a << 1) | (a >> 7), a & 0x80))

    def x_RRC(self, t, o, v):
        self._rot(o, v, lambda a: ((a >> 1) | ((a & 1) << 7), a & 1))

    def x_RL(self, t, o, v):
        c = 1 if self.flag(C) else 0
        self._rot(o, v, lambda a: ((a << 1) | c, a & 0x80))

    def x_RR(self, t, o, v):
        c = 0x80 if self.flag(C) else 0
        self._rot(o, v, lambda a: ((a >> 1) | c, a & 1))

    def x_SLA(self, t, o, v):
        self._rot(o, v, lambda a: (a << 1, a & 0x80))

    def x_SRA(self, t, o, v):
        self._rot(o, v, lambda a: ((a >> 1) | (a & 0x80), a & 1))

    def x_SRL(self, t, o, v):
        self._rot(o, v, lambda a: (a >> 1, a & 1))

    def x_RLD(self, t, o, v):
        hl = self.get16("HL")
        m, a = self.rd(hl), self.r["A"]
        self.wr(hl, ((m << 4) | (a & 0xF)) & 0xFF)
        a = (a & 0xF0) | (m >> 4)
        self.r["A"] = a
        self.r["F"] = (self.r["F"] & C) | _szp(a)

    def x_RRD(self, t, o, v):
        hl = self.get16("HL")
        m, a = self.rd(hl), self.r["A"]
        self.wr(hl, ((a << 4) | (m >> 4)) & 0xFF)
        a = (a & 0xF0) | (m & 0xF)
        self.r["A"] = a
        self.r["F"] = (self.r["F"] & C) | _szp(a)

    def x_BIT(self, t, o, v):
        b = self.get8(o[1], v) & (1 << o[0])
        f = (self.r["F"] & C) | H
        if not b:
            f |= Z | PV
        if o[0] == 7 and b:
            f |= S
        self.r["F"] = f

    def x_SET(self, t, o, v):
        self.set8(o[1], self.get8(o[1], v) | (1 << o[0]), v)

    def x_RES(self, t, o, v):
        self.set8(o[1], self.get8(o[1], v) & ~(1 << o[0]), v)

    # sauts
    def x_JP(self, t, o, v):
        if o[-1] in ("(HL)", "(IX)", "(IY)"):
            self.pc = self.get16(o[-1][1:-1])
        elif len(o) == 1 or self.cond(o[0]):
            self.pc = v[z80.NN]

    def x_JR(self, t, o, v):
        if len(o) == 1 or self.cond(o[0]):
            self.pc = v[z80.E]

    def x_DJNZ(self, t, o, v):
        b = (self.r["B"] - 1) & 0xFF
        self.r["B"] = b
        if b:
            self.pc = v[z80.E]

    def x_CALL(self, t, o, v):
        if len(o) == 1 or self.cond(o[0]):
            self.push(self.pc)
            self.pc = v[z80.NN]

    def x_RET(self, t, o, v):
        if not o or self.cond(o[0]):
            self.pc = self.pop()

    x_RETI = x_RETN = x_RET

    def x_RST(self, t, o, v):
        self.push(self.pc)
        self.pc = o[0]

    # E/S
    def x_IN(self, t, o, v):
        port = v[z80.PORT] if o[1] == z80.PORT else self.r["C"]
        val = self.port_in(port)
        self.r[o[0]] = val
        if o[1] == "(C)":
            self.r["F"] = (self.r["F"] & C) | _szp(val)

    def x_OUT(self, t, o, v):
        port = v[z80.PORT] if o[0] == z80.PORT else self.r["C"]
        self.ports_out.append((port, self.r[o[1]]))

    def port_in(self, port):
        return 0xFF

    # blocs
    def _ld_block(self, delta):
        hl, de, bc = self.get16("HL"), self.get16("DE"), self.get16("BC")
        self.wr(de, self.rd(hl))
        self.set16("HL", hl + delta)
        self.set16("DE", de + delta)
        bc = (bc - 1) & 0xFFFF
        self.set16("BC", bc)
        self.r["F"] = (self.r["F"] & (S | Z | C)) | (PV if bc else 0)
        return bc

    def x_LDI(self, t, o, v):
        self._ld_block(1)

    def x_LDD(self, t, o, v):
        self._ld_block(-1)

    def x_LDIR(self, t, o, v):
        while self._ld_block(1):
            self.steps += 1

    def x_LDDR(self, t, o, v):
        while self._ld_block(-1):
            self.steps += 1

    def _cp_block(self, delta):
        hl, bc = self.get16("HL"), self.get16("BC")
        m = self.rd(hl)
        c = self.r["F"] & C
        self.sub8(self.r["A"], m)
        self.set16("HL", hl + delta)
        bc = (bc - 1) & 0xFFFF
        self.set16("BC", bc)
        self.r["F"] = (self.r["F"] & ~(PV | C)) | c | (PV if bc else 0)
        return bc and not self.flag(Z)

    def x_CPI(self, t, o, v):
        self._cp_block(1)

    def x_CPD(self, t, o, v):
        self._cp_block(-1)

    def x_CPIR(self, t, o, v):
        while self._cp_block(1):
            self.steps += 1

    def x_CPDR(self, t, o, v):
        while self._cp_block(-1):
            self.steps += 1

    def __getattr__(self, name):
        if name.startswith("x_"):
            def unsupported(t, o, v):
                raise SimError("instruction non simulée : %s" % name[2:])
            return unsupported
        raise AttributeError(name)


# ======================================================================
#  Imitation du Canon X-07
# ======================================================================

class X07(CPU):
    """CPU + écran LCD 20x4, clavier et sous-processeur imités."""
    W, HGT = 20, 4

    def __init__(self, keys="", lines=None, echo=None, input_fn=None):
        super().__init__()
        self.screen = [[" "] * self.W for _ in range(self.HGT)]
        self.transcript = []
        self.keys = list(keys)
        self.lines = list(lines or [])
        self.input_fn = input_fn
        self.echo = echo              # fonction appelée pour chaque caractère affiché
        self.pixels = set()
        from .lcd import LCD
        self.lcd = LCD()              # écran à points 120 x 32 (texte et graphismes)
        self.interactive = False      # touches et saisies fournies en direct (fenêtre)
        self.t6log = []
        self.beeps = []
        self.notes = []               # bips joués : (fréquence en Hz, 0 = silence ; durée en s)
        self.on_note = None           # fonction (fréquence, durée) : haut-parleur du PC
        self.empty_polls = 0
        sym = x07sym.all_symbols()
        self.CSRX, self.CSRY = sym["CSRX"], sym["CSRY"]
        T = self.traps
        T[EXIT] = lambda c: None
        T[sym["LCDPUT"]] = self._lcdput
        T[sym["LCDCLS"]] = self._cls
        T[sym["INKEY"]] = self._inkey
        T[sym["KBWAIT"]] = self._kbwait
        T[sym["INPUTQ"]] = lambda c: self._input(True)
        T[sym["INPUTL"]] = lambda c: self._input(False)
        T[sym["T6CMDP"]] = self._t6
        T[T6CMDV] = self._t6v
        T[sym["BEEPR"]] = self._beep
        T[sym["SPEAKER"]] = self._speaker      # tous les bips de la ROM passent par $C331
        T[sym["CURSET"]] = self._curset
        T[sym["CHKBATT"]] = self._chkbatt
        T[sym["BATTMSG"]] = self._battmsg
        T[sym["T6FLUSH"]] = lambda c: None
        T[sym["T6CMD"]] = lambda c: self._t6_exec(c.r["A"] & 0x7F, [], None)
        T[sym["T6POKE"]] = lambda c: None
        T[sym["T6PEEK"]] = lambda c: c.r.__setitem__("A", 0)
        self.brk = sym["BRKFLG"]
        self.powered_off = 0
        self.real_off = False         # OFF exécuté par la ROM (rangement de l'état, coupure)
        self.held = set()             # touches tenues : "haut", "bas", "gauche", "droite",
        #                               "milieu" (STRIG(1)), "espace" (STRIG(0))
        self.on_state = 0             # réponse à ON STATE ($22) : bit 0 = rallumée après OFF
        self.udk = [b""] * 12         # touches de fonction F1-F12 (KEY$) ; d'usine : inconnues
        self.udk_on = True            # UDK ON ($18) / UDK OFF ($19)
        self.clock = None             # horloge du T6834 : fonction -> datetime (défaut : le PC)
        from collections import deque
        self.serial_in = deque()      # octets envoyés par le PC, pas encore arrivés
        self.serial_out = []          # octets émis par le X-07
        self.on_serial = None         # fonction appelée à chaque octet émis
        self.rx_latch = None
        self.rx_next = 0
        self.rx_err = 0
        self.overruns = 0
        self.int_mask = 0
        self.byte_steps = 1500        # ~ un octet à 4800 bauds
        self.t6_port = []             # commande T6834 en cours de réception sur le port $F1
        self.t6_resp = deque()        # sa réponse, relue sur le port $F1
        self._setcur(0, 0)

    # écran
    def _use_rom_routines(self):
        for name in ("BATTMSG", "BEEPR"):     # BEEPR : on y entre aussi sans CALL ($C2DE)
            self.traps.pop(x07sym.all_symbols()[name], None)

    # ports du HD61L202F : bus vers le T6834 toujours libre ; UART émulée
    def port_in(self, port):
        if port == 0xF6:                      # état UART : TXRDY, RXRDY, TXE, CTS=0
            self._uart_tick()
            return 0x05 | (0x02 if self.rx_latch is not None else 0) | self.rx_err
        if port == 0xF7:                      # donnée reçue
            v = self.rx_latch if self.rx_latch is not None else 0
            self.rx_latch = None
            self.rx_next = self.steps + self.byte_steps
            return v
        if port == 0xF1:                      # réponse du T6834 (port direct)
            return self.t6_resp.popleft() if self.t6_resp else 0x00
        return {0xF0: 0x00, 0xF2: 0x02, 0xF4: 0x00}.get(port, 0xFF)

    def x_OUT(self, t, o, v):
        port = v[z80.PORT] if o[0] == z80.PORT else self.r["C"]
        val = self.r[o[1]]
        self.ports_out.append((port, val))
        if port == 0xF0:
            self.int_mask = val
        elif port == 0xF1:                    # octet pour le T6834, envoyé sans la ROM
            self._t6_port_byte(val)
        elif port == 0xF7:                    # octet émis vers le PC
            self.serial_out.append(val)
            if self.on_serial:
                self.on_serial(val)

    def _t6_port_byte(self, b):
        """Octet écrit sur $F1 : la commande, puis ses paramètres ; exécutée dès
        qu'elle est complète, comme si elle venait de la routine de la ROM."""
        buf = self.t6_port
        buf.append(b)
        cmd = buf[0] & 0x7F                   # bit 7 : « sans paramètre » pour la ROM
        if cmd in T6_TEXT:
            if len(buf) < 3 or buf[-1] != 0:
                return
        elif len(buf) - 1 < T6_PARAMS.get(cmd, 0):
            return
        self.t6_port = []
        self.t6_resp.extend(self._t6_exec(cmd, buf[1:], None))

    def _uart_tick(self):
        """Fait arriver l'octet suivant de la ligne série au rythme du débit."""
        if self.rx_latch is None and self.serial_in and self.steps >= self.rx_next:
            self.rx_latch = self.serial_in.popleft()
            self.rx_next = self.steps + self.byte_steps
        elif self.rx_latch is not None and self.serial_in and \
                self.steps >= self.rx_next + self.byte_steps:
            self.serial_in.popleft()           # octet non lu à temps : perdu (débordement)
            self.rx_err |= 0x10
            self.overruns += 1
            self.rx_next = self.steps

    def irq(self):
        if self.serial_in or self.rx_latch is not None:
            self._uart_tick()
            if self.rx_latch is not None and self.int_mask & 0x01:
                return 0x34                   # INTERRUPT B : interruptions série
        return None

    # Comme dans la ROM : $B8 = ligne, $B9 = colonne, comptées à partir de 1.
    def _cursor(self):
        return max(self.mem[self.CSRX] - 1, 0), max(self.mem[self.CSRY] - 1, 0)

    def _setcur(self, x, y):
        self.mem[self.CSRX], self.mem[self.CSRY] = x + 1, y + 1

    def _scroll(self):
        self.screen.pop(0)
        self.screen.append([" "] * self.W)
        self.lcd.scroll()

    def putc(self, ch):
        x, y = self._cursor()
        x, y = min(x, self.W - 1), min(y, self.HGT - 1)
        if ch == 13:
            x = 0
        elif ch == 10:
            y += 1
        elif ch == 8:
            x = max(0, x - 1)
        elif ch == 7:
            self.beeps.append("BELL")
        elif ch == 12:
            self._cls(self)
            return
        elif ch >= 32:
            self.screen[y][x] = chr(ch) if ch < 127 else "?"
            self.lcd.put_char(x, y, ch)
            x += 1
            if x >= self.W:
                x, y = 0, y + 1
        if y >= self.HGT:
            self._scroll()
            y = self.HGT - 1
        self._setcur(x, y)
        if ch == 10:
            self.transcript.append("\n")
        elif ch >= 32:
            self.transcript.append(chr(ch) if ch < 127 else "?")
        if self.echo and (ch == 10 or ch >= 32):
            self.echo("\n" if ch == 10 else self.transcript[-1])

    def _curset(self, c):
        self.mem[self.CSRY], self.mem[self.CSRX] = c.r["L"], c.r["H"]

    def _chkbatt(self, c):
        a = self.mem[self.brk]
        if a & 0x80 and self.real_off:     # la vraie ROM range son état puis coupe ($23)
            return REAL
        if a & 0x80:                       # OFF : la vraie ROM éteint la machine
            self.mem[self.brk] = 0
            self.powered_off += 1
            a = 0
        c.r["A"] = a                       # comme $C5A6 : OR A puis RET P
        c.r["F"] = _szp(a) & ~PV

    def _battmsg(self, c):
        a = self.mem[self.brk]
        if a & 0x0A:
            for ch in "LOW BATTERY\r\n":
                self.putc(ord(ch))
            self.mem[self.brk] = a & ~0x0A
        c.r["A"] = self.mem[self.brk]

    def _lcdput(self, c):
        self.putc(c.r["A"])

    def _cls(self, c):
        self.screen = [[" "] * self.W for _ in range(self.HGT)]
        self.lcd.clear()
        self._setcur(0, 0)

    def screen_text(self):
        bar = "+" + "-" * self.W + "+"
        return "\n".join([bar] + ["|" + "".join(r) + "|" for r in self.screen] + [bar])

    def output(self):
        return "".join(self.transcript)

    # clavier
    def _inkey(self, c):
        if self.interactive and not self.keys:
            c.r["A"] = 0
            c.setf(Z, True)
            self.empty_polls += 1
            if self.empty_polls % 200 == 0:
                import time
                time.sleep(0.002)             # pas la peine de tourner à vide
            return
        if self.keys:
            k = self.keys.pop(0)
            c.r["A"] = ord(k)
            c.setf(Z, False)
            self.empty_polls = 0
        else:
            c.r["A"] = 0
            c.setf(Z, True)
            self.empty_polls += 1
            if self.empty_polls > 20000:
                raise SimError("le programme attend une touche (aucune touche fournie)")

    def _kbwait(self, c):
        """$C8C5 : A = touche ; CY = 1 si BREAK (Échap dans la fenêtre)."""
        if self.interactive:
            k = self._wait_key() if not self.keys else self.keys.pop(0)
            c.r["A"] = 0 if k == "\x1b" else ord(k)
            c.setf(C, k == "\x1b")
            return
        if not self.keys:
            raise SimError("le programme attend une touche (aucune touche fournie)")
        c.r["A"] = ord(self.keys.pop(0))

    def _wait_key(self):
        """Attend une touche venue de la fenêtre (curseur affiché)."""
        import time
        self.lcd.cursor = self._cursor()
        self.lcd.version += 1
        while not self.keys:
            if self.stop_requested:
                raise SimError("arrêt demandé")
            if getattr(self, "debug_pause", False):    # débogueur : F9 ou Ctrl+C
                self.lcd.cursor = None
                raise SimError("interrompu pendant l'attente d'une touche")
            time.sleep(0.01)
        self.lcd.cursor = None
        self.lcd.version += 1
        return self.keys.pop(0)

    def read_line(self):
        """Saisie d'une ligne au clavier de la fenêtre, avec écho.
        Renvoie la ligne, ou None si BREAK (Échap)."""
        line = []
        while True:
            k = self._wait_key()
            if k == "\x1b":
                return None
            if k == "\r":
                self.putc(13)
                self.putc(10)
                return "".join(line)
            if k == "\x08":
                if line:
                    line.pop()
                    x, y = self._cursor()
                    if x > 0:
                        self._setcur(x - 1, y)
                        self.putc(32)
                        self._setcur(x - 1, y)
                continue
            if 32 <= ord(k) < 256 and len(line) < 80:
                line.append(k)
                self.putc(ord(k))

    def _input(self, q):
        if self.interactive and getattr(self, "real_display", False):
            return REAL                          # l'éditeur plein écran de la ROM
        if q:
            for ch in "? ":
                self.putc(ord(ch))
        if self.lines and self.lines[0] is None:     # None : BREAK pendant la saisie
            self.lines.pop(0)
            self.set16("HL", x07sym.VARIABLES["INPBUF"][0] - 1)
            self.setf(C, True)
            return
        if not self.lines and self.interactive:
            line = self.read_line()
            if line is None:                     # Échap : BREAK pendant la saisie
                self.set16("HL", x07sym.VARIABLES["INPBUF"][0] - 1)
                self.setf(C, True)
                return
            self._store_line(line)
            return
        if self.lines:
            line = self.lines.pop(0)
        elif self.input_fn:
            line = self.input_fn()
            if line is None:
                raise SimError("INPUT : plus de données en entrée")
        else:
            raise SimError("INPUT : aucune ligne fournie")
        for ch in line:
            self.putc(ord(ch) if ord(ch) < 256 else 63)
        self.putc(13)
        self.putc(10)
        self._store_line(line)

    def _store_line(self, line):
        """Range la ligne saisie dans le tampon, comme $EBFF (HL = tampon-1)."""
        buf = x07sym.VARIABLES["INPBUF"][0]
        data = line.encode("latin-1", "replace")[:255]
        for i, b in enumerate(data):
            self.mem[buf + i] = b
        self.mem[buf + len(data)] = 0
        self.set16("HL", buf - 1)
        self.setf(C, False)                  # CY=1 signifierait BREAK

    # T6834
    def _t6(self, c):
        """$C92F : commande A, B paramètres en (HL), réponse en (DE)."""
        cmd = c.r["A"] & 0x7F
        n = 0 if c.r["A"] & 0x80 else c.r["B"]          # bit 7 de A : aucun paramètre
        hl, de = c.get16("HL"), c.get16("DE")
        params = [c.rd(hl + i) for i in range(n)]
        c.set16("HL", hl + n)
        self._t6_exec(cmd, params, de)

    def _t6v(self, c):
        """$C951 : comme $C92F, mais réponse de longueur variable terminée par
        00 (UDK READ, SP READ).  C=$FE : compte seulement ; C=$FF : range en
        (DE).  Au retour, A = ($020F) = nombre d'octets."""
        cmd = c.r["A"] & 0x7F
        n = 0 if c.r["A"] & 0x80 else c.r["B"]
        hl, de = c.get16("HL"), c.get16("DE")
        params = [c.rd(hl + i) for i in range(n)]
        resp = self._t6_exec(cmd, params, None)[:0xFE]
        if c.r["C"] == 0xFF:
            for i, b in enumerate(resp):
                c.mem[de + i] = b
        c.mem[0x020F] = len(resp)
        c.mem[0x026D] = 0
        c.r["A"] = len(resp)

    def function_key(self, n):
        """Touche de fonction Fn enfoncée : le T6834 frappe sa définition
        (KEY$(n)).  Le bouton du milieu du pavé est F6."""
        if self.udk_on:
            self.keys.extend(chr(b) for b in self.udk[n - 1])

    def _t6_exec(self, cmd, params, de):
        """Imitation des commandes du sous-processeur T6834."""
        c = self
        self.t6log.append((cmd, params))
        resp = []
        lcd, p = self.lcd, params + [0] * 10
        if cmd == 0x22:                          # ON STATE : démarrage à froid, ou après OFF
            resp = [self.on_state]
        elif cmd == 0x23 and self.real_off:      # OFF REQUEST : alimentation coupée
            self.is_off = True
            raise PowerOff("machine éteinte par OFF")
        elif cmd == 0x11:                        # PSET
            self.pixels.add(tuple(params[:2]))
            lcd.pset(p[0], p[1])
        elif cmd == 0x12:                        # PRESET
            self.pixels.discard(tuple(params[:2]))
            lcd.preset(p[0], p[1])
        elif cmd == 0x13:                        # PEOR (inversion)
            lcd.peor(p[0], p[1])
        elif cmd == 0x10:                        # POINT : texte et graphismes
            resp = [0 if lcd.get(p[0], p[1]) else 0xFF]
        elif cmd == 0x14:                        # LINE
            lcd.line(p[0], p[1], p[2], p[3])
        elif cmd == 0x15:                        # CIRCLE
            lcd.circle(p[0], p[1], p[2])
        elif cmd == 0x1A:                        # UDC WRITE : code + 8 octets
            lcd.udc_write(p[0], p[1:9])
        elif cmd == 0x1C:                        # UDC INIT
            lcd.udc_init()
        elif cmd == 0x1B:                        # UDC READ
            resp = list(lcd.font[p[0] * 8:p[0] * 8 + 8])
        elif cmd == 0x2E:                        # CLS
            lcd.clear()
        elif cmd in (0x2B, 0x2C):                # DISP OFF / DISP ON : l'écran garde son contenu
            lcd.display(cmd == 0x2C)
        elif cmd == 0x09:                        # LINE CLEAR
            lcd.clear_row(p[0])
        elif cmd == 0x07:                        # SCROLL SET : première et dernière ligne
            self.scroll_range = (p[0], p[1])
        elif cmd == 0x08:                        # SCROLL EXEC
            first, last = getattr(self, "scroll_range", (0, 3))
            lcd.scroll(max(0, first), min(3, last))
        elif cmd == 0x24:                        # LOCATE x,y + caractère (0 : aucun)
            self.t6_cursor = (p[0], p[1])
            if p[2]:
                lcd.put_char(p[0], p[1], p[2])
        elif cmd == 0x41:                        # CHAR WRITE : motif au curseur
            x, y = self._cursor()
            lcd.put_pattern(x, y, p[0:8])
        elif cmd == 0x02:                        # STICK : direction tenue (0 aucune, 1 haut,
            resp = [0x30 + self.stick()]         # 3 droite, 5 bas, 7 gauche, 2 4 6 8 diagonales)
        elif cmd == 0x03:                        # STRIG(1) : bouton du milieu du pavé
            resp = [0x00 if "milieu" in self.held else 0xFF]
        elif cmd == 0x04:                        # STRIG(0) : barre d'espace
            resp = [0x00 if "espace" in self.held else 0xFF]
        elif cmd in (0x16, 0x35) and params and 1 <= p[0] <= 12:   # UDK WRITE, UDK CONT
            text = bytes(params[1:]).split(b"\0")[0]
            k = p[0] - 1
            self.udk[k] = (self.udk[k] if cmd == 0x35 else b"") + text
        elif cmd == 0x17 and params and 1 <= p[0] <= 12:            # UDK READ
            resp = list(self.udk[p[0] - 1])
        elif cmd == 0x01:                        # TIME CALL : année (2 octets, poids fort
            import datetime                      # d'abord), mois, date, jour, heure, min, s
            t = (self.clock or datetime.datetime.now)()
            dow = (t.weekday() + 1) % 7          # dimanche = 0 : son bit (6 - dow) à 0
            resp = [t.year >> 8, t.year & 0xFF, t.month, t.day, 0xFF & ~(1 << (6 - dow)),
                    t.hour, t.minute, t.second]
        elif cmd == 0x40:                        # UDK INIT
            self.udk = [b""] * 12
        elif cmd in (0x18, 0x19):                # UDK ON / UDK OFF
            self.udk_on = cmd == 0x18
        if de is not None:
            for i, b in enumerate(resp):
                c.mem[de + i] = b
        return resp

    def stick(self):
        """Direction des flèches tenues, numérotée comme STICK (codes des
        Applications en assembleur : 1 haut, 3 droite, 5 bas, 7 gauche)."""
        h = self.held
        up, down = "haut" in h and "bas" not in h, "bas" in h and "haut" not in h
        left, right = "gauche" in h and "droite" not in h, "droite" in h and "gauche" not in h
        return {(1, 0, 0, 0): 1, (1, 0, 0, 1): 2, (0, 0, 0, 1): 3, (0, 1, 0, 1): 4,
                (0, 1, 0, 0): 5, (0, 1, 1, 0): 6, (0, 0, 1, 0): 7,
                (1, 0, 1, 0): 8}.get((up, down, left, right), 0)

    def _beep(self, c):
        """$C2DF sans la ROM : comme elle, dépile l'adresse de retour puis celle
        que l'appelant a empilée avant le CALL (HL = cette dernière)."""
        self.beeps.append((c.iy, c.r["H"]))
        ret = c.pop()
        c.set16("HL", c.pop())
        c.pc = ret

    def _speaker(self, c):
        """$C331 (BEEP6) : IY = diviseur, HL = demi-périodes, C = $FF : silence.
        Le buzzer sonne à 192000/IY Hz (BEEP 1 = do 262 Hz, BEEP 10 = la 440) et
        HL compte ses demi-périodes : durée = HL x IY / 384000 s, soit
        <durée> x 50 ms comme le dit le manuel.  Le vrai code s'exécute ensuite."""
        iy = c.iy or 0x10000
        freq = 0.0 if c.r["C"] & 0x80 else 192000.0 / iy
        dur = c.get16("HL") * iy / 384000.0
        self.notes.append((round(freq, 1), round(dur, 3)))
        if self.on_note:
            self.on_note(freq, dur)
        return REAL


def run_program(mem, entry, keys="", lines=None, max_steps=20_000_000, echo=None,
                input_fn=None):
    """Exécute un programme chargé en mémoire comme par EXEC &Hentry."""
    m = X07(keys, lines, echo, input_fn)
    m.load(mem)
    m.sp = min(mem) if min(mem) > 0x0600 else 0x7FF0
    m.push(EXIT)
    m.pc = entry
    m.run(max_steps)
    return m
