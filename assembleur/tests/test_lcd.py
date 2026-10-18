"""Tests de l'écran à points (x07asm/lcd.py) et de son intégration."""
import os
import struct
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from x07asm import emu                       # noqa: E402
from x07asm.lcd import LCD, WIDTH, HEIGHT, load_font   # noqa: E402
from x07asm.basic import compile_basic       # noqa: E402
from x07asm.asm import Assembler             # noqa: E402

HAVE_FONT = any(load_font())
needs_rom = unittest.skipUnless(emu.rom_path() is not None, "ROM_x07/x07.bin absente")
needs_font = unittest.skipUnless(HAVE_FONT, "ROM_x07/charset.rom absente")


def cell(lcd, col, row):
    """Les 8 lignes de 6 points d'une case, sous forme de chaînes."""
    return ["".join("#" if lcd.get(col * 6 + x, row * 8 + y) else "." for x in range(6))
            for y in range(8)]


class TestLCD(unittest.TestCase):
    @needs_font
    def test_font_glyph(self):
        lcd = LCD()
        lcd.put_char(3, 1, ord("A"))
        self.assertEqual(cell(lcd, 3, 1), [".###..", "#...#.", "#...#.", "#####.",
                                          "#...#.", "#...#.", "#...#.", "......"])

    def test_graphics(self):
        lcd = LCD(bytes(2048))
        lcd.line(0, 0, 10, 5)
        self.assertTrue(lcd.get(0, 0) and lcd.get(10, 5))
        lcd.circle(60, 16, 10)
        for x, y in ((70, 16), (50, 16), (60, 6), (60, 26)):
            self.assertTrue(lcd.get(x, y), (x, y))
        self.assertFalse(lcd.get(60, 16))
        lcd.pset(119, 31)
        lcd.peor(119, 31)
        self.assertFalse(lcd.get(119, 31))
        lcd.pset(200, 200)                         # hors écran : ignoré

    def test_udc_and_scroll(self):
        lcd = LCD(bytes(2048))
        lcd.udc_write(0x80, [0xFC] * 8)
        lcd.put_char(0, 3, 0x80)
        self.assertEqual(cell(lcd, 0, 3), ["######"] * 8)
        lcd.scroll()
        self.assertEqual(cell(lcd, 0, 2), ["######"] * 8)
        self.assertEqual(cell(lcd, 0, 3), ["......"] * 8)
        lcd.udc_init()
        self.assertEqual(lcd.font[0x80 * 8], 0)

    def test_png_and_braille(self):
        lcd = LCD(bytes(2048))
        lcd.pset(0, 0)
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "e.png")
            lcd.png(p, zoom=2, border=0)
            with open(p, "rb") as fh:
                data = fh.read()
        self.assertEqual(data[:8], b"\x89PNG\r\n\x1a\n")
        self.assertEqual(struct.unpack(">II", data[16:24]), (WIDTH * 2, HEIGHT * 2))
        lines = lcd.braille().split("\n")
        self.assertEqual((len(lines), len(lines[0])), (8, 60))
        self.assertEqual(lines[0][0], chr(0x2801))


