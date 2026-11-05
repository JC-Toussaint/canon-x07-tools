"""Programmes C pour le Canon X-07, compilés par SDCC (sdcc -mz80).

Le démarrage (c/crt0.s) et la bibliothèque d'appui (c/x07.c, c/x07.h : écran,
clavier, graphismes, son par la ROM) sont compilés avec le programme.  Le code
est suivi de ses données ; comme pour le BASIC compilé, le programme est placé
par défaut en haut de la RAM (CLEAR 50,&H(org-1) puis EXEC &H(org)), et garde
la pile du BASIC, sous lui.

Symboles rendus : les noms C (main, compte...) et LN_n, adresse de la
première instruction de la ligne n du source (débogueur, IDE).
"""
import os
import re
import shutil
import subprocess
import tempfile

from . import formats

LIB = os.path.join(os.path.dirname(os.path.abspath(__file__)), "c")
SDCC_LIB = "/usr/share/sdcc/lib/z80"
LIB_MODULES = ("x07.c", "x07real.c")            # bibliothèque d'appui (x07.h)


class CError(Exception):
    pass


class CProgram:
    def __init__(self, mem, entry, end, symbols, listing, warnings, variables=()):
        self.mem, self.entry, self.end = mem, entry, end      # end : dernier octet occupé
        self.symbols, self.listing, self.warnings = symbols, listing, warnings
        self.variables = list(variables)          # (nom, adresse, taille) des globales


def tools():
    """Chemins de sdcc, sdasz80, sdldz80 et sdar ; CError si SDCC n'est pas installé."""
    found = [shutil.which(t) for t in ("sdcc", "sdasz80", "sdldz80", "sdar")]
    if None in found:
        raise CError("SDCC n'est pas installé (sous Debian, Ubuntu, WSL : "
                     "sudo apt install sdcc)")
    return found


def _lib_dir(sdcc):
    """Bibliothèque z80.lib de SDCC (printf, multiplications...)."""
    for d in (SDCC_LIB, os.path.join(os.path.dirname(os.path.dirname(sdcc)),
                                     "share", "sdcc", "lib", "z80")):
        if os.path.exists(os.path.join(d, "z80.lib")):
            return d
    raise CError("z80.lib de SDCC introuvable")


def _run(cmd, cwd, what):
    p = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    out = (p.stdout + p.stderr).strip()
    if p.returncode != 0:
        raise CError("%s :\n%s" % (what, out or "échec (code %d)" % p.returncode))
    return out


def _warnings(text):
    return [l.strip() for l in text.splitlines() if "warning" in l.lower()]


def _read_map(path):
    syms = {}
    with open(path, encoding="latin-1") as f:
        for line in f:
            m = re.match(r"\s+([0-9A-F]{8})\s+(\S+)", line)
            if m:
                syms.setdefault(m.group(2), int(m.group(1), 16))
    return syms


def _line_symbols(rst_text, source_name):
    """LN_n : adresse de la première instruction de la ligne n du source."""
    out, pending = {}, None
    for line in rst_text.splitlines():
        m = re.search(r";(.+?):(\d+): ", line)
        if m and os.path.basename(m.group(1)) == source_name:
            pending = int(m.group(2))
            continue
        a = re.match(r"\s+([0-9A-F]{6})\s", line)
        if a and pending is not None:
            out.setdefault("LN_%d" % pending, int(a.group(1), 16))
            pending = None
    return out


def _labels(rst_text):
    """Étiquettes du listing (statiques comprises) : {nom C: adresse} et
    variables [(nom, adresse, taille)] des zones de données (« .ds n »)."""
    labels, variables, area, last = {}, [], None, None
    for line in rst_text.splitlines():
        m = re.search(r"\.area\s+(\w+)", line)
        if m:
            area, last = m.group(1), None
            continue
        m = re.match(r"\s+([0-9A-F]{6})\s+\d+\s+_(\w+)::?\s*$", line)
        if m:
            last = (m.group(2), int(m.group(1), 16))
            labels.setdefault(last[0], last[1])
            continue
        m = re.search(r"\.ds\s+(\d+)", line)
        if m and last and area in ("_DATA", "_INITIALIZED"):
            variables.append((last[0], last[1], int(m.group(1))))
            last = None
    return labels, variables


