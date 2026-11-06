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
LIB_MODULES = ("x07.c", "x07real.c", "x07rstr.c", "x07file.c", "x07ftok.c", "x07fsp.c")   # bibliothèque (x07.h)
FSET_RESERVED = 80     # sous les fichiers : FSET y écrit la zone des chaînes et sa pile


class CError(Exception):
    pass


class CProgram:
    def __init__(self, mem, entry, end, symbols, listing, warnings, variables=()):
        self.mem, self.entry, self.end = mem, entry, end      # end : dernier octet occupé
        self.symbols, self.listing, self.warnings = symbols, listing, warnings
        self.variables = list(variables)          # (nom, adresse, taille) des globales


def _windows_dirs():
    """Dossiers d'installation de SDCC sous Windows (l'installeur ne met pas
    toujours SDCC dans le PATH)."""
    out = []
    if os.environ.get("SDCC_HOME"):
        out.append(os.environ["SDCC_HOME"])
    for var in ("ProgramFiles", "ProgramFiles(x86)", "ProgramW6432"):
        if os.environ.get(var):
            out.append(os.path.join(os.environ[var], "SDCC"))
    return out


def tools():
    """Chemins de sdcc, sdasz80, sdldz80 et sdar ; CError si SDCC n'est pas installé."""
    names = ("sdcc", "sdasz80", "sdldz80", "sdar")
    found = [shutil.which(t) for t in names]
    if None in found:
        for d in _windows_dirs():
            alt = [shutil.which(t, path=os.path.join(d, "bin")) for t in names]
            if None not in alt:
                return alt
    if None in found:
        raise CError("SDCC n'est pas installé ou pas trouvé.\n"
                     "  Debian, Ubuntu, WSL : sudo apt install sdcc\n"
                     "  Windows : installeur de https://sdcc.sourceforge.net, puis "
                     "ajoutez C:\\Program Files\\SDCC\\bin au PATH (ou définissez "
                     "SDCC_HOME=C:\\Program Files\\SDCC)")
    return found


def _lib_dir(sdcc):
    """Bibliothèque z80.lib de SDCC (printf, multiplications...).
    Linux : <préfixe>/share/sdcc/lib/z80 ; Windows : <préfixe>\\lib\\z80."""
    prefix = os.path.dirname(os.path.dirname(os.path.abspath(sdcc)))
    for d in (SDCC_LIB, os.path.join(prefix, "share", "sdcc", "lib", "z80"),
              os.path.join(prefix, "lib", "z80")):
        if os.path.exists(os.path.join(d, "z80.lib")):
            return d
    raise CError("z80.lib de SDCC introuvable (cherchée sous %s)" % prefix)


_ENV = None


def _sdcc_env(sdcc):
    """Environnement des outils SDCC.  Sous Windows, sdcpp.exe (un GCC réduit)
    lance cc1.exe, rangé dans le dossier de SDCC ; il ne le trouve pas toujours
    (« cannot execute 'cc1' »), surtout si un autre GCC a défini GCC_EXEC_PREFIX.
    On lui indique alors le dossier de cc1.exe par COMPILER_PATH."""
    env = dict(os.environ)
    if os.name != "nt":
        return env
    env.pop("GCC_EXEC_PREFIX", None)
    prefix = os.path.dirname(os.path.dirname(os.path.abspath(sdcc)))
    dirs = []
    for sub in ("libexec", "bin", "lib"):
        for root, _, files in os.walk(os.path.join(prefix, sub)):
            if any(f.lower() in ("cc1.exe", "cc1") for f in files):
                dirs.append(root)
    if dirs:
        old = env.get("COMPILER_PATH")
        env["COMPILER_PATH"] = os.pathsep.join(dirs + ([old] if old else []))
    return env


def _run(cmd, cwd, what):
    p = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True,
                       encoding="utf-8", errors="replace", env=_ENV)
    out = (p.stdout + p.stderr).strip()
    if p.returncode != 0:
        raise CError("%s :\n%s" % (what, out or "échec (code %d)" % p.returncode))
    return out


def _warnings(text):
    return [l.strip() for l in text.splitlines() if "warning" in l.lower()]


def translate_qc(path):
    """Texte C d'un programme Quick C (.qc) ; CError avec fichier et ligne."""
    from . import qc
    with open(path, encoding="utf-8", errors="replace") as f:
        text = f.read()
    try:
        return qc.translate(text, os.path.abspath(path))
    except qc.QCError as e:
        raise CError("%s:%s: %s" % (os.path.basename(path), e.line, e))


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


