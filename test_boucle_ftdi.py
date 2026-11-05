#!/usr/bin/env python3
"""Test de bouclage (loopback) d'un module FTDI FT232R.

Montage : relier la broche TXD du module à sa broche RXD (et rien d'autre ;
X-07 débranché). Tout octet envoyé sur TXD doit revenir sur RXD.

Fonctionne sous Linux et sous Windows. Dépendance : pyserial
    pip install pyserial

Exemples :
    python test_boucle_ftdi.py                  # détecte le module FTDI
    python test_boucle_ftdi.py --liste          # liste les ports série
    python test_boucle_ftdi.py -p COM5          # Windows
    python test_boucle_ftdi.py -p /dev/ttyUSB0  # Linux
    python test_boucle_ftdi.py -p /dev/ttyUSB0 --toutes-vitesses
    python test_boucle_ftdi.py -p loop://       # auto-test du script, sans matériel
"""

import argparse
import os
import sys
import time

try:
    import serial
    from serial.tools import list_ports
except ImportError:
    sys.exit("Module pyserial absent : installez-le avec  pip install pyserial")

FTDI_VID = 0x0403
VITESSES = [300, 1200, 2400, 4800, 9600, 19200, 38400, 57600, 115200]


def lister_ports():
    ports = list(list_ports.comports())
    if not ports:
        print("Aucun port série détecté.")
    for p in ports:
        ids = f"{p.vid:04X}:{p.pid:04X}" if p.vid is not None else "----:----"
        print(f"  {p.device:<15} {ids}  {p.description}")
    return ports


def trouver_ftdi():
    candidats = [p for p in list_ports.comports() if p.vid == FTDI_VID]
    if len(candidats) == 1:
        return candidats[0].device
    if not candidats:
        print("Aucun module FTDI (VID 0403) détecté. Ports disponibles :")
    else:
        print("Plusieurs modules FTDI détectés, précisez-en un avec -p :")
    lister_ports()
    sys.exit(2)


def echanger(port, donnees, delai):
    """Envoie `donnees` et lit autant d'octets en retour (ou jusqu'au délai)."""
    port.reset_input_buffer()
    port.write(donnees)
    port.flush()
    recu = bytearray()
    fin = time.monotonic() + delai
    while len(recu) < len(donnees) and time.monotonic() < fin:
        morceau = port.read(len(donnees) - len(recu))
        if morceau:
            recu += morceau
    return bytes(recu)


def comparer(nom, envoye, recu):
    if recu == envoye:
        print(f"  [OK]    {nom} : {len(envoye)} octet(s) renvoyé(s) à l'identique")
        return True
    print(f"  [ECHEC] {nom} : {len(envoye)} envoyés, {len(recu)} reçus")
    if not recu:
        return False
    erreurs = [i for i in range(min(len(envoye), len(recu))) if envoye[i] != recu[i]]
    print(f"          {len(erreurs)} octet(s) différent(s) sur la partie reçue")
    for i in erreurs[:5]:
        print(f"          position {i} : envoyé {envoye[i]:02X}, reçu {recu[i]:02X}")
    return False


def tester_vitesse(url, vitesse, taille_bloc, nb_blocs):
    # Durée d'un octet en 8N1 : 10 bits. On laisse une large marge.
    delai = 1.0 + 10 * taille_bloc / vitesse * 3
    print(f"\n=== {url} à {vitesse} bauds (8N1, sans contrôle de flux) ===")
    with serial.serial_for_url(url, baudrate=vitesse, bytesize=8, parity="N",
                               stopbits=1, timeout=0.1, rtscts=False,
                               dsrdtr=False, xonxoff=False) as port:
        resultats = [
            comparer("octet 0x55 (01010101)", b"\x55", echanger(port, b"\x55", delai)),
            comparer("texte ASCII", b"Canon X-07\r\n", echanger(port, b"Canon X-07\r\n", delai)),
            comparer("les 256 valeurs 00..FF", bytes(range(256)),
                     echanger(port, bytes(range(256)), 1.0 + 2560 / vitesse * 3)),
        ]
        for n in range(nb_blocs):
            bloc = os.urandom(taille_bloc)
            resultats.append(comparer(f"bloc aléatoire {n + 1}/{nb_blocs}", bloc,
                                      echanger(port, bloc, delai)))
    return all(resultats)


def diagnostic():
    print("\nPistes :")
    print(" - Rien reçu : TXD et RXD ne sont pas reliés, ou le fil est sur la")
    print("   mauvaise broche (TXL/RXL sont des sorties de LED, pas des données).")
    print(" - Reçu mais faux : contact douteux, fil trop long, ou masse absente.")
    print(" - Le port ne s'ouvre pas : droits d'accès (Linux : groupe dialout),")
    print("   port déjà utilisé, ou pilote FTDI manquant (Windows).")


def main():
    ap = argparse.ArgumentParser(description="Test de bouclage TXD->RXD d'un FT232R")
    ap.add_argument("-p", "--port", help="port série (COM5, /dev/ttyUSB0, loop://)")
    ap.add_argument("-b", "--vitesse", type=int, default=4800,
                    help="vitesse en bauds (défaut : 4800)")
    ap.add_argument("--toutes-vitesses", action="store_true",
                    help=f"tester successivement {', '.join(map(str, VITESSES))} bauds")
    ap.add_argument("--blocs", type=int, default=5, help="nombre de blocs aléatoires")
    ap.add_argument("--taille", type=int, default=128, help="taille d'un bloc aléatoire")
    ap.add_argument("--liste", action="store_true", help="lister les ports série et quitter")
    args = ap.parse_args()

    if args.liste:
        lister_ports()
        return 0

    url = args.port or trouver_ftdi()
    vitesses = VITESSES if args.toutes_vitesses else [args.vitesse]
    print(f"Port : {url}  -- vérifiez que TXD est relié à RXD sur le module.")

    bilan = {}
    try:
        for v in vitesses:
            bilan[v] = tester_vitesse(url, v, args.taille, args.blocs)
    except serial.SerialException as e:
        print(f"\nImpossible d'utiliser le port {url} : {e}")
        diagnostic()
        return 2

    print("\n=== Bilan ===")
    for v, ok in bilan.items():
        print(f"  {v:>6} bauds : {'OK' if ok else 'ECHEC'}")
    if all(bilan.values()):
        print("\nLe module émet sur TXD et reçoit sur RXD correctement.")
        return 0
    diagnostic()
    return 1


if __name__ == "__main__":
    sys.exit(main())
