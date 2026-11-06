#!/usr/bin/env python3
"""Test de communication PC <-> Canon X-07 par écho.

Le X-07 exécute le petit programme ECHO ci-dessous : il annonce « R », puis
renvoie chaque octet reçu et l'affiche. Le PC envoie un texte, puis les 256
valeurs d'octet, une à la fois, et vérifie chaque écho. ÉCHAP (27) termine.

Programme ECHO (python test_echo_x07.py --programme l'affiche) :

    10 REM TEST ECHO SERIE
    20 DEFINT V:INIT#1,"COM:",4800,"B":OUT#1,82
    30 V=INP(#1):OUT#1,V
    40 IF V=13 THEN PRINT
    50 IF V<32 THEN 60
    55 PRINT CHR$(V);
    60 IF V=27 THEN 70
    65 GOTO 30
    70 PRINT:PRINT "FIN DU TEST"

Deux façons de le mettre sur le X-07 :
  - le taper au clavier, puis RUN une fois le script lancé ;
  - --charger : le PC l'envoie par la prise série et le lance lui-même. Sur le
    X-07, on tape seulement NEW puis la ligne
        INIT#5,"COM:",4800,"B":EXEC &HEE1F
    (fonction cachée de la ROM : le BASIC lit ses lignes sur la prise série,
    voir assembleur/TRANSFERT.md). À la fin, le PC rend le clavier au X-07.

Câble : FT232R avec TXD et RXD inversés (FT_Prog), voir
ref_docs/X07_FT232RL_liaison_serie.md. Réglage du PC : 4800 bauds, 8 bits,
sans parité, 2 bits d'arrêt, sans contrôle de flux.

    python test_echo_x07.py -p COM5             # Windows
    python test_echo_x07.py -p /dev/ttyUSB0     # Linux
    python test_echo_x07.py -p /dev/ttyUSB0 --charger   # programme envoyé par le PC
    python test_echo_x07.py --emu [--charger]   # essai avec le X-07 émulé
"""

import argparse
import os
import sys
import time

BAUDS = (1200, 2400, 4800, 8000)
PRET = 0x52                     # « R »
FIN = 27                        # ÉCHAP : termine le programme du X-07
RETABLIR = "POKE &HA3,&H0A:POKE &HA4,&HC9"     # rend le clavier au X-07 (après $EE1F)


def mise_en_route(baud=4800):
    """Ligne à taper sur le X-07 pour --charger."""
    return 'INIT#5,"COM:",%d,"B":EXEC &HEE1F' % baud


def programme(baud=4800):
    return "\n".join([
        "10 REM TEST ECHO SERIE",
        '20 DEFINT V:INIT#1,"COM:",%d,"B":OUT#1,82' % baud,
        "30 V=INP(#1):OUT#1,V",
        "40 IF V=13 THEN PRINT",
        "50 IF V<32 THEN 60",
        "55 PRINT CHR$(V);",
        "60 IF V=27 THEN 70",
        "65 GOTO 30",
        '70 PRINT:PRINT "FIN DU TEST"',
    ]) + "\n"


def sequence():
    """Les octets envoyés : un texte, puis 0..255 sauf ÉCHAP, puis ÉCHAP."""
    texte = b"BONJOUR X-07\r"
    return [("texte", b) for b in texte] + \
           [("valeurs 00..FF", b) for b in range(256) if b != FIN] + \
           [("fin", FIN)]


class Testeur:
    """Protocole côté PC, piloté par les octets reçus du X-07 (envoi-attente)."""

    def __init__(self):
        self.seq = sequence()
        self.i = -1                 # -1 : on attend le « R »
        self.avant = bytearray()    # octets reçus avant le « R »
        self.erreurs = []           # (phase, envoyé, reçu)
        self.fini = False

    def a_envoyer(self):
        return bytes([self.seq[self.i][1]]) if 0 <= self.i < len(self.seq) else b""

    def on_byte(self, b):
        """Traite un octet reçu ; renvoie l'octet suivant à envoyer."""
        if self.fini:
            return b""
        if self.i < 0:
            if b != PRET:
                self.avant.append(b)
                return b""
            self.i = 0
            return self.a_envoyer()
        phase, attendu = self.seq[self.i]
        if b != attendu:
            self.erreurs.append((phase, attendu, b))
        self.i += 1
        if self.i >= len(self.seq):
            self.fini = True
            return b""
        return self.a_envoyer()

    def progression(self):
        return max(self.i, 0), len(self.seq)


