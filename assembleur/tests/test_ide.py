"""Tests de l'éditeur-débogueur (x07asm/ide.py).

La session (compilation, lignes, points d'arrêt, pas à pas, variables) est
testée sans affichage ; la fenêtre, seulement si un affichage existe."""
import gc
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
from x07asm import syntaxe                    # noqa: E402

needs_rom = unittest.skipUnless(emu.rom_path() is not None, "ROM_x07/x07.bin absente")
EX = os.path.join(ROOT, "exemples")


def has_display():
    try:
        import tkinter
        tkinter.Tk().destroy()
        return True
    except Exception:
        return False


class TestSyntaxe(unittest.TestCase):
    def colored(self, text, kind):
        lines = text.split("\n")
        return [(c, lines[n - 1][a:b]) for c, n, a, b in syntaxe.zones(text, kind)]

    def test_basic_x07(self):
        # comme la ROM : mots-clés collés reconnus, rien dans les chaînes, REM, DATA, &H
        self.assertEqual(self.colored('10 FORI=1TO9:PRINT"FOR";MID$(A$,I):NEXT\n'
                                      '20 X=&HFF:DATA TO,1:REM FOR\n30 A=1\'NEXT', "bas"),
                         [("numero", "10"), ("motcle", "FOR"), ("motcle", "TO"),
                          ("motcle", "PRINT"), ("chaine", '"FOR"'), ("fonction", "MID$"),
                          ("motcle", "NEXT"), ("numero", "20"), ("motcle", "DATA"),
                          ("commentaire", "REM FOR"), ("numero", "30"),
                          ("commentaire", "'NEXT")])

    def test_quickbasic(self):
        self.assertEqual(self.colored('DO WHILE fin <> 0: total = LEN(a$) \' fin\n'
                                      'rem x\nprint "if"; ucase$(nom$)', "qbas"),
                         [("motcle", "DO"), ("motcle", "WHILE"), ("fonction", "LEN"),
                          ("commentaire", "' fin"), ("commentaire", "rem x"),
                          ("motcle", "print"), ("chaine", '"if"'), ("fonction", "ucase$")])

    def test_assembly(self):
        # « ; » dans une chaîne, AF', caractère 'x', étiquette sans « : », « * » en tête
        self.assertEqual(self.colored('DEBUT:  LD   HL,MSG  ; (HL)\n.ATT ex af,af\'\n'
                                      'MSG: DB "a;b",\'x\',0\nN EQU 3\n* note', "asm"),
                         [("etiquette", "DEBUT"), ("motcle", "LD"), ("registre", "HL"),
                          ("commentaire", "; (HL)"), ("etiquette", ".ATT"), ("motcle", "ex"),
                          ("registre", "af"), ("registre", "af'"), ("etiquette", "MSG"),
                          ("directive", "DB"), ("chaine", '"a;b"'), ("chaine", "'x'"),
                          ("etiquette", "N"), ("directive", "EQU"), ("commentaire", "* note")])
        self.assertEqual(syntaxe.zones("PRINT 1", "txt"), [])


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

    def test_register_values_and_changes(self):
        from x07asm.ide import REG_ROWS, SuiviRegistres
        s = self.session("bonjour.asm")
        v = s.register_values()
        self.assertEqual(set(v) - {"steps"}, {n for row in REG_ROWS for n, _ in row})
        self.assertEqual((v["PC"], v["SP"]), (s.m.pc, s.m.sp))
        suivi = SuiviRegistres()
        self.assertEqual(suivi.changed(v), set())                # premier arrêt : rien
        s.step_line(True)                                        # LD HL,MSG
        s.step_line(True)
        w = s.register_values()
        self.assertTrue({"PC", "HL"} <= suivi.changed(w))
        self.assertEqual(suivi.changed(w), suivi.changed(w))     # même arrêt : gardés

    def test_register_detail_tab(self):
        from x07asm.ide import binaire, detail_valeur
        s = self.session("bonjour.asm")
        base = s.register_values()
        s.step_line(True)
        s.step_line(True)                                        # HL -> MSG
        lines = s.registres_detail(base)
        text = ["".join(t for t, _ in segs) for segs in lines]
        a = next(t for t in text if t.startswith("A "))
        self.assertIn("%02X" % s.m.r["A"], a)
        self.assertIn(binaire(s.m.r["A"], 8), a)                 # « 0000 1100 »
        self.assertTrue(any(t.startswith("(HL)") and "BONJOUR" in t for t in text))
        changed = [t for segs in lines for t, st in segs if st == "change"]
        self.assertIn("%04X" % s.m.get16("HL"), changed)         # valeur changée
        self.assertIn("1", changed)                              # et ses bits
        self.assertEqual(detail_valeur("A", 0xFF), "A = FF : 255 (signé -1)\n1111 1111   « · »")
        self.assertEqual(detail_valeur("HL", 0x41), "HL = 0041 : 65 (signé 65)\n"
                                                    "0000 0000 0100 0001")

    def test_breakpoints_survive_rebuild(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "t.qbas")
            shutil.copy(os.path.join(EX, "qbasic", "rapide.qbas"), p)
            s = Session(p)
            s.toggle_break(27)                                   # avant compilation
            s.build()
            self.assertIn(s.line_addr[27], s.dbg.breaks)
            self.assertEqual(s.run(), "point d'arrêt")

    def test_memory_kept_between_runs_without_option(self):
        # comme sur la machine : relancer un programme ne perd pas ses fichiers en RAM
        image = None
        for note, count in (("PAIN", 1), ("ZOE", 2)):
            s = Session(os.path.join(EX, "qbasic", "journal.qbas"), image=image)
            s.build()
            s.m.keys = list(note + "\r ")
            s.run()
            self.assertTrue(s.save_memory())
            self.assertIn(" %d note(s)" % count, "\n".join(s.m.lcd.text()))
            image = s.image

    def test_memory_kept_between_runs(self):
        # --memoire : les fichiers en RAM d'une exécution sont retrouvés à la suivante
        with tempfile.TemporaryDirectory() as d:
            mem = os.path.join(d, "x07.mem")
            for note, count in (("PAIN", 1), ("ZOE", 2)):
                s = Session(os.path.join(EX, "qbasic", "journal.qbas"), memoire=mem)
                s.build()
                s.m.keys = list(note + "\r ")
                s.run()
                self.assertTrue(s.finished)
                self.assertTrue(s.save_memory())
                self.assertIn(" %d note(s)" % count, "\n".join(s.m.lcd.text()))

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
    def tearDown(self):
        # la fenêtre fermée reste prise dans des cycles de références : on la
        # libère ici, dans le fil principal ; sinon le ramasse-miettes pourrait
        # le faire dans le fil d'émulation du test suivant, et Tcl abandonne
        # (« Tcl_AsyncDelete: async handler deleted by the wrong thread »)
        gc.collect()

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
                self.assertEqual(e.regs.values["PC"].cget("text"), "%04X" % e.session.m.pc)
                self.assertIn("binaire", e.panels["registres"].get("1.0", "end"))
                self.assertIn("PC = %04X" % e.session.m.pc, e.regs.bulle("PC"))
                self.assertIn("TRI.D% = 9", e.panels["variables"].get("1.0", "end"))
                e.do_run()
                pump(0.1)
                e.toggle(28)                                   # occupé : refusé sans erreur
            finally:
                e.close()

    def test_syntax_colors(self):
        from x07asm.ide import Editeur
        e = Editeur(os.path.join(EX, "fleches_x07.bas"))
        try:
            e.root.update()
            t = e.text
            self.assertEqual(t.get(*t.tag_ranges("motcle")[:2]), "CLEAR")
            self.assertIn("STICK", [t.get(a, b) for a, b in zip(*[iter(t.tag_ranges("fonction"))] * 2)])
            t.insert("end", "180 GOTO 10\n")            # recoloré après la frappe
            e.colorize()
            self.assertIn("GOTO", [t.get(a, b) for a, b in zip(*[iter(t.tag_ranges("motcle"))] * 2)])
        finally:
            e.text.edit_modified(False)
            e.close()

    def test_arrow_pad(self):
        from x07asm.ide import Editeur
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "s.bas")
            with open(p, "w") as f:
                f.write('10 S=STICK(0):T=STRIG(1):IF INKEY$<>"Q" THEN 10\n')
            e = Editeur(p)
            r = e.root

            def pump(t):
                end = time.time() + t
                while time.time() < end:
                    r.update()
                    time.sleep(0.02)
            try:
                pump(0.2)
                self.assertIsNone(e.running_machine())          # rien ne tourne
                e.pave.click("droite")                          # sans effet, sans erreur
                e.pave.unclick()
                e.compile()
                e.do_run()
                pump(0.8)
                e.pave.click("droite")
                pump(0.4)
                e.do_pause()
                for _ in range(40):
                    pump(0.05)
                    if not e.busy():
                        break
                self.assertIn("S# = 3", e.panels["variables"].get("1.0", "end"))
                e.pave.unclick()
            finally:
                e.close()

    def test_menus_and_toolbar(self):
        from x07asm.ide import Editeur, TOOLBAR
        e = Editeur(os.path.join(EX, "table.bas"))
        r = e.root

        def pump(t):
            end = time.time() + t
            while time.time() < end:
                r.update()
                time.sleep(0.02)
        try:
            pump(0.2)
            labels = [e.menubar.entrycget(k, "label") for k in range(1, 4)]
            self.assertEqual(labels, ["Fichier", "Exécution", "Aide"])
            self.assertEqual(set(e.buttons), {k for k, *_ in TOOLBAR if k})
            # largeur : la barre d'outils tient dans une petite partie de la fenêtre
            self.assertLess(e.buttons["reinit"].master.winfo_reqwidth(), 500)
            states = {label: menu.entrycget(label, "state") for menu, label, _ in e.menu_items}
            self.assertEqual(states["Pause"], "disabled")          # rien ne tourne
            self.assertEqual(states["Continuer"], "normal")
            self.assertEqual(str(e.buttons["pause"]["state"]), "disabled")
            e.compile()
            e.toggle(4)
            e.toggle(5)
            e.clear_breaks()                                       # Exécution › Enlever...
            self.assertEqual(e.session.break_lines, set())
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

    def test_new_program_and_save_as(self):
        from x07asm.ide import Editeur, TEMPLATES
        with tempfile.TemporaryDirectory() as d:
            e = Editeur()
            r = e.root

            def pump(t):
                end = time.time() + t
                while time.time() < end:
                    r.update()
                    time.sleep(0.02)
            try:
                pump(0.2)
                for ext, answer, shown in ((".bas", "ZOE", "BONJOUR ZOE"),
                                           (".qbas", "ZOE", "Bonjour ZOE"),
                                           (".asm", "X", "BONJOUR X-07 !")):
                    path = os.path.join(d, "essai" + ext)
                    self.assertTrue(e.new_file(path))          # modèle selon l'extension
                    with open(path) as f:
                        self.assertEqual(f.read(), TEMPLATES[ext])
                    self.assertTrue(e.compile())
                    e.entry.insert(0, answer)
                    e.send_line()                              # gardée jusqu'au départ
                    e.do_run()
                    for _ in range(100):
                        pump(0.05)
                        if not e.busy():
                            break
                    self.assertTrue(e.session.finished, ext)
                    self.assertIn(shown, "\n".join(e.session.m.lcd.text()))
                e.toggle(7)                                    # point d'arrêt, gardé
                e.text.insert("end", "; ajout\n")
                copy = os.path.join(d, "copie.asm")
                self.assertTrue(e.save_as(copy))
                self.assertEqual(e.path, copy)
                with open(copy) as f:
                    self.assertTrue(f.read().endswith("; ajout\n"))
                self.assertFalse(e.text.edit_modified())
                self.assertTrue(e.compile())
                self.assertEqual(e.session.break_lines, {7})
                self.assertFalse(e.save_as(os.path.join(d, "copie.txt")))   # extension refusée
            finally:
                e.text.edit_modified(False)
                e.close()


if __name__ == "__main__":
    unittest.main()
