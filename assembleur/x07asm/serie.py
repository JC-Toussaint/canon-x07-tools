"""Transfert d'un programme machine vers le X-07 par la prise série
(câble FT232RL, voir ref_docs/X07_FT232RL_liaison_serie.md).

Côté X-07 : un petit programme BASIC de réception (RECEPTEUR, à taper une
fois) ouvre « COM: » par INIT#1 et lit les octets par INP(#1).
Côté PC : x07asm.py send envoie le binaire.

Protocole (les pilotes série de la ROM n'ont qu'un tampon de 32 octets et
coupent RTS dès 6 octets ; RTS n'étant pas câblé, le PC se règle sur le X-07) :

  X-07 -> PC  « R »                         prêt
  PC -> X-07  adresse, longueur, lancement  3 mots, poids faible d'abord
  PC -> X-07  blocs de 16 octets            après chaque bloc le X-07 répond « K »
  PC -> X-07  somme des octets (mod 65536)  avec le dernier bloc
  X-07 -> PC  « O » correct, « E » erreur, « C » faire CLEAR d'abord
"""
import os
import sys
import time

BLOCK = 16
BAUDS = (1200, 2400, 4800, 8000)        # diviseur exact 24000/v (vérifié ROM : $DEBD)


def receiver_program(baud=4800):
    """Programme BASIC de réception, à taper sur le X-07."""
    return "\n".join([
        "10 REM RECEPTEUR SERIE X07ASM (%d BAUDS)" % baud,
        '20 DEFINT I,V:INIT#1,"COM:",%d,"B":OUT#1,82' % baud,
        "30 L=INP(#1):H=INP(#1):A=L+256*H",
        "40 L=INP(#1):H=INP(#1):N=L+256*H",
        "50 L=INP(#1):H=INP(#1):E=L+256*H",
        "60 M=PEEK(&H1DF)+256*PEEK(&H1E0)",
        '70 IF A<=M THEN OUT#1,67:PRINT "FAIRE CLEAR 50,&H";HEX$(A-1):END',
        '80 PRINT "RECEPTION...":S=0',
        "90 FOR I=0 TO N-1:V=INP(#1):POKE A+I,V:S=S+V",
        "100 IF (I AND 15)=15 THEN OUT#1,75",
        "110 NEXT:L=INP(#1):H=INP(#1):S=S-INT(S/65536)*65536",
        '120 IF L+256*H<>S THEN OUT#1,69:PRINT "ERREUR DE TRANSMISSION":END',
        '130 OUT#1,79:PRINT "OK. EXEC &H";HEX$(E)',
    ]) + "\n"


class TransferError(Exception):
    pass


class Sender:
    """Protocole côté PC, piloté par les octets reçus du X-07."""

    def __init__(self, mem, entry):
        if not mem:
            raise TransferError("rien à envoyer")
        lo, hi = min(mem), max(mem)
        self.org, self.entry = lo, entry
        self.data = bytes(mem.get(a, 0) for a in range(lo, hi + 1))
        self.blocks = [self.data[k:k + BLOCK] for k in range(0, len(self.data), BLOCK)]
        self.next_block = 0
        self.state = "attente"
        self.result = None
        self.progress = None          # fonction(octets envoyés, total)

    def _word(self, v):
        return bytes([v & 0xFF, (v >> 8) & 0xFF])

    def _block(self):
        b = self.blocks[self.next_block]
        self.next_block += 1
        out = b
        if self.next_block == len(self.blocks):          # dernier bloc + somme
            out += self._word(sum(self.data) & 0xFFFF)
            self.state = "fin"
        if self.progress:
            self.progress(min(self.next_block * BLOCK, len(self.data)), len(self.data))
        return out

    def on_byte(self, b):
        """Octet reçu du X-07 -> octets à lui envoyer."""
        c = chr(b)
        if c == "C":
            self.result = "clear"
            return b""
        if c in "OE" and self.state == "fin":
            self.result = "ok" if c == "O" else "erreur"
            return b""
        if self.state == "attente" and c == "R":
            self.state = "blocs"
            head = self._word(self.org) + self._word(len(self.data)) + self._word(self.entry)
            if not self.blocks:
                self.state = "fin"
                return head + self._word(0)
            return head + self._block()
        if self.state == "blocs" and c == "K":
            return self._block()
        return b""                     # « K » après le dernier bloc, bruit...


