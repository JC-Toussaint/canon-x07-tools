"""Tests du compilateur BASIC : compilation, assemblage, exécution simulée."""
import os
import random
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from x07asm.basic import compile_basic, CompileError      # noqa: E402
from x07asm.asm import Assembler                           # noqa: E402
from x07asm.sim import run_program, SimError               # noqa: E402


def run(src, keys="", lines=None, **opts):
    asm, comp = compile_basic(src, "T", 0x1000, **opts)
    a = Assembler()
    mem = a.assemble_text(asm)
    if a.errors:
        raise AssertionError("%s\n%s" % (a.errors[0], asm))
    m = run_program(mem, a.entry, keys, lines, max_steps=5_000_000)
    return m.output(), m


def s16(v):
    v &= 0xFFFF
    return v - 65536 if v > 32767 else v


def ref_eval(e, env):
    k = e[0]
    if k == "num":
        return e[1]
    if k == "var":
        return env[e[1]]
    if k == "neg":
        return s16(-ref_eval(e[1], env))
    if k == "not":
        return s16(~ref_eval(e[1], env))
    if k == "fn":
        x = ref_eval(e[2], env)
        return {"ABS": s16(abs(x)), "SGN": (x > 0) - (x < 0)}[e[1]]
    op, a, b = e[1], ref_eval(e[2], env), ref_eval(e[3], env)
    if op in ("/", "MOD") and b == 0:
        raise ZeroDivisionError
    return s16({
        "+": lambda: a + b, "-": lambda: a - b, "*": lambda: a * b,
        "/": lambda: int(a / b), "MOD": lambda: a - b * int(a / b),
        "AND": lambda: a & b, "OR": lambda: a | b, "XOR": lambda: a ^ b,
        "=": lambda: -(a == b), "<>": lambda: -(a != b), "<": lambda: -(a < b),
        ">": lambda: -(a > b), "<=": lambda: -(a <= b), ">=": lambda: -(a >= b),
        "^": lambda: a ** b if b >= 0 else 0,
    }[op]())


def to_basic(e):
    k = e[0]
    if k == "num":
        return str(e[1]) if e[1] >= 0 else "(%d)" % e[1]
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


OPS = ["+", "-", "*", "/", "MOD", "AND", "OR", "XOR", "=", "<>", "<", ">", "<=", ">="]


def rand_expr(rnd, depth):
    if depth == 0 or rnd.random() < 0.25:
        if rnd.random() < 0.6:
            return ("var", rnd.choice("ABCDE"))
        return ("num", rnd.choice([0, 1, 2, 7, -1, -3, 100, 255, 32767, -32768,
                                   rnd.randrange(-32768, 32768)]))
    r = rnd.random()
    if r < 0.08:
        return ("neg", rand_expr(rnd, depth - 1))
    if r < 0.12:
        return ("not", rand_expr(rnd, depth - 1))
    if r < 0.18:
        return ("fn", rnd.choice(["ABS", "SGN"]), rand_expr(rnd, depth - 1))
    if r < 0.21:
        return ("bin", "^", rand_expr(rnd, depth - 1), ("num", rnd.randrange(0, 4)))
    return ("bin", rnd.choice(OPS), rand_expr(rnd, depth - 1), rand_expr(rnd, depth - 1))


class TestArithmetic(unittest.TestCase):
    def test_random_expressions(self):
        rnd = random.Random(42)
        for prog in range(25):
            env = {v: rnd.choice([0, 1, -1, 3, -7, 1000, 32767, -32768,
                                  rnd.randrange(-32768, 32768)]) for v in "ABCDE"}
            lines = ["10 " + ":".join("%s=%d" % (k, v) for k, v in env.items())]
            exprs, expect = [], []
            while len(exprs) < 12:
                e = rand_expr(rnd, 3)
                try:
                    expect.append(ref_eval(e, env))
                except ZeroDivisionError:
                    continue
                exprs.append(e)
            for i, e in enumerate(exprs):
                lines.append("%d PRINT %s" % (20 + i, to_basic(e)))
            out, _ = run("\n".join(lines))
            got = [int(x) for x in out.split()]
            for e, x, y in zip(exprs, got, expect):
                self.assertEqual(x, y, "%s avec %s" % (to_basic(e), env))

    def test_division_by_zero(self):
        out, m = run("10 A=0\n20 PRINT 5/A\n30 PRINT \"PAS ICI\"")
        self.assertIn("?DIV0", out)
        self.assertNotIn("PAS ICI", out)

    def test_print_format(self):
        out, _ = run('10 PRINT 5;-5;0;"X";32767;-32768')
        self.assertEqual(out, " 5 -5  0 X 32767 -32768 \n")


