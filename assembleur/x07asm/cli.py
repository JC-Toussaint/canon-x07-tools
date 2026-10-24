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
    if args.md:
        sys.stdout.write(x07sym.markdown())
        return 0
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
RAM_RESERVED = 14       # haut de la RAM gardé par la ROM (MEMSIZ = $xFF1, signature 5A A5)


def free_top(ram):
    """Dernière adresse utilisable par un programme : MEMSIZ après démarrage."""
    return RAM_TOP[ram] - RAM_RESERVED


def read_text(path):
    with open(path, "rb") as f:
        raw = f.read()
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        return raw.decode("latin-1")


def read_basic(path):
    """Texte BASIC du X-07 du fichier ; un programme QuickBASIC (.qbas) est
    d'abord traduit (sinon la ROM répondrait SN Error dès DECLARE ou SUB)."""
    text = read_text(path)
    if path.lower().endswith(".qbas"):
        from . import basic, qbasic
        try:
            text, warns, _ = qbasic.translate(text)
        except qbasic.QBError as e:
            raise basic.CompileError("QuickBASIC : %s" % e)
        for w in warns:
            print("attention : %s" % w, file=sys.stderr)
    return text


def build_basic(path, org="auto", ram=8, direct=False, **opts):
    """Compile un source BASIC (ou QuickBASIC .qbas) puis l'assemble.
    direct : un .qbas est compilé directement (qbcomp : récursivité, tableaux
    par adresse), sans passer par le BASIC du X-07.
    Renvoie (texte assembleur, assembleur, mémoire, compilateur)."""
    from . import basic
    direct = direct and path.lower().endswith(".qbas")
    text = read_text(path) if direct else read_basic(path)
    name = os.path.splitext(os.path.basename(path))[0].upper()

    def once(o):
        if direct:
            from . import qbasic, qbcomp
            try:
                src, comp, warns = qbcomp.compile_qbasic(text, name, o, **opts)
            except qbasic.QBError as e:
                raise basic.CompileError("QuickBASIC : %s" % e)
            comp.warnings = list(dict.fromkeys(warns))
        else:
            src, comp = basic.compile_basic(text, name, o, **opts)
        a = asmmod.Assembler()
        mem = a.assemble_text(src, name + ".asm")
        if a.errors:
            raise basic.CompileError("erreur d'assemblage interne : %s" % a.errors[0])
        return src, a, mem, comp

    top = free_top(ram)
    if org == "auto":
        src, a, mem, comp = once(0x1000)
        if getattr(comp, "file_space", 0):
            # FSET n : la zone des fichiers est en haut de la RAM ; le code va dessous
            # (MEMSIZ après FSET n = haut de la RAM - n - 1)
            top = RAM_TOP[ram] - comp.file_space - 1
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
              "au-delà de la RAM libre de %d Ko ($%04X)." % (end - 1, ram, top), file=sys.stderr)
    return result


def cmd_basic(args):
    from . import basic
    try:
        src, a, mem, comp = build_basic(
            args.source, args.org, args.ram, strcap=args.strlen, brk=not args.no_break,
            debug=args.debug, bounds=not args.no_bounds, default=args.default,
            direct=args.direct)
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


def _show_screen(m, args):
    """Écran final : texte, points dans le terminal (--ecran), image (--png)."""
    print()
    print("Écran du X-07 à la fin :")
    if getattr(args, "ecran", False):
        print(m.lcd.braille())
    else:
        print(m.screen_text())
    if getattr(args, "png", None):
        m.lcd.png(args.png, zoom=args.zoom)
        print("image de l'écran ->", args.png)


