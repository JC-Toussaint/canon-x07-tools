"""Tests de x07asm :  python3 -m unittest discover -s tests"""
import os
import random
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from x07asm import z80, formats                       # noqa: E402
from x07asm.asm import Assembler, AsmError            # noqa: E402
from x07asm.dis import Disassembler, parse_range      # noqa: E402


def asm(text, **kw):
    a = Assembler(**kw)
    mem = a.assemble_text(text)
    if a.errors:
        raise a.errors[0]
    return a, [mem[k] for k in sorted(mem)]


def roundtrip(mem, **kw):
    """désassemble puis réassemble : doit redonner les mêmes octets."""
    entries = kw.pop("entries", None)
    trace = kw.pop("trace", False)
    data = kw.pop("data", ())
    d = Disassembler(mem, **kw)
    d.analyse(entries, trace, data)
    src = d.source()
    a = Assembler()
    out = a.assemble_text(src)
    if a.errors:
        raise AssertionError("%s\n---\n%s" % (a.errors[0], src))
    return out, src


class TestTable(unittest.TestCase):
    def test_counts(self):
        from collections import Counter
        c = Counter(t.prefix for t in z80.TEMPLATES)
        self.assertEqual(c[()], 252)
        self.assertEqual(c[(0xCB,)], 248)
        self.assertEqual(c[(0xED,)], 58)
        self.assertEqual(c[(0xDD,)], 39)
        self.assertEqual(c[(0xDD, 0xCB)], 31)

    def test_known_encodings(self):
        cases = {
            "LD A,(IX+5)": [0xDD, 0x7E, 0x05],
            "LD (IY-2),$12": [0xFD, 0x36, 0xFE, 0x12],
            "BIT 7,(IX+1)": [0xDD, 0xCB, 0x01, 0x7E],
            "SET 0,(IY+0)": [0xFD, 0xCB, 0x00, 0xC6],
            "RES 0,A": [0xCB, 0x87],
            "LD HL,($1234)": [0x2A, 0x34, 0x12],     # forme courte, pas ED 6B
            "LD ($1234),SP": [0xED, 0x73, 0x34, 0x12],
            "LD BC,($1234)": [0xED, 0x4B, 0x34, 0x12],
            "EX AF,AF'": [0x08],
            "EX (SP),IX": [0xDD, 0xE3],
            "JP (IY)": [0xFD, 0xE9],
            "JP (HL)": [0xE9],
            "IM 2": [0xED, 0x5E],
            "RST 38H": [0xFF],
            "RST $08": [0xCF],
            "IN A,($F4)": [0xDB, 0xF4],
            "OUT (C),E": [0xED, 0x59],
            "LDIR": [0xED, 0xB0],
            "OTDR": [0xED, 0xBB],
            "SUB B": [0x90],
            "SUB A,B": [0x90],          # forme tolérée
            "ADD B": [0x80],            # forme tolérée
            "SBC HL,DE": [0xED, 0x52],
            "ADD IY,IY": [0xFD, 0x29],
            "LD SP,IX": [0xDD, 0xF9],
            "LD A,(IX)": [0xDD, 0x7E, 0x00],
            "LD A,R": [0xED, 0x5F],
            "LD A,(5+3)": [0x3A, 0x08, 0x00],      # indirection
            "LD A,(5+3)*2": [0x3E, 0x10],          # expression immédiate
        }
        for src, ref in cases.items():
            with self.subTest(src=src):
                _, b = asm("  " + src)
                self.assertEqual(b, ref)

    def test_every_template_roundtrip(self):
        """Chaque gabarit : encode -> décode -> texte -> réassemble."""
        rnd = random.Random(1)
        for t in z80.TEMPLATES:
            for _ in range(3):
                vals = {}
                for o in t.ops:
                    if o in (z80.N, z80.PORT):
                        vals[o] = rnd.randrange(256)
                    elif o in (z80.NN, z80.MEM):
                        vals[o] = rnd.randrange(65536)
                    elif o in (z80.IXD, z80.IYD):
                        vals[o] = rnd.randrange(-128, 128)
                    elif o == z80.E:
                        vals[o] = rnd.randrange(-128, 128)
                org = 0x4000
                code = t.encode(vals)
                self.assertEqual(len(code), t.size, t)
                mem = {org + i: b for i, b in enumerate(code)}
                r = z80.decode(mem.get, org)
                self.assertIsNotNone(r, t)
                self.assertIs(r[0], t)
                out, src = roundtrip(mem, x07=False)
                self.assertEqual([out[k] for k in sorted(out)], code, src)