class TestStrings(unittest.TestCase):
    def test_functions(self):
        src = '''
10 A$="BONJOUR":B$=""
20 PRINT LEFT$(A$,3);"|";RIGHT$(A$,4);"|";MID$(A$,2,3);"|";MID$(A$,5)
30 PRINT LEN(A$);LEN(B$);ASC(A$);ASC(B$);VAL(" -123X");VAL("&HFF")
40 PRINT CHR$(65)+CHR$(66);STR$(42);STR$(-7);HEX$(255);HEX$(0);HEX$(-1)
50 PRINT STRING$(3,"*");STRING$(2,45);LEFT$(A$,0);"|";LEFT$(A$,99);MID$(A$,9)
60 C$=A$+" "+A$:PRINT C$
70 C$=A$:C$=C$+"!":PRINT C$;LEN(C$)
80 PRINT ("ABC"<"ABD");("AB"<"ABC");("B">"ABC");(A$=A$);("A"<>"A");(""<"A")
'''
        out, _ = run(src)
        self.assertEqual(out.split("\n")[:7], [
            "BON|JOUR|ONJ|OUR",
            " 7  0  66  0 -123  255 ",
            "AB 42-7FF0FFFF",
            "***--|BONJOUR",
            "BONJOUR BONJOUR",
            "BONJOUR! 8 ",
            "-1 -1 -1 -1  0 -1 ",
        ])

    def test_truncation(self):
        out, _ = run('10 A$="ABCDEFGHIJ":FOR I=1 TO 3:A$=A$+A$:NEXT:PRINT LEN(A$)',
                     strcap=50)
        self.assertEqual(out.split(), ["50"])

    def test_random_string_ops(self):
        rnd = random.Random(5)
        for _ in range(8):
            s = "".join(rnd.choice("ABCXYZ ") for _ in range(rnd.randrange(0, 12)))
            n, p = rnd.randrange(-2, 15), rnd.randrange(-1, 15)
            lines = ['10 S$="%s":N=%d:P=%d' % (s, n, p),
                     '20 PRINT "[";LEFT$(S$,N);"]"', '30 PRINT "[";RIGHT$(S$,N);"]"',
                     '40 PRINT "[";MID$(S$,P,N);"]"', '50 PRINT "[";MID$(S$,P);"]"']
            out, _ = run("\n".join(lines))
            nn = max(n, 0)
            pp = max(p, 1)
            exp = [s[:nn], s[len(s) - nn:] if nn < len(s) else s,
                   s[pp - 1:pp - 1 + nn], s[pp - 1:]]
            self.assertEqual(out.split("\n")[:4], ["[%s]" % x for x in exp], (s, n, p))