@needs_rom
class TestScreenMatchesRom(unittest.TestCase):
    """Le même programme, interprété par la ROM ou compilé, donne les mêmes points."""

    def compare(self, src):
        ref, mr = emu.run_basic(src)
        asm, _ = compile_basic(src, "T", 0x3000)
        a = Assembler()
        mem = a.assemble_text(asm)
        m = emu.run_binary(mem, a.entry)
        # la ROM affiche son invite « > » en fin de programme : on ignore cette case
        row = mr.mem[0xB8] - 1
        for y in range(row * 8, row * 8 + 8):
            for x in range(6):
                mr.lcd.set(x, y, 0)
                m.lcd.set(x, y, 0)
        self.assertEqual(bytes(m.lcd.px), bytes(mr.lcd.px), src)
        return m

    def test_text_and_graphics(self):
        m = self.compare('10 CLS:PRINT "X-07";\n20 PSET(60,10):LINE(0,31)-(119,20)\n'
                         '30 CIRCLE(90,15),8:PRESET(91,23)\n40 PRINT POINT(60,10);POINT(2,2);')
        self.assertTrue(m.lcd.get(60, 10))

    def test_user_defined_character(self):
        self.compare('10 CLS:LOCATE 3,1:PRINT CHR$(128);CHR$(65)')

    def test_font_redefinition(self):
        m = self.compare('10 CLS:FONT$(128)="&H50,&HF8,&HF8,&H70,&H20,0,0,0"\n'
                         '20 FONT$(&HE0)="1,2,3,4,5,6,7,&H08":PRINT CHR$(128);CHR$(224)')
        self.assertEqual(cell(m.lcd, 0, 0)[:5], [".#.#..", "#####.", "#####.",
                                                ".###..", "..#..."])

    def test_font_errors(self):
        for src, msg in (('10 FONT$(65)="1,2,3,4,5,6,7,8"', "FC Error"),
                         ('10 FONT$(128)="1,2,3"', "SN Error"),
                         ('10 FONT$(128)="1,2,3,4,5,6,7,8,9"', "SN Error"),
                         ('10 FONT$(128)="1,2,3,4,5,6,7,256"', "FC Error")):
            ref, _ = emu.run_basic(src)
            self.assertIn(msg, ref)
            asm, _ = compile_basic(src, "T", 0x3000)
            a = Assembler()
            m = emu.run_binary(a.assemble_text(asm), a.entry)
            self.assertIn(msg, m.screen_text(), src)

    def test_example_graphisme(self):
        with open(os.path.join(ROOT, "exemples", "graphisme.bas")) as f:
            src = f.read()
        ref, mr = emu.run_basic(src, keys=" ")
        asm, _ = compile_basic(src, "T", 0x3000)
        a = Assembler()
        m = emu.run_binary(a.assemble_text(asm), a.entry, keys=" ")
        for x in range(6):                          # invite « > » de la ROM en bas à gauche
            for y in range(24, 32):
                mr.lcd.set(x, y, 0)
                m.lcd.set(x, y, 0)
        self.assertEqual(bytes(m.lcd.px), bytes(mr.lcd.px))
        self.assertTrue(m.lcd.get(96, 15))         # centre allumé grâce à POINT

    def test_scrolling(self):
        self.compare('10 CLS:FOR I=1 TO 6:PRINT "LIGNE";I:NEXT')


@needs_rom
@needs_font
class TestScreenEditor(unittest.TestCase):
    """Mode de la fenêtre : la ROM affiche elle-même, son éditeur plein écran
    reçoit les touches (flèches comprises)."""

    def session(self, keys, src="", preload=None):
        from x07asm.sim import SimError

        def setup(m):
            m.keys = list(keys)

            def wait_key():                       # plus de touches : fin de l'essai
                if not m.keys:
                    raise SimError("fin des touches")
                return m.keys.pop(0)
            m._wait_key = wait_key
        _, m = emu.run_basic(src, setup=setup, live=True, max_steps=20_000_000,
                             preload=preload)
        return m.lcd.text()

    def test_cold_boot_screen(self):
        m = emu.boot(16, real_display=True)
        self.assertEqual(m.lcd.text()[:3], ["Copyright(c) 1983 by", " Microsoft & Canon  ",
                                            "14940 Bytes free    "])

    def test_edit_listed_line_with_arrows(self):
        keys = (list("10 PRINT 123\rLIST\r") + ["\x1e"] + ["\x1c"] * 9
                + list("5\r") + list("RUN\r"))
        self.assertEqual(self.session(keys)[-2:], [" 523                ", ">                   "])

    def test_program_input(self):
        screen = self.session(list("7\r"), '10 INPUT "N";N:PRINT N*2')
        self.assertIn(" 14                 ", screen)

    def test_preloaded_program_with_input(self):
        """--charger : CLEAR tapé, programme en mémoire, EXEC ; après un INPUT,
        le retour au BASIC ne doit pas donner SN Error (ligne EXEC rétablie)."""
        asm, _ = compile_basic('10 INPUT "N";N:PRINT N*2', "T", 0x3000)
        a = Assembler()
        mem = a.assemble_text(asm)
        screen = self.session(list("EXEC &H%X:PRINT 99\r7\r" % a.entry), preload=mem)
        self.assertIn(" 14                 ", screen)
        self.assertIn(" 99                 ", screen)
        self.assertNotIn("Error", " ".join(screen))


if __name__ == "__main__":
    unittest.main()


