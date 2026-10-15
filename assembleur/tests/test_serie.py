"""Tests du transfert par la prise série (protocole, X-07 émulé, pseudo-port)."""
import os
import sys
import threading
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from x07asm import serie, emu                  # noqa: E402
from x07asm.asm import Assembler               # noqa: E402

needs_rom = unittest.skipUnless(emu.rom_path() is not None, "ROM_x07/x07.bin absente")


def program(n, org=0x1C00):
    return {org + i: (i * 7 + 3) & 0xFF for i in range(n)}


class TestProtocol(unittest.TestCase):
    def play(self, mem, entry):
        """Joue le rôle du X-07 et renvoie ce qu'il a reçu."""
        snd = serie.Sender(mem, entry)
        got = bytearray(snd.on_byte(ord("R")))
        while snd.state != "fin":
            got += snd.on_byte(ord("K"))
        snd.on_byte(ord("K"))                       # « K » du dernier bloc : ignoré
        snd.on_byte(ord("O"))
        return got, snd

    def test_layout(self):
        for n in (1, 15, 16, 17, 32, 100):
            with self.subTest(n=n):
                mem = program(n)
                got, snd = self.play(mem, 0x1C05)
                self.assertEqual(got[:6], bytes([0x00, 0x1C, n & 255, n >> 8, 0x05, 0x1C]))
                data = got[6:-2]
                self.assertEqual(bytes(data), bytes(mem[0x1C00 + i] for i in range(n)))
                s = sum(data) & 0xFFFF
                self.assertEqual(got[-2:], bytes([s & 255, s >> 8]))
                self.assertEqual(snd.result, "ok")

    def test_never_more_than_buffer(self):
        """Jamais plus de 22 octets d'avance (le tampon de la ROM en a 32)."""
        snd = serie.Sender(program(200), 0x1C00)
        first = snd.on_byte(ord("R"))
        self.assertLessEqual(len(first), 22)
        while snd.state != "fin":
            self.assertLessEqual(len(snd.on_byte(ord("K"))), 18)

    def test_errors(self):
        snd = serie.Sender(program(10), 0x1C00)
        snd.on_byte(ord("C"))
        self.assertEqual(snd.result, "clear")
        snd = serie.Sender(program(10), 0x1C00)
        snd.on_byte(ord("R"))
        snd.on_byte(ord("E"))
        self.assertEqual(snd.result, "erreur")


@needs_rom
class TestEmulatedX07(unittest.TestCase):
    def test_transfer(self):
        a = Assembler()
        mem = a.assemble_file(os.path.join(ROOT, "exemples", "bonjour.asm"))
        out, snd, m = serie.send_emulated(mem, a.entry)
        self.assertEqual(snd.result, "ok")
        self.assertEqual(m.overruns, 0)
        self.assertTrue(all(m.mem[k] == v for k, v in mem.items()))
        self.assertIn("OK. EXEC &H1C00", out)

    def test_needs_clear(self):
        out, snd, m = serie.send_emulated(program(40), 0x1C00, clear=False)
        self.assertEqual(snd.result, "clear")
        self.assertIn("FAIRE CLEAR 50,&H1BFF", out)

    def test_receiver_is_valid_x07_basic(self):
        """Le récepteur ne doit déclencher aucune erreur de syntaxe sur le X-07."""
        src = serie.receiver_program(4800)
        self.assertNotIn("DEF ", src)
        out, snd, m = serie.send_emulated(program(1), 0x1C00)
        self.assertNotIn("Error", out)


@needs_rom
@unittest.skipUnless(hasattr(os, "openpty"), "pseudo-terminaux indisponibles")
class TestPseudoPort(unittest.TestCase):
    """Le vrai code d'envoi, sur un pseudo-port relié au X-07 émulé."""

    def run_over_pty(self, hide_pyserial):
        import tty
        saved = sys.modules.get("serial")
        if hide_pyserial:
            sys.modules["serial"] = None
        try:
            mem = program(100, 0x3800)
            master, slave = os.openpty()
            tty.setraw(master)
            res = {}

            def x07():
                def setup(m):
                    m.on_serial = lambda b: os.write(master, bytes([b]))

                    def feed():
                        while not res.get("fin"):
                            try:
                                d = os.read(master, 64)
                            except OSError:
                                break
                            m.serial_in.extend(d)
                    threading.Thread(target=feed, daemon=True).start()
                src = "5 CLEAR 50,%d\n" % (0x3800 - 1) + serie.receiver_program(4800)
                res["out"], res["m"] = emu.run_basic(src, setup=setup, max_steps=100_000_000)

            t = threading.Thread(target=x07)
            t.start()
            port = serie.SerialPort(os.ttyname(slave), 4800)
            try:
                serie.send(port, mem, 0x3800, timeout=60, log=lambda *a, **k: None)
            finally:
                port.close()
            t.join(120)
            res["fin"] = True
            m = res["m"]
            self.assertTrue(all(m.mem[k] == v for k, v in mem.items()))
            return port.kind
        finally:
            if hide_pyserial:
                if saved is None:
                    sys.modules.pop("serial", None)
                else:
                    sys.modules["serial"] = saved

    def test_termios(self):
        self.assertEqual(self.run_over_pty(True), "termios")

    def test_pyserial(self):
        try:
            import serial  # noqa: F401
        except ImportError:
            self.skipTest("pyserial non installé")
        self.assertEqual(self.run_over_pty(False), "pyserial")


if __name__ == "__main__":
    unittest.main()