class TestControl(unittest.TestCase):
    def test_for_loops(self):
        src = '''
10 FOR I=1 TO 3:PRINT I;:NEXT:PRINT
20 FOR I=10 TO 1 STEP -3:PRINT I;:NEXT I:PRINT
30 S=2:FOR I=0 TO 6 STEP S:PRINT I;:NEXT:PRINT
40 S=-2:FOR I=0 TO -4 STEP S:PRINT I;:NEXT:PRINT
50 FOR I=32765 TO 32767:PRINT I;:NEXT:PRINT
60 FOR I=1 TO 2:FOR J=1 TO 2:PRINT I*10+J;:NEXT J,I:PRINT
70 FOR I=5 TO 1:PRINT "UNE FOIS";:NEXT:PRINT
'''
        out, _ = run(src)
        self.assertEqual(out.split("\n")[:7], [
            " 1  2  3 ", " 10  7  4  1 ", " 0  2  4  6 ", " 0 -2 -4 ",
            " 32765  32766  32767 ", " 11  12  21  22 ", "UNE FOIS"])

    def test_if_goto_gosub_on_while(self):
        src = '''
10 X=0
20 X=X+1:IF X<3 THEN 20
30 IF X=3 THEN PRINT "TROIS" ELSE PRINT "AUTRE"
40 IF X<>3 THEN PRINT "NON" ELSE PRINT "OUI":PRINT "SUITE"
50 FOR K=1 TO 4:ON K GOSUB 200,300:NEXT
60 ON 2 GOTO 70,80
70 PRINT "MAUVAIS"
80 W=1:WHILE W<100:W=W*3:WEND:PRINT W
90 IF X=3 THEN IF W=243 THEN PRINT "IMBRIQUE" ELSE PRINT "NON"
100 END
200 PRINT "A";:RETURN
300 PRINT "B";:RETURN
'''
        out, _ = run(src)
        self.assertEqual(out.split("\n")[:5],
                         ["TROIS", "OUI", "SUITE", "AB 243 ", "IMBRIQUE"])

    def test_data_read_restore(self):
        src = '''
10 READ A,B$,C:PRINT A;B$;C
20 READ D$,E$:PRINT D$;"|";E$
30 RESTORE 100:READ F:PRINT F
40 RESTORE:READ G:PRINT G
50 READ X,X,X,X,X,X
90 DATA 12,"BON, JOUR",-5
100 DATA 7, SANS GUILLEMETS ,&H10
'''
        out, _ = run(src)
        self.assertEqual(out.split("\n")[:5],
                         [" 12 BON, JOUR-5 ", "7|SANS GUILLEMETS", " 7 ", " 12 ", "?DATA"])

    def test_arrays(self):
        src = '''
10 DIM T(5),M(2,3),N$(3)
20 FOR I=0 TO 5:T(I)=I*I:NEXT
30 FOR I=0 TO 2:FOR J=0 TO 3:M(I,J)=I*10+J:NEXT:NEXT
40 N$(1)="UN":N$(3)="TROIS":N$(2)=N$(1)+N$(3)
50 PRINT T(5);T(2);M(2,3);M(1,2);M(0,0);N$(2);LEN(N$(0))
60 K=6:PRINT T(K)
'''
        out, _ = run(src)
        self.assertEqual(out.split("\n")[:2], [" 25  4  23  12  0 UNTROIS 0 ", "?INDICE"])

    def test_input(self):
        out, _ = run('10 INPUT "NOM";N$\n20 INPUT A,B\n30 PRINT N$;A+B',
                     lines=["TOTO", "3, 4"])
        self.assertTrue(out.endswith("TOTO 7 \n"), out)

    def test_def_fn(self):
        out, _ = run("10 DEF FNC(X)=X*X+1\n20 DEF FND(A,B)=A-B\n"
                     "30 PRINT FNC(3);FND(10,FNC(2));FNC(FNC(1))")
        self.assertEqual(out.split(), ["10", "5", "5"])

    def test_crunched_source(self):
        out, _ = run('10 FORI=1TO3:PRINTI;:NEXT:IFI=4THENPRINT"OK"')
        self.assertEqual(out.split(), ["1", "2", "3", "OK"])

    def test_inkey_and_graphics(self):
        src = '''
10 K$=INKEY$:IF K$="" THEN 10
20 PRINT "TOUCHE ";K$
30 PSET(3,4):PRINT POINT(3,4);POINT(5,5)
40 LINE(0,0)-(10,10):CIRCLE(20,15),5:PRESET(3,4):PRINT POINT(3,4)
50 LOCATE 5,2:PRINT "ICI";
60 CLS:PRINT CSRLIN;POS(0)
'''
        out, m = run(src, keys="Z")
        self.assertIn("TOUCHE Z", out)
        self.assertIn("-1  0 \n 0 ", out)
        self.assertEqual([c for c, _ in m.t6log], [0x11, 0x10, 0x10, 0x14, 0x15, 0x12, 0x10])
        self.assertEqual(m.t6log[3][1], [0, 0, 10, 10])
        self.assertEqual("".join(m.screen[0]).rstrip(), " 0  3")

    def test_break_stops_infinite_loop(self):
        asm, _ = compile_basic("10 GOTO 10", "T", 0x1000)
        a = Assembler()
        mem = a.assemble_text(asm)
        from x07asm.sim import X07, EXIT
        m = X07()
        m.load(mem)
        m.sp = 0x1000
        m.push(EXIT)
        m.pc = a.entry
        m.mem[0x2B] = 1                     # BREAK enfoncée
        m.run(100000)
        self.assertIn("?BREAK", m.output())
        self.assertEqual(m.mem[0x2B], 0)

    def test_registers_restored(self):
        asm, _ = compile_basic('10 A=5:GOSUB 20:END\n20 PRINT A:RETURN', "T", 0x1000)
        a = Assembler()
        mem = a.assemble_text(asm)
        from x07asm.sim import X07, EXIT
        m = X07()
        m.load(mem)
        m.sp = 0x1000
        m.push(EXIT)
        m.set16("HL", 0x1234)
        m.ix, m.iy = 0x5678, 0x9ABC
        m.pc = a.entry
        m.run()
        self.assertEqual((m.get16("HL"), m.ix, m.iy, m.sp), (0x1234, 0x5678, 0x9ABC, 0x1000))