def bilan(t):
    print()
    if t.avant:
        print("Octets reçus avant le « R » :", " ".join("%02X" % b for b in t.avant[:16]))
    if t.i < 0:
        print("ECHEC : le X-07 n'a jamais envoyé « R » (52).")
        if t.avant:
            print(" Des octets arrivent, mais pas « 52 » : l'inversion de TXD/RXD n'est")
            print(" probablement pas active (FT_Prog), ou la vitesse diffère.")
        else:
            print(" Rien n'arrive : vérifiez SP-4 -> RXD, la masse, CTS (SP-6) au +5 V,")
            print(" et que le programme ECHO a bien été lancé par RUN.")
        return False
    if not t.fini:
        fait, total = t.progression()
        print("ECHEC : plus de réponse après %d octets sur %d." % (fait, total))
        if fait == 0:
            print(" Le X-07 émet (« R » reçu) mais ne reçoit pas : vérifiez TXD -> SP-5.")
        return False
    if t.erreurs:
        print("ECHEC : %d écho(s) faux sur %d octets :" % (len(t.erreurs), len(t.seq)))
        for phase, e, r in t.erreurs[:10]:
            print("  %-15s envoyé %02X, reçu %02X" % (phase, e, r))
        return False
    print("OK : %d octets envoyés et renvoyés à l'identique." % len(t.seq))
    print("La liaison fonctionne dans les deux sens.")
    return True


def envoyer_lignes(p, lignes, pause_car, pause_ligne):
    """Envoie des lignes au BASIC du X-07, comme tapées au clavier."""
    for ligne in lignes:
        for b in (ligne + "\r").encode("ascii"):
            p.write(bytes([b]))
            p.flush()
            time.sleep(pause_car)
        time.sleep(pause_ligne)


def test_port(url, baud, attente, delai, charger=False, pause_car=0.02, pause_ligne=0.5):
    try:
        import serial
    except ImportError:
        sys.exit("Module pyserial absent : pip install pyserial")
    t = Testeur()
    with serial.serial_for_url(url, baudrate=baud, bytesize=8, parity="N", stopbits=2,
                               timeout=0.1, rtscts=False, dsrdtr=False, xonxoff=False) as p:
        p.reset_input_buffer()
        print("Port %s, %d bauds 8N2." % (url, baud))
        if charger:
            print("Sur le X-07, tapez NEW, puis :  %s" % mise_en_route(baud))
            input("puis appuyez sur Entrée ici... ")
            lignes = programme(baud).splitlines()
            print("Envoi du programme ECHO (%d lignes), puis RUN..." % len(lignes))
            envoyer_lignes(p, lignes, pause_car, pause_ligne)
            p.reset_input_buffer()
            envoyer_lignes(p, ["RUN"], pause_car, 0)
        else:
            print("Tapez RUN sur le X-07 (ECHO)...")
        try:
            return _boucle(p, t, attente, delai)
        finally:
            if charger:
                if not t.fini:                 # termine ECHO s'il attend encore
                    p.write(bytes([FIN]))
                    time.sleep(1)
                envoyer_lignes(p, [RETABLIR], pause_car, pause_ligne)
                print("Clavier du X-07 rétabli.")


def _boucle(p, t, attente, delai):
    limite = time.monotonic() + attente
    while not t.fini and time.monotonic() < limite:
        data = p.read(64)
        if not data:
            continue
        for b in data:
            out = t.on_byte(b)
            if out:
                p.write(out)
        if t.i >= 0:
            limite = time.monotonic() + delai      # après le « R » : délai par octet
            fait, total = t.progression()
            print("\r  %d / %d octets" % (fait, total), end="", flush=True)
    return bilan(t)


