"""Interface en ligne de commande : x07asm asm|dis|sym ..."""
import argparse
import os
import sys

from . import asm as asmmod
from . import dis as dismod
from . import formats
from . import x07sym


def _num(s):
    s = s.strip()
    for p in ("$", "&H", "&h", "0x", "0X"):
        if s.startswith(p):
            return int(s[len(p):], 16)
    if s[-1:] in "hH":
        return int(s[:-1], 16)
    return int(s, 16)          # par défaut : hexadécimal


def cmd_asm(args):
    defines = {}
    for d in args.define or []:
        k, _, v = d.partition("=")
        defines[k] = int(v, 0) if v else 1
    a = asmmod.Assembler(x07=not args.no_x07, defines=defines)
    try:
        mem = a.assemble_file(args.source)
    except asmmod.AsmError as e:
        print("erreur : %s" % e, file=sys.stderr)
        return 1
    for e in a.errors:
        print("erreur : %s" % e, file=sys.stderr)
    if a.errors:
        print("%d erreur(s), rien n'a été écrit." % len(a.errors), file=sys.stderr)
        return 1
    if not mem:
        print("aucun octet produit.", file=sys.stderr)
        return 1

    base = args.output or os.path.splitext(args.source)[0]
    if base.endswith(".bin"):
        base = base[:-4]
    wanted = {f for f in (args.format or "bin,lst").split(",") if f}
    written = []

    def write(ext, data, mode="w"):
        path = base + ext
        with open(path, mode) as f:
            f.write(data)
        written.append(path)

    if "bin" in wanted:
        write(".bin", formats.to_bin(mem), "wb")
    if "hex" in wanted:
        write(".hex", formats.to_ihex(mem, a.entry))
    if "lst" in wanted:
        write(".lst", a.listing_text())
    if "txt" in wanted:
        write(".txt", formats.to_hexdump(mem))
    if "bas" in wanted:
        text, warns = formats.to_basic(mem, a.entry, os.path.basename(base))
        for w in warns:
            print("attention : %s" % w, file=sys.stderr)
        write(".bas", text)
    unknown = wanted - {"bin", "hex", "lst", "txt", "bas"}
    if unknown:
        print("format inconnu : %s" % ", ".join(sorted(unknown)), file=sys.stderr)
        return 1

    segs = formats.segments(mem)
    print("%d octets, %s ; lancement : EXEC &H%X" % (
        len(mem), ", ".join("$%04X-$%04X" % s for s in segs), a.entry))
    lo, hi = min(mem), max(mem)
    if lo < formats.BASIC_START:
        print("attention : le code commence avant $0553 (zone système du X-07).",
              file=sys.stderr)
    if 0x8000 <= hi and lo < 0xB000:
        print("attention : le code dépasse $7FFF (RAM vidéo X-720 / ROM).", file=sys.stderr)
    for p in written:
        print("  ->", p)
    return 0


def _load_labels(path):
    labels = {}
    with open(path, encoding="utf-8", errors="replace") as f:
        for line in f:
            line = line.split(";")[0].strip()
            if not line:
                continue
            parts = line.replace("=", " ").replace(":", " ").split()
            if len(parts) >= 3 and parts[1].upper() == "EQU":
                parts = [parts[0], parts[2]]
            if len(parts) >= 2:
                labels[_num(parts[1])] = parts[0]
    return labels


def cmd_dis(args):
    try:
        mem = formats.load_any(args.input, _num(args.org) if args.org else None,
                               10 if args.decimal else 16)
    except (OSError, ValueError) as e:
        print("erreur : %s" % e, file=sys.stderr)
        return 1
    if not mem:
        print("aucun octet lu.", file=sys.stderr)
        return 1
    if args.start or args.end:
        lo = _num(args.start) if args.start else 0
        hi = _num(args.end) if args.end else 0xFFFF
        mem = {a: b for a, b in mem.items() if lo <= a <= hi}
    data = [dismod.parse_range(r) for r in (args.data or [])]
    entries = [_num(e) for e in (args.entry or [])] or None
    labels = _load_labels(args.labels) if args.labels else None
    d = dismod.Disassembler(mem, x07=not args.no_x07, rst8_inline=not args.no_rst8,
                            labels=labels)
    d.analyse(entries, args.trace, data)
    text = d.source(listing=args.listing, title=os.path.basename(args.input))
    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(text)
        print("%d octets désassemblés -> %s" % (len(mem), args.output))
    else:
        sys.stdout.write(text)
    return 0