def build_c(path, org="auto", top=None, min_org=0x0600):
    """Compile et relie un programme C.  org : adresse (entier) ou "auto"
    (en haut de la RAM, sous top).  Rend un CProgram."""
    sdcc, sdas, sdld, sdar = tools()
    libdir = _lib_dir(sdcc)
    src = os.path.abspath(path)
    name = os.path.splitext(os.path.basename(path))[0]
    tmp = tempfile.mkdtemp(prefix="x07c_")
    try:
        warns = []
        _run([sdas, "-plosgff", "crt0.rel", os.path.join(LIB, "crt0.s")], tmp,
             "démarrage crt0.s")
        lib = [os.path.splitext(f)[0] for f in LIB_MODULES]
        for c, rel in [(os.path.join(LIB, m + ".c"), m + ".rel") for m in lib] + \
                [(src, name + ".rel")]:
            out = _run([sdcc, "-mz80", "-c", "-I", LIB, c, "-o", rel], tmp,
                       "erreur de compilation" if c == src else
                       "bibliothèque %s" % os.path.basename(c))
            if c == src:
                warns += _warnings(out)
        # bibliothèque : l'éditeur de liens n'y prend que les modules utilisés
        _run([sdar, "-rc", "x07.lib"] + [m + ".rel" for m in lib], tmp, "bibliothèque x07.lib")

        def link(at):
            with open(os.path.join(tmp, "prog.lk"), "w") as f:
                f.write("-mjwxiu\n-b _CODE=0x%04X\n-k .\n-l x07\n-k %s\n-l z80\nprog.ihx\n"
                        "crt0.rel\n%s.rel\n-e\n" % (at, libdir, name))
            out = _run([sdld, "-f", "prog.lk"], tmp, "édition de liens")
            if re.search(r"\?ASlink-Warning-Undefined", out):
                raise CError("édition de liens :\n%s" % "\n".join(
                    l for l in out.splitlines() if "ASlink >>" not in l))
            syms = _read_map(os.path.join(tmp, "prog.map"))
            end = syms["s__HEAP_END"] + syms.get("l__HEAP_END", 0)
            return syms, end

        if org == "auto":
            syms, end = link(0x1000)
            size = end - 0x1000
            at = ((top + 1) - size) & ~0xF
            if at < min_org:
                raise CError("programme trop gros pour la RAM (%d octets avec les données)"
                             % size)
        else:
            at = org
        syms, end = link(at)
        if top is not None and end - 1 > top:
            raise CError("le programme et ses données finissent en $%04X, au-delà de la "
                         "RAM libre ($%04X)" % (end - 1, top))
        with open(os.path.join(tmp, "prog.ihx")) as f:
            mem = formats.from_ihex(f.read())
        mem = mem[0] if isinstance(mem, tuple) else mem
        rst_path = os.path.join(tmp, name + ".rst")
        listing = ""
        if os.path.exists(rst_path):
            with open(rst_path, encoding="latin-1") as f:
                listing = f.read()
        symbols = {}
        for n, a in syms.items():
            if n.startswith(("s__", "l__")) or not n.startswith("_") or n.startswith("__"):
                continue
            symbols[n[1:]] = a                    # nom C : _main -> main
        labels, variables = _labels(listing)
        for n, a in labels.items():
            symbols.setdefault(n, a)
        symbols["VARS_END"] = end
        symbols.update(_line_symbols(listing, os.path.basename(path)))
        return CProgram(mem, at, end - 1, symbols, listing, warns, variables)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
