"""Émulation du BASIC du Canon X-07 : la vraie ROM ($B000-$FFFF) s'exécute
dans le simulateur Z80 ; seuls le sous-processeur T6834 (écran, clavier,
graphismes) et la saisie d'une ligne sont imités (voir sim.X07).

  boot(ram)            démarrage à froid ($C3C3), mémorisé une fois
  run_basic(src, ...)  tape le programme, puis RUN ; renvoie l'affichage
  run_binary(mem, ...) charge un programme machine et l'exécute par EXEC

Sert de référence pour vérifier le compilateur, et de BASIC du X-07 sur PC.
"""
import os
import re

from .sim import X07, SimError, EXIT, REAL, PowerOff

ROM_PATHS = (os.path.join(os.path.dirname(__file__), "..", "..", "ROM_x07", "x07.bin"),)
RAM_TOP = {8: 0x1FFF, 16: 0x3FFF, 24: 0x5FFF}

_rom = None
_snapshots = {}


def rom_path():
    env = os.environ.get("X07_ROM")
    for p in ((env,) if env else ()) + ROM_PATHS:
        if p and os.path.exists(p):
            return os.path.abspath(p)
    return None


def load_rom():
    global _rom
    if _rom is None:
        p = rom_path()
        if p is None:
            raise SimError("ROM introuvable : placez x07.bin dans ROM_x07/ "
                           "ou indiquez son chemin dans X07_ROM")
        with open(p, "rb") as f:
            _rom = f.read()
    return _rom


class Finished(Exception):
    """Le BASIC attend une nouvelle ligne de commande : programme terminé."""


DISPLAY_TRAPS = ("LCDPUT", "LCDCLS", "CURSET")


def boot(ram=16, real_display=False):
    """Machine démarrée à froid, prête à recevoir une commande (invite >).

    real_display=False : l'affichage ($C1BE...) est imité en Python, ce qui
    donne aussi un texte de l'écran (tests, mode texte).
    real_display=True : la ROM affiche elle-même et ne parle qu'au T6834
    imité, comme sur la machine ; son éditeur plein écran fonctionne
    (flèches, correction d'une ligne affichée).  Mode de la fenêtre."""
    from . import x07sym
    key = (ram, real_display)
    if key not in _snapshots:
        m = X07()
        m.load_rom(load_rom())
        if real_display:
            for n in DISPLAY_TRAPS:
                m.traps.pop(x07sym.all_symbols()[n], None)
        m.ram_top = RAM_TOP[ram]
        m.strict = False
        m.sp, m.pc = 0, 0xC3C3

        def ready(c):
            raise Finished()
        m.traps[0xEBFF] = ready
        try:
            m.run(2_000_000)
        except Finished:
            pass
        _snapshots[key] = (bytes(m.mem), dict(m.r), m.sp, m.ix, m.iy, m.rd16(m.sp),
                           bytes(m.lcd.px), getattr(m, "scroll_range", (0, 3)))
    mem, regs, sp, ix, iy, ready, px, scroll = _snapshots[key]
    m = X07()
    m._use_rom_routines()
    m.has_rom = True
    m.ram_top = RAM_TOP[ram]
    m.strict = False
    m.mem[:] = mem
    m.r.update(regs)
    m.sp, m.ix, m.iy = sp, ix, iy
    m.transcript = []
    m.ready_ret = ready             # adresse de retour de la saisie d'une commande
    m.real_display = real_display
    if real_display:
        for n in DISPLAY_TRAPS:
            m.traps.pop(x07sym.all_symbols()[n], None)
        m.lcd.px[:] = px            # l'écran tel que la ROM l'a laissé
        m.scroll_range = scroll
    else:
        m._cls(m)
    return m