def test_emule_charge(baud):
    """--charger avec le X-07 émulé : vraie ROM, vrai éditeur, UART émulée."""
    sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "assembleur"))
    from x07asm import emu
    from x07asm.sim import SimError, REAL
    t = Testeur()
    m = emu.boot(16, real_display=True)
    m.interactive = True
    m.traps[0xEBFF] = lambda c: REAL              # éditeur de la ROM
    m.traps[0xEBF2] = lambda c: REAL
    m.traps.pop(0xC8C5, None)                     # attente d'une touche par $00A2
    m.byte_steps = max(200, int(1500 * 4800 / baud))

    def aucune_touche():
        raise SimError("le X-07 attend une touche")
    m._wait_key = aucune_touche
    m.keys = list("NEW\r" + mise_en_route(baud) + "\r")
    m.pc = 0xEBFF

    def run(n):
        try:
            m.run(m.steps + n)
        except SimError as e:
            if "limite" not in str(e):
                raise

    def lignes(ls):
        for ligne in ls:
            for b in (ligne + "\r").encode("ascii"):
                m.serial_in.append(b)
                run(m.byte_steps)
            run(60_000)

    print("X-07 émulé (vraie ROM), %d bauds, programme envoyé par la prise série..." % baud)
    run(3_000_000)
    lignes(programme(baud).splitlines())
    m.on_serial = lambda b: m.serial_in.extend(t.on_byte(b))
    lignes(["RUN"])
    for _ in range(400):
        if t.fini:
            break
        run(500_000)
    m.on_serial = None
    run(3_000_000)                                # retour à l'invite, qui lit la prise série
    lignes([RETABLIR])
    ok = bilan(t)
    clavier = m.rd16(0x00A3) == 0xC90A
    print("Clavier du X-07 %s." % ("rétabli" if clavier else "NON rétabli"))
    return ok and clavier


def test_emule(baud):
    sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "assembleur"))
    from x07asm import emu
    t = Testeur()

    def setup(m):
        m.byte_steps = max(200, int(1500 * 4800 / baud))
        m.on_serial = lambda b: m.serial_in.extend(t.on_byte(b))

    print("X-07 émulé (vraie ROM), %d bauds..." % baud)
    ecran, _ = emu.run_basic(programme(baud), setup=setup, max_steps=400_000_000)
    print(ecran)
    return bilan(t)


def main():
    ap = argparse.ArgumentParser(description="Test d'écho PC <-> Canon X-07")
    ap.add_argument("-p", "--port", help="port série (COM5, /dev/ttyUSB0)")
    ap.add_argument("-b", "--baud", type=int, default=4800, choices=BAUDS)
    ap.add_argument("--attente", type=float, default=120,
                    help="temps laissé pour taper RUN sur le X-07, en secondes (défaut 120)")
    ap.add_argument("--delai", type=float, default=3,
                    help="attente maximale d'un écho, en secondes (défaut 3)")
    ap.add_argument("--programme", action="store_true",
                    help="afficher le programme à taper sur le X-07 et quitter")
    ap.add_argument("--emu", action="store_true", help="essai avec le X-07 émulé, sans câble")
    ap.add_argument("--charger", action="store_true",
                    help="le PC envoie le programme ECHO et le lance (sur le X-07 : NEW, "
                         "puis INIT#5,\"COM:\",4800,\"B\":EXEC &HEE1F)")
    ap.add_argument("--pause-car", type=float, default=0.02,
                    help="--charger : pause après chaque caractère, en s (défaut 0,02)")
    ap.add_argument("--pause-ligne", type=float, default=0.5,
                    help="--charger : pause après chaque ligne, en s (défaut 0,5)")
    a = ap.parse_args()
    if a.programme:
        print(programme(a.baud), end="")
        return 0
    if a.emu:
        ok = test_emule_charge(a.baud) if a.charger else test_emule(a.baud)
        return 0 if ok else 1
    if not a.port:
        ap.error("indiquez le port avec -p (ou --emu, ou --programme)")
    try:
        ok = test_port(a.port, a.baud, a.attente, a.delai, a.charger,
                       a.pause_car, a.pause_ligne)
    except KeyboardInterrupt:
        print("\ninterrompu")
        return 2
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
