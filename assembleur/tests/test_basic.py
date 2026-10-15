"""Tests du compilateur BASIC.

La référence est l'interpréteur de la vraie ROM du X-07, exécuté par le
simulateur (x07asm.emu) : chaque programme est lancé par RUN dans la ROM,
puis compilé et lancé par EXEC ; les deux affichages (texte et écran)
doivent être identiques.  Nécessite ROM_x07/x07.bin.
"""
import os
import random
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from x07asm import emu                                     # noqa: E402
from x07asm.basic import compile_basic, CompileError      # noqa: E402
from x07asm.asm import Assembler                           # noqa: E402

HAVE_ROM = emu.rom_path() is not None
needs_rom = unittest.skipUnless(HAVE_ROM, "ROM_x07/x07.bin absente")


def build(src, org=0x3000, **opts):
    asm, comp = compile_basic(src, "T", org, **opts)
    a = Assembler()
    mem = a.assemble_text(asm)
    if a.errors:
        raise AssertionError("%s\n%s" % (a.errors[0], asm))
    return mem, a.entry, asm


def compiled(src, inputs=(), keys="", **opts):
    mem, entry, _ = build(src, **opts)
    return emu.run_binary(mem, entry, keys=keys, inputs=inputs, max_steps=20_000_000)


class OracleCase(unittest.TestCase):
    def same(self, src, inputs=(), keys="", **opts):
        """La ROM et le code compilé doivent afficher exactement la même chose."""
        opts.setdefault("debug", True)
        ref, mr = emu.run_basic(src, inputs=inputs, keys=keys)
        m = compiled(src, inputs, keys, **opts)
        # la ROM passe à la ligne avant son invite « > » : ce n'est pas le programme
        self.assertEqual(m.output().rstrip("\n"), ref.rstrip("\n"), "\n" + src)
        # l'écran (positions du curseur, TAB...) : on ignore l'invite « > » de la ROM
        scr_ref = [l.rstrip() for l in mr.screen_text().replace("|>", "| ").splitlines()]
        scr = [l.rstrip() for l in m.screen_text().splitlines()]
        if scr_ref != scr and ref.endswith("\n") and not m.output().endswith("\n"):
            m.putc(13)                   # même passage à la ligne final que la ROM
            m.putc(10)
            scr = [l.rstrip() for l in m.screen_text().splitlines()]
        self.assertEqual(scr, scr_ref, "\n" + src)
        return ref


