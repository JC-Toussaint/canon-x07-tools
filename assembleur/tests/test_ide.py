"""Tests de l'éditeur-débogueur (x07asm/ide.py).

La session (compilation, lignes, points d'arrêt, pas à pas, variables) est
testée sans affichage ; la fenêtre, seulement si un affichage existe."""
import os
import shutil
import sys
import tempfile
import time
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from x07asm import emu                        # noqa: E402
from x07asm.ide import Session                # noqa: E402

needs_rom = unittest.skipUnless(emu.rom_path() is not None, "ROM_x07/x07.bin absente")
EX = os.path.join(ROOT, "exemples")


def has_display():
    try:
        import tkinter
        tkinter.Tk().destroy()
        return True
    except Exception:
        return False


@needs_rom
class TestSession(unittest.TestCase):
    def session(self, name):
        s = Session(os.path.join(EX, name))
        s.build()
        return s

    def test_qbasic_lines_breakpoints_and_steps(self):
        s = self.session("qbasic/rapide.qbas")
        self.assertEqual(s.toggle_break(27), (27, True))
        self.assertEqual(s.run(), "point d'arrêt")
        self.assertEqual(s.current_line(), 27)
        lines = []
        for _ in range(7):
            s.step_line(True)
            lines.append(s.current_line())
        self.assertEqual(lines, [28, 29, 30, 31, 32, 33, 28])    # boucle DO
        variables = "\n".join(s.variables())
        self.assertIn("TRI.T() -> A%()", variables)              # tableau reçu par adresse
        self.assertIn("FACT# (résultat) = 0", variables)
        self.assertIn("A%(0..9) =", variables)

    def test_step_into_and_finish(self):
        s = self.session("qbasic/rapide.qbas")
        s.toggle_break(36)
        s.run()
        s.toggle_break(36)                                       # enlevé
        s.step_line(over=False)                                  # entre dans l'appel récursif
        self.assertEqual(s.current_line(), 25)
        s.finish()                                               # sortie de cet appel
        self.assertEqual(s.current_line(), 36)

    def test_breakpoint_on_line_without_code(self):
        s = self.session("qbasic/rapide.qbas")
        self.assertEqual(s.toggle_break(23), (25, True))         # ligne vide, puis SUB : 25
        self.assertEqual(s.toggle_break(25), (25, False))
        self.assertEqual(s.toggle_break(43), (None, False))      # après la dernière ligne

    def test_basic_x07_lines(self):
        s = self.session("table.bas")
        s.m.keys = list("7\r")
        s.toggle_break(4)                                        # 40 PRINT I;"x";N;"=";I*N
        s.run()
        self.assertEqual(s.current_line(), 4)
        s.step_line(True)
        s.step_line(True)
        self.assertEqual(s.current_line(), 4)                    # tour suivant de FOR
        self.assertIn("I# = 2", s.variables())

    def test_assembly_lines_and_data_labels(self):
        s = self.session("bonjour.asm")
        first = min(s.line_addr)
        self.assertEqual(s.current_line(), first)
        s.step_line(True)                                        # CALL LCDCLS : par-dessus
        self.assertEqual(s.current_line(), first + 1)
        self.assertTrue(any(v.startswith("MSG") for v in s.variables()))
        self.assertIn("PC=", s.registers())
        self.assertIn(">", s.disassembly())

    def test_breakpoints_survive_rebuild(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "t.qbas")
            shutil.copy(os.path.join(EX, "qbasic", "rapide.qbas"), p)
            s = Session(p)
            s.toggle_break(27)                                   # avant compilation
            s.build()
            self.assertIn(s.line_addr[27], s.dbg.breaks)
            self.assertEqual(s.run(), "point d'arrêt")

    def test_compile_error(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "e.qbas")
            with open(p, "w") as f:
                f.write("PRINT UCASE$(\"a\")\n")
            with self.assertRaises(Exception) as cm:
                Session(p).build()
            self.assertIn("UCASE$", str(cm.exception))


@needs_rom
@unittest.skipUnless(has_display(), "pas d'affichage graphique")
class TestWindow(unittest.TestCase):
    def test_click_run_and_edit(self):
        from x07asm.ide import Editeur
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "t.qbas")
            shutil.copy(os.path.join(EX, "qbasic", "rapide.qbas"), p)
            e = Editeur(p)
            r = e.root

            def pump(t):
                end = time.time() + t
                while time.time() < end:
                    r.update()
                    time.sleep(0.02)
            try:
                pump(0.3)
                self.assertTrue(e.compile())
                e.toggle(27)
                e.text.insert("24.0", "' ajout\n")             # le point d'arrêt suit : 28
                pump(0.2)
                self.assertEqual(e.session.break_lines, {28})
                e.do_run()
                for _ in range(100):
                    pump(0.05)
                    if not e.busy():
                        break
                pump(0.2)
                self.assertIn("point d'arrêt, ligne 28", e.status.cget("text"))
                self.assertIn("TRI.D% = 9", e.panels["variables"].get("1.0", "end"))
                e.do_run()
                pump(0.1)
                e.toggle(28)                                   # occupé : refusé sans erreur
            finally:
                e.close()

    def test_typing_while_stopped_and_input_field(self):
        from x07asm.ide import Editeur
        e = Editeur(os.path.join(EX, "table.bas"))
        r = e.root

        def pump(t):
            end = time.time() + t
            while time.time() < end:
                r.update()
                time.sleep(0.02)
        try:
            pump(0.3)
            e.compile()
            e.toggle(2)                                        # arrêt avant 20 CLS:INPUT
            e.do_run()
            pump(1.0)
            c = e.ecran.canvas
            c.event_generate("<Button-1>", x=40, y=30)
            pump(0.1)
            c.event_generate("<KeyPress>", keysym="7")         # programme arrêté : gardée
            pump(0.1)
            self.assertEqual(e.session.m.keys, ["7"])
            e.session.m.keys.clear()
            e.entry.insert(0, "8")
            e.send_line()                                      # champ « Taper pour le X-07 »
            self.assertEqual(e.session.m.keys, ["8", "\r"])
            e.toggle(2)
            e.do_run()
            for _ in range(80):
                pump(0.05)
                if not e.busy():
                    break
            self.assertIn("MOYENNE 40", "\n".join(e.session.m.lcd.text()))
        finally:
            e.close()


if __name__ == "__main__":
    unittest.main()