@needs_rom
class TestStickStrig(unittest.TestCase):
    """Pavé de flèches du X-07 : directions et boutons tenus (sim.X07.held)."""

    CASES = ((set(), "0  0  0"), ({"haut"}, "1  0  0"), ({"droite"}, "3  0  0"),
             ({"bas"}, "5  0  0"), ({"gauche"}, "7  0  0"), ({"haut", "droite"}, "2  0  0"),
             ({"bas", "gauche"}, "6  0  0"), ({"haut", "bas"}, "0  0  0"),
             ({"milieu"}, "0  0 -1"), ({"espace"}, "0 -1  0"))
    SRC = "10 PRINT STICK(0);STRIG(0);STRIG(1)"

    def test_rom_basic(self):
        for held, expected in self.CASES:
            out, _ = emu.run_basic(self.SRC, setup=lambda m, h=held: m.held.update(h))
            self.assertEqual(out.strip(), expected, held)

    def test_example_fleches(self):
        with open(os.path.join(ROOT, "exemples", "fleches.bas")) as f:
            src = f.read().replace("170 CLS:END", "170 END")   # garder l'écran final
        cases = (({"droite"}, "aaaaaQ", [(66, 20)]),          # 6 pas vers la droite
                 ({"haut", "gauche"}, "aaaQ", [(56, 16)]),     # diagonale (STICK 8)
                 ({"droite", "milieu"}, "aaaaQ", [(x, 20) for x in range(60, 66)]))  # trace
        for held, keys, points in cases:
            for compiled in (False, True):
                if compiled:
                    asm, _ = compile_basic(src, "T", 0x3000)
                    a = Assembler()
                    m = emu.prepare_binary(a.assemble_text(asm), a.entry, keys=keys)
                    m.held.update(held)
                    m.run(50_000_000)
                else:
                    _, m = emu.run_basic(src, keys=keys,
                                         setup=lambda m, h=held: m.held.update(h))
                lit = [(x, y) for x in range(6, 120) for y in range(11, 32) if m.lcd.get(x, y)]
                self.assertEqual(sorted(lit), points, (held, compiled))

    def test_compiled(self):
        asm, _ = compile_basic(self.SRC, "T", 0x3000)
        a = Assembler()
        mem = a.assemble_text(asm)
        for held, expected in self.CASES:
            m = emu.prepare_binary(mem, a.entry)
            m.held.update(held)
            m.run(20_000_000)
            self.assertEqual(m.output().strip(), expected, held)


def has_display():
    try:
        import tkinter
        tkinter.Tk().destroy()
        return True
    except Exception:
        return False


@needs_rom
@unittest.skipUnless(has_display(), "pas d'affichage graphique")
class TestPad(unittest.TestCase):
    def test_touches_debounce_and_pad(self):
        import time
        import tkinter as tk
        from x07asm.afficheur import Pave, Touches, send_key, release_key
        root = tk.Tk()
        m = emu.boot(16)

        def pump(t):
            end = time.time() + t
            while time.time() < end:
                root.update()
                time.sleep(0.01)

        class Ev:
            def __init__(self, sym, ch=""):
                self.keysym, self.char = sym, ch
        try:
            t = Touches(root, lambda: m)
            pad = Pave(root, t)
            pad.click("gauche")                          # souris : tenue et tapée
            self.assertEqual((m.held, m.keys), ({"gauche"}, ["\x1d"]))
            pad.unclick()
            pump(0.2)
            self.assertEqual(m.held, set())
            # répétition automatique : relâchement suivi aussitôt d'un appui
            send_key(m, Ev("Up"), t)
            release_key(Ev("Up"), t)
            send_key(m, Ev("Up"), t)
            pump(0.2)
            self.assertEqual(m.held, {"haut"})
            release_key(Ev("Up"), t)
            pump(0.2)
            self.assertEqual(m.held, set())
            m.keys.clear()
            send_key(m, Ev("space", " "), t)             # espace : tapé et tenu
            self.assertEqual((m.held, m.keys), ({"espace", "milieu"}, [" "]))
            release_key(Ev("space", " "), t)
            send_key(m, Ev("KP_Begin"), t)               # 5 du pavé numérique
            pump(0.2)
            self.assertEqual(m.held, {"milieu"})
            send_key(m, Ev("KP_5", "5"), t)              # verrou allumé : un chiffre
            self.assertEqual(m.keys[-1], "5")
        finally:
            root.destroy()
