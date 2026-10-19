"""Tests de la compilation directe QuickBASIC -> assembleur (x07asm/qbcomp.py).

Les programmes s'exécutent dans l'émulateur (vraie ROM) ; leur sortie est
comparée à celle qu'aurait donnée QuickBASIC."""
import contextlib
import io
import os
import shutil
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from x07asm import emu, qbcomp, qbasic        # noqa: E402
from x07asm.asm import Assembler             # noqa: E402
from tests import test_qbasic                 # noqa: E402

needs_rom = unittest.skipUnless(emu.rom_path() is not None, "ROM_x07/x07.bin absente")


def run(src, inputs=(), keys=""):
    asm, comp, warns = qbcomp.compile_qbasic(src, "T", 0x3000)
    a = Assembler()
    mem = a.assemble_text(asm)
    assert not a.errors, a.errors[:3]
    m = emu.run_binary(mem, a.entry, keys=keys, inputs=inputs)
    return m, asm, warns


@needs_rom
class TestDirect(unittest.TestCase):
    def qb(self, src, expected, inputs=()):
        m, asm, warns = run(src, inputs)
        self.assertEqual(m.output().rstrip("\n"), expected.rstrip("\n"), src)
        return asm, warns

    def test_listing_shows_source_lines(self):
        # le listing montre chaque ligne QuickBASIC au-dessus de son code
        asm, _, _ = qbcomp.compile_qbasic("DEFINT A-Z\n' rien\nx = 1\n\tPRINT x\n", "T", 0x3000)
        self.assertIn("; 3: x = 1\nLN_3:", asm)
        self.assertIn("; 4: PRINT x\nLN_4:", asm)
        self.assertNotIn("; 2:", asm)                         # pas de code : pas de ligne

    def test_beep_and_sound(self):
        m, _, warns = run(test_qbasic.TestQBasic.BEEP_SRC)
        self.assertEqual(m.notes, test_qbasic.TestQBasic.BEEP_NOTES)
        self.assertEqual(len(warns), 2)

    def test_recursive_functions_and_sub(self):
        self.qb('''
DECLARE FUNCTION Fact# (n%)
DECLARE FUNCTION Fib% (n%)
DECLARE SUB Hanoi (n%, de%, vers%, par%)
DIM SHARED coups AS INTEGER
PRINT Fact#(10); Fib%(15)
Hanoi 4, 1, 3, 2
PRINT "Hanoi :"; coups
END
FUNCTION Fact# (n%)
    IF n% <= 1 THEN Fact# = 1 ELSE Fact# = n% * Fact#(n% - 1)
END FUNCTION
FUNCTION Fib% (n%)
    IF n% < 2 THEN
        Fib% = n%
    ELSE
        Fib% = Fib%(n% - 1) + Fib%(n% - 2)
    END IF
END FUNCTION
SUB Hanoi (n%, de%, vers%, par%)
    IF n% = 0 THEN EXIT SUB
    Hanoi n% - 1, de%, par%, vers%
    coups = coups + 1
    Hanoi n% - 1, par%, vers%, de%
END SUB''', " 3628800  610 \nHanoi : 15 \n")

    def test_quicksort_two_arrays_one_copy(self):
        asm, _ = self.qb('''
DECLARE SUB Tri (t%(), g%, d%)
DIM a%(9), b%(5)
FOR i% = 0 TO 9: READ a%(i%): NEXT
FOR i% = 0 TO 5: READ b%(i%): NEXT
DATA 5, 3, 9, 1, 7, 0, 8, 2, 6, 4
DATA 60, 10, 50, 20, 40, 30
Tri a%(), 0, 9
Tri b%(), 0, 5
FOR i% = 0 TO 9: PRINT a%(i%);: NEXT: PRINT
FOR i% = 0 TO 5: PRINT b%(i%);: NEXT: PRINT
SUB Tri (t%(), g%, d%)
    IF g% >= d% THEN EXIT SUB
    pivot% = t%((g% + d%) \\ 2)
    i% = g%: j% = d%
    DO WHILE i% <= j%
        DO WHILE t%(i%) < pivot%: i% = i% + 1: LOOP
        DO WHILE t%(j%) > pivot%: j% = j% - 1: LOOP
        IF i% <= j% THEN
            SWAP t%(i%), t%(j%)
            i% = i% + 1: j% = j% - 1
        END IF
    LOOP
    Tri t%(), g%, j%
    Tri t%(), i%, d%
END SUB''', " 0  1  2  3  4  5 \n 6  7  8  9 \n 10  20  30  40  50  60 \n")
        self.assertEqual(asm.count("QP_TRI:"), 1)       # une seule copie de la procédure
        self.assertIn("CALL RT_PA1", asm)               # tableau atteint par son adresse

    def test_by_reference_through_recursion(self):
        self.qb('''
DECLARE SUB Compte (n%, total%)
t% = 0
Compte 5, t%
PRINT t%
SUB Compte (n%, total%)
  IF n% = 0 THEN EXIT SUB
  total% = total% + n%
  Compte n% - 1, total%
END SUB''', " 15 \n")

    def test_for_loops_inside_recursion(self):
        # permutations : la boucle FOR (variable et limite) est propre à chaque appel
        self.qb('''
DECLARE SUB Place (k%)
DIM SHARED n%, compte%, pris%(5)
n% = 4
Place 1
PRINT compte%
SUB Place (k%)
  IF k% > n% THEN compte% = compte% + 1: EXIT SUB
  FOR v% = 1 TO n%
    IF pris%(v%) = 0 THEN
      pris%(v%) = 1
      Place k% + 1
      pris%(v%) = 0
    END IF
  NEXT
END SUB''', " 24 \n")

    def test_recursive_strings(self):
        self.qb('''
DECLARE FUNCTION Envers$ (s$)
PRINT Envers$("BONJOUR")
FUNCTION Envers$ (s$)
  IF LEN(s$) <= 1 THEN Envers$ = s$ ELSE Envers$ = Envers$(MID$(s$, 2)) + LEFT$(s$, 1)
END FUNCTION''', "RUOJNOB\n")

    def test_two_dimension_array_parameter(self):
        self.qb('''
DECLARE SUB Remplir (m%(), n%)
DIM a%(2, 3)
Remplir a%(), 10
PRINT a%(0, 0); a%(1, 2); a%(2, 3)
SUB Remplir (m%(), n%)
  FOR i% = 0 TO 2: FOR j% = 0 TO 3: m%(i%, j%) = n% * i% + j%: NEXT: NEXT
END SUB''', " 0  12  23 \n")

    def test_errors_at_run_time(self):
        m, _, _ = run('''
DECLARE SUB Pose (t%())
DIM a%(3)
Pose a%()
SUB Pose (t%())
  t%(5) = 1
END SUB''')
        self.assertIn("BS Error", m.output())
        m, _, _ = run('''
DECLARE FUNCTION P% (n%)
PRINT P%(20000)
FUNCTION P% (n%)
  IF n% = 0 THEN P% = 0 ELSE P% = P%(n% - 1) + 1
END FUNCTION''')
        self.assertIn("OM Error", m.output())             # récursivité trop profonde

    def test_example_mots_strings(self):
        with open(os.path.join(ROOT, "exemples", "qbasic", "mots.qbas"), encoding="utf-8") as f:
            src = f.read()
        asm, _, _ = qbcomp.compile_qbasic(src, "T", 0x2000)
        a = Assembler()
        m = emu.run_binary(a.assemble_text(asm), a.entry, inputs=["RADAR"], keys=" ")
        screen = m.screen_text()
        for row in ("Mot     : RADAR", "Envers  : RADAR", "Cesar+3 : UDGDU",
                    "Voyelles : 2 PALIN"):
            self.assertIn(row, screen)

    def test_long_names_kept(self):
        _, asm, _ = run('alphabet = 1: alphanumerique = 2: total = 3\nPRINT alphabet; total')
        self.assertIn("V_ALPHABET_F", asm)
        self.assertIn("V_ALPHANUMERIQUE_F", asm)

    def test_parameter_type_mismatch(self):
        # QuickBASIC : « Parameter type mismatch » pour un tableau ou une variable
        # passée par référence ; une expression est convertie
        refused = (
            ("DEFINT A-Z\nDECLARE SUB S (t())\nDIM b(5) AS DOUBLE\nS b()\nSUB S (t())\nEND SUB",
             "B() est de type double précision"),
            ("DECLARE SUB S (n%)\nx! = 2.5\nS x!\nSUB S (n%)\nEND SUB",
             "passez une expression : (X!)"),
            ('DECLARE SUB S (n%)\nS "A"\nSUB S (n%)\nEND SUB', "reçoit une chaîne"),
            ("DECLARE SUB S (a$)\nS 3\nSUB S (a$)\nEND SUB", "reçoit un nombre"))
        for src, msg in refused:
            with self.assertRaises(qbasic.QBError) as cm:
                qbcomp.compile_qbasic(src)
            self.assertIn(msg, str(cm.exception), src)
            self.assertIn("Parameter type mismatch", str(cm.exception))
        qbcomp.compile_qbasic("DECLARE SUB S (n%)\nx! = 2.5\nS (x!)\nS x! + 1\nS 3.7\nSUB S (n%)\nEND SUB")

    def test_refused(self):
        for src, msg in (("PRINT INSTR(\"AB\", \"B\")", "INSTR"),
                         ("n = 3\nDIM t(n)", "constantes"),
                         ("PRINT UCASE$(\"a\")", "UCASE$")):
            with self.assertRaises(qbasic.QBError) as cm:
                qbcomp.compile_qbasic(src)
            self.assertIn(msg, str(cm.exception), src)

    def test_command_direct(self):
        from x07asm.cli import main
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "tri.qbas")
            shutil.copy(os.path.join(ROOT, "exemples", "qbasic", "tri2.qbas"), path)
            with contextlib.redirect_stdout(io.StringIO()) as out:
                self.assertEqual(main(["qb", path, "--direct"]), 0)
            self.assertTrue(os.path.exists(os.path.join(d, "tri.asm")))
            self.assertFalse(os.path.exists(os.path.join(d, "tri.bas")))
            with contextlib.redirect_stdout(io.StringIO()) as out:
                self.assertEqual(main(["run", path, "--direct"]), 0)
            self.assertIn("Moyenne : 11.5", out.getvalue())


