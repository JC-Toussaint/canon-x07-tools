"""Tests de Quick C (.qc) : réels du X-07 écrits comme des nombres, traduits en
appels de la bibliothèque (x07asm/qc.py), compilés par SDCC et exécutés par la
ROM (émulateur).  Passés si SDCC ou la ROM manquent."""
import os
import shutil
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from x07asm import ccomp, emu, qc            # noqa: E402

has_rom = emu.rom_path() is not None
needs_rom = unittest.skipUnless(has_rom, "ROM_x07/x07.bin absente")
needs_sdcc = unittest.skipUnless(has_rom and shutil.which("sdcc"), "SDCC ou ROM absent")

HEAD = '#include <stdio.h>\n'


def run(text, keys="", lines=()):
    d = tempfile.mkdtemp()
    try:
        path = os.path.join(d, "t.qc")
        with open(path, "w", encoding="utf-8") as f:
            f.write(HEAD + text)
        prog = ccomp.build_c(path, "auto", top=0x3FF1, ram_top=0x3FFF)
    finally:
        shutil.rmtree(d)
    m = emu.prepare_binary(prog.mem, prog.entry, keys, list(lines), 16)
    m.run(30_000_000)
    return m.output()


@needs_rom
class TestTranslation(unittest.TestCase):
    def tr(self, text):
        return qc.translate(text, "t.qc")

    def test_untouched_without_reals(self):
        src = "int main(void)\n{\n    int a = 2;\n    a = a * 3 + 1;\n    return a;\n}\n"
        out = self.tr(src)
        self.assertTrue(out.endswith(src))
        self.assertIn('#line 1 "t.qc"', out)

    def test_lines_are_kept(self):
        src = "real x;\nint main(void)\n{\n    x = 2.5 *\n        x;\n    return 0;\n}\n"
        body = self.tr(src).split('#line 1 "t.qc"\n', 1)[1]
        self.assertEqual(body.count("\n"), src.count("\n"))
        self.assertIn("r_mul", body.split("\n")[3])

    def test_real_and_int_macros(self):
        out = self.tr("#define G 9.81   /* commentaire */\n#define N (10)\n"
                      "real x; int main(void) { x = x * G + N; return 0; }")
        self.assertIn("/* 9.81 */", out)                    # constante réelle, pas tronquée
        self.assertIn("r_int(&_qc_t2, N)", out)

    def test_errors(self):
        for src, msg in (
                ("real x; int main(void) { printf(\"%d\", x); return 0; }", "str(x)"),
                ("real x; int main(void) { int n = 3; n = n % x; return 0; }", "« % »"),
                ("struct p { real x; };", "structure"),
                ("real a, b = a * 2;", "constante"),
                ("int main(void) { real x; int n; n += x; return 0; }", "n = n + x"),
                ("#define G (9.81 * 2)\nreal x; int main(void) { x = x * G; return 0; }",
                 "G mêlé à un réel")):
            with self.assertRaises(qc.QCError) as e:
                self.tr(src)
            self.assertIn(msg, str(e.exception), src)


class TestDecodeReal(unittest.TestCase):
    def test_bcd_to_text(self):
        from x07asm.cdebug import decode_real
        for data, text in (("4120", "2"), ("4050", "0.5"), ("C12250", "-2.25"),
                           ("2D10", "1E-20"), ("7F10", "1E+62"), ("3D123", "0.000123"),
                           ("4E12345678901234", "12345678901234"),
                           ("411414213562373", "1.414213562373"), ("00", "0")):
            b = bytes.fromhex((data + "0" * 16)[:16])
            self.assertEqual(decode_real(b), text)