class TestRomConventions(unittest.TestCase):
    """Comportements vérifiés dans le vidage de la ROM (ROM_x07/x07.bin)."""

    def _machine(self, src):
        asm, _ = compile_basic(src, "T", 0x1000)
        a = Assembler()
        mem = a.assemble_text(asm)
        from x07asm.sim import X07, EXIT
        m = X07()
        m.load(mem)
        m.sp = 0x1000
        m.push(EXIT)
        m.pc = a.entry
        return m

    def test_locate_position(self):
        out, m = run('10 CLS:LOCATE 5,2:PRINT "ICI";:PRINT CSRLIN;POS(0)')
        self.assertEqual("".join(m.screen[2])[5:8], "ICI")
        self.assertEqual((m.mem[0xB8], m.mem[0xB9]), (4, 1))    # ligne, colonne (base 1)
        self.assertIn("ICI 2  11", out)

    def test_tab_and_comma(self):
        out, _ = run('10 PRINT "A";TAB(5);"B",1')
        self.assertEqual(out, "A    B     1 \n")

    def test_break_clears_bits_0_and_2(self):
        m = self._machine("10 GOTO 10")
        m.mem[0x2B] = 0x01
        m.run(100000)
        self.assertIn("?BREAK", m.output())
        self.assertEqual(m.mem[0x2B] & 0x05, 0)

    def test_off_during_loop(self):
        m = self._machine("10 FOR I=1 TO 3:NEXT:PRINT I")
        m.mem[0x2B] = 0x80
        m.run(100000)
        self.assertEqual(m.powered_off, 1)
        self.assertEqual(m.output().split(), ["4"])

    def test_break_during_input(self):
        out, _ = run('10 INPUT A\n20 PRINT "NON"', lines=[None])
        self.assertIn("?BREAK", out)
        self.assertNotIn("NON", out)


class TestErrors(unittest.TestCase):
    def test_compile_errors(self):
        for src in ("10 PRINT 1.5", "10 GOTO 99", "10 A$=5", "10 NEXT",
                    "10 FOR I=1 TO 2", "10 PRINT SIN(1)", "10 PRINT \"A\"+1",
                    "20 PRINT\n10 PRINT", "10 X=FNZ(1)", "10 DIM A(N)",
                    "10 LPRINT 1"):
            with self.subTest(src=src):
                with self.assertRaises(CompileError):
                    run(src)

    def test_debug_line_numbers(self):
        out, _ = run("10 A=0\n20 B=1/A", debug=True)
        self.assertIn("?DIV0 LIGNE 20", out)


if __name__ == "__main__":
    unittest.main()
