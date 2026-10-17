"""Fichiers en RAM du X-07 (vérifiés dans la ROM) et persistance après OFF.

Étude préalable à la gestion des fichiers QuickBASIC (FICHIERS.md)."""
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from x07asm import emu                        # noqa: E402

needs_rom = unittest.skipUnless(emu.rom_path() is not None, "ROM_x07/x07.bin absente")

# EOF(C) : pointeur de LECTURE du canal C (KBNTAB + 4) au-delà de la fin (+6),
# ou sur un octet 0 ; le saut de ligne laissé par la ligne précédente est sauté
EOF_SUB = '''900 K=&H2C5+8*(C-1):P=PEEK(K+4)+256*PEEK(K+5):F=PEEK(K+6)+256*PEEK(K+7)
910 IF P<=F THEN IF PEEK(P)=10 THEN P=P+1
920 E=(P>F):IF NOT E THEN E=(PEEK(P)=0)
930 RETURN
940 IF LEFT$(A$,1)=CHR$(10) THEN A$=MID$(A$,2)
950 RETURN
'''


@needs_rom
class TestRamFiles(unittest.TestCase):
    def run_prog(self, src):
        out, m = emu.run_basic(src, max_steps=20_000_000)
        self.assertIsNone(m.error)
        return out.strip().replace("\n", " | "), m

    def test_write_read_dir(self):
        out, m = self.run_prog('10 FSET 400\n20 INIT#1,"RAM:DATA",100\n'
                               '30 PRINT #1,"BONJOUR,12"\n40 INIT#2,"RAM:DATA"\n'
                               '50 INPUT #2,A$,B\n60 PRINT A$;B\n70 DIR')
        self.assertEqual(out, "BONJOUR 12  | RAM: | DATA   D   | 400/273")
        # en haut de la RAM, sous les 14 octets de la ROM ; MEMSIZ abaissé
        self.assertEqual(m.rd16(0x212), 0x3FF7)
        self.assertEqual(m.rd16(0x3FFC), m.rd16(0x210))     # copie de RAMSTR
        self.assertLess(m.rd16(0x1DF), m.rd16(0x210))

    def test_limits(self):
        cases = (('10 FSET 400\n20 INIT#1,"RAM:F",10\n30 FOR I=1 TO 10:PRINT #1,"ABCDE":NEXT',
                  "IO Error"),                                   # taille fixe
                 ('10 FSET 400\n20 INIT#1,"RAM:F",50\n30 PRINT #1,"X"\n40 INIT#2,"RAM:F"\n'
                  '50 INPUT #2,A$\n60 INPUT #2,B$', "IO Error in 60"),     # lecture après la fin
                 ('10 INIT#1,"RAM:DATA"', "NE Error"),         # fichier absent
                 ('10 PRINT EOF(1)', " 0"),                    # pas d'EOF : un tableau
                 ('10 CLOSE #1', "SN Error"))                  # pas de CLOSE
        for src, expected in cases:
            out, m = emu.run_basic(src, max_steps=20_000_000)
            self.assertIn(expected, out, src)

    def test_delete_and_six_letter_names(self):
        out, _ = self.run_prog('10 FSET 200\n20 INIT#1,"RAM:AB",20\n30 INIT#2,"RAM:NOMLONG1",10\n'
                               '40 DELETE "AB"\n50 DIR')
        self.assertEqual(out, "RAM: | NOMLON D   | 200/163")

    def test_eof_truncate_append(self):
        out, _ = self.run_prog('10 FSET 300\n20 INIT#1,"RAM:F",60\n30 FOR I=1 TO 3:PRINT #1,"L";I:NEXT\n'
                               '40 INIT#2,"RAM:F"\n50 C=2:GOSUB 900:IF E THEN 80\n'
                               '60 LINE INPUT #2,A$:GOSUB 940:PRINT A$;"/";\n70 GOTO 50\n'
                               '80 PRINT "FIN":END\n' + EOF_SUB)
        self.assertEqual(out, "L 1 /L 2 /L 3 /FIN")
        # OUTPUT : données remises à zéro après INIT# (sinon l'ancien texte reste)
        out, _ = self.run_prog('10 FSET 300\n20 INIT#1,"RAM:F",40\n30 PRINT #1,"LONGUE":PRINT #1,"DEUX"\n'
                               '40 INIT#1,"RAM:F"\n50 K=&H2C5:D=PEEK(K+4)+256*PEEK(K+5)\n'
                               '60 F=PEEK(K+6)+256*PEEK(K+7):FOR P=D TO F:POKE P,0:NEXT\n'
                               '70 PRINT #1,"COURT"\n80 INIT#2,"RAM:F"\n90 C=2:GOSUB 900:IF E THEN 120\n'
                               '100 LINE INPUT #2,A$:GOSUB 940:PRINT A$;"/";\n110 GOTO 90\n'
                               '120 PRINT "FIN":END\n' + EOF_SUB)
        self.assertEqual(out, "COURT/FIN")
        # APPEND : pointeur d'ÉCRITURE (+2) placé sur le premier octet nul
        out, _ = self.run_prog('10 FSET 300\n20 INIT#1,"RAM:F",40\n30 PRINT #1,"UN"\n40 INIT#1,"RAM:F"\n'
                               '50 K=&H2C5:P=PEEK(K+4)+256*PEEK(K+5):F=PEEK(K+6)+256*PEEK(K+7)\n'
                               '60 IF P<=F THEN IF PEEK(P)<>0 THEN P=P+1:GOTO 60\n'
                               '70 POKE K+2,P AND 255:POKE K+3,P\\256\n80 PRINT #1,"DEUX"\n'
                               '90 INIT#2,"RAM:F"\n100 C=2:GOSUB 900:IF E THEN 130\n'
                               '110 LINE INPUT #2,A$:GOSUB 940:PRINT A$;"/";\n120 GOTO 100\n'
                               '130 PRINT "FIN":END\n' + EOF_SUB)
        self.assertEqual(out, "UN/DEUX/FIN")