@needs_rom
class TestAgainstRom(OracleCase):
    def test_numbers_and_types(self):
        self.same('''10 PRINT 1/3;2/3;10/4;1E10;123456789#
20 A!=1/3:PRINT A!,CSNG(1234567)
30 PRINT -0.5;.001;1E-10;3.14159265358979#;300*300;-32768
40 DEFINT I-K:DEFSNG S:DEFSTR T
50 I=7.9:S=1/3:T="CHAINE":X=1/3
60 PRINT I;S;T;X;I/2;I\\2;S*3;X*3;7.9\\2
70 A%=32767:B!=1E10:C#=1D10:PRINT A%;B!;C#;B!*B!;C#/3
80 PRINT 999999.5!;1234567.5!;.1234565!;&H7FFF;&HFFFF''')

    def test_functions(self):
        self.same('''10 PRINT SIN(1);COS(1);TAN(1);ATN(1)
20 PRINT SQR(2);LOG(10);EXP(1);SQR(16)
30 PRINT SIN(1!);SQR(2!);2^10;2!^0.5;(-2)^3;2^15;2^0.5
40 PRINT INT(-2.5);INT(2.5);FIX(-2.5);ABS(-3.5);SGN(-0.1);CINT(-2.6);CINT(2.6)
50 PRINT RND(1);RND(1);RND(1)
60 PRINT CDBL(1/3!);CSNG(2/3);INT(1E10/3)''')

    def test_loops(self):
        self.same('''10 N=0:FOR X=0 TO 1 STEP .1:N=N+1:NEXT:PRINT N;X
20 FOR Y!=1 TO 0 STEP -1/3:PRINT Y!;:NEXT:PRINT
30 FOR K%=1 TO 3:PRINT K%;:NEXT:PRINT K%
40 S=0:FOR I=1 TO 100:S=S+1/I:NEXT:PRINT S
50 FOR I=5 TO 1:PRINT "X";:NEXT:PRINT I
60 P=-.5:FOR Z=2 TO 0 STEP P:PRINT Z;:NEXT:PRINT
70 FOR I=1 TO 2:FOR J=1 TO 2:PRINT I*10+J;:NEXT J,I''')

    def test_print_layout(self):
        self.same('''10 PRINT 1,2,3
20 PRINT "A";TAB(5);"B";TAB(2);"C"
30 PRINT 12345678;12345678;12345678
40 PRINT "ABCDEFGHIJKLMNOP";1.5
50 PRINT STR$(1.5);STR$(-2);VAL("3.5")+1;VAL(" 12");VAL("&H10")
60 LOCATE 5,2:PRINT "ICI";CSRLIN;POS(0);:PRINT TAB(15);"FIN"''')

    def test_integer_overflow_becomes_double(self):
        self.same('''10 A%=30000:B%=300:PRINT A%+A%;B%*B%;-A%-A%;ABS(-32767-1)
20 S#=0:FOR I%=1 TO 300 STEP 50:S#=S#+I%*I%:NEXT:PRINT S#
30 X=B%*B%/7:PRINT X
40 C%=A%+A%''')

    def test_comparisons(self):
        self.same('''10 A=1/3:B=0.333333
20 PRINT A=B;A>B;A<B;A<>B;A>=B;A<=B
30 IF A THEN PRINT "VRAI"
40 IF 0.0 THEN PRINT "NON" ELSE PRINT "FAUX"
50 PRINT 1<2;2.5>2;-1=-1#;1/3=1/3!;"A"<"B";"AB">"A"''')

    def test_strings(self):
        self.same('''10 A$="BONJOUR":B$=""
20 PRINT LEFT$(A$,3);"|";RIGHT$(A$,4);"|";MID$(A$,2,3);"|";MID$(A$,5)
30 PRINT LEN(A$);LEN(B$);ASC(A$);VAL(" -123X");VAL("1.5E3")
40 PRINT CHR$(65)+CHR$(66);STR$(42);STR$(-7);HEX$(255);HEX$(0);HEX$(-1)
50 PRINT STRING$(3,"*");STRING$(2,45);LEFT$(A$,0);"|";LEFT$(A$,99)
60 C$=A$:C$=C$+"!":PRINT C$;LEN(C$)''')

    def test_control(self):
        self.same('''10 X=0
20 X=X+1:IF X<3 THEN 20
30 IF X=3 THEN PRINT "TROIS" ELSE PRINT "AUTRE"
40 FOR K=1 TO 4:ON K GOSUB 200,300:NEXT:PRINT
60 ON 2 GOTO 70,80
70 PRINT "MAUVAIS"
80 DEFFNC(T)=T*T+1:DEFFNH%(U)=U/2:DEFFNP=7
85 DEFFNA(X,Y)=X*Y-FNP
90 PRINT FNC(3);FNC(1/3);FNH%(7);FNA(3,4)
100 END
200 PRINT "A";:RETURN
300 PRINT "B";:RETURN''')

    def test_data_read(self):
        self.same('''10 READ A,B$,C,D%
20 PRINT A;B$;C;D%
30 RESTORE 100:READ F:PRINT F
40 RESTORE:READ G:PRINT G
50 READ X,X,X,X,X,X
90 DATA 1.5,"BON, JOUR",-5E-3,7.9
100 DATA 7, SANS GUILLEMETS ,&H10''')

    def test_arrays(self):
        self.same('''10 DIM T(5),M(2,3),N$(3),E%(4),S!(2)
20 FOR I=0 TO 5:T(I)=I*I/2:NEXT
30 M(2,3)=1/3:N$(2)="X"+STR$(T(5)):E%(4)=-7:S!(1)=2/3
40 PRINT T(5);M(2,3);N$(2);T(3);E%(4);S!(1)
50 K=6:T(K)=1''')

    def test_input(self):
        self.same('''10 INPUT "NOM";N$
20 INPUT "AGE";A:INPUT B%,C!
30 PRINT N$;A;B%;C!;A/3''', inputs=["TOTO", "12.5", "7.9, 0.125"])

    def test_errors(self):
        for src in ('10 A=0\n20 PRINT 1/A', '10 A%=0\n20 PRINT 5\\A%',
                    '10 A=1E62\n20 PRINT "X";A*100', '10 A%=40000.5',
                    '10 PRINT SQR(-1)', '10 PRINT 1;LOG(0)', '10 READ A,B\n20 DATA 1'):
            with self.subTest(src=src):
                self.same(src)


# ---------------------------------------------------------------- aléatoire

def s16(v):
    v &= 0xFFFF
    return v - 65536 if v > 32767 else v


class Overflow(Exception):
    pass


