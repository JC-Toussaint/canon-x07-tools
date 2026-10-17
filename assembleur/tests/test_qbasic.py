"""Tests de la traduction QuickBASIC -> BASIC du X-07 (x07asm/qbasic.py).

Chaque programme est traduit, exécuté par la ROM du X-07 (émulateur) et
comparé à la sortie qu'aurait donnée QuickBASIC ; quand le compilateur
accepte le résultat, la version compilée doit afficher la même chose."""
import contextlib
import io
import os
import shutil
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from x07asm import emu, qbasic                # noqa: E402
from x07asm.asm import Assembler             # noqa: E402
from x07asm.basic import compile_basic       # noqa: E402

needs_rom = unittest.skipUnless(emu.rom_path() is not None, "ROM_x07/x07.bin absente")


@needs_rom
class TestQBasic(unittest.TestCase):
    def qb(self, src, expected, inputs=(), compiled=True):
        out, warns, _ = qbasic.translate(src)
        ref, m = emu.run_basic(out, inputs=inputs)
        self.assertIsNone(m.error, out)
        self.assertEqual(ref.rstrip("\n"), expected.rstrip("\n"), "\n" + out)
        if compiled:
            asm, _ = compile_basic(out, "T", 0x3000)
            a = Assembler()
            mc = emu.run_binary(a.assemble_text(asm), a.entry, inputs=inputs)
            self.assertEqual(mc.output().rstrip("\n"), ref.rstrip("\n"), "\n" + out)
        return out, warns

    def test_blocks_sub_function_by_reference(self):
        out, _ = self.qb('''
' Essai
DECLARE FUNCTION Carre% (n%)
DECLARE SUB Ligne (texte$, total)
CONST LIMITE = 5
DIM SHARED compteur AS INTEGER
total = 0
FOR i% = 1 TO LIMITE
    total = total + Carre%(i%)
NEXT i%
Ligne "SOMME", total
DO WHILE compteur < 3
    compteur = compteur + 1
    SELECT CASE compteur
        CASE 1: PRINT "UN";
        CASE 2 TO 3
            PRINT "PLUS";
        CASE ELSE
            PRINT "?";
    END SELECT
LOOP
PRINT
IF total > 50 THEN
    PRINT "GRAND"
ELSEIF total > 10 THEN
    PRINT "MOYEN"
ELSE
    PRINT "PETIT"
END IF
FOR k = 1 TO 0
    PRINT "JAMAIS"
NEXT
END

FUNCTION Carre% (n%)
    Carre% = n% * n%
END FUNCTION

SUB Ligne (texte$, total)
    PRINT texte$; total
    total = 0
END SUB
''', "SOMME 55 \nUNPLUSPLUS\nPETIT\n")
        self.assertTrue(out.startswith("10 DEFSNG A-Z\n"))

    def test_by_value_in_parentheses(self):
        self.qb('''
DECLARE SUB Inc (x)
a = 1: b = 1
Inc a
Inc (b)
PRINT a; b
SUB Inc (x)
  x = x + 1
END SUB''', " 2  1 \n")

    def test_integer_rounding(self):
        # QuickBASIC arrondit (le X-07 tronque) ; \\ et MOD identiques
        self.qb('a% = 2.7: b% = -2.7: c% = CINT(3.6)\nPRINT a%; b%; c%; 7 \\ 2; 7 MOD 3',
                " 3 -3  4  3  1 \n")

    def test_loops_and_exits(self):
        self.qb('''
i = 0
DO
  i = i + 1
  IF i = 3 THEN EXIT DO
LOOP
PRINT i;
FOR j = 1 TO 10
  IF j * j > 20 THEN EXIT FOR
NEXT
PRINT j;
k = 0
DO UNTIL k >= 4: k = k + 2: LOOP
PRINT k;
n = 10
DO: n = n - 3: LOOP WHILE n > 0
PRINT n;
w = 1
WHILE w < 100: w = w * 3: WEND
PRINT w''', " 3  5  4 -2  243 \n")

    def test_empty_for_with_variable_bounds(self):
        # le X-07 exécuterait le corps une fois : la traduction ajoute une garde
        self.qb('n = 0\nFOR i = 1 TO n: PRINT "X";: NEXT\nFOR i = n TO 1 STEP -1: PRINT "Y";: NEXT'
                '\nFOR i = 2 TO n STEP -1: PRINT "W";: NEXT'
                '\ns = -1\nFOR i = 1 TO 3 STEP s: PRINT "Z";: NEXT\nPRINT "FIN"', "WWWFIN\n")

    def test_strings(self):
        self.qb('''
a$ = "BONJOUR"
PRINT LEFT$(a$, 3); MID$(a$, 4, 2); RIGHT$(a$, 2); LEN(a$); SPACE$(2); "|"
PRINT ASC("A"); CHR$(66); STR$(5); VAL("12")''', "BONJOUR 7   |\n 65 B 5 12 \n")

    def test_instr_rom_only(self):
        _, warns = self.qb('PRINT INSTR("BONJOUR", "J")', " 4 \n", compiled=False)
        self.assertTrue(any("INSTR" in w for w in warns))

    def test_swap_deffn_const_select(self):
        self.qb('''
CONST PI = 3.14159
DEF FNAire (r) = PI * r * r
x = 1: y = 2: SWAP x, y: PRINT x; y;
PRINT INT(FNAire(2))
c$ = "B"
SELECT CASE c$
CASE "A": PRINT "a"
CASE "B", "C": PRINT "bc"
END SELECT
v = 7
SELECT CASE v
CASE IS < 0: PRINT "neg"
CASE 1 TO 5: PRINT "petit"
CASE IS >= 6: PRINT "grand"
END SELECT''', " 2  1  12 \nbc\ngrand\n")

    def test_labels_gosub_data_restore(self):
        self.qb('''
RESTORE Donnees2
READ a, b$
PRINT a; b$
GOSUB Affiche
END
Affiche:
  PRINT "FIN"
  RETURN
Donnees1:
DATA 1, "un"
Donnees2:
DATA 2, "deux"''', " 2 deux\nFIN\n")

    def test_array_parameter_and_locals(self):
        self.qb('''
DECLARE SUB Tri (t())
DIM v(1 TO 5)
FOR i = 1 TO 5: READ v(i): NEXT
DATA 5, 3, 9, 1, 7
Tri v()
FOR i = 1 TO 5: PRINT v(i);: NEXT
PRINT i
SUB Tri (t())
  FOR i = 1 TO 4
    FOR j = i + 1 TO 5
      IF t(j) < t(i) THEN SWAP t(i), t(j)
    NEXT
  NEXT
END SUB''', " 1  3  5  7  9  6 \n")

    def test_function_calls_in_conditions(self):
        self.qb('''
DECLARE FUNCTION Double$ (s$)
DECLARE FUNCTION Pair% (n%)
n% = 0
DO WHILE Pair%(n%) < 6
  n% = n% + 1
LOOP
PRINT n%; Double$("AB")
IF Pair%(2) = 4 THEN PRINT "OK" ELSE PRINT "KO"
FUNCTION Double$ (s$)
  Double$ = s$ + s$
END FUNCTION
FUNCTION Pair% (n%)
  Pair% = 2 * n%
END FUNCTION''', " 3 ABAB\nOK\n")

    def test_locals_are_reset_unless_static(self):
        self.qb('''
DECLARE SUB Compte ()
DECLARE SUB Garde ()
FOR i = 1 TO 3: Compte: Garde: NEXT
PRINT
SUB Compte
  c = c + 1: PRINT c;
END SUB
SUB Garde STATIC
  g = g + 1: PRINT g;
END SUB''', " 1  1  1  2  1  3 \n")

    def test_input(self):
        self.qb('INPUT "Nom"; n$\nINPUT a, b\nPRINT n$; a + b', "Nom? ZOE\n? 2,3\nZOE 5 \n",
                inputs=["ZOE", "2,3"])

    def test_screen_coordinates(self):
        out, _, _ = qbasic.translate('CLS\nLOCATE 2, 3: PRINT "X";\nPRINT POS(0); CSRLIN;')
        _, m = emu.run_basic(out)
        self.assertEqual(m.screen_text().splitlines()[2].rstrip("| "), "|  X 4  2")

    def test_graphics_box(self):
        out, _, _ = qbasic.translate('LINE (10, 10)-(30, 20), , B\nLINE (40, 10)-(45, 13), , BF\n'
                                     'PSET (60, 14)\nPSET (61, 14)\nPSET (61, 14), 0')
        _, m = emu.run_basic(out)
        lcd = m.lcd
        self.assertTrue(lcd.get(30, 20) and lcd.get(20, 10) and lcd.get(10, 15) and lcd.get(60, 14))
        self.assertFalse(lcd.get(20, 15) or lcd.get(61, 14))
        self.assertTrue(all(lcd.get(x, y) for x in range(40, 46) for y in range(10, 14)))

    def test_long_names_and_keywords_in_names(self):
        # 2 caractères significatifs sur le X-07, TOTAL contient TO
        self.qb('alpha = 1: album = 2: total = 3: forme = 4\nPRINT alpha; album; total; forme',
                " 1  2  3  4 \n")

    def example(self, name):
        with open(os.path.join(ROOT, "exemples", "qbasic", name), encoding="utf-8") as f:
            return f.read()

    def test_example_tri(self):
        # écran de 20 colonnes : un nombre qui ne tient plus passe à la ligne
        self.qb(self.example("tri.qbas"), " 6  7  9  11  12 \n 14  15  18 \nMoyenne : 11.5 \n")

    def test_example_tri2_same_sub_two_arrays(self):
        # Trier reçoit deux tableaux : une copie de la procédure pour chacun
        out, warns = self.qb(self.example("tri2.qbas"),
                             " 6  7  9  11  12 \n 14  15  18 \nMoyenne : 11.5 \n")
        self.assertTrue(any("2 tableaux" in w for w in warns))

    def test_array_passed_on_and_local_arrays(self):
        # tableau transmis d'une procédure à l'autre ; tableau local remis à
        # zéro à chaque appel (QuickBASIC), sauf dans une procédure STATIC
        self.qb('''
DECLARE SUB Remplir (t(), v)
DECLARE SUB Doubler (t())
DECLARE FUNCTION Somme (t())
DECLARE SUB Garde ()
DIM a(3), b(3)
Remplir a(), 1
Remplir b(), 10
Doubler b()
PRINT Somme(a()); Somme(b())
Garde
Garde
SUB Remplir (t(), v)
  DIM w(2)
  w(1) = w(1) + 1
  FOR i = 0 TO 3: t(i) = v: NEXT
  PRINT w(1);
END SUB
SUB Doubler (t())
  FOR i = 0 TO 3: t(i) = 2 * t(i): NEXT
  Remplir t(), Somme(t())
END SUB
FUNCTION Somme (t())
  s = 0
  FOR i = 0 TO 3: s = s + t(i): NEXT
  Somme = s
END FUNCTION
SUB Garde STATIC
  DIM g$(1, 1)
  g$(1, 1) = g$(1, 1) + "*"
  PRINT g$(1, 1);
END SUB''', " 1  1  1  4  320 \n***\n")   # STATIC : * puis **

    def test_example_mystere(self):
        src = self.example("mystere.qbas")
        out, _, _ = qbasic.translate(src)
        inputs = [str(i) for i in range(1, 101)]      # 1, 2, 3... jusqu'au nombre
        ref, m = emu.run_basic(out, inputs=inputs, keys="X")
        self.assertIsNone(m.error)
        n = ref.count("Plus grand") + 1
        self.assertTrue(ref.rstrip().endswith("Trouve en %d coups" % n), ref)
        asm, _ = compile_basic(out, "T", 0x3000)
        a = Assembler()
        mc = emu.run_binary(a.assemble_text(asm), a.entry, inputs=inputs, keys="X")
        self.assertEqual(mc.output().rstrip(), ref.rstrip())

    def test_command_output_name(self):
        from x07asm.cli import main
        with tempfile.TemporaryDirectory() as d:
            for name, out in (("jeu.qbas", "jeu.bas"), ("jeu2.bas", "jeu2_x07.bas")):
                shutil.copy(os.path.join(ROOT, "exemples", "qbasic", "tri.qbas"),
                            os.path.join(d, name))
                with contextlib.redirect_stdout(io.StringIO()):
                    self.assertEqual(main(["qb", os.path.join(d, name)]), 0)
                self.assertTrue(os.path.exists(os.path.join(d, out)), out)

    def test_commands_accept_qbas(self):
        # emu, run, basic, send : un .qbas est traduit au passage (sinon SN Error)
        from x07asm.cli import read_basic, build_basic
        path = os.path.join(ROOT, "exemples", "qbasic", "tri.qbas")
        text = read_basic(path)
        self.assertTrue(text.startswith("10 DEFSNG A-Z\n"))
        ref, m = emu.run_basic(text)
        self.assertIn("Moyenne : 11.5", ref)
        _, a, mem, _ = build_basic(path, "auto", 16)
        self.assertEqual(emu.run_binary(mem, a.entry).output().rstrip(), ref.rstrip())

    def test_refused(self):
        for src, msg in (
                ("DECLARE FUNCTION F (n)\nPRINT F(3)\nFUNCTION F (n)\n"
                 "IF n = 0 THEN F = 1 ELSE F = n * F(n - 1)\nEND FUNCTION", "récursive"),
                ("TYPE Point\nx AS INTEGER\nEND TYPE", "TYPE"),
                ("PRINT UCASE$(\"a\")", "UCASE$"),
                ("OPEN \"F\" FOR INPUT AS #1", "OPEN"),
                ("DIM t(2 TO 5)", "toujours de 0 à n"),
                ("CONST N = 3\nDECLARE SUB S (n)\nSUB S (n)\nEND SUB", "constante")):
            with self.assertRaises(qbasic.QBError) as cm:
                qbasic.translate(src)
            self.assertIn(msg, str(cm.exception), src)

    def test_warnings(self):
        _, warns, _ = qbasic.translate('SCREEN 1\nCOLOR 2\nx& = 5\nINPUT "A", a')
        text = " ".join(warns)
        for w in ("SCREEN", "COLOR", "LONG", "« ? »"):
            self.assertIn(w, text)


if __name__ == "__main__":
    unittest.main()