@needs_rom
class TestPowerCycle(unittest.TestCase):
    def test_files_and_program_survive_off(self):
        out, m = emu.run_basic('10 FSET 200\n20 INIT#1,"RAM:NOTES",40\n'
                               '30 PRINT #1,"BONJOUR,42"\n40 PRINT "ECRIT"')
        self.assertEqual(out.strip(), "ECRIT")
        image = emu.power_off(m)                      # OFF : la ROM range son état
        m2 = emu.power_on(image)                      # rallumée : RAM gardée
        out, m2 = emu.run_basic('NEW\n10 INIT#2,"RAM:NOTES":INPUT #2,A$,N:PRINT A$;N',
                                machine=m2)
        self.assertEqual(out.strip(), "BONJOUR 42")

    def test_program_kept_after_off(self):
        _, m = emu.run_basic('10 PRINT "GARDE"')
        m2 = emu.power_on(emu.power_off(m))
        out, _ = emu.run_basic("RUN", machine=m2)     # le programme est toujours là
        self.assertIn("GARDE", out)


if __name__ == "__main__":
    unittest.main()


@needs_rom
class TestQBasicFiles(unittest.TestCase):
    """OPEN, PRINT #, WRITE #, INPUT #, LINE INPUT #, EOF, KILL : traduction
    en BASIC du X-07, exécutée par la ROM."""

    def translate_run(self, src, machine=None, **kw):
        from x07asm import qbasic
        out, warns, _ = qbasic.translate(src)
        res, m = emu.run_basic(out, machine=machine, max_steps=40_000_000, **kw)
        self.assertIsNone(m.error, out)
        return res.strip().replace("\n", " | "), m, out

    def test_output_write_append_input_eof(self):
        res, _, out = self.translate_run('''
OPEN "notes.dat" FOR OUTPUT AS #1
FOR i% = 1 TO 3
    PRINT #1, "Ligne"; i%
NEXT i%
WRITE #1, "a,b", 42
CLOSE #1
OPEN "notes.dat" FOR APPEND AS #1
PRINT #1, "Ajout"
CLOSE #1
OPEN "notes.dat" FOR INPUT AS #2
n% = 0
DO WHILE NOT EOF(2)
    LINE INPUT #2, l$
    n% = n% + 1
    PRINT l$; "/";
LOOP
CLOSE
PRINT n%''')
        self.assertEqual(res, 'Ligne 1 /Ligne 2 /Ligne 3 /"a,b", 42 /Ajout/ 5')
        self.assertIn("FSET 1024", out)
        self.assertIn('INIT #1,"RAM:NOTES",256', out)

    def test_input_values_and_rewrite(self):
        res, _, _ = self.translate_run('''
OPEN "val" FOR OUTPUT AS #1 LEN = 100
WRITE #1, "Zoe", 12
WRITE #1, "Max", 30
CLOSE #1
OPEN "val" FOR OUTPUT AS #1
WRITE #1, "Lea", 7
CLOSE #1
OPEN "val" FOR INPUT AS #1
DO UNTIL EOF(1)
    INPUT #1, nom$, age%
    PRINT nom$; age%; "/";
LOOP''')
        self.assertEqual(res, "Lea 7 /")          # OUTPUT a vidé le fichier

    def test_kill_and_channel_limit(self):
        from x07asm import qbasic
        res, m, out = self.translate_run('OPEN "a" FOR OUTPUT AS #1\nPRINT #1, 1\nKILL "a"\n'
                                         'OPEN "b" FOR OUTPUT AS #1\nCLOSE')
        self.assertIn('DELETE "A"', out)
        with self.assertRaises(qbasic.QBError):
            qbasic.translate('OPEN "a" FOR OUTPUT AS #6')

    def test_journal_survives_power_off(self):
        with open(os.path.join(ROOT, "exemples", "qbasic", "journal.qbas"),
                  encoding="utf-8") as f:
            src = f.read()
        machine = None
        for note, count in (("PAIN", 1), ("ZOE", 2), ("PILES", 3)):
            res, m, _ = self.translate_run(src, machine=machine, inputs=[note], keys=" ")
            self.assertIn("%d %s" % (count, note), res)
            self.assertIn(" %d note(s)" % count, res)
            machine = emu.power_on(emu.power_off(m))      # éteint, rallumé

    def test_memory_option(self):
        import contextlib
        import io
        import tempfile
        from x07asm.cli import main
        src = ('n% = 0\nOPEN "compte" FOR APPEND AS #1\nCLOSE\nOPEN "compte" FOR INPUT AS #1\n'
               'IF NOT EOF(1) THEN INPUT #1, n%\nCLOSE\nn% = n% + 1\n'
               'OPEN "compte" FOR OUTPUT AS #1\nPRINT #1, n%\nCLOSE\nPRINT "LANCEMENT"; n%\n')
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "compte.qbas")
            with open(p, "w") as f:
                f.write(src)
            mem = os.path.join(d, "x07.mem")
            for k in (1, 2, 3):
                with contextlib.redirect_stdout(io.StringIO()) as out:
                    self.assertEqual(main(["emu", p, "--memoire", mem]), 0)
                self.assertIn("LANCEMENT %d" % k, out.getvalue())
            self.assertEqual(os.path.getsize(mem), 16384)
            with contextlib.redirect_stdout(io.StringIO()), \
                    contextlib.redirect_stderr(io.StringIO()) as err:
                self.assertEqual(main(["emu", p, "--memoire", mem, "--ram", "8"]), 1)
            self.assertIn("16 Ko", err.getvalue())