# ---------------------------------------------------------------- port série

class SerialPort:
    """Port série : pyserial s'il est installé, sinon termios (Linux, WSL)."""

    def __init__(self, name, baud):
        self.name = name
        try:
            import serial
            self.s = serial.Serial(name, baud, bytesize=8, parity="N", stopbits=2,
                                   timeout=0.1, rtscts=False, xonxoff=False)
            self.kind = "pyserial"
            self.s.reset_input_buffer()
            return
        except ImportError:
            pass
        import termios
        speeds = {1200: termios.B1200, 2400: termios.B2400, 4800: termios.B4800}
        if baud not in speeds:
            raise TransferError("sans pyserial, vitesses possibles : 1200, 2400, 4800")
        self.fd = os.open(name, os.O_RDWR | os.O_NOCTTY | os.O_NONBLOCK)
        a = termios.tcgetattr(self.fd)
        a[0] = 0                                   # iflag : brut
        a[1] = 0                                   # oflag
        a[2] = termios.CS8 | termios.CSTOPB | termios.CREAD | termios.CLOCAL  # 8N2
        a[3] = 0                                   # lflag
        a[4] = a[5] = speeds[baud]
        a[6][termios.VMIN] = 0
        a[6][termios.VTIME] = 1
        termios.tcsetattr(self.fd, termios.TCSANOW, a)
        termios.tcflush(self.fd, termios.TCIOFLUSH)
        self.kind = "termios"

    def read(self):
        if self.kind == "pyserial":
            return self.s.read(64)
        import select
        r, _, _ = select.select([self.fd], [], [], 0.1)
        return os.read(self.fd, 64) if r else b""

    def write(self, data):
        if self.kind == "pyserial":
            self.s.write(data)
            self.s.flush()
        else:
            os.write(self.fd, data)
            import termios
            termios.tcdrain(self.fd)

    def close(self):
        if self.kind == "pyserial":
            self.s.close()
        else:
            os.close(self.fd)


def send(port, mem, entry, timeout=60, log=print):
    """Envoie mem au X-07 qui exécute RECEPTEUR.  Renvoie « ok »."""
    snd = Sender(mem, entry)
    snd.progress = lambda done, total: log("\r  %d / %d octets" % (done, total), end="")
    log("Attente du X-07 : lancez RECEPTEUR (RUN) sur la machine...")
    last = time.time()
    while snd.result is None:
        data = port.read()
        if data:
            last = time.time()
            for b in data:
                out = snd.on_byte(b)
                if out:
                    port.write(out)
        elif time.time() - last > timeout:
            raise TransferError("le X-07 ne répond plus (vérifiez le câble, CTS, la vitesse)")
    log("")
    if snd.result == "clear":
        raise TransferError("tapez d'abord CLEAR 50,&H%X sur le X-07" % (snd.org - 1))
    if snd.result == "erreur":
        raise TransferError("somme de contrôle incorrecte : recommencez")
    return snd


# ---------------------------------------------------------------- émulation

def send_emulated(mem, entry, baud=4800, ram=16, clear=True, max_steps=200_000_000):
    """Transfert complet avec le X-07 émulé (vraie ROM, UART émulée).
    Renvoie (affichage du X-07, Sender, machine)."""
    from . import emu
    snd = Sender(mem, entry)
    src = receiver_program(baud)
    if clear:
        top = snd.org - 1
        src = "5 CLEAR 50,%d\n" % top + src
    m_holder = {}

    def setup(m):
        m_holder["m"] = m
        m.byte_steps = max(200, int(1500 * 4800 / baud))

        def on_serial(b):
            out = snd.on_byte(b)
            m.serial_in.extend(out)
        m.on_serial = on_serial

    out, m = emu.run_basic(src, ram=ram, max_steps=max_steps, setup=setup)
    return out, snd, m
