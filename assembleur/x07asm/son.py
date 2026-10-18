"""Haut-parleur du X-07 : les bips de BEEP joués sur le PC.

Le buzzer reçoit une onde carrée ; on la joue par ffplay (PulseAudio, que
WSLg fournit sous Windows), un seul processus alimenté en continu.  Comme sur
la machine, un BEEP rend la main tout de suite, et le suivant attend la fin
du précédent : le programme garde son rythme.  Sans ffplay, ou en muet, les
durées sont respectées en silence."""
import queue
import shutil
import struct
import subprocess
import threading
import time

RATE = 22050                  # échantillons par seconde
VOLUME = 5000                 # amplitude de l'onde carrée (16 bits signés)


def square(freq, dur, rate=RATE):
    """Échantillons (16 bits, mono) d'une onde carrée ; freq = 0 : silence."""
    n = int(rate * dur)
    if not freq:
        return bytes(2 * n)
    half = rate / (2.0 * freq)                # échantillons par demi-période
    hi, lo = struct.pack("<h", VOLUME), struct.pack("<h", -VOLUME)
    return b"".join(hi if int(i / half) % 2 == 0 else lo for i in range(n))


class HautParleur:
    def __init__(self, muet=False):
        self.muet = muet or shutil.which("ffplay") is None
        self.until = 0.0                      # fin du bip en cours (time.monotonic)
        self.proc = None
        self.queue = queue.Queue()
        self.lock = threading.Lock()

    def note(self, freq, dur, cancel=lambda: False):
        """Un bip (appelé par la machine, dans son fil d'exécution)."""
        while time.monotonic() < self.until:  # le buzzer est encore occupé
            if cancel():
                return
            time.sleep(min(0.01, self.until - time.monotonic()) or 0)
        self.until = time.monotonic() + dur
        if not self.muet and freq:
            self._play(square(freq, dur) + square(0, 0.02))
        # un silence (BEEP 0,d) occupe aussi le buzzer, sans son

    def _play(self, data):
        with self.lock:
            if self.proc is None:
                try:
                    self.proc = subprocess.Popen(
                        ["ffplay", "-f", "s16le", "-ar", str(RATE), "-ch_layout", "mono",
                         "-nodisp", "-loglevel", "quiet", "-i", "-"],
                        stdin=subprocess.PIPE, stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL)
                except OSError:
                    self.muet = True
                    return
                threading.Thread(target=self._writer, daemon=True).start()
        self.queue.put(data)

    def _writer(self):
        while True:
            data = self.queue.get()
            if data is None:
                return
            try:
                self.proc.stdin.write(data)
                self.proc.stdin.flush()
            except (BrokenPipeError, OSError, ValueError):
                self.muet = True
                return

    def close(self):
        with self.lock:
            if self.proc is not None:
                self.queue.put(None)
                try:
                    self.proc.stdin.close()
                except OSError:
                    pass
                self.proc.terminate()
                self.proc = None