def ref_int(e, env):
    """Évaluation entière ; Overflow si un calcul sort des 16 bits."""
    k = e[0]
    if k == "num":
        return e[1]
    if k == "var":
        return env[e[1]]
    if k == "neg":
        v = -ref_int(e[1], env)
    elif k == "not":
        return s16(~ref_int(e[1], env))
    elif k == "fn":
        x = ref_int(e[2], env)
        v = abs(x) if e[1] == "ABS" else (x > 0) - (x < 0)
    else:
        op, a, b = e[1], ref_int(e[2], env), ref_int(e[3], env)
        if op in ("\\", "MOD") and b == 0:
            raise ZeroDivisionError
        v = {"+": lambda: a + b, "-": lambda: a - b, "*": lambda: a * b,
             "\\": lambda: int(a / b), "MOD": lambda: a - b * int(a / b),
             "AND": lambda: a & b, "OR": lambda: a | b, "XOR": lambda: a ^ b,
             "=": lambda: -(a == b), "<>": lambda: -(a != b), "<": lambda: -(a < b),
             ">": lambda: -(a > b), "<=": lambda: -(a <= b), ">=": lambda: -(a >= b),
             }[op]()
    if not -32768 <= v <= 32767:
        raise Overflow
    return v


def to_basic(e):
    k = e[0]
    if k in ("num", "flt"):
        v = e[1]
        return str(v) if not str(v).startswith("-") else "(%s)" % v
    if k == "var":
        return e[1]
    if k == "neg":
        return "(-%s)" % to_basic(e[1])
    if k == "not":
        return "(NOT %s)" % to_basic(e[1])
    if k == "fn":
        return "%s(%s)" % (e[1], to_basic(e[2]))
    op = e[1]
    sep = " %s " % op if op.isalpha() else op
    return "(%s%s%s)" % (to_basic(e[2]), sep, to_basic(e[3]))


INT_OPS = ["+", "-", "*", "\\", "MOD", "AND", "OR", "XOR", "=", "<>", "<", ">", "<=", ">="]


def rand_int(rnd, depth):
    if depth == 0 or rnd.random() < 0.25:
        if rnd.random() < 0.6:
            return ("var", rnd.choice("ABCDE"))
        return ("num", rnd.choice([0, 1, 2, 7, -1, -3, 100, 255, 32767,
                                   rnd.randrange(-32768, 32768)]))
    r = rnd.random()
    if r < 0.08:
        return ("neg", rand_int(rnd, depth - 1))
    if r < 0.12:
        return ("not", rand_int(rnd, depth - 1))
    if r < 0.18:
        return ("fn", rnd.choice(["ABS", "SGN"]), rand_int(rnd, depth - 1))
    return ("bin", rnd.choice(INT_OPS), rand_int(rnd, depth - 1), rand_int(rnd, depth - 1))


FLOATS = ["1.5", "0.1", "3.14159265", "1E5", "2.5!", "7#", "1E-3", "123456",
          "1234567", "0.333333", "2", "10", "100"]


def rand_float(rnd, depth):
    if depth == 0 or rnd.random() < 0.3:
        r = rnd.random()
        if r < 0.5:
            return ("var", rnd.choice(["A", "B!", "C%", "D#"]))
        return ("flt", rnd.choice(FLOATS))
    r = rnd.random()
    if r < 0.08:
        return ("neg", rand_float(rnd, depth - 1))
    if r < 0.25:
        f = rnd.choice(["ABS", "INT", "FIX", "SGN", "SIN", "COS", "ATN", "CSNG", "CDBL"])
        return ("fn", f, rand_float(rnd, depth - 1))
    if r < 0.30:
        return ("fn", "SQR", ("fn", "ABS", rand_float(rnd, depth - 1)))
    if r < 0.35:
        return ("bin", "^", ("fn", "ABS", rand_float(rnd, depth - 1)),
                ("flt", rnd.choice(["2", "3", "0.5", "-1"])))
    if r < 0.45:
        b = rand_float(rnd, depth - 1)
        return ("bin", "/", rand_float(rnd, depth - 1),
                ("bin", "+", ("bin", "*", b, b), ("flt", "1")))
    op = rnd.choice(["+", "-", "*", "+", "-", "*", "<", ">", "=", "<>"])
    return ("bin", op, rand_float(rnd, depth - 1), rand_float(rnd, depth - 1))