class TestAssembler(unittest.TestCase):
    def test_expressions(self):
        a, b = asm("""
X   EQU  $10 + &H20 + 0x01 + 10H + %11 + 0101B + 'A'
    DB   X, HIGH($1234), LOW($1234), 7 MOD 4, 1 << 3, ~0 & $FF, -1
    DW   $, X*2
""")
        x = 0x10 + 0x20 + 1 + 0x10 + 3 + 5 + 65
        self.assertEqual(b[:7], [x, 0x12, 0x34, 3, 8, 0xFF, 0xFF])
        self.assertEqual(b[7:9], [7, 0])

    def test_labels_forward_local(self):
        _, b = asm("""
        ORG $2000
START:  JR  FIN
A1:     DJNZ .L
.L      NOP
B1:     JR .L
.L:     NOP
FIN     JP  A1.L
""")
        self.assertEqual(b, [0x18, 0x06, 0x10, 0x00, 0x00, 0x18, 0x00, 0x00,
                             0xC3, 0x04, 0x20])

    def test_strings(self):
        _, b = asm("""
    DB "AB",'C',0
    DM "x;y"        ; point-virgule dans la chaîne
    DZ "OK"
""")
        self.assertEqual(b, [65, 66, 67, 0, ord("x"), ord(";"), ord("y"), 79, 75, 0])

    def test_ds_align_if(self):
        a, b = asm("""
        ORG 0
        DB 1
        DS 3,$AA
        ALIGN 8
        DB 2
DEBUG   EQU 0
        IF DEBUG
        DB $EE
        ELSE
        DB $55
        ENDIF
""")
        self.assertEqual(b, [1, 0xAA, 0xAA, 0xAA, 2, 0x55])
        self.assertEqual(sorted(a.mem)[-2:], [8, 9])

    def test_x07_symbols(self):
        a, b = asm(" CALL INKEY\n LD A,T_CLS\n RST 18H\n IN A,(P_MODE)")
        self.assertEqual(b, [0xCD, 0x0A, 0xC9, 0x3E, 0x2E, 0xDF, 0xDB, 0xF4])
        with self.assertRaises(AsmError):
            asm(" CALL INKEY", x07=False)

    def test_user_overrides_x07(self):
        _, b = asm("INKEY: RET\n CALL INKEY")
        self.assertEqual(b, [0xC9, 0xCD, 0x00, 0x00])

    def test_errors(self):
        for src in (" JR $+200", " LD A,300", " LD (IX+200),A", " LD A,HL",
                    " FOO", " JP NOWHERE", "X: NOP\nX: NOP", " IF 1\n NOP"):
            with self.subTest(src=src):
                with self.assertRaises(AsmError):
                    asm(src)

    def test_book_caso(self):
        """Exemple CASO du livre : octets identiques aux DATA publiés."""
        a = Assembler()
        mem = a.assemble_file(os.path.join(ROOT, "exemples", "caso.asm"))
        self.assertFalse(a.errors)
        ref = ("11,96,E7,FD,21,C5,2,3E,0,CD,A8,E6,DB,F4,CB,C7,D3,F4,CD,54,1C,CD,54,1C,"
               "11,C5,2,CD,27,E8,3E,0,CD,8F,E8,3E,0,CD,8F,E8,3E,0,CD,8F,E8,21,61,1C,7E,"
               "FE,0,28,6,CD,8F,E8,23,18,F5,3E,FF,CD,8F,E8,3E,FF,CD,8F,E8,3E,FF,CD,8F,E8,"
               "CD,54,1C,DB,F4,CB,87,D3,F4,C9,C5,6,7F,E,FF,D,20,FD,5,20,F8,C1,C9,1,2,3,4,"
               "5,6,0")
        self.assertEqual([mem[k] for k in sorted(mem)], [int(x, 16) for x in ref.split(",")])
        self.assertEqual(min(mem), 0x1C00)