def power_off(m, max_steps=5_000_000):
    """Éteint la machine par OFF, comme sur le X-07 : la ROM range son état
    puis coupe l'alimentation.  Rend l'image de la RAM (qui reste alimentée)."""
    m.real_off = True
    typed = []

    def command(c):                          # la commande OFF, tapée à l'invite
        if typed:
            raise SimError("OFF n'a pas éteint la machine")
        typed.append(1)
        _type_line(m, "OFF", echo=False)
    m.traps[0xEBFF] = command
    try:
        m.run(m.steps + max_steps)
    except PowerOff:
        return bytes(m.mem[0:m.ram_top + 1])
    raise SimError("la machine ne s'est pas éteinte")


def power_on(image, ram=16, real_display=False):
    """Rallume une machine dont la RAM a été gardée (image de power_off) :
    les programmes et les fichiers en RAM sont retrouvés.  Rend la machine
    à l'invite, comme boot()."""
    m = X07()
    m.load_rom(load_rom())
    if real_display:
        from . import x07sym
        for n in DISPLAY_TRAPS:
            m.traps.pop(x07sym.all_symbols()[n], None)
    m.ram_top = RAM_TOP[ram]
    m.strict = False
    m.mem[0:len(image)] = image
    m.on_state = 0x01                        # ON STATE : rallumée après OFF
    m.sp, m.pc = 0, 0xC3C3

    def ready(c):
        raise Finished()
    m.traps[0xEBFF] = ready
    try:
        m.run(3_000_000)
    except Finished:
        pass
    m._use_rom_routines()
    m.has_rom = True
    m.transcript = []
    m.ready_ret = m.rd16(m.sp)
    m.real_display = real_display
    if not real_display:
        m._cls(m)
    m.on_state = 0
    return m


def run_basic(src, inputs=(), keys="", ram=16, max_steps=50_000_000, echo=None, setup=None,
              live=False, preload=None, machine=None):
    """Tape le programme puis RUN.  Renvoie (affichage du programme, machine).
    L'affichage commence après « RUN » et s'arrête au retour à l'invite.

    live=True (fenêtre) : vrai affichage de la ROM ; le programme, RUN et les
    réponses aux INPUT sont tapés au clavier dans l'éditeur plein écran de la
    ROM, puis l'utilisateur a la main.

    preload=mem (avec live) : programme machine à mettre en mémoire comme par
    le câble série.  « CLEAR 50,&H(org-1) » est d'abord tapé ; le programme est
    chargé dès que le BASIC a exécuté ce CLEAR (sinon sa pile et ses chaînes,
    encore en haut de la mémoire, l'écraseraient).  Reste à taper EXEC."""
    # machine : une machine déjà allumée (power_on) au lieu d'un démarrage à froid ;
    # son ancien programme est effacé (NEW) avant de taper le nouveau, pas ses fichiers
    m = machine if machine is not None else boot(ram, real_display=live)
    if machine is not None and any(re.match(r"\s*\d", l) for l in src.splitlines()):
        src = "NEW\n" + src
    m.keys = list(keys)
    m.echo = echo
    if setup:
        setup(m)
    if live:
        typed = "".join(l.strip() + "\r" for l in src.splitlines() if l.strip())
        if typed:
            typed += "RUN\r"
        typed += "".join(str(x) + "\r" for x in inputs)
        lines_in = {"n": 0}
        if preload:
            typed = "CLEAR 50,&H%X\r" % (min(preload) - 1) + typed

        def editor_line(c):                # chaque ligne lue par l'éditeur de la ROM
            lines_in["n"] += 1
            if preload and lines_in["n"] == 2:     # le CLEAR vient d'être exécuté
                for a, b in preload.items():
                    m.mem[a] = b
                m.cache.clear()
                m.preloaded = True
            return REAL
        m.keys[:0] = list(typed)
        m.interactive = True
        m.preloaded = False
        m.traps[0xEBFF] = editor_line         # l'éditeur de la ROM, pour tout
        m.traps[0xEBF2] = lambda c: REAL
        m.pc = 0xEBFF
        m.error = None
        try:
            m.run(max_steps)
        except SimError as e:
            m.error = str(e)
        return "", m
    lines = [l for l in src.splitlines() if l.strip()]
    state = {"phase": "saisie"}
    queue = list(lines) + (["RUN"] if lines else [])
    user = list(inputs)
    start = {}

    def live_line(c):                  # saisie dans la fenêtre (mode interactif)
        line = m.read_line()
        if line is None:                   # Échap : BREAK
            m._store_line("")
            c.setf(0x01, True)
        else:
            m._store_line(line)

    def command(c):                    # invite > : on tape la ligne suivante
        if c.rd16(c.sp) != m.ready_ret:    # INPUT "texte",V du programme (sans « ? »)
            if not user and m.interactive:
                return live_line(c)
            if not user:
                raise SimError("INPUT : aucune ligne fournie")
            _type_line(m, user.pop(0))
            return
        if not queue and m.interactive:    # le BASIC du X-07, en direct
            line = m.read_line()
            m._store_line(line or "")
            return
        if not queue:
            raise Finished()
        line = queue.pop(0)
        _type_line(m, line, echo=False)
        if line == "RUN":                  # le programme démarre sur un écran vierge
            state["phase"] = "exécution"
            m._cls(m)
            start["pos"] = len(m.transcript)

    def program_input(c):              # INPUT du programme (avec « ? »)
        for ch in "? ":
            m.putc(ord(ch))
        if not user and m.interactive:
            return live_line(c)
        if not user:
            raise SimError("INPUT : aucune ligne fournie")
        _type_line(m, user.pop(0))

    m.traps[0xEBFF] = command
    m.traps[0xEBF2] = program_input
    m.pc = 0xEBFF
    m.error = None
    try:
        m.run(max_steps)
    except Finished:
        pass
    except SimError as e:              # on garde ce qui a été affiché
        m.error = str(e)
    out = "".join(m.transcript)[start.get("pos", 0):]
    if out.endswith(">"):
        out = out[:-1]
    return out, m