@needs_rom
class TestRandom(OracleCase):
    def test_random_integer_expressions(self):
        """Entiers (DEFINT) : le compilateur calcule dans HL, la ROM dans FAC."""
        rnd = random.Random(42)
        for prog in range(12):
            env = {v: rnd.choice([0, 1, -1, 3, -7, 1000, 32767, -32768,
                                  rnd.randrange(-32768, 32768)]) for v in "ABCDE"}
            lines = ["10 DEFINT A-Z:" + ":".join("%s=%d" % (k, v) for k, v in env.items())]
            while len(lines) < 13:
                e = rand_int(rnd, 3)
                try:
                    ref_int(e, env)
                except (ZeroDivisionError, Overflow):
                    continue
                lines.append("%d PRINT %s" % (10 + 10 * len(lines), to_basic(e)))
            with self.subTest(prog=prog):
                self.same("\n".join(lines))

    def test_random_float_expressions(self):
        rnd = random.Random(7)
        for prog in range(15):
            lines = ["10 A=%s:B!=%s:C%%=%d:D#=%s" % (
                rnd.choice(["1/3", "2.5", "-7", "1E4"]), rnd.choice(["0.1", "-2.5", "1/7"]),
                rnd.choice([0, 3, -12]), rnd.choice(["3.14159265358979", "-1D-5", "2"]))]
            for k in range(10):
                lines.append("%d PRINT %s" % (20 + 10 * k, to_basic(rand_float(rnd, 3))))
            with self.subTest(prog=prog):
                self.same("\n".join(lines))

    def test_random_string_functions(self):
        rnd = random.Random(5)
        for _ in range(4):
            lines = []
            for k in range(6):
                s = "".join(rnd.choice("ABCXYZ ") for _ in range(rnd.randrange(0, 12)))
                n, p = rnd.randrange(0, 15), rnd.randrange(1, 15)
                lines.append('%d S$="%s":PRINT "[";LEFT$(S$,%d);"|";RIGHT$(S$,%d);"|";'
                             'MID$(S$,%d,%d);"|";MID$(S$,%d);"]"' % (10 + 10 * k, s, n, n, p, n, p))
            self.same("\n".join(lines))


# ---------------------------------------------------------------- machine

@needs_rom
class TestMachine(unittest.TestCase):
    def _machine(self, src):
        mem, entry, _ = build(src)
        m = emu.boot(16)
        for a, b in mem.items():
            m.mem[a] = b
        m.cache.clear()
        top = min(mem) - 1
        for adr, v in ((0x01DF, top), (0x0204, top), (0x01DD, top - 50)):
            m.mem[adr], m.mem[adr + 1] = v & 0xFF, v >> 8
        m.sp = top - 50
        from x07asm.sim import EXIT
        m.push(EXIT)
        m.pc = entry
        return m

    def test_break(self):
        m = self._machine("10 GOTO 10")
        m.mem[0x2B] = 0x01
        m.run(200000)
        self.assertIn("Break", m.output())
        self.assertEqual(m.mem[0x2B] & 0x05, 0)

    def test_off_during_loop(self):
        m = self._machine("10 FOR I=1 TO 3:NEXT:PRINT I")
        m.mem[0x2B] = 0x80
        m.run(500000)
        self.assertEqual(m.powered_off, 1)
        self.assertEqual(m.output().split(), ["4"])

    def test_break_during_input(self):
        m = compiled('10 INPUT A\n20 PRINT "NON"', inputs=[None])
        self.assertIn("Break", m.output())
        self.assertNotIn("NON", m.output())

    def test_registers_and_hook_restored(self):
        m = self._machine('10 A=5:GOSUB 20:END\n20 PRINT A/3:RETURN')
        hook = bytes(m.mem[0xAB:0xAE])
        m.set16("HL", 0x1234)
        m.ix, m.iy = 0x5678, 0x9ABC
        m.run(2_000_000)
        self.assertEqual((m.get16("HL"), m.ix, m.iy), (0x1234, 0x5678, 0x9ABC))
        self.assertEqual(bytes(m.mem[0xAB:0xAE]), hook)

    def test_hook_restored_after_error(self):
        m = self._machine('10 PRINT 1/0')
        hook = bytes(m.mem[0xAB:0xAE])
        m.run(2_000_000)
        self.assertIn("/0 Error", m.output())
        self.assertEqual(bytes(m.mem[0xAB:0xAE]), hook)

    def test_graphics(self):
        m = compiled("10 PSET(3,4):PRINT POINT(3,4);POINT(5,5)\n"
                     "20 LINE(0,0)-(10,10):CIRCLE(20,15),5:PRESET(3,4)")
        cmds = [c for c, _ in m.t6log if c in (0x10, 0x11, 0x12, 0x14, 0x15)]
        self.assertEqual(cmds, [0x11, 0x10, 0x10, 0x14, 0x15, 0x12])
        self.assertIn("-1  0", m.output())


class TestCompileErrors(unittest.TestCase):
    def test_compile_errors(self):
        for src in ("10 GOTO 99", "10 A$=5", "10 NEXT", "10 FOR I=1 TO 2",
                    "10 PRINT \"A\"+1", "20 PRINT\n10 PRINT", "10 X=FNZ(1)",
                    "10 DIM A(N)", "10 LPRINT 1", '10 INPUT "X",A', "10 A%=40000%",
                    "10 DEF FNA(X)=X"):
            with self.subTest(src=src):
                with self.assertRaises(CompileError):
                    build(src)

    def test_integer_program_needs_no_rom_constant(self):
        asm, _ = compile_basic("10 DEFINT A-Z:FOR I=1 TO 10:A=A+I:NEXT:PRINT A")
        self.assertNotIn("FLT_", asm)


if __name__ == "__main__":
    unittest.main()
