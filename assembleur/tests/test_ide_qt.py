"""Tests de l'éditeur-débogueur Qt (x07asm/ide_qt.py).

Les mêmes scénarios que la fenêtre tkinter (tests/test_ide.py), sans
affichage (plateforme Qt « offscreen ») ; sautés si PyQt6 est absent."""
import os
import shutil
import sys
import tempfile
import time
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from x07asm import emu                        # noqa: E402

try:
    from PyQt6.QtCore import QEvent, Qt   # noqa: E402
    from PyQt6.QtGui import QKeyEvent    # noqa: E402
    from x07asm import ide_qt             # noqa: E402
except ImportError:
    ide_qt = None

needs_rom = unittest.skipUnless(emu.rom_path() is not None, "ROM_x07/x07.bin absente")
needs_qt = unittest.skipUnless(ide_qt is not None, "PyQt6 absent")
EX = os.path.join(ROOT, "exemples")


def pump(e, t):
    end = time.monotonic() + t
    while time.monotonic() < end:
        e.app.processEvents()
        time.sleep(0.02)


def run_until_stopped(e, tries=100):
    for _ in range(tries):
        pump(e, 0.05)
        if not e.busy():
            break
    pump(e, 0.1)


@needs_qt
class TestKeys(unittest.TestCase):
    def test_qt_keys_as_tk_events(self):
        K, M = Qt.Key, Qt.KeyboardModifier

        def ev(key, text="", mods=M.NoModifier):
            return ide_qt.touche_qt(QKeyEvent(QEvent.Type.KeyPress, key, mods, text))
        self.assertEqual(ev(K.Key_Return).keysym, "Return")
        self.assertEqual(ev(K.Key_Up).keysym, "Up")
        self.assertEqual(ev(K.Key_Up, mods=M.KeypadModifier).keysym, "KP_Up")
        self.assertEqual(ev(K.Key_Clear).keysym, "KP_Begin")     # 5 du pavé, verrou éteint
        self.assertEqual((ev(K.Key_A, "a").keysym, ev(K.Key_A, "a").char), ("a", "a"))