@needs_rom
class TestDirectAgainstTranslatorSuite(test_qbasic.TestQBasic):
    """Les programmes des tests de la traduction, compilés directement."""

    def qb(self, src, expected, inputs=(), compiled=True):
        m, asm, warns = run(src, inputs)
        self.assertEqual(m.output().rstrip("\n"), expected.rstrip("\n"), src)
        return asm, warns

    def test_print_using_like_the_rom(self):
        # champs numériques : la routine de la ROM ($BBAC), comme son PRINT USING
        vals = ["0", "-3", "1234", "0.5", "-2.345", "99.996", "1E6"]
        fmts = ["####", "##.##", "+##.#", "##.#-", ".##", "X=#### Y=##.#", "#,###",
                "##,##.##", "**##", "$$##.##", "**$##.#", "###+"]
        src = "".join('PRINT USING "%s"; %s\n' % (f, v) for f in fmts for v in vals)
        src += 'PRINT USING "##"; 1; 2; 3\nPRINT USING "A=## "; 7;\nPRINT "/"\n'
        out, _, _ = qbasic.translate(src)
        rom, _ = emu.run_basic(out)
        m, _, _ = run(src)
        self.assertEqual(m.output(), rom)
        # chaînes (que la ROM ne connaît pas) : comme QuickBASIC
        m, _, _ = run('PRINT USING "! & [\\  \\]"; "ABCD"; "EFGH"; "IJKLMN"\n')
        self.assertEqual(m.output(), "A EFGH [IJKL]\n")
        for bad in ('PRINT USING "#.##^^^^"; 1', 'f$ = "#"\nPRINT USING f$; 1'):
            with self.assertRaises(qbasic.QBError):
                run(bad + "\n")

    def test_timer(self):
        import datetime
        asm, _, _ = qbcomp.compile_qbasic("t! = TIMER\nPRINT t!\nRANDOMIZE TIMER\n", "T", 0x3000)
        a = Assembler()
        m = emu.prepare_binary(a.assemble_text(asm), a.entry)
        m.clock = lambda: datetime.datetime(2026, 10, 18, 12, 3, 30)
        m.run(5_000_000)
        self.assertEqual(m.output().strip(), str(12 * 3600 + 3 * 60 + 30))

    def test_ubound_variable_size(self):
        with self.assertRaises(qbasic.QBError):                  # tailles fixes seulement
            run("DEFINT A-Z\nn = 6\nDIM v(n)\nPRINT UBOUND(v)\n")

    def test_recursive_function_reads_bounds_of_received_array(self):
        m, _, _ = run('''DEFINT A-Z
DECLARE FUNCTION Somme (t(), k)
DIM b(1 TO 4)
FOR i = 1 TO 4: b(i) = i * 10: NEXT
PRINT Somme(b(), UBOUND(b))
FUNCTION Somme (t(), k)
IF k < LBOUND(t) THEN Somme = 0 ELSE Somme = t(k) + Somme(t(), k - 1)
END FUNCTION
''')
        self.assertEqual(m.output().strip(), "100")

    def test_redim(self):
        # tableaux de taille fixe : REDIM refusé, avec le conseil de traduire
        with self.assertRaises(qbasic.QBError) as cm:
            run("DEFINT A-Z\nREDIM a(5)\n")
        self.assertIn("sans --direct", str(cm.exception))

    # tests propres à la traduction en BASIC, refaits pour la compilation directe
    def test_blocks_sub_function_by_reference(self):
        import inspect
        src = inspect.getsource(test_qbasic.TestQBasic.test_blocks_sub_function_by_reference)
        self.qb(src.split("self.qb(\'\'\'", 1)[1].split("\'\'\'", 1)[0],
                "SOMME 55 \nUNPLUSPLUS\nPETIT\n")

    def test_example_tri2_same_sub_two_arrays(self):
        asm, _ = self.qb(self.example("tri2.qbas"),
                         " 6  7  9  11  12 \n 14  15  18 \nMoyenne : 11.5 \n")
        self.assertEqual(asm.count("QP_TRIER:"), 1)

    def test_instr_rom_only(self):
        with self.assertRaises(qbasic.QBError):
            qbcomp.compile_qbasic('PRINT INSTR("BONJOUR", "J")')

    def test_example_mystere(self):
        inputs = [str(i) for i in range(1, 101)]
        m, _, _ = run(self.example("mystere.qbas"), inputs, keys="X")
        out = m.output()
        self.assertTrue(out.rstrip().endswith("Trouve en %d coups" % (out.count("Plus grand") + 1)))

    def test_screen_coordinates(self):
        m, _, _ = run('CLS\nLOCATE 2, 3: PRINT "X";\nPRINT POS(0); CSRLIN;')
        self.assertEqual(m.screen_text().splitlines()[2].rstrip("| "), "|  X 4  2")

    def test_graphics_box(self):
        m, _, _ = run('LINE (10, 10)-(30, 20), , B\nLINE (40, 10)-(45, 13), , BF\n'
                      'PSET (60, 14)\nPSET (61, 14)\nPSET (61, 14), 0')
        lcd = m.lcd
        self.assertTrue(lcd.get(30, 20) and lcd.get(20, 10) and lcd.get(10, 15) and lcd.get(60, 14))
        self.assertFalse(lcd.get(20, 15) or lcd.get(61, 14))
        self.assertTrue(all(lcd.get(x, y) for x in range(40, 46) for y in range(10, 14)))

    def test_refused(self):                     # la récursivité est permise ici
        m, _, _ = run("DECLARE FUNCTION F (n)\nPRINT F(5)\nFUNCTION F (n)\n"
                      "IF n = 0 THEN F = 1 ELSE F = n * F(n - 1)\nEND FUNCTION")
        self.assertEqual(m.output(), " 120 \n")
        for src in ("TYPE Point\nx AS INTEGER\nEND TYPE", 'OPEN "F" FOR RANDOM AS #1',
                    "DIM t(2 TO 5)"):
            with self.assertRaises(qbasic.QBError):
                qbcomp.compile_qbasic(src)

    def test_warnings(self):
        _, _, warns = run("SCREEN 1\nCOLOR 2\nx& = 5\nPRINT x&")
        text = " ".join(warns)
        for w in ("SCREEN", "COLOR", "LONG"):
            self.assertIn(w, text)

    # traduction seulement (nom du .bas produit, lecture par la ROM)
    def test_command_output_name(self):
        pass

    def test_commands_accept_qbas(self):
        pass

    def test_locals_are_reset_unless_static(self):
        test_qbasic.TestQBasic.test_locals_are_reset_unless_static(self)

if __name__ == "__main__":
    unittest.main()
