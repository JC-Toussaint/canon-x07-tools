"""Vitesse comparée du C (SDCC) et du Turbo Pascal compilés pour le X-07.

    python3 exemples/bench/mesure.py

Chaque programme existe en deux versions, NOM.c et NOM.pas, qui donnent le
même résultat.  Les deux sont compilés, puis exécutés par la ROM du X-07
(émulateur) ; on compte les instructions Z80, environ 2 microsecondes chacune
sur la machine.  Le C demande SDCC (sudo apt install sdcc).
"""
import os
import sys

ICI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(os.path.dirname(ICI)))

from x07asm import cli, emu                  # noqa: E402

PROGRAMMES = ("crible", "fib", "prodi", "racines")


def mesure(path, ram=16):
    """(instructions exécutées, octets avec les variables, affichage)."""
    if path.endswith(".c"):
        p = cli.build_c(path, "auto", ram)
        mem, entry, size = p.mem, p.entry, p.end + 1 - p.entry
    else:
        _, a, mem, comp = cli.build_basic(path, "auto", ram)
        entry, size = a.entry, a.symbols["VARS_END"] - a.entry
    m = emu.prepare_binary(mem, entry, "", [], ram)
    m.run(400_000_000)
    return m.steps, size, m.output().strip()


def main():
    print("%-8s %11s %11s %8s   %s" % ("", "C", "Pascal", "C plus", "octets C / Pascal"))
    print("%-8s %11s %11s %8s" % ("", "(instr.)", "(instr.)", "rapide"))
    for nom in PROGRAMMES:
        c, cs, co = mesure(os.path.join(ICI, nom + ".c"))
        p, ps, po = mesure(os.path.join(ICI, nom + ".pas"))
        print("%-8s %11d %11d %7.1fx   %5d / %5d   (%s | %s)" % (nom, c, p, p / c, cs, ps, co, po))
    print("environ 2 microsecondes par instruction sur la machine")


if __name__ == "__main__":
    main()