def cmd_sym(args):
    q = (args.filter or "").upper()
    groups = (("Routines ROM", x07sym.ROUTINES, "$%04X"),
              ("Variables système", x07sym.VARIABLES, "$%04X"),
              ("Ports E/S", x07sym.PORTS, "$%02X"))
    for title, table, fmt in groups:
        rows = [(n, v, c) for n, (v, c) in sorted(table.items(), key=lambda x: x[1][0])
                if not q or q in n or q in c.upper() or q in (fmt % v)]
        if rows:
            print("; " + title)
            for n, v, c in rows:
                print("%-12s EQU  %-6s ; %s" % (n, fmt % v, c))
            print()
    rows = [(n, v) for n, v in sorted(x07sym.T6834.items(), key=lambda x: x[1])
            if not q or q in n]
    if rows:
        print("; Commandes du T6834")
        for n, v in rows:
            print("%-12s EQU  $%02X" % (n, v))
    return 0


RAM_TOP = {8: 0x1FFF, 16: 0x3FFF, 24: 0x5FFF}


def build_basic(path, org="auto", ram=8, **opts):
    """Compile un source BASIC puis l'assemble.
    Renvoie (texte assembleur, assembleur, mémoire, compilateur)."""
    from . import basic
    with open(path, "rb") as f:
        raw = f.read()
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        text = raw.decode("latin-1")
    name = os.path.splitext(os.path.basename(path))[0].upper()

    def once(o):
        src, comp = basic.compile_basic(text, name, o, **opts)
        a = asmmod.Assembler()
        mem = a.assemble_text(src, name + ".asm")
        if a.errors:
            raise basic.CompileError("erreur d'assemblage interne : %s" % a.errors[0])
        return src, a, mem, comp

    top = RAM_TOP[ram]
    if org == "auto":
        src, a, mem, comp = once(0x1000)
        size = a.symbols["VARS_END"] - 0x1000
        o = (top + 1 - size) & ~0xF
        if o < 0x0600:
            raise basic.CompileError(
                "programme trop gros pour %d Ko (%d octets avec les variables)" % (ram, size))
        return once(o)
    result = once(_num(org))
    end = result[1].symbols["VARS_END"]
    if end - 1 > top:
        print("attention : le programme et ses variables finissent en $%04X, "
              "au-delà de la RAM de %d Ko ($%04X)." % (end - 1, ram, top), file=sys.stderr)
    return result


def cmd_basic(args):
    from . import basic
    try:
        src, a, mem, comp = build_basic(
            args.source, args.org, args.ram, strcap=args.strlen, brk=not args.no_break,
            debug=args.debug, bounds=not args.no_bounds, default=args.default)
    except basic.CompileError as e:
        print("erreur : %s" % e, file=sys.stderr)
        return 1
    for w in comp.warnings:
        print("attention : %s" % w, file=sys.stderr)
    base = args.output or os.path.splitext(args.source)[0]
    wanted = {f for f in (args.format or "asm,bin").split(",") if f}
    unknown = wanted - {"asm", "bin", "hex", "lst", "txt", "bas"}
    if unknown:
        print("format inconnu : %s" % ", ".join(sorted(unknown)), file=sys.stderr)
        return 1
    written = []

    def write(path, data, mode="w"):
        with open(path, mode, **({} if "b" in mode else {"encoding": "utf-8"})) as f:
            f.write(data)
        written.append(path)

    if "asm" in wanted:
        write(base + ".asm", src)
    if "bin" in wanted:
        write(base + ".bin", formats.to_bin(mem), "wb")
    if "hex" in wanted:
        write(base + ".hex", formats.to_ihex(mem, a.entry))
    if "lst" in wanted:
        write(base + ".lst", a.listing_text())
    if "txt" in wanted:
        write(base + ".txt", formats.to_hexdump(mem))
    if "bas" in wanted:
        text, warns = formats.to_basic(mem, a.entry, os.path.basename(base))
        for w in warns:
            print("attention : %s" % w, file=sys.stderr)
        write(base + "_chargeur.bas", text)
    org, end = a.entry, a.symbols["VARS_END"]
    print("%d octets de code, %d avec les variables : $%04X-$%04X" % (
        len(mem), end - org, org, end - 1))
    print("sur le X-07 : CLEAR 50,&H%X  puis  EXEC &H%X" % (org - 1, org))
    for p in written:
        print("  ->", p)
    return 0