class TestDisassembler(unittest.TestCase):
    def test_random_roundtrip_linear(self):
        rnd = random.Random(7)
        for seed in range(40):
            n = rnd.randrange(1, 400)
            org = rnd.randrange(0, 0x10000 - n)
            mem = {org + i: rnd.randrange(256) for i in range(n)}
            for x07 in (True, False):
                out, src = roundtrip(mem, x07=x07)
                self.assertEqual(out, mem, src)

    def test_random_roundtrip_trace_with_gaps(self):
        rnd = random.Random(11)
        for seed in range(30):
            mem = {}
            for _ in range(3):
                org = rnd.randrange(0, 0xF000)
                for i in range(rnd.randrange(1, 120)):
                    mem[org + i] = rnd.randrange(256)
            out, src = roundtrip(mem, trace=True, entries=[min(mem)])
            self.assertEqual(out, mem, src)

    def test_trace_separates_data(self):
        a = Assembler()
        mem = a.assemble_file(os.path.join(ROOT, "exemples", "caso.asm"))
        d = Disassembler(mem)
        d.analyse(trace=True)
        src = d.source()
        self.assertIn("DB    $01,$02,$03,$04,$05,$06,$00", src)
        self.assertIn("CALL  DEVOPEN", src)
        out, _ = roundtrip(mem, trace=True)
        self.assertEqual(out, mem)

    def test_rst8_inline(self):
        mem = {0x100: 0xCF, 0x101: ord("("), 0x102: 0xC9}
        d = Disassembler(mem)
        d.analyse()
        src = d.source()
        self.assertIn("RST   $08", src)
        self.assertIn("DB    $28", src)
        self.assertIn("RET", src)

    def test_rst38_inline(self):
        """RST 38 est suivi d'un octet en ligne, comme RST 08 (vérifié ROM : $E906)."""
        mem = {0x100: 0xFF, 0x101: 0x81, 0x102: 0x79, 0x103: 0xC9}
        d = Disassembler(mem)
        d.analyse()
        src = d.source()
        self.assertIn("DB    $81", src)
        self.assertIn("LD    A,C", src)

    def test_rom_map_up_to_date(self):
        """ROM.md doit être régénéré après toute modification de x07sym.py."""
        from x07asm import x07sym
        with open(os.path.join(ROOT, "ROM.md"), encoding="utf-8") as f:
            self.assertEqual(f.read(), x07sym.markdown(),
                             "lancez : python3 x07asm.py sym --md > ROM.md")

    def test_data_ranges(self):
        mem = {0x200 + i: b for i, b in enumerate(
            [0xC9, 0x34, 0x12, 0x00, 0x02] + [ord(c) for c in "HELLO"])}
        rngs = [parse_range("201-204:w"), parse_range("t:205-209")]
        d = Disassembler(mem)
        d.analyse(data=rngs)
        src = d.source()
        self.assertIn("DW    $1234,D0200", src.replace("L0200", "D0200"))
        self.assertIn('DM    "HELLO"', src)
        out, _ = roundtrip(mem, data=rngs)
        self.assertEqual(out, mem)


class TestFormats(unittest.TestCase):
    def setUp(self):
        self.mem = {0x1C00 + i: (i * 37) & 0xFF for i in range(50)}
        self.mem.update({0x3000 + i: i for i in range(5)})

    def test_ihex(self):
        self.assertEqual(formats.from_ihex(formats.to_ihex(self.mem, 0x1C00)), self.mem)

    def test_basic_loader(self):
        text, _ = formats.to_basic(self.mem, 0x1C00)
        self.assertIn("CLEAR 50,&H1BFF", text)
        self.assertEqual(formats.from_text(text), self.mem)

    def test_hexdump(self):
        self.assertEqual(formats.from_text(formats.to_hexdump(self.mem)), self.mem)

    def test_data_lines(self):
        m = formats.from_text("10 DATA 11,96,E7\n20 DATA C9", org=0x1C00)
        self.assertEqual(m, {0x1C00: 0x11, 0x1C01: 0x96, 0x1C02: 0xE7, 0x1C03: 0xC9})
        m = formats.from_text("10000 DATA 017,150,231", org=0x800, base=10)
        self.assertEqual(m, {0x800: 17, 0x801: 150, 0x802: 231})


if __name__ == "__main__":
    unittest.main()
