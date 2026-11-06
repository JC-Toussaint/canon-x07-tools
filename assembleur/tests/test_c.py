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
        return ccomp.build_c(path, kw.pop("org", "auto"), top=kw.pop("top", 0x3FF1),
                             ram_top=0x3FFF)
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

    def test_bcd_reals_like_basic(self):
        # mêmes résultats que le BASIC du X-07 (PRINT, STR$) : calcul décimal de la ROM
        prog = build('''#include <stdio.h>
#include "x07.h"
int main(void)
{
    real a, b, c;
    char buf[26];
    r_int(&a, 1); r_int(&b, 3);
    r_div(&c, &a, &b); printf("%s\\n", r_str(buf, &c));
    r_mul(&c, &c, &b); printf("%s %d\\n", r_str(buf, &c), r_cmp(&c, &a));
    r_set(&a, "0.1"); r_set(&b, "0.2"); r_add(&c, &a, &b); r_set(&a, ".3");
    printf("%d\\n", r_cmp(&c, &a));
    r_set(&a, "2"); r_sqrt(&c, &a); printf("%s\\n", r_str(buf, &c));
    r_set(&a, "-1234.5678"); printf("[%s] %d\\n", r_fmt(buf, &a, 5, 2), r_toint(&a));
    r_neg(&a, &a); r_intp(&b, &a); printf("%s\\n", r_str(buf, &b));
    r_set(&a, "12345678901234"); r_print(&a);
    return 0;
}''')
        m = run(prog)
        self.assertEqual(m.output(), " .33333333333333\n .99999999999999 -1\n0\n"
                                     " 1.414213562373\n[-1234.57] -1234\n 1234\n"
                                     " 12345678901234")

    def test_rom_error_stops_program(self):
        for body, msg in (('r_int(&a, 1); r_int(&b, 0); r_div(&a, &a, &b);', "/0 Error"),
                          ('r_set(&a, "40000"); r_toint(&a);', "OV Error")):
            prog = build('''#include <stdio.h>
#include "x07.h"
int main(void) { real a, b; %s printf("jamais"); return 0; }''' % body)
            m = emu.prepare_binary(prog.mem, prog.entry, "", [], 16)
            hook = bytes(m.mem[0xAB:0xAE])
            m.run(5_000_000)
            self.assertEqual(m.pc, emu.EXIT)
            self.assertEqual(m.output().strip(), msg)
            self.assertEqual(bytes(m.mem[0xAB:0xAE]), hook)  # crochet de la ROM rétabli

    def test_reals_only_linked_when_used(self):
        prog = build('#include "x07.h"\nint main(void) { cls(); return 0; }')
        self.assertNotIn("r_add", prog.symbols)

    def test_ram_files(self):
        prog = build('''#include <stdio.h>
#include "x07.h"
int main(void)
{
    char s[30];
    int n;
    f_open(1, "notes", F_WRITE, 200);
    f_printf(1, "%d,%s\\n", 12, "bonjour");
    f_puts(1, "ligne 2\\n");
    f_open(2, "notes", F_READ, 0);
    while ((n = f_gets(2, s, sizeof s)) >= 0)
        printf("[%s]%d\\n", s, n);
    f_open(1, "notes", F_APPEND, 200);
    f_putc(1, 'X');
    f_open(2, "NOTES", F_READ, 0);
    for (n = 0; !f_eof(2); n++)
        f_gets(2, s, sizeof s);
    printf("%d %d\\n", n, f_getc(2));
    f_open(1, "notes", F_WRITE, 200);
    printf("%d\\n", f_eof(1));
    f_delete("notes");
    f_open(3, "notes", F_READ, 0);
    printf("jamais\\n");
    return 0;
}''')
        self.assertLessEqual(prog.end, 0x3FFF - 1024 - 1 - 80)       # sous la zone des fichiers
        m = run(prog)
        self.assertEqual(m.output(), "[12,bonjour]10\n[ligne 2]7\n3 -1\n1\nNE Error\n")

    def test_files_shared_with_basic(self):
        # fichier écrit en C, relu par un programme BASIC, et inversement ; la RAM
        # passe d'un programme à l'autre comme sur la machine (--memoire)
        from x07asm.cli import main
        with tempfile.TemporaryDirectory() as d:
            mem = os.path.join(d, "x07.mem")
            files = {
                "w.c": '#include "x07.h"\nint main(void) { f_open(1, "echang", F_WRITE, 100);'
                       ' f_printf(1, "%d,%s\\n", 42, "DEPUIS C"); return 0; }\n',
                "r.bas": '10 INIT#1,"RAM:ECHANG"\n20 INPUT #1,A,B$\n30 PRINT A;B$\n'
                         '40 INIT#2,"RAM:RETOUR",100\n50 PRINT #2,"DU BASIC":PRINT #2,"FIN"\n',
                "r.c": '#include <stdio.h>\n#include "x07.h"\nint main(void) { char s[20];'
                       ' f_open(1, "retour", F_READ, 0); while (f_gets(1, s, sizeof s) >= 0)'
                       ' printf("<%s>", s); return 0; }\n'}
            for n, t in files.items():
                with open(os.path.join(d, n), "w") as f:
                    f.write(t)
            outs = []
            for cmd in ("run", "emu", "run"):
                name = {"run": "w.c", "emu": "r.bas"}[cmd] if not outs or cmd == "emu" else "r.c"
                with contextlib.redirect_stdout(io.StringIO()) as out, \
                        contextlib.redirect_stderr(io.StringIO()):
                    main([cmd, os.path.join(d, name), "--ram", "16", "--memoire", mem])
                outs.append(out.getvalue())
            self.assertIn(" 42 DEPUIS C", outs[1])
            self.assertIn("<DU BASIC><FIN>", outs[2])

    def test_file_full_and_zone_size(self):
        prog = build('''#include "x07.h"
const unsigned int x07_fspace = 2000;
int main(void) { f_open(1, "petit", F_WRITE, 10); f_puts(1, "0123456789AB"); return 0; }''')
        self.assertEqual(prog.file_space, 2000)
        self.assertLessEqual(prog.end, 0x3FFF - 2000 - 1 - 80)
        m = run(prog)
        self.assertEqual(m.output().strip(), "IO Error")
        self.assertEqual(m.pc, emu.EXIT)

    def test_files_only_linked_when_used(self):
        prog = build('#include "x07.h"\nint main(void) { cls(); return 0; }')
        self.assertNotIn("f_open", prog.symbols)
        self.assertEqual(prog.file_space, 0)
        self.assertGreater(prog.end, 0x3FFF - 1024)               # en haut de la RAM

    def test_light_printf_matches_c(self):
        # printf de x07.lib (x07printf.c), comparé au % de Python (mêmes règles que C)
        cases = [("%d", "0"), ("%d", "-32768"), ("%d", "32767"), ("%u", "65535"),
                 ("%5d", "-42"), ("%-5d|", "42"), ("%05d", "-42"), ("%x", "48879"),
                 ("%X", "48879"), ("%o", "8"), ("%ld", "-2147483647L"), ("%lu", "4294967295UL"),
                 ("%lx", "3735928559UL"), ("%8ld", "70000L"), ("%c", "'A'"), ("%3c|", "'z'"),
                 ("%s", '"abc"'), ("%-6s|", '"ab"'), ("%6s|", '"ab"'), ("%%", None),
                 ("%2u", "7")]
        body = "\n".join('    printf("[%s]\\n"%s);' % (f, ", " + v if v else "") for f, v in cases)
        prog = build('#include <stdio.h>\n#include "x07.h"\nint main(void)\n{\n    char b[20];\n'
                     + body + '\n    sprintf(b, "<%d,%s>", 12, "x");\n    printf("%s %d", b, '
                     'printf("ok"));\n    return 0;\n}\n')
        self.assertNotIn("_print_format", ccomp.LIB_MODULES)       # pas celui de SDCC
        out = run(prog).output()
        want = ""
        for f, v in cases:
            val = None if v is None else eval(v.rstrip("UL").rstrip("L")) if not v.startswith("'") \
                else v[1]
            if f[-1] in "dulxXo" and val is not None and "l" not in f and f[-1] != "d":
                val &= 0xFFFF
            if "l" in f and f[-1] in "uxX":
                val &= 0xFFFFFFFF
            want += "[%s]\n" % (f.replace("l", "") % val if val is not None else "%")
        self.assertEqual(out, want + "ok<12,x> 2")

    def test_compile_error_is_reported(self):
        with self.assertRaises(ccomp.CError) as e:
            build("int main(void) { return x; }", name="faux.c")
        self.assertIn("faux.c", str(e.exception))

    def test_examples_build(self):
        for name in ("bonjour.c", "dessin.c", "reels.c", "pret.c", "carnet.c"):
            prog = ccomp.build_c(os.path.join(ROOT, "exemples", "c", name), "auto", top=0x3FF1)
            self.assertIn("main", prog.symbols)

    def test_pret_example(self):
        prog = ccomp.build_c(os.path.join(ROOT, "exemples", "c", "pret.c"), "auto", top=0x3FF1)
        m = emu.prepare_binary(prog.mem, prog.entry, "  ", ["150000", "3.5", "20"], 16)
        m.run(20_000_000)
        self.assertIn("Mensualite   869.94\nTotal paye   208785\nInterets      58785", m.output())

    def test_benchmarks_c_and_pascal_agree(self):
        sys.path.insert(0, os.path.join(ROOT, "exemples", "bench"))
        import mesure
        for nom in ("crible", "fib", "prodi"):
            c = mesure.mesure(os.path.join(ROOT, "exemples", "bench", nom + ".c"))
            p = mesure.mesure(os.path.join(ROOT, "exemples", "bench", nom + ".pas"))
            self.assertEqual(c[2], p[2], nom)
            self.assertLess(c[0], p[0], nom)                    # le C est plus rapide

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