def _type_line(m, line, echo=True):
    """Simule la frappe d'une ligne : affichage puis HL = tampon-1."""
    for ch in line:
        m.putc(ord(ch) if ord(ch) < 256 else 63)
    m.putc(13)
    m.putc(10)
    data = line.encode("latin-1", "replace")[:255]
    m.mem[0xD5:0xD5 + len(data)] = data
    m.mem[0xD5 + len(data)] = 0
    m.set16("HL", 0xD4)
    m.setf(0x01, False)


def run_binary(mem, entry, keys="", inputs=(), ram=16, max_steps=50_000_000, echo=None):
    """Charge un programme machine sur la machine démarrée et l'exécute
    comme CLEAR 50,&H(org-1) puis EXEC &Hentry.  Renvoie la machine."""
    m = prepare_binary(mem, entry, keys, inputs, ram, echo=echo)
    m.run(max_steps)
    return m


def prepare_binary(mem, entry, keys="", inputs=(), ram=16, real_display=False, echo=None):
    """Machine prête à exécuter le programme (CLEAR 50,&H(org-1), puis EXEC
    &Hentry) : PC sur l'entrée, retour au BASIC empilé.  Sert au débogueur."""
    m = boot(ram, real_display=real_display)
    m.keys = list(keys)
    m.lines = list(inputs)
    m.echo = echo
    for a, b in mem.items():
        m.mem[a] = b
    m.cache.clear()
    m.strict = True
    org = min(mem)
    if org >= 0x0600:                       # comme CLEAR 50,&H(org-1)
        top = org - 1
        for adr, v in ((0x01DF, top), (0x0204, top), (0x01DD, top - 50)):
            m.mem[adr], m.mem[adr + 1] = v & 0xFF, v >> 8
        m.sp = top - 50
    m.push(EXIT)
    m.pc = entry
    return m