DEBUG_FLAGS = ["--max-allocs-per-node", "1"]
# Pour le débogueur : avec l'allocation de registres complète, SDCC réutilise sur
# une ligne des calculs d'adresse de la précédente (après une copie de réel), et
# cette ligne n'a plus d'instruction à elle : ni point d'arrêt ni pas à pas.  Ce
# réglage les garde toutes ; le code est un peu plus gros (2 à 3 %) et le calcul
# sur entiers plus lent (jusqu'à 2 fois) : seulement pour debug et l'IDE.


def build_c(path, org="auto", top=None, min_org=0x0600, ram_top=None, debug=False):
    """Compile et relie un programme C.  org : adresse (entier) ou "auto"
    (en haut de la RAM, sous top).  Un programme qui ouvre des fichiers est
    placé sous leur zone (x07_fspace octets sous ram_top, dernier octet de la
    RAM), avec la marge qu'écrit FSET.  Rend un CProgram."""
    global _ENV
    sdcc, sdas, sdld, sdar = tools()
    libdir = _lib_dir(sdcc)
    _ENV = _sdcc_env(sdcc)
    src = os.path.abspath(path)
    name = os.path.splitext(os.path.basename(path))[0]
    tmp = tempfile.mkdtemp(prefix="x07c_")
    try:
        warns = []
        if path.lower().endswith(".qc"):          # Quick C : traduit en C, lignes gardées
            src = os.path.join(tmp, name + "_qc.c")
            with open(src, "w", encoding="utf-8") as f:
                f.write(translate_qc(path))
        _run([sdas, "-plosgff", "crt0.rel", os.path.join(LIB, "crt0.s")], tmp,
             "démarrage crt0.s")
        lib = [os.path.splitext(f)[0] for f in LIB_MODULES]
        for c, rel in [(os.path.join(LIB, m + ".c"), m + ".rel") for m in lib] + \
                [(src, name + ".rel")]:
            out = _run([sdcc, "-mz80", "-c"] + (["--debug"] if c == src else []) +
                       (DEBUG_FLAGS if debug and c == src else []) +
                       ["-I", LIB, "-I", os.path.dirname(os.path.abspath(path)), c, "-o", rel],
                       tmp,
                       "erreur de compilation" if c == src else
                       "bibliothèque %s" % os.path.basename(c))
            if c == src:
                warns += _warnings(out)
        # bibliothèque : l'éditeur de liens n'y prend que les modules utilisés
        _run([sdar, "-rc", "x07.lib"] + [m + ".rel" for m in lib], tmp, "bibliothèque x07.lib")
        # z80.lib copiée à côté : son chemin (« C:\Program Files\SDCC... » sous
        # Windows) peut contenir des espaces, que le script de l'éditeur de liens coupe
        shutil.copy(os.path.join(libdir, "z80.lib"), os.path.join(tmp, "z80.lib"))

        def link(at):
            with open(os.path.join(tmp, "prog.lk"), "w") as f:
                f.write("-mjwxiu\n-b _CODE=0x%04X\n-k .\n-l x07\n-l z80\nprog.ihx\n"
                        "crt0.rel\n%s.rel\n-e\n" % (at, name))
            out = _run([sdld, "-f", "prog.lk"], tmp, "édition de liens")
            if re.search(r"\?ASlink-Warning-Undefined", out):
                raise CError("édition de liens :\n%s" % "\n".join(
                    l for l in out.splitlines() if "ASlink >>" not in l))
            syms = _read_map(os.path.join(tmp, "prog.map"))
            end = syms["s__HEAP_END"] + syms.get("l__HEAP_END", 0)
            return syms, end

        def image():
            with open(os.path.join(tmp, "prog.ihx")) as f:
                mem = formats.from_ihex(f.read())
            return mem[0] if isinstance(mem, tuple) else mem

        syms, end = link(0x1000)
        file_space = 0
        if "_f_open" in syms:                     # fichiers en RAM : zone en haut de la RAM
            mem = image()
            a = syms["_x07_fspace"]
            file_space = mem.get(a, 0) | mem.get(a + 1, 0) << 8
            if ram_top is not None:
                below = ram_top - file_space - 1 - FSET_RESERVED
                top = below if top is None else min(top, below)
        if org == "auto":
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
                         "RAM libre ($%04X%s)" % (end - 1, top, ", sous les %d octets des "
                                                  "fichiers" % file_space if file_space else ""))
        mem = image()
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
        prog = CProgram(mem, at, end - 1, symbols, listing, warns, variables)
        prog.file_space = file_space
        adb = os.path.join(tmp, name + ".adb")      # --debug : place et type des variables
        prog.debug = None
        if os.path.exists(adb):
            from .cdebug import CDebugInfo
            with open(adb, encoding="latin-1") as f:
                prog.debug = CDebugInfo(f.read(), symbols, (at, end - 1))
        return prog
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
