"""Tests du débogueur (x07asm/debug.py) : le programme tourne dans l'émulateur."""
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from x07asm import debug, emu                # noqa: E402
from x07asm.asm import Assembler             # noqa: E402
from x07asm.cli import build_basic           # noqa: E402

needs_rom = unittest.skipUnless(emu.rom_path() is not None, "ROM_x07/x07.bin absente")

ASM = """
        ORG  $3000
START:  LD   A,5
        LD   B,3
BOUCLE: ADD  A,B
        DJNZ BOUCLE
        LD   ($3100),A
        CALL SOUS
        RET
SOUS:   LD   HL,$1234        ; dans la sous-routine
        CALL SOUS2
        RET
SOUS2:  LD   DE,$5678
        RET
"""


@needs_rom
class TestDebugger(unittest.TestCase):
    def asm(self, text=ASM):
        a = Assembler()
        mem = a.assemble_text(text)
        self.assertEqual(a.errors, [])
        m = emu.prepare_binary(mem, a.entry)
        self.lines = []
        return debug.Debugger(m, a.symbols, a.listing, (min(mem), max(mem)),
                              out=self.lines.append)

    def run_cmds(self, d, *cmds):
        self.lines.clear()
        for c in cmds:
            self.assertTrue(d.command(c))
        return "\n".join(self.lines)

    def test_breakpoint_and_registers(self):
        d = self.asm()
        out = self.run_cmds(d, "b BOUCLE", "c")
        self.assertIn("[point d'arrêt]", out)
        self.assertEqual((d.m.pc, d.m.r["A"]), (d.symbols["BOUCLE"], 5))
        self.run_cmds(d, "c")                          # deuxième passage dans la boucle
        self.assertEqual(d.m.r["A"], 8)
        self.assertIn("BOUCLE", self.run_cmds(d, "b"))
        out = self.run_cmds(d, "d BOUCLE", "c")
        self.assertIn("programme terminé", out)
        self.assertEqual(d.m.mem[0x3100], 11)

    def test_watch_step_over_and_finish(self):
        d = self.asm()
        out = self.run_cmds(d, "w 3100", "c")
        self.assertIn("surveillance $3100 : 00 -> 0B", out)
        self.assertEqual(d.m.pc, d.symbols["SOUS"] - 4)    # arrêt juste après : CALL SOUS
        self.run_cmds(d, "n")                          # par-dessus : toute la sous-routine
        self.assertEqual(d.m.pc, d.symbols["SOUS"] - 1)
        self.assertEqual((d.m.get16("HL"), d.m.get16("DE")), (0x1234, 0x5678))
        d2 = self.asm()
        self.run_cmds(d2, "j SOUS", "s")               # dans SOUS, après LD HL
        self.assertEqual(d2.m.pc, d2.symbols["SOUS"] + 3)
        out = self.run_cmds(d2, "f")                   # sortie de SOUS (SOUS2 compris)
        self.assertEqual(d2.m.pc, d2.symbols["SOUS"] - 1)    # le RET final du programme
        self.assertEqual(d2.m.get16("DE"), 0x5678)

    def test_listing_shows_labels_and_source(self):
        d = self.asm()
        out = self.run_cmds(d, "l SOUS 2")
        self.assertIn("SOUS", out)
        self.assertIn("LD    HL,$1234", out)
        self.assertIn("dans la sous-routine", out)       # commentaire du source
        self.assertIn("CALL  SOUS2", out)

    def test_set_registers_and_memory(self):
        d = self.asm()
        self.run_cmds(d, "r A=#65 HL=BOUCLE", "m 3200 41 42 43", "x 3200 3")
        self.assertEqual((d.m.r["A"], d.m.get16("HL")), (65, d.symbols["BOUCLE"]))
        self.assertIn("41 42 43", self.lines[-1])
        self.assertIn("ABC", self.lines[-1])
        self.run_cmds(d, "r PC=SOUS2", "s 2")
        self.assertEqual(d.m.get16("DE"), 0x5678)

    def test_errors_stop_on_faulty_instruction(self):
        d = self.asm("        ORG $3000\nSTART:  LD A,1\n        LD ($C000),A\n        RET\n")
        out = self.run_cmds(d, "c")
        self.assertIn("erreur : écriture hors de la RAM", out)
        self.assertEqual(d.m.pc, 0x3002)               # sur l'instruction fautive
        self.assertIn("adresse inconnue", self.run_cmds(d, "b NULLEPART"))
        self.assertIn("commande inconnue", self.run_cmds(d, "zz"))

    def test_pause_request(self):
        d = self.asm("        ORG $3000\nSTART:  JR START\n")
        d.m.debug_pause = True
        self.assertIn("[interrompu]", self.run_cmds(d, "c"))

    def test_compiled_basic_lines_and_variables(self):
        path = os.path.join(ROOT, "exemples", "premiers.bas")
        _, a, mem, _ = build_basic(path, "auto", 16, debug=True)
        m = emu.prepare_binary(mem, a.entry)
        self.lines = []
        d = debug.Debugger(m, a.symbols, a.listing,
                           (min(mem), a.symbols["VARS_END"] - 1), out=self.lines.append)
        out = self.run_cmds(d, "b ligne 50", "c", "c")
        self.assertIn("ligne BASIC 50", out)
        self.assertIn("LN_50", out)
        out = self.run_cmds(d, "v I")
        self.assertIn("I% = 3", out)                   # deuxième nombre premier
        self.assertIn("P%(4) = 1", self.run_cmds(d, "v P%(4)"))
        out = self.run_cmds(d, "d tout", "c", "e")
        self.assertIn("programme terminé", out)
        self.assertIn(" 491  499", out)

    def test_float_variables_through_rom(self):
        src = "10 A=1/3:B!=2.5:N$=\"OK\"\n20 PRINT A\n"
        path = os.path.join(ROOT, "tests", "_debug_tmp.bas")
        with open(path, "w") as f:
            f.write(src)
        try:
            _, a, mem, _ = build_basic(path, "auto", 16, debug=True)
        finally:
            os.remove(path)
        m = emu.prepare_binary(mem, a.entry)
        self.lines = []
        d = debug.Debugger(m, a.symbols, a.listing,
                           (min(mem), a.symbols["VARS_END"] - 1), out=self.lines.append)
        out = self.run_cmds(d, "j ligne 20", "v")
        self.assertIn("A# = .33333333333333", out)
        self.assertIn("B! = 2.5", out)
        self.assertIn('N$ = "OK"', out)


if __name__ == "__main__":
    unittest.main()