def _exec(m, mem, entry, max_steps):
    """Comme CLEAR 50,&H(org-1) puis EXEC &Hentry sur la machine démarrée."""
    from . import sim
    for a, b in mem.items():
        m.mem[a] = b
    m.cache.clear()
    m.strict = True
    org = min(mem)
    if org >= 0x0600:
        top = org - 1
        for adr, v in ((0x01DF, top), (0x0204, top), (0x01DD, top - 50)):
            m.mem[adr], m.mem[adr + 1] = v & 0xFF, v >> 8
        m.sp = top - 50
    m.push(sim.EXIT)
    m.pc = entry
    m.run(max_steps)
    return 0


def cmd_run(args):
    from . import basic, sim, emu
    try:
        if args.source.lower().endswith(".asm"):
            a = asmmod.Assembler()
            mem = a.assemble_file(args.source)
            if a.errors:
                raise basic.CompileError(str(a.errors[0]))
        else:
            _, a, mem, comp = build_basic(args.source, args.org, args.ram,
                                          strcap=args.strlen, debug=args.debug,
                                          default=args.default)
            for w in comp.warnings:
                print("attention : %s" % w, file=sys.stderr)
    except (basic.CompileError, asmmod.AsmError) as e:
        print("erreur : %s" % e, file=sys.stderr)
        return 1
    keys = args.keys.encode().decode("unicode_escape") if args.keys else ""
    input_fn = None
    if not args.input and sys.stdin.isatty():
        def input_fn():
            sys.stdout.flush()
            line = sys.stdin.readline()
            return line.rstrip("\r\n") if line else None

    def echo(ch):
        sys.stdout.write(ch)
        sys.stdout.flush()

    m = None
    try:
        m = emu.boot(args.ram)
        m.keys, m.lines, m.echo, m.input_fn = list(keys), list(args.input or []), echo, input_fn
        status = _exec(m, mem, a.entry, args.max)
    except sim.SimError as e:
        print("\n[simulation arrêtée : %s]" % e, file=sys.stderr)
        status = 2
    print()
    print("Écran du X-07 à la fin :")
    print(m.screen_text())
    print("(%d instructions Z80 exécutées)" % m.steps)
    return status


def cmd_emu(args):
    """Exécute un programme avec le vrai BASIC de la ROM (émulation)."""
    from . import emu, sim
    try:
        with open(args.source, "rb") as f:
            raw = f.read()
        try:
            src = raw.decode("utf-8")
        except UnicodeDecodeError:
            src = raw.decode("latin-1")
        keys = args.keys.encode().decode("unicode_escape") if args.keys else ""
        out, m = emu.run_basic(src, inputs=args.input or [], keys=keys, ram=args.ram,
                               max_steps=args.max)
    except sim.SimError as e:
        print("[émulation impossible : %s]" % e, file=sys.stderr)
        return 2
    sys.stdout.write(out)
    status = 0
    if m.error:
        print("\n[émulation arrêtée : %s]" % m.error, file=sys.stderr)
        status = 2
    print()
    print("Écran du X-07 à la fin :")
    print(m.screen_text())
    print("(%d instructions Z80 exécutées par la ROM)" % m.steps)
    return status