def _window(title, zoom, target, muet=False):
    """Ouvre la fenêtre de l'afficheur et y fait tourner target(setup)."""
    from . import afficheur
    try:
        f = afficheur.Fenetre(title, zoom, muet)
    except Exception as e:                       # pas d'affichage graphique
        print("erreur : fenêtre impossible (%s). Essayez --ecran ou --png." % e,
              file=sys.stderr)
        return 1
    f.start(lambda: target(f.attach))
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
            _, a, mem, comp = build_basic(args.source, args.org, args.ram, direct=args.direct,
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

    if args.fenetre:
        def target(setup):
            m = emu.boot(args.ram, real_display=True)
            m.keys, m.lines = list(keys), list(args.input or [])
            setup(m)
            _exec(m, mem, a.entry, 10 ** 12)
        return _window("Canon X-07 : %s (compilé)" % os.path.basename(args.source),
                       args.zoom, target, args.muet)

    m = None
    try:
        machine = _memory_load(args)              # --memoire : X-07 rallumé avec sa RAM
        m = machine if machine is not None else emu.boot(args.ram)
        m.keys, m.lines, m.echo, m.input_fn = list(keys), list(args.input or []), echo, input_fn
        status = _exec(m, mem, a.entry, args.max)
    except (OSError, ValueError) as e:
        print("erreur : %s" % e, file=sys.stderr)
        return 1
    except sim.SimError as e:
        print("\n[simulation arrêtée : %s]" % e, file=sys.stderr)
        status = 2
    _show_screen(m, args)
    if getattr(args, "memoire", None) and status == 0:
        _memory_save(args, emu.power_off(m))
    print("(%d instructions Z80 exécutées)" % m.steps)
    return status


def _memory_load(args, real_display=False):
    """--memoire : rallume le X-07 avec la RAM enregistrée (None si absente)."""
    from . import emu
    path = getattr(args, "memoire", None)
    if not path or not os.path.exists(path):
        if path:
            print("%s : pas encore de mémoire enregistrée, démarrage à froid" % path)
        return None
    with open(path, "rb") as f:
        image = f.read()
    expected = emu.RAM_TOP[args.ram] + 1
    if len(image) != expected:
        raise ValueError("%s : mémoire de %d Ko, pas de %d Ko (option --ram)"
                         % (path, len(image) // 1024, args.ram))
    print("%s : X-07 rallumé avec sa mémoire (programmes et fichiers en RAM)" % path)
    return emu.power_on(image, args.ram, real_display=real_display)


def _memory_save(args, image):
    with open(args.memoire, "wb") as f:
        f.write(image)
    print("X-07 éteint par OFF : mémoire enregistrée -> %s" % args.memoire)


def cmd_emu(args):
    """Exécute un programme avec le vrai BASIC de la ROM (émulation)."""
    from . import emu, sim
    if args.charger and not args.fenetre:
        print("erreur : --charger s'utilise avec --fenetre", file=sys.stderr)
        return 1
    src = ""
    if args.source and args.source.lower().endswith((".asm", ".bin", ".rom")):
        # un programme machine, pas un texte BASIC à taper au X-07
        print("erreur : %s n'est pas un programme BASIC ; pour le lancer :\n"
              "  python3 x07asm.py run %s --fenetre\n"
              "  python3 x07asm.py emu --fenetre --charger %s   (puis EXEC &H...)\n"
              "  python3 x07asm.py ide %s"
              % ((args.source,) * 4), file=sys.stderr)
        return 1
    if args.source:
        from . import basic
        try:
            src = read_basic(args.source)
        except OSError as e:
            print("erreur : %s : %s" % (args.source, e.strerror), file=sys.stderr)
            return 1
        except basic.CompileError as e:
            print("erreur : %s" % e, file=sys.stderr)
            return 1
    elif not args.fenetre:
        print("erreur : indiquez un programme, ou --fenetre pour le BASIC en direct",
              file=sys.stderr)
        return 1
    keys = args.keys.encode().decode("unicode_escape") if args.keys else ""
    preload = None
    if args.charger:
        if not args.fenetre:
            print("erreur : --charger s'utilise avec --fenetre", file=sys.stderr)
            return 1
        from . import basic
        try:
            preload, entry, end = _load_program(argparse.Namespace(
                source=args.charger, org=args.org, entry=args.entry, ram=args.ram,
                direct=args.direct))
        except (basic.CompileError, asmmod.AsmError, ValueError, OSError) as e:
            print("erreur : %s" % e, file=sys.stderr)
            return 1
        org = min(preload)
        if org < 0x0600 or end > free_top(args.ram):
            print("erreur : %s occupe $%04X-$%04X, hors de la RAM libre de %d Ko "
                  "($0600-$%04X ; voir --ram, --org)"
                  % (args.charger, org, end, args.ram, free_top(args.ram)), file=sys.stderr)
            return 1
        print("%s : $%04X-$%04X (%d octets, variables comprises)."
              % (args.charger, org, end, end - org + 1))
        print("Dans la fenêtre, CLEAR 50,&H%X est tapé pour vous ; tapez ensuite :  EXEC &H%X"
              % (org - 1, entry))
    try:
        machine = _memory_load(args, real_display=args.fenetre)
    except (OSError, ValueError, sim.SimError) as e:
        print("erreur : %s" % e, file=sys.stderr)
        return 1
    if args.fenetre:
        name = os.path.basename(args.source or args.charger or "BASIC")

        def target(setup):
            def setup2(m):
                setup(m)
                m.real_off = bool(args.memoire)        # OFF éteint vraiment
            _, m = emu.run_basic(src, inputs=args.input or [], keys=keys, ram=args.ram,
                                 max_steps=10 ** 12, setup=setup2, live=True,
                                 preload=preload, machine=machine)
            if args.memoire:
                if getattr(m, "is_off", False):
                    _memory_save(args, bytes(m.mem[0:m.ram_top + 1]))
                    holder["f"].close_requested = True
                else:
                    print("mémoire non enregistrée : éteignez le X-07 par OFF avant de "
                          "fermer la fenêtre", file=sys.stderr)
        holder = {}
        from . import afficheur
        try:
            f = afficheur.Fenetre("Canon X-07 : %s" % name, args.zoom, args.muet)
        except Exception as e:
            print("erreur : fenêtre impossible (%s). Essayez --ecran ou --png." % e,
                  file=sys.stderr)
            return 1
        holder["f"] = f
        if args.memoire:
            print("Tapez OFF dans la fenêtre pour éteindre le X-07 et garder sa mémoire.")
        f.start(lambda: target(f.attach))
        return 0
    try:
        out, m = emu.run_basic(src, inputs=args.input or [], keys=keys, ram=args.ram,
                               max_steps=args.max, machine=machine)
    except sim.SimError as e:
        print("[émulation impossible : %s]" % e, file=sys.stderr)
        return 2
    sys.stdout.write(out)
    status = 0
    if m.error:
        print("\n[émulation arrêtée : %s]" % m.error, file=sys.stderr)
        status = 2
        if args.memoire:
            print("mémoire non enregistrée (programme interrompu)", file=sys.stderr)
    _show_screen(m, args)
    print("(%d instructions Z80 exécutées par la ROM)" % m.steps)
    if args.memoire and not m.error:
        _memory_save(args, emu.power_off(m))      # après l'écran : OFF l'efface
    return status


def _load_program(args):
    """Programme à envoyer : .bas ou .qbas (compilé), .hex, ou .bin avec --org.
    Renvoie (mémoire, entrée, dernière adresse occupée, variables comprises)."""
    src = args.source
    low = src.lower()
    if low.endswith((".bas", ".qbas")):
        _, a, mem, comp = build_basic(src, args.org or "auto", args.ram,
                                      direct=getattr(args, "direct", False))
        for w in comp.warnings:
            print("attention : %s" % w, file=sys.stderr)
        return mem, a.entry, a.symbols["VARS_END"] - 1
    if low.endswith(".asm"):
        a = asmmod.Assembler()
        mem = a.assemble_file(src)
        if a.errors:
            raise asmmod.AsmError(str(a.errors[0]))
        return mem, a.entry, max([max(mem)] + [v - 1 for k, v in a.symbols.items()
                                               if k == "VARS_END"])
    mem = formats.load_any(src, _num(args.org) if args.org and args.org != "auto" else None)
    if low.endswith((".bin", ".rom")) and not args.org:
        raise ValueError("pour un .bin, indiquez l'adresse de chargement : --org 1C00")
    entry = _num(args.entry) if args.entry else min(mem)
    return mem, entry, max(mem)


def cmd_recepteur(args):
    from . import serie
    text = serie.receiver_program(args.baud)
    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(text)
        print("->", args.output)
    else:
        sys.stdout.write(text)
    return 0


def cmd_send(args):
    from . import serie, basic, sim
    try:
        mem, entry, _ = _load_program(args)
    except (basic.CompileError, asmmod.AsmError, ValueError, OSError) as e:
        print("erreur : %s" % e, file=sys.stderr)
        return 1
    org, end = min(mem), max(mem)
    print("%d octets, $%04X-$%04X, lancement EXEC &H%X" % (end - org + 1, org, end, entry))
    if args.emu:
        out, snd, m = serie.send_emulated(mem, entry, args.baud, args.ram)
        sys.stdout.write(out)
        ok = snd.result == "ok" and all(m.mem[k] == v for k, v in mem.items())
        print("[émulation : %s, %d octets perdus par l'UART]" % (
            "transfert correct" if ok else "ÉCHEC (%s)" % (snd.result or m.error), m.overruns))
        return 0 if ok else 2
    if not args.port:
        print("erreur : indiquez le port série (--port /dev/ttyUSB0 ou COM3)", file=sys.stderr)
        return 1
    print("Sur le X-07 : CLEAR 50,&H%X  puis lancez RECEPTEUR (RUN)" % (org - 1))
    try:
        port = serie.SerialPort(args.port, args.baud)
    except (OSError, serie.TransferError) as e:
        print("erreur : port %s : %s" % (args.port, e), file=sys.stderr)
        return 1
    try:
        serie.send(port, mem, entry, timeout=args.timeout,
                   log=lambda *a, **k: print(*a, **k, flush=True))
    except serie.TransferError as e:
        print("\nerreur : %s" % e, file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        print("\ninterrompu", file=sys.stderr)
        return 2
    finally:
        port.close()
    print("Transfert correct. Sur le X-07 : EXEC &H%X" % entry)
    return 0


def load_for_debug(src, ram=16, org=None, entry=None, direct=False):
    """Programme prêt à déboguer : (mémoire, entrée, symboles, listing,
    zone du programme et de ses variables, avertissements).  Un .bas ou
    .qbas est compilé avec les numéros de ligne (option --debug)."""
    low = src.lower()
    listing, symbols, warns = [], {}, []
    if low.endswith((".bas", ".qbas")):
        _, a, mem, comp = build_basic(src, org or "auto", ram, debug=True, direct=direct)
        warns = comp.warnings
        start, listing, symbols = a.entry, a.listing, a.symbols
    elif low.endswith(".asm"):
        a = asmmod.Assembler()
        mem = a.assemble_file(src)
        if a.errors:
            raise asmmod.AsmError(str(a.errors[0]))
        start, listing, symbols = a.entry, a.listing, a.symbols
    else:
        if low.endswith((".bin", ".rom")) and not org:
            raise ValueError("pour un .bin, indiquez l'adresse de chargement : --org 3000")
        mem = formats.load_any(src, _num(org) if org else None)
        start = min(mem)
    if entry:
        start = _num(entry)
    prog_range = (min(mem), max(max(mem), symbols.get("VARS_END", 0) - 1))   # avec les variables
    return mem, start, symbols, listing, prog_range, warns


def cmd_debug(args):
    """Débogueur : le programme machine tourne dans l'émulateur, pas à pas."""
    from . import basic, debug, emu
    src = args.source
    try:
        mem, entry, symbols, listing, prog_range, warns = load_for_debug(
            src, args.ram, args.org, args.entry, args.direct)
        for w in warns:
            print("attention : %s" % w, file=sys.stderr)
    except (basic.CompileError, asmmod.AsmError, ValueError, OSError) as e:
        print("erreur : %s" % e, file=sys.stderr)
        return 1
    keys = args.keys.encode().decode("unicode_escape") if args.keys else ""
    script = [c for c in (args.commandes or "").split(";") if c.strip()]
    print("%s : $%04X-$%04X, entrée $%04X" % (src, prog_range[0], prog_range[1], entry))

    def make(real_display):
        m = emu.prepare_binary(mem, entry, keys, args.input or [], args.ram,
                               real_display=real_display)
        dbg = debug.Debugger(m, symbols, listing, prog_range)
        for b in args.arret or []:
            try:
                dbg.breaks.add(dbg.addr(b))
            except debug.DebugError as e:
                print("erreur : %s" % e, file=sys.stderr)
        return m, dbg

    def read_line(prompt):
        return input(prompt)

    interactive = sys.stdin.isatty()
    if args.fenetre:
        import signal
        holder = {}

        def target(setup):
            m, dbg = make(True)
            holder["m"] = m
            setup(m)
            try:
                dbg.repl(read_line if interactive else None, script)
            finally:
                holder["f"].close_requested = True

        def on_sigint(sig, frame):                   # Ctrl+C : arrêt du programme
            if "m" in holder:
                holder["m"].debug_pause = True
        from . import afficheur
        try:
            f = afficheur.Fenetre("Canon X-07 : %s (débogueur)" % os.path.basename(src),
                                  args.zoom, args.muet)
        except Exception as e:
            print("erreur : fenêtre impossible (%s)" % e, file=sys.stderr)
            return 1
        holder["f"] = f
        signal.signal(signal.SIGINT, on_sigint)
        f.start(lambda: target(f.attach))
        return 0
    m, dbg = make(False)
    if interactive:
        def input_fn():                              # INPUT du programme
            sys.stdout.write("[INPUT du programme] ")
            sys.stdout.flush()
            line = sys.stdin.readline()
            return line.rstrip("\r\n") if line else None
        m.input_fn = input_fn
    dbg.repl(read_line if interactive else None, script)
    return 0


def cmd_ide(args):
    """Éditeur-débogueur visuel (fenêtre)."""
    if args.qt:
        try:
            from . import ide_qt as ide
        except ImportError as ex:
            print("erreur : PyQt6 absent (%s) : pip install PyQt6" % ex, file=sys.stderr)
            return 1
    else:
        from . import ide
    try:
        e = ide.Editeur(args.source, ram=args.ram, zoom=args.zoom, memoire=args.memoire,
                        muet=args.muet)
    except Exception as ex:                      # pas d'affichage graphique
        print("erreur : fenêtre impossible (%s)" % ex, file=sys.stderr)
        return 1
    e.mainloop()
    return 0


def cmd_qb(args):
    """Traduit un programme QuickBASIC en BASIC du X-07 (puis le compile)."""
    from . import qbasic
    try:
        with open(args.source, "rb") as f:
            raw = f.read()
    except OSError as e:
        print("erreur : %s : %s" % (args.source, e.strerror), file=sys.stderr)
        return 1
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        text = raw.decode("latin-1")
    if args.direct:                               # compilation directe en assembleur
        return main(["basic", args.source, "--direct", "-f", args.format or "asm,bin",
                     "--ram", str(args.ram), "--org", args.org]
                    + (["-o", args.output] if args.output else []))
    try:
        out, warns, names = qbasic.translate(text, args.largeur)
    except qbasic.QBError as e:
        print("erreur : %s" % e, file=sys.stderr)
        return 1
    for w in warns:
        print("attention : %s" % w, file=sys.stderr)
    root, ext = os.path.splitext(args.source)
    # tri.qbas -> tri.bas ; une autre extension ne doit pas écraser la source
    dest = args.output or root + (".bas" if ext.lower() == ".qbas" else "_x07.bas")
    with open(dest, "w", encoding="utf-8") as f:
        f.write(out)
    print("%d lignes de BASIC du X-07 -> %s" % (out.count("\n"), dest))
    if args.noms:
        print("noms :")
        for qb, x in names:
            print("  %-24s %s" % (qb, x))
    wanted = [f for f in (args.format or "").split(",") if f]
    if wanted:
        return main(["basic", dest, "-f", ",".join(wanted), "--ram", str(args.ram),
                     "--org", args.org])
    print("ensuite :  emu %s   (vrai BASIC du X-07)" % dest)
    print("           basic %s --ram %d   (assembleur)" % (dest, args.ram))
    return 0


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
    s.add_argument("--md", action="store_true", help="carte complète au format Markdown (ROM.md)")
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
    b.add_argument("--direct", action="store_true",
                   help="QuickBASIC (.qbas) compilé directement, sans BASIC du X-07 "
                        "(récursivité, tableaux par adresse)")
    b.set_defaults(func=cmd_basic)

    g = sub.add_parser("debug", help="déboguer un programme machine dans l'émulateur")
    g.add_argument("source", help=".asm, .bas, .qbas (compilés), .hex ou .bin (--org)")
    g.add_argument("--org", help="adresse de chargement d'un .bin, implantation d'un .bas")
    g.add_argument("--entry", help="adresse de départ (défaut : celle du programme)")
    g.add_argument("--ram", type=int, choices=(8, 16, 24), default=16,
                   help="mémoire du X-07 en Ko (défaut : 16)")
    g.add_argument("-b", "--arret", action="append",
                   help="point d'arrêt (répétable) : adresse, étiquette, « ligne 40 »")
    g.add_argument("-x", "--commandes",
                   help="commandes à exécuter d'abord, séparées par « ; » (ex. \"b START;c;r\")")
    g.add_argument("-k", "--keys", help="touches lues par INKEY$")
    g.add_argument("-i", "--input", action="append", help="réponse à un INPUT (répétable)")
    g.add_argument("--fenetre", action="store_true",
                   help="écran du X-07 dans une fenêtre, commandes dans le terminal")
    g.add_argument("--zoom", type=int, default=5, help="taille de la fenêtre (défaut : 5)")
    g.add_argument("--muet", action="store_true",
                   help="fenêtre sans son (les BEEP gardent leur durée)")
    g.add_argument("--direct", action="store_true",
                   help="QuickBASIC (.qbas) compilé directement, sans BASIC du X-07 "
                        "(récursivité, tableaux par adresse)")
    g.set_defaults(func=cmd_debug)

    ed = sub.add_parser("ide", help="éditeur-débogueur visuel (fenêtre)")
    ed.add_argument("source", nargs="?", help=".asm, .bas ou .qbas (compilé directement)")
    ed.add_argument("--ram", type=int, choices=(8, 16, 24), default=16,
                    help="mémoire du X-07 en Ko (défaut : 16)")
    ed.add_argument("--zoom", type=int, default=3, help="taille de l'écran du X-07 (défaut : 3)")
    ed.add_argument("--muet", action="store_true",
                    help="fenêtre sans son (les BEEP gardent leur durée)")
    ed.add_argument("--memoire", metavar="FICHIER",
                    help="mémoire du X-07 gardée d'une exécution à l'autre (fichiers en RAM)")
    ed.add_argument("--qt", action="store_true",
                    help="fenêtre Qt (PyQt6) au lieu de tkinter")
    ed.set_defaults(func=cmd_ide)

    q = sub.add_parser("qb", help="traduire un programme QuickBASIC en BASIC du X-07")
    q.add_argument("source", help="programme QuickBASIC (extension .qbas)")
    q.add_argument("-o", "--output", help="programme X-07 produit (défaut : NOM.qbas -> NOM.bas)")
    q.add_argument("-f", "--format", default=None,
                   help="puis compiler : asm,bin,hex,lst,txt,bas (comme la commande basic)")
    q.add_argument("--ram", type=int, choices=(8, 16, 24), default=8,
                   help="mémoire du X-07 en Ko, pour la compilation (défaut : 8)")
    q.add_argument("--org", default="auto", help="adresse d'implantation, pour la compilation")
    q.add_argument("--largeur", type=int, default=72,
                   help="longueur maximale d'une ligne produite (défaut : 72)")
    q.add_argument("--noms", action="store_true",
                   help="affiche la correspondance des noms de variables")
    q.add_argument("--direct", action="store_true",
                   help="QuickBASIC (.qbas) compilé directement, sans BASIC du X-07 "
                        "(récursivité, tableaux par adresse)")
    q.set_defaults(func=cmd_qb)

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
    r.add_argument("--fenetre", action="store_true",
                   help="affichage graphique en direct, avec le clavier (Échap = BREAK)")
    r.add_argument("--ecran", action="store_true",
                   help="écran final en points (caractères braille) dans le terminal")
    r.add_argument("--png", metavar="FICHIER", help="image PNG de l'écran final")
    r.add_argument("--zoom", type=int, default=5, help="agrandissement (défaut : 5)")
    r.add_argument("--muet", action="store_true",
                   help="fenêtre sans son (les BEEP gardent leur durée)")
    r.add_argument("--direct", action="store_true",
                   help="QuickBASIC (.qbas) compilé directement, sans BASIC du X-07 "
                        "(récursivité, tableaux par adresse)")
    r.add_argument("--memoire", metavar="FICHIER",
                   help="mémoire du X-07 gardée d'une session à l'autre (fichiers en RAM)")
    r.set_defaults(func=cmd_run)

    e = sub.add_parser("emu", help="exécuter un programme BASIC avec la vraie ROM (émulation)")
    e.add_argument("source", nargs="?", help="programme BASIC (.bas) ; sans programme avec "
                   "--fenetre : le BASIC du X-07 en direct")
    e.add_argument("-k", "--keys", help="touches pour INKEY$")
    e.add_argument("-i", "--input", action="append", help="ligne tapée pour INPUT (répétable)")
    e.add_argument("--ram", type=int, choices=(8, 16, 24), default=16)
    e.add_argument("--max", type=int, default=50_000_000, help="instructions au plus")
    e.add_argument("--charger", metavar="FICHIER",
                   help="avec --fenetre : met un programme machine en mémoire, comme le câble "
                        "(.bas compilé au passage, .asm, .hex, .bin avec --org) ; tapez ensuite EXEC")
    e.add_argument("--org", help="adresse (hexa) d'un .bin, ou implantation d'un .bas pour --charger")
    e.add_argument("--entry", help="adresse de lancement (hexa) d'un .bin pour --charger")
    e.add_argument("--fenetre", action="store_true",
                   help="affichage graphique en direct, avec le clavier (Échap = BREAK)")
    e.add_argument("--memoire", metavar="FICHIER",
                   help="mémoire du X-07 gardée d'une session à l'autre (programmes, fichiers "
                        "en RAM) : rallumé avec elle, éteint par OFF à la fin")
    e.add_argument("--ecran", action="store_true",
                   help="écran final en points (caractères braille) dans le terminal")
    e.add_argument("--png", metavar="FICHIER", help="image PNG de l'écran final")
    e.add_argument("--zoom", type=int, default=5, help="agrandissement (défaut : 5)")
    e.add_argument("--muet", action="store_true",
                   help="fenêtre sans son (les BEEP gardent leur durée)")
    e.add_argument("--direct", action="store_true",
                   help="QuickBASIC (.qbas) compilé directement, sans BASIC du X-07 "
                        "(récursivité, tableaux par adresse)")
    e.set_defaults(func=cmd_emu)

    rc = sub.add_parser("recepteur", help="programme BASIC de réception série, à taper sur le X-07")
    rc.add_argument("-o", "--output", help="fichier .bas produit (défaut : écran)")
    rc.add_argument("--baud", type=int, default=4800, choices=(1200, 2400, 4800, 8000))
    rc.set_defaults(func=cmd_recepteur)

    sd = sub.add_parser("send", help="envoyer un programme au X-07 par le câble série (FT232RL)")
    sd.add_argument("source", help=".bas (compilé au passage), .asm, .hex, ou .bin avec --org")
    sd.add_argument("-p", "--port", help="port série : /dev/ttyUSB0, COM3...")
    sd.add_argument("--baud", type=int, default=4800, choices=(1200, 2400, 4800, 8000))
    sd.add_argument("--org", help="adresse (hexa) d'un .bin, ou implantation d'un .bas")
    sd.add_argument("--entry", help="adresse de lancement (hexa) d'un .bin")
    sd.add_argument("--ram", type=int, choices=(8, 16, 24), default=8)
    sd.add_argument("--timeout", type=float, default=60, help="attente maximale du X-07 (s)")
    sd.add_argument("--emu", action="store_true",
                    help="essai complet avec le X-07 émulé (vraie ROM), sans câble")
    sd.add_argument("--direct", action="store_true",
                   help="QuickBASIC (.qbas) compilé directement, sans BASIC du X-07 "
                        "(récursivité, tableaux par adresse)")
    sd.set_defaults(func=cmd_send)

    args = p.parse_args(argv)
    if args.cmd == "dis" and args.entry:
        args.trace = True
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