@needs_rom
@needs_qt
class TestWindowQt(unittest.TestCase):
    def test_click_run_and_edit(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "t.qbas")
            shutil.copy(os.path.join(EX, "qbasic", "rapide.qbas"), p)
            e = ide_qt.Editeur(p)
            try:
                pump(e, 0.2)
                self.assertTrue(e.compile())
                e.toggle(27)
                c = e.text.textCursor()                        # le point d'arrêt suit : 28
                c.setPosition(e.text.document().findBlockByNumber(23).position())
                c.insertText("' ajout\n")
                pump(e, 0.1)
                self.assertEqual(e.session.break_lines, {28})
                e.do_run()
                run_until_stopped(e)
                self.assertIn("point d'arrêt, ligne 28", e.status.text())
                self.assertIn("TRI.D% = 9", e.panels["variables"].toPlainText())
                self.assertEqual(len(e.text.extraSelections()), 2)   # arrêt + ligne en cours
                e.do_run()
                pump(e, 0.1)
                e.toggle(28)                                   # occupé : refusé sans erreur
            finally:
                e.text.document().setModified(False)
                e.close()

    def test_arrow_pad(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "s.bas")
            with open(p, "w") as f:
                f.write('10 S=STICK(0):T=STRIG(1):IF INKEY$<>"Q" THEN 10\n')
            e = ide_qt.Editeur(p)
            try:
                pump(e, 0.2)
                self.assertIsNone(e.running_machine())
                e.pave.click("droite")                         # sans effet, sans erreur
                e.pave.unclick()
                e.compile()
                e.do_run()
                pump(e, 0.8)
                e.pave.click("droite")
                pump(e, 0.4)
                e.do_pause()
                run_until_stopped(e, 40)
                self.assertIn("S# = 3", e.panels["variables"].toPlainText())
                e.pave.unclick()
                pump(e, 0.2)                                   # relâchée après le délai
                self.assertEqual(e.session.m.held, set())
            finally:
                e.close()

    def test_typing_while_stopped_and_input_field(self):
        e = ide_qt.Editeur(os.path.join(EX, "table.bas"))
        try:
            pump(e, 0.2)
            e.compile()
            e.toggle(2)                                        # arrêt avant 20 CLS:INPUT
            e.do_run()
            run_until_stopped(e)
            e.ecran.keyPressEvent(QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_7,
                                            Qt.KeyboardModifier.NoModifier, "7"))
            self.assertEqual(e.session.m.keys, ["7"])          # programme arrêté : gardée
            e.session.m.keys.clear()
            e.entry.setText("8")
            e.send_line()                                      # champ « Taper pour le X-07 »
            self.assertEqual(e.session.m.keys, ["8", "\r"])
            e.toggle(2)
            e.do_run()
            run_until_stopped(e)
            self.assertIn("MOYENNE 40", "\n".join(e.session.m.lcd.text()))
            on = ide_qt.QColor(ide_qt.ON).rgb()             # l'écran Qt montre le texte
            self.assertTrue(any(e.ecran.image.pixel(x, y) == on
                                for x in range(120) for y in range(8)))
        finally:
            e.close()

    def test_new_program_and_save_as(self):
        with tempfile.TemporaryDirectory() as d:
            e = ide_qt.Editeur()
            try:
                pump(e, 0.2)
                for ext, answer, shown in ((".bas", "ZOE", "BONJOUR ZOE"),
                                           (".qbas", "ZOE", "Bonjour ZOE"),
                                           (".asm", "X", "BONJOUR X-07 !")):
                    path = os.path.join(d, "essai" + ext)
                    self.assertTrue(e.new_file(path))
                    with open(path) as f:
                        self.assertEqual(f.read(), ide_qt.TEMPLATES[ext])
                    self.assertTrue(e.compile())
                    e.entry.setText(answer)
                    e.send_line()                              # gardée jusqu'au départ
                    e.do_run()
                    run_until_stopped(e)
                    self.assertTrue(e.session.finished, ext)
                    self.assertIn(shown, "\n".join(e.session.m.lcd.text()))
                e.toggle(7)                                    # point d'arrêt, gardé
                c = e.text.textCursor()
                c.movePosition(c.MoveOperation.End)
                c.insertText("; ajout\n")
                copy = os.path.join(d, "copie.asm")
                self.assertTrue(e.save_as(copy))
                self.assertEqual(e.path, copy)
                with open(copy) as f:
                    self.assertTrue(f.read().endswith("; ajout\n"))
                self.assertFalse(e.modified())
                self.assertTrue(e.compile())
                self.assertEqual(e.session.break_lines, {7})
            finally:
                e.close()

    def test_menus_toolbar_and_colors(self):
        e = ide_qt.Editeur(os.path.join(EX, "table.bas"))
        try:
            pump(e, 0.2)
            titles = [a.text().replace("&", "") for a in e.menubar.actions()]
            self.assertEqual(titles, ["Fichier", "Exécution", "Aide"])
            self.assertEqual(set(e.actions), {k for k, *_ in ide_qt.TOOLBAR if k})
            self.assertFalse(e.actions["pause"].isEnabled())   # rien ne tourne
            self.assertTrue(e.actions["continuer"].isEnabled())
            # coloration : le numéro de la première ligne est en couleur
            fmts = e.text.document().firstBlock().layout().formats()
            self.assertTrue(any(f.start == 0 for f in fmts))
            # police à chasse fixe, quel que soit le système
            fm = e.text.fontMetrics()
            self.assertEqual(fm.horizontalAdvance("i"), fm.horizontalAdvance("W"))
            e.compile()
            e.toggle(4)
            e.toggle(5)
            e.clear_breaks()                                   # Exécution › Enlever...
            self.assertEqual(e.session.break_lines, set())
        finally:
            e.close()


if __name__ == "__main__":
    unittest.main()