def main(argv=None):
    p = argparse.ArgumentParser(
        prog="x07asm",
        description="Assembleur / désassembleur Z80 (NSC800) pour le Canon X-07.")
    sub = p.add_subparsers(dest="cmd", required=True)

    a = sub.add_parser("asm", help="assembler un source")
    a.add_argument("source")
    a.add_argument("-o", "--output", help="nom de base des fichiers produits")
    a.add_argument("-f", "--format", default=None,
                   help="formats séparés par des virgules : bin,hex,lst,txt,bas "
                        "(défaut : bin,lst)")
    a.add_argument("-D", "--define", action="append", metavar="NOM=VAL",
                   help="définit un symbole")
    a.add_argument("--no-x07", action="store_true",
                   help="sans les symboles prédéfinis du X-07")
    a.set_defaults(func=cmd_asm)

    d = sub.add_parser("dis", help="désassembler")
    d.add_argument("input", help=".bin, .hex (Intel), .bas/.txt (DATA ou vidage)")
    d.add_argument("-o", "--output", help="fichier source produit (défaut : écran)")
    d.add_argument("--org", help="adresse de chargement d'un binaire (hexa)")
    d.add_argument("--start", help="première adresse à désassembler (hexa)")
    d.add_argument("--end", help="dernière adresse à désassembler (hexa)")
    d.add_argument("-e", "--entry", action="append",
                   help="point d'entrée (hexa), répétable ; implique de suivre le flot")
    d.add_argument("-t", "--trace", action="store_true",
                   help="suit le flot d'exécution ; le reste devient des données")
    d.add_argument("--data", action="append", metavar="DEBUT-FIN[:b|w|t]",
                   help="zone de données : b octets, w mots, t texte (répétable)")
    d.add_argument("-l", "--listing", action="store_true",
                   help="affiche adresses et octets (non réassemblable)")
    d.add_argument("--labels", help="fichier d'étiquettes (NOM EQU $adr)")
    d.add_argument("--decimal", action="store_true",
                   help="les DATA du texte d'entrée sont en décimal")
    d.add_argument("--no-x07", action="store_true", help="sans les symboles du X-07")
    d.add_argument("--no-rst8", action="store_true",
                   help="ne traite pas l'octet qui suit RST 08 comme une donnée")
    d.set_defaults(func=cmd_dis)

    s = sub.add_parser("sym", help="liste les symboles du X-07")
    s.add_argument("filter", nargs="?", help="filtre (nom, texte ou valeur)")
    s.set_defaults(func=cmd_sym)

    b = sub.add_parser("basic", help="compiler un programme BASIC")
    b.add_argument("source")
    b.add_argument("-o", "--output", help="nom de base des fichiers produits")
    b.add_argument("-f", "--format", default=None,
                   help="asm,bin,hex,lst,txt,bas (défaut : asm,bin) ; "
                        "bas produit NOM_chargeur.bas")
    b.add_argument("--org", default="auto",
                   help="adresse d'implantation (hexa) ou auto : en haut de la RAM")
    b.add_argument("--ram", type=int, choices=(8, 16, 24), default=8,
                   help="mémoire du X-07 en Ko (défaut : 8)")
    b.add_argument("--strlen", type=int, default=80,
                   help="longueur maximale des chaînes (défaut : 80)")
    b.add_argument("--no-break", action="store_true",
                   help="pas de test de la touche BREAK dans les boucles")
    b.add_argument("--no-bounds", action="store_true",
                   help="pas de contrôle des indices de tableaux")
    b.add_argument("--debug", action="store_true",
                   help="les erreurs indiquent le numéro de ligne")
    b.add_argument("--default", choices=("d", "f", "i"), default="d",
                   help="type des variables sans suffixe : d double (X-07), f simple, i entier")
    b.set_defaults(func=cmd_basic)

    r = sub.add_parser("run", help="exécuter un programme sur le simulateur (PC)")
    r.add_argument("source", help="programme BASIC (.bas) ou source assembleur (.asm)")
    r.add_argument("-k", "--keys", help="touches pour INKEY$ (ex. \"AB\\r\")")
    r.add_argument("-i", "--input", action="append",
                   help="ligne tapée pour INPUT (répétable)")
    r.add_argument("--max", type=int, default=20_000_000, help="instructions au plus")
    r.add_argument("--org", default="auto")
    r.add_argument("--ram", type=int, choices=(8, 16, 24), default=8)
    r.add_argument("--strlen", type=int, default=80)
    r.add_argument("--debug", action="store_true")
    r.add_argument("--default", choices=("d", "f", "i"), default="d")
    r.set_defaults(func=cmd_run)

    e = sub.add_parser("emu", help="exécuter un programme BASIC avec la vraie ROM (émulation)")
    e.add_argument("source", help="programme BASIC (.bas)")
    e.add_argument("-k", "--keys", help="touches pour INKEY$")
    e.add_argument("-i", "--input", action="append", help="ligne tapée pour INPUT (répétable)")
    e.add_argument("--ram", type=int, choices=(8, 16, 24), default=16)
    e.add_argument("--max", type=int, default=50_000_000, help="instructions au plus")
    e.set_defaults(func=cmd_emu)

    args = p.parse_args(argv)
    if args.cmd == "dis" and args.entry:
        args.trace = True
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