@needs_sdcc
class TestQuickC(unittest.TestCase):
    def test_arithmetic_like_basic(self):
        out = run('''int main(void)
{
    real x, y = 2.5, t[3] = {1, 2, 0.5};
    int n = 3, i;
    x = sqrt(y) * 3 + n;
    printf("%s\\n", str(x));
    for (i = 0; i < 3; i++)
        x += t[i] / 2;
    n = x;
    printf("%s %d %s\\n", str(x), n, fmt(x * x, 3, 2));
    x = 1 / 3.0 * 3;
    printf("%s %d\\n", str(x), x == 1);
    x = 0.1 + 0.2;
    printf("%d %d\\n", x == 0.3, -x < 0);
    return 0;
}''')
        self.assertEqual(out, " 7.7434164902523\n 9.4934164902523 9  90.12\n"
                              " .99999999999999 0\n1 1\n")

    def test_functions_by_value_and_recursion(self):
        out = run('''real fact(int n) { return n <= 1 ? 1 : n * fact(n - 1); }
real moitie(real a) { a = a / 2; return a; }
void double_tout(real *t, int n) { int i; for (i = 0; i < n; i++) t[i] = t[i] * 2; }
int main(void)
{
    real x = 10, t[2] = {1.5, -2};
    printf("%s\\n", str(fact(15)));
    printf("%s %s\\n", str(moitie(x)), str(x));      /* x n'a pas changé */
    double_tout(t, 2);
    printf("%s %s\\n", str(t[0]), str(t[1]));
    return 0;
}''')
        self.assertEqual(out, " 1307674368000\n 5  10\n 3 -4\n")

    def test_increments_conditions_and_input(self):
        out = run('''int main(void)
{
    real x, s = 0;
    char buf[16];
    int k = 0;
    input(buf, sizeof buf);
    x = val(buf);
    while (x > 0.5) { x /= 2; k++; }
    s++; ++s; s--;
    printf("%d %s %s %d\\n", k, str(x), str(s), !s);
    return 0;
}''', lines=["10"])
        self.assertEqual(out, "10\n5  .3125  1 0\n")           # saisie en écho

    def test_ram_files_with_reals(self):
        out = run('''int main(void)
{
    real t, s = 0;
    int j, n = 0;
    f_open(1, "releve", F_WRITE, 300);
    f_printf(1, "12 18.5\\n14,%s\\n", str(-2.25));
    f_puts(1, "20 ; 7\\n");
    f_open(2, "releve", F_READ, 0);
    while (!f_eof(2)) {
        j = f_val(2);
        t = f_val(2);
        s += t;
        n++;
        printf("%d:%s ", j, str(t));
    }
    printf("%d%s\\n", n, str(s / n));
    t = f_val(2);
    printf("jamais");
    return 0;
}''')
        self.assertEqual(out, "12: 18.5 14:-2.25 20: 7 3 7.75\nIO Error\n")

    def test_debugger_shows_locals_and_reals(self):
        from x07asm.ide import Session
        d = tempfile.mkdtemp()
        try:
            path = os.path.join(d, "v.qc")
            with open(path, "w", encoding="utf-8") as f:
                f.write(HEAD + '''real g = 2.5;
int carre(int a) { return a * a; }
int main(void)
{
    real x = 3;
    int t[3] = {1, 2, 3};
    long w = 70000;
    char c = 'A';
    x = x * g;
    printf("%d %ld %c %s", carre(t[1]), w, c, str(x));
    return 0;
}
''')
            s = Session(path, 16)
            s.build()
            s.toggle_break(11)                               # la ligne du printf
            s.m.interactive = False
            self.assertEqual(s.run(), "point d'arrêt")
            text = "\n".join(s.variables())
        finally:
            shutil.rmtree(d)
        for want in ("g = 2.5", "— main —", "x = 7.5", "t = {1, 2, 3}"):
            self.assertIn(want, text)
        for name in ("w", "c"):          # selon SDCC : valeur, registre, ou optimisée
            self.assertRegex(text, r"(?m)^%s [=:]" % name)
        self.assertNotIn("_qc_", text)                      # temporaires cachés

    def test_sdcc_errors_point_to_qc_lines(self):
        with self.assertRaises(ccomp.CError) as e:
            run("int main(void)\n{\n    real x;\n    x = inconnue;\n    return 0;\n}\n")
        self.assertIn("t.qc:5", str(e.exception))     # ligne 4 du texte + HEAD

    def test_examples_build(self):
        for f in sorted(os.listdir(os.path.join(ROOT, "exemples", "qc"))):
            if f.endswith(".qc"):
                prog = ccomp.build_c(os.path.join(ROOT, "exemples", "qc", f), "auto",
                                     top=0x3FF1, ram_top=0x3FFF)
                self.assertIn("main", prog.symbols, f)


if __name__ == "__main__":
    unittest.main()
