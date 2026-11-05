"""Tests des programmes C (SDCC) : compilation, bibliothèque x07.h, exécution
par la ROM du X-07 (émulateur).  Passés si SDCC n'est pas installé."""
import contextlib
import io
import os
import shutil
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from x07asm import ccomp, emu                # noqa: E402

needs = unittest.skipUnless(shutil.which("sdcc") and emu.rom_path() is not None,
                            "SDCC ou ROM_x07/x07.bin absent")


def build(text, name="t.c", **kw):
    d = tempfile.mkdtemp()
    try:
        path = os.path.join(d, name)
        with open(path, "w", encoding="utf-8") as f:
            f.write(text)
        return ccomp.build_c(path, kw.pop("org", "auto"), top=kw.pop("top", 0x3FF1))
    finally:
        shutil.rmtree(d)


def run(prog, keys="", lines=(), steps=20_000_000):
    m = emu.prepare_binary(prog.mem, prog.entry, keys, list(lines), 16)
    m.run(steps)
    return m


@needs
class TestC(unittest.TestCase):
    def test_printf_globals_and_return_to_basic(self):
        prog = build('''#include <stdio.h>
#include "x07.h"
int a = 7, b;
static long c = 100000;
int main(void) { b += a; printf("%d %d %ld\\n", a, b, c * 3); return 0; }''')
        m = run(prog)
        self.assertEqual(m.output(), "7 7 300000\n")
        self.assertEqual(m.pc, emu.EXIT)
        # relancé (EXEC) : variables remises à leur valeur de départ
        m2 = emu.prepare_binary(prog.mem, prog.entry, "", [], 16,
                                machine=emu.power_on(emu.power_off(m), 16))
        self.assertEqual(m2.mem[prog.symbols["b"]], 7)    # la RAM a gardé b = 7
        m2.run(5_000_000)
        self.assertTrue(m2.output().endswith("7 7 300000\n"))

    def test_placed_at_top_of_ram(self):
        prog = build('int main(void) { return 0; }')
        self.assertLessEqual(prog.end, 0x3FF1)
        self.assertGreater(prog.entry, 0x3000)
        self.assertEqual(prog.entry & 0xF, 0)
        fixed = build('int main(void) { return 0; }', org=0x2000)
        self.assertEqual(fixed.entry, 0x2000)

    def test_input_and_keys(self):
        prog = build('''#include <stdio.h>
#include "x07.h"
int main(void) { char s[8]; char k; input(s, sizeof s); k = getkey();
  printf("[%s] %c\\n", s, k); return 0; }''')
        m = run(prog, keys="Z", lines=["Bonjour X-07"])
        self.assertIn("[Bonjour] Z", m.output())        # tronqué à 7 caractères

    def test_break_stops_program(self):
        prog = build('''#include <stdio.h>
#include "x07.h"
int main(void) { unsigned n = 0; for (;;) printf("%u ", n++); }''')
        m = emu.prepare_binary(prog.mem, prog.entry, "", [], 16)
        with self.assertRaises(emu.SimError):
            m.run(300_000)
        m.mem[0x2B] |= 0x01                              # touche BREAK
        m.run(2_000_000)
        self.assertEqual(m.pc, emu.EXIT)
        self.assertTrue(m.output().rstrip().endswith("Break"))

    def test_line_symbols_and_variables(self):
        prog = build('''int total;
static unsigned char t[5];
int main(void)
{
    total = 3;
    t[1] = 2;
    return 0;
}''')
        self.assertIn("LN_5", prog.symbols)
        self.assertLess(prog.symbols["LN_5"], prog.symbols["LN_6"])
        self.assertEqual(sorted((n, s) for n, _, s in prog.variables), [("t", 5), ("total", 2)])

    def test_compile_error_is_reported(self):
        with self.assertRaises(ccomp.CError) as e:
            build("int main(void) { return x; }", name="faux.c")
        self.assertIn("faux.c", str(e.exception))

    def test_examples_build(self):
        for name in ("bonjour.c", "dessin.c"):
            prog = ccomp.build_c(os.path.join(ROOT, "exemples", "c", name), "auto", top=0x3FF1)
            self.assertIn("main", prog.symbols)

    def test_cli_formats(self):
        from x07asm.cli import main
        with tempfile.TemporaryDirectory() as d:
            src = os.path.join(d, "p.c")
            shutil.copy(os.path.join(ROOT, "exemples", "c", "dessin.c"), src)
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(main(["c", src, "-f", "bin,lst"]), 0)
            self.assertEqual(sorted(os.listdir(d)), ["p.bin", "p.c", "p.lst"])
            with contextlib.redirect_stderr(io.StringIO()) as err:
                self.assertEqual(main(["c", src, "-f", "asm"]), 1)
            self.assertIn("-f lst", err.getvalue())


if __name__ == "__main__":
    unittest.main()
