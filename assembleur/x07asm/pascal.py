"""Turbo Pascal 3.0 simplifié pour le Canon X-07.

Le programme Pascal est traduit en QuickBASIC, que qbcomp compile
directement en code machine (récursivité, tableaux par adresse, double
précision) : le générateur de code vérifié contre la ROM sert tel quel.

Ce qui est pris en charge :
  - program, uses (ignoré), const, type, var, procedure, function, forward ;
  - integer, byte, real (double précision du X-07), boolean, char,
    string[n], types énumérés et intervalles ;
  - array[a..b, c..d] of ..., record ... end (imbriqués, tableaux de records),
    with ;
  - if, while, repeat, for to / downto, case ... of ... else, exit, halt ;
  - paramètres par valeur et var, récursivité ;
  - write / writeln (largeur :n et décimales :n:d comme Turbo Pascal),
    read / readln, read(kbd, c) ;
  - fonctions et procédures standard : abs, sqr, sqrt, sin, cos, arctan, exp,
    ln, trunc, round, frac, int, odd, ord, chr, succ, pred, length, copy,
    concat, pos, upcase, insert, delete, str, val, inc, dec, random,
    randomize, pi, keypressed, readkey, clrscr, gotoxy, wherex, wherey,
    delay, sound, nosound, mem[], port[] ;
  - pour le X-07 : plot, draw, circle (écran de 120 x 32 points), beep.

Les records sont décomposés : chaque champ devient une variable (p.x), un
tableau de records un tableau par champ, une affectation de records une
copie champ par champ, un record en paramètre un paramètre par champ.

Ce qui ne l'est pas : set (sauf « x in [constantes] »), pointeurs,
fichiers, procédures imbriquées, goto, label.

translate(texte) rend (texte QuickBASIC, avertissements, correspondance
ligne QuickBASIC -> ligne Pascal).
"""
import re

from .qbasic import FUNCTIONS, OPERATOR_WORDS, STATEMENT_WORDS


class PasError(Exception):
    def __init__(self, msg, line=None):
        self.msg, self.line = msg, line
        super().__init__(("ligne %d : %s" % (line, msg)) if line else msg)


# ======================================================================= lexique
KEYWORDS = set("""and array begin case const div do downto else end file for forward
function goto if in label mod nil not of or packed procedure program record repeat
set shl shr string then to type until uses var while with xor""".split())


class Tok:
    __slots__ = ("kind", "val", "line")

    def __init__(self, kind, val, line):
        self.kind, self.val, self.line = kind, val, line

    def __repr__(self):
        return "%s:%r" % (self.kind, self.val)


_TOKEN = re.compile(r"""
    (?P<ws>[ \t\r\f]+) | (?P<nl>\n)
  | (?P<com>\{[^}]*\}|\(\*.*?\*\))
  | (?P<real>\d+\.\d+(?:[eE][+-]?\d+)?|\d+[eE][+-]?\d+)
  | (?P<int>\d+) | (?P<hex>\$[0-9A-Fa-f]+)
  | (?P<str>(?:'(?:[^'\n]|'')*'|\#\d+|\#\$[0-9A-Fa-f]+)+)
  | (?P<id>[A-Za-z_][A-Za-z0-9_]*)
  | (?P<op>:=|<=|>=|<>|\.\.|[-+*/=<>()\[\],;:.^@])
""", re.S | re.X)


def tokenize(text):
    toks, i, line = [], 0, 1
    while i < len(text):
        m = _TOKEN.match(text, i)
        if not m:
            raise PasError("caractère inattendu %r" % text[i], line)
        k, v = m.lastgroup, m.group()
        if k == "nl":
            line += 1
        elif k == "com":
            line += v.count("\n")
        elif k == "int":
            toks.append(Tok("num", int(v), line))
        elif k == "hex":
            toks.append(Tok("num", int(v[1:], 16), line))
        elif k == "real":
            toks.append(Tok("real", v, line))
        elif k == "str":
            s = ""
            for part in re.findall(r"'(?:[^'\n]|'')*'|#\$[0-9A-Fa-f]+|#\d+", v):
                if part[0] == "'":
                    s += part[1:-1].replace("''", "'")
                else:
                    s += chr(int(part[2:], 16) if part[1] == "$" else int(part[1:]))
            toks.append(Tok("str", s, line))
        elif k == "id":
            low = v.lower()
            toks.append(Tok("kw" if low in KEYWORDS else "id", low, line))
        elif k == "op":
            toks.append(Tok("op", v, line))
        i = m.end()
    toks.append(Tok("eof", None, line))
    return toks


# ========================================================================= types
INT, REAL, BOOL, CHAR = ("int",), ("real",), ("bool",), ("char",)


def string_t(n=255):
    return ("str", n)


def is_ordinal(t):
    return t[0] in ("int", "bool", "char", "enum")


def is_scalar(t):
    return t[0] in ("int", "real", "bool", "char", "str", "enum")


def is_text(t):
    return t[0] in ("char", "str")


def suffix(t):
    return {"real": "#", "char": "$", "str": "$"}.get(t[0], "%")


def tname(t):
    return {"int": "integer", "real": "real", "bool": "boolean", "char": "char",
            "str": "string", "enum": "énuméré", "array": "tableau",
            "record": "record"}[t[0]]


def ord_value(v):
    """Valeur ordinale d'une constante (entier, caractère, booléen)."""
    if isinstance(v, bool):
        return int(v)
    if isinstance(v, str):
        if len(v) != 1:
            raise ValueError
        return ord(v)
    return v


def leaves(t, path=(), dims=()):
    """Feuilles scalaires d'un type : (chemin de champs, type, dimensions).
    Une dimension est (bas, haut) ; un tableau de records donne un tableau
    par champ."""
    if t[0] == "array":
        return leaves(t[3], path, dims + ((t[1], t[2]),))
    if t[0] == "record":
        out = []
        for name, ft in t[1]:
            out += leaves(ft, path + (name,), dims)
        return out
    return [(path, t, dims)]


# ============================================================ noms QuickBASIC
QB_RESERVED = (set(STATEMENT_WORDS) | set(OPERATOR_WORDS) | {f.rstrip("$") for f in FUNCTIONS}
               | {"FN", "AS", "SHARED", "STATIC", "TO", "STEP", "THEN", "ELSE", "IS", "USING",
                  "INTEGER", "SINGLE", "DOUBLE", "STRING", "LONG", "ANY", "TP"})


# ======================================================== bibliothèque d'appui
# Fonctions QuickBASIC ajoutées au programme quand il s'en sert.  Leurs noms
# et ceux de leurs variables commencent par TP, réservé (un identifiant
# Pascal « tp... » est renommé).
PRELUDE = {
    "TPINT$": ("FUNCTION TPINT$ (TP.N%)", """
    TP.S$ = STR$(TP.N%)
    IF TP.N% >= 0 THEN TP.S$ = MID$(TP.S$, 2)
    TPINT$ = TP.S$"""),
    "TPPAD$": ("FUNCTION TPPAD$ (TP.S$, TP.W%)", """
    IF LEN(TP.S$) < TP.W% THEN
        TPPAD$ = STRING$(TP.W% - LEN(TP.S$), " ") + TP.S$
    ELSE
        TPPAD$ = TP.S$
    END IF"""),
    "TPBOOL$": ("FUNCTION TPBOOL$ (TP.B%)", """
    IF TP.B% THEN TPBOOL$ = "TRUE" ELSE TPBOOL$ = "FALSE\""""),
    # notation scientifique de Turbo Pascal : " 1.2345678900E+00" (d décimales)
    "TPSCI$": ("FUNCTION TPSCI$ (TP.X#, TP.D%)", """
    TP.G$ = " ": TP.A# = TP.X#: TP.E% = 0
    IF TP.A# < 0 THEN TP.G$ = "-": TP.A# = -TP.A#
    IF TP.A# <> 0 THEN
        TP.E% = INT(LOG(TP.A#) / LOG(10#))
        TP.A# = TP.A# / 10# ^ TP.E%
        IF TP.A# >= 10 THEN TP.A# = TP.A# / 10: TP.E% = TP.E% + 1
        IF TP.A# < 1 THEN TP.A# = TP.A# * 10: TP.E% = TP.E% - 1
    END IF
    TP.M# = INT(TP.A# * 10# ^ TP.D% + .5#)
    IF TP.M# >= 10# ^ (TP.D% + 1) THEN TP.M# = INT(TP.M# / 10 + .5#): TP.E% = TP.E% + 1
    TP.T$ = MID$(STR$(TP.M#), 2)
    IF LEN(TP.T$) <= TP.D% THEN TP.T$ = TP.T$ + STRING$(TP.D% + 1 - LEN(TP.T$), "0")
    TP.R$ = TP.G$ + LEFT$(TP.T$, 1) + "." + MID$(TP.T$, 2) + "E"
    IF TP.E% < 0 THEN TP.R$ = TP.R$ + "-" ELSE TP.R$ = TP.R$ + "+"
    TP.U$ = MID$(STR$(ABS(TP.E%)), 2)
    IF LEN(TP.U$) < 2 THEN TP.U$ = "0" + TP.U$
    TPSCI$ = TP.R$ + TP.U$"""),
    # virgule fixe de Turbo Pascal : x:w:d, sans espace devant
    "TPFIX$": ("FUNCTION TPFIX$ (TP.X#, TP.D%)", """
    TP.A# = ABS(TP.X#)
    TP.M# = INT(TP.A# * 10# ^ TP.D% + .5#)
    TP.T$ = MID$(STR$(TP.M#), 2)
    IF LEN(TP.T$) <= TP.D% THEN TP.T$ = STRING$(TP.D% + 1 - LEN(TP.T$), "0") + TP.T$
    IF TP.D% > 0 THEN
        TP.T$ = LEFT$(TP.T$, LEN(TP.T$) - TP.D%) + "." + RIGHT$(TP.T$, TP.D%)
    END IF
    IF TP.X# < 0 THEN TP.T$ = "-" + TP.T$
    TPFIX$ = TP.T$"""),
    "TPPOS%": ("FUNCTION TPPOS% (TP.A$, TP.B$)", """
    TPPOS% = 0
    IF LEN(TP.A$) = 0 THEN EXIT FUNCTION
    FOR TP.I% = 1 TO LEN(TP.B$) - LEN(TP.A$) + 1
        IF MID$(TP.B$, TP.I%, LEN(TP.A$)) = TP.A$ THEN TPPOS% = TP.I%: EXIT FUNCTION
    NEXT TP.I%"""),
    "TPUPC$": ("FUNCTION TPUPC$ (TP.C$)", """
    TPUPC$ = TP.C$
    IF TP.C$ >= "a" AND TP.C$ <= "z" THEN TPUPC$ = CHR$(ASC(TP.C$) - 32)"""),
    "TPKP%": ("FUNCTION TPKP%", """
    IF TP.K$ = "" THEN TP.K$ = INKEY$
    TPKP% = (TP.K$ <> "")"""),
    "TPRK$": ("FUNCTION TPRK$", """
    DO WHILE TP.K$ = ""
        TP.K$ = INKEY$
    LOOP
    TPRK$ = TP.K$: TP.K$ = \"\""""),
    # Delay : une note si Sound est en cours (BEEP du X-07, par pas de 50 ms),
    # sinon une boucle d'attente : 19 tours font environ 500 instructions,
    # soit environ 1 ms sur un Z80 à 3,84 MHz (durée approximative)
    "TPDELAY": ("SUB TPDELAY (TP.MS%)", """
    IF TP.F% > 0 THEN
        TP.L% = TP.MS% \\ 50
        IF TP.L% < 1 THEN TP.L% = 1
        BEEP INT(192000# / TP.F%), TP.L%
    ELSE
        FOR TP.J% = 1 TO TP.MS%
            FOR TP.L% = 1 TO 19
            NEXT TP.L%
        NEXT TP.J%
    END IF"""),
}
# variables partagées de la bibliothèque, et ce dont chaque fonction dépend
PRELUDE_SHARED = {"TPKP%": "TP.K$", "TPRK$": "TP.K$", "TPDELAY": "TP.F%"}


# ===================================================================== analyse
class Parser:
    def __init__(self, text):
        self.toks = tokenize(text)
        self.i = 0

    # -------------------------------------------------------------- outils
    @property
    def cur(self):
        return self.toks[self.i]

    def peek(self, k=1):
        return self.toks[min(self.i + k, len(self.toks) - 1)]

    def next(self):
        t = self.toks[self.i]
        self.i += 1
        return t

    def err(self, msg, tok=None):
        raise PasError(msg, (tok or self.cur).line)

    def is_op(self, v):
        return self.cur.kind == "op" and self.cur.val == v

    def is_kw(self, *v):
        return self.cur.kind == "kw" and self.cur.val in v

    def accept_op(self, v):
        if self.is_op(v):
            return self.next()
        return None

    def accept_kw(self, v):
        if self.is_kw(v):
            return self.next()
        return None

    def expect_op(self, v):
        if not self.is_op(v):
            self.err("« %s » attendu%s" % (v, self.near()))
        return self.next()

    def expect_kw(self, v):
        if not self.is_kw(v):
            self.err("« %s » attendu%s" % (v, self.near()))
        return self.next()

    def ident(self):
        if self.cur.kind != "id":
            self.err("identificateur attendu%s" % self.near())
        return self.next().val

    def near(self):
        t = self.cur
        if t.kind == "eof":
            return " (fin du programme)"
        return " près de « %s »" % (t.val if t.kind != "str" else "'%s'" % t.val)

    # ----------------------------------------------------------- programme
    def program(self):
        name = "PROGRAMME"
        if self.accept_kw("program"):
            name = self.ident()
            if self.accept_op("("):
                while not self.accept_op(")"):
                    self.next()
            self.expect_op(";")
        if self.accept_kw("uses"):
            while not self.accept_op(";"):
                self.next()
        decls = self.declarations(top=True)
        line = self.cur.line
        body = self.compound()
        if not self.accept_op("."):
            self.err("« . » attendu à la fin du programme%s" % self.near())
        return {"name": name, "decls": decls, "body": body, "line": line}

    def declarations(self, top):
        out = []
        while True:
            t = self.cur
            if self.accept_kw("const"):
                while self.cur.kind == "id":
                    line = self.cur.line
                    name = self.ident()
                    typ = None
                    if self.accept_op(":"):             # constante typée (Turbo)
                        typ = self.type_spec()
                        self.expect_op("=")
                        e = self.expr()
                        self.expect_op(";")
                        out.append(("var", [name], typ, line, e))
                        continue
                    self.expect_op("=")
                    out.append(("const", name, self.expr(), line))
                    self.expect_op(";")
            elif self.accept_kw("type"):
                while self.cur.kind == "id":
                    line = self.cur.line
                    name = self.ident()
                    self.expect_op("=")
                    out.append(("type", name, self.type_spec(), line))
                    self.expect_op(";")
            elif self.accept_kw("var"):
                while self.cur.kind == "id":
                    line = self.cur.line
                    names = [self.ident()]
                    while self.accept_op(","):
                        names.append(self.ident())
                    self.expect_op(":")
                    out.append(("var", names, self.type_spec(), line, None))
                    self.expect_op(";")
            elif self.is_kw("procedure", "function"):
                if not top:
                    self.err("procédure imbriquée dans une autre : non prise en charge "
                             "(déclarez-la au niveau du programme)")
                out.append(self.routine())
            elif self.is_kw("label", "goto"):
                self.err("label / goto : non pris en charge")
            else:
                return out

    def routine(self):
        kind = self.next().val
        line = self.cur.line
        name = self.ident()
        params = []
        if self.accept_op("("):
            while True:
                byref = bool(self.accept_kw("var"))
                if self.is_kw("const"):
                    self.next()
                names = [self.ident()]
                while self.accept_op(","):
                    names.append(self.ident())
                self.expect_op(":")
                typ = self.type_spec(param=True)
                params += [(n, typ, byref) for n in names]
                if not self.accept_op(";"):
                    break
            self.expect_op(")")
        ret = None
        if kind == "function":
            self.expect_op(":")
            ret = self.type_spec(param=True)
        self.expect_op(";")
        if self.accept_kw("forward"):
            self.expect_op(";")
            return ("routine", kind, name, params, ret, None, None, line)
        decls = self.declarations(top=False)
        body = self.compound()
        self.expect_op(";")
        return ("routine", kind, name, params, ret, decls, body, line)

    # --------------------------------------------------------------- types
    def type_spec(self, param=False):
        t = self.cur
        if self.accept_kw("packed"):
            return self.type_spec(param)
        if self.accept_kw("string"):
            n = 255
            if self.accept_op("["):
                n = self.expr()
                self.expect_op("]")
            return ("string", n)
        if self.accept_kw("array"):
            ranges = []
            if self.accept_op("["):
                while True:
                    ranges.append(self.range_spec())
                    if not self.accept_op(","):
                        break
                self.expect_op("]")
            elif not param:
                self.err("array : bornes [a..b] attendues")
            self.expect_kw("of")
            elem = self.type_spec(param)
            for r in reversed(ranges):
                elem = ("array", r, elem)
            return elem if ranges else ("openarray", elem)
        if self.accept_kw("record"):
            fields = []
            while self.cur.kind == "id":
                names = [self.ident()]
                while self.accept_op(","):
                    names.append(self.ident())
                self.expect_op(":")
                ft = self.type_spec()
                fields += [(n, ft) for n in names]
                if not self.accept_op(";"):
                    break
            if self.is_kw("case"):
                self.err("record à partie variable (case) : non pris en charge")
            self.expect_kw("end")
            return ("record", fields)
        if self.is_kw("set", "file") or self.is_op("^"):
            self.err("%s : non pris en charge" % ("pointeur" if self.is_op("^") else t.val))
        if self.accept_op("("):
            names = [self.ident()]
            while self.accept_op(","):
                names.append(self.ident())
            self.expect_op(")")
            return ("enum", names)
        if t.kind == "id" and not self.is_op_at(1, ".."):
            self.next()
            return ("named", t.val, t.line)
        return ("range",) + self.range_spec()

    def is_op_at(self, k, v):
        t = self.peek(k)
        return t.kind == "op" and t.val == v

    def range_spec(self):
        lo = self.expr()
        self.expect_op("..")
        return (lo, self.expr())

    # --------------------------------------------------------- instructions
    def compound(self):
        line = self.cur.line
        self.expect_kw("begin")
        stmts = self.stmt_list("end")
        self.expect_kw("end")
        return ("block", stmts, line)

    def stmt_list(self, *enders):
        stmts = [self.statement()]
        while self.accept_op(";"):
            stmts.append(self.statement())
        if not self.is_kw(*enders):
            self.err("« ; » ou « %s » attendu%s" % (enders[0], self.near()))
        return [s for s in stmts if s is not None]

    def statement(self):
        t = self.cur
        line = t.line
        if t.kind == "kw":
            k = t.val
            if k == "begin":
                return self.compound()
            if k == "if":
                self.next()
                c = self.expr()
                self.expect_kw("then")
                a = None if self.is_kw("else") else self.statement()
                b = self.statement() if self.accept_kw("else") else None
                return ("if", c, a, b, line)
            if k == "while":
                self.next()
                c = self.expr()
                self.expect_kw("do")
                return ("while", c, self.statement(), line)
            if k == "repeat":
                self.next()
                body = self.stmt_list("until")
                self.expect_kw("until")
                return ("repeat", body, self.expr(), line)
            if k == "for":
                self.next()
                v = self.designator()
                self.expect_op(":=")
                a = self.expr()
                down = bool(self.accept_kw("downto"))
                if not down:
                    self.expect_kw("to")
                b = self.expr()
                self.expect_kw("do")
                return ("for", v, a, b, down, self.statement(), line)
            if k == "case":
                self.next()
                e = self.expr()
                self.expect_kw("of")
                arms, other = [], None
                while not self.is_kw("end", "else"):
                    labels = []
                    while True:
                        lo = self.expr()
                        hi = self.expr() if self.accept_op("..") else None
                        labels.append((lo, hi))
                        if not self.accept_op(","):
                            break
                    self.expect_op(":")
                    arms.append((labels, self.statement()))
                    if not self.accept_op(";"):
                        break
                if self.accept_kw("else"):
                    other = self.stmt_list("end")
                self.expect_kw("end")
                return ("case", e, arms, other, line)
            if k == "with":
                self.next()
                recs = [self.designator()]
                while self.accept_op(","):
                    recs.append(self.designator())
                self.expect_kw("do")
                return ("with", recs, self.statement(), line)
            if k == "goto":
                self.err("goto : non pris en charge")
            if k in ("end", "until", "else"):
                return None                          # instruction vide
            self.err("instruction attendue%s" % self.near())
        if t.kind == "id":
            d = self.designator()
            if self.accept_op(":="):
                return ("assign", d, self.expr(), line)
            return ("call", d, line)
        if self.is_op(";"):
            return None
        self.err("instruction attendue%s" % self.near())

    # -------------------------------------------------------- expressions
    REL = ("=", "<>", "<", ">", "<=", ">=")

    def expr(self):
        a = self.simple()
        if self.cur.kind == "op" and self.cur.val in self.REL:
            op = self.next().val
            return ("bin", op, a, self.simple())
        if self.accept_kw("in"):
            return ("in", a, self.set_value())
        return a

    def set_value(self):
        self.expect_op("[")
        items = []
        if not self.is_op("]"):
            while True:
                lo = self.expr()
                items.append((lo, self.expr() if self.accept_op("..") else None))
                if not self.accept_op(","):
                    break
        self.expect_op("]")
        return items

    def simple(self):
        if self.is_op("-") or self.is_op("+"):
            op = self.next().val
            a = self.term()
            a = ("un", "-", a) if op == "-" else a
        else:
            a = self.term()
        while (self.cur.kind == "op" and self.cur.val in "+-") or self.is_kw("or", "xor"):
            op = self.next().val
            a = ("bin", op, a, self.term())
        return a

    def term(self):
        a = self.factor()
        while (self.cur.kind == "op" and self.cur.val in "*/") or \
                self.is_kw("div", "mod", "and", "shl", "shr"):
            op = self.next().val
            a = ("bin", op, a, self.factor())
        return a

    def factor(self):
        t = self.cur
        if t.kind == "num":
            self.next()
            return ("num", t.val, "int")
        if t.kind == "real":
            self.next()
            return ("num", t.val, "real")
        if t.kind == "str":
            self.next()
            return ("str", t.val)
        if self.accept_kw("not"):
            return ("un", "not", self.factor())
        if self.accept_op("("):
            e = self.expr()
            self.expect_op(")")
            return ("paren", e)
        if self.is_op("["):
            self.err("ensemble [...] : seulement après « in »")
        if self.is_kw("nil"):
            self.err("nil / pointeurs : non pris en charge")
        if t.kind == "id":
            return self.designator()
        self.err("expression attendue%s" % self.near())

    def designator(self):
        t = self.cur
        name = self.ident()
        sels = []
        while True:
            if self.accept_op("["):
                idx = [self.expr()]
                while self.accept_op(","):
                    idx.append(self.expr())
                self.expect_op("]")
                sels += [("idx", e) for e in idx]
            elif self.is_op(".") and self.peek().kind == "id":
                self.next()
                sels.append(("fld", self.ident()))
            elif self.is_op("("):
                self.next()
                args = []
                if not self.is_op(")"):
                    while True:
                        e = self.expr()
                        if self.accept_op(":"):          # write(x:w:d)
                            w = self.expr()
                            dd = self.expr() if self.accept_op(":") else None
                            e = ("fmt", e, w, dd)
                        args.append(e)
                        if not self.accept_op(","):
                            break
                self.expect_op(")")
                sels.append(("args", args))
            elif self.is_op("^"):
                self.err("pointeurs : non pris en charge")
            else:
                return ("desig", name, sels, t.line)


# ================================================================= traduction
class Translator:
    def __init__(self, text):
        self.prog = Parser(text).program()
        self.lines = []            # (texte QuickBASIC, ligne Pascal)
        self.warnings = []
        self.used = set()          # fonctions de la bibliothèque d'appui
        self.globals = {}          # nom Pascal -> symbole
        self.local = None          # symboles de la routine en cours
        self.routine = None        # routine en cours (symbole)
        self.qbnames = set()       # noms QuickBASIC déjà pris (variables, routines)
        self.with_stack = []       # (record désigné, type)
        self.ntemp = 0
        self.indent = 0
        self.line = self.prog["line"]

    # ------------------------------------------------------------- sortie
    def emit(self, text, line=None):
        self.lines.append(("    " * self.indent + text, line or self.line))

    def warn(self, msg):
        if msg not in self.warnings:
            self.warnings.append(msg)

    def err(self, msg, line=None):
        raise PasError(msg, line or self.line)

    def temp(self, suf):
        self.ntemp += 1
        return "TP.V%d%s" % (self.ntemp, suf)

    def qbname(self, name, local=False):
        """Nom QuickBASIC (sans suffixe) d'un identifiant Pascal : renommé s'il
        est réservé par QuickBASIC, ou, pour une variable locale, s'il est
        déjà pris par le programme (QuickBASIC le prendrait pour la variable
        globale)."""
        base = re.sub(r"[^A-Z0-9]", "", name.upper()) or "V"
        if base.startswith(("TP", "FN")):        # bibliothèque d'appui, DEF FN
            base = "P" + base
        cand, k = base, 1
        while cand in QB_RESERVED or cand in self.qbnames:
            cand = "%sV%s" % (base, k if k > 1 else "")
            k += 1
        self.qbnames.add(cand)
        return cand

    # ---------------------------------------------------------- symboles
    def lookup(self, name, line=None, quiet=False):
        if self.local is not None and name in self.local:
            return self.local[name]
        if name in self.globals:
            return self.globals[name]
        if quiet:
            return None
        self.err("identificateur inconnu : %s" % name, line)

    def declare(self, scope, name, sym, line):
        if name in scope:
            self.err("%s déjà déclaré" % name, line)
        scope[name] = sym

    def resolve(self, t, line):
        """Type déclaré -> type interne."""
        k = t[0]
        if k == "named":
            n = t[1]
            base = {"integer": INT, "byte": INT, "word": INT, "shortint": INT,
                    "longint": INT, "real": REAL, "single": REAL, "double": REAL,
                    "boolean": BOOL, "char": CHAR, "string": string_t()}
            if n in ("longint", "word"):
                self.warn("%s : entier de 16 bits sur le X-07 (-32768 à 32767)" % n)
            sym = self.lookup(n, t[2], quiet=True)
            if sym is not None and sym["cls"] == "type":
                return sym["type"]
            if n in base:
                return base[n]
            if n == "text":
                self.err("fichiers : non pris en charge", line)
            self.err("type inconnu : %s" % n, t[2])
        if k == "string":
            n = t[1] if isinstance(t[1], int) else self.const_int(t[1])
            return string_t(n)
        if k == "array":
            lo, hi = (self.const_ord(e) for e in t[1])
            if hi < lo:
                self.err("array[%d..%d] : bornes inversées" % (lo, hi), line)
            return ("array", lo, hi, self.resolve(t[2], line))
        if k == "openarray":
            self.err("paramètre « array of ... » sans bornes : déclarez un type tableau", line)
        if k == "record":
            fields = [(n, self.resolve(ft, line)) for n, ft in t[1]]
            names = [n for n, _ in fields]
            if len(set(names)) != len(names):
                self.err("champ déclaré deux fois dans un record", line)
            return ("record", fields)
        if k == "enum":
            et = ("enum", tuple(t[1]))
            for i, n in enumerate(t[1]):
                self.declare(self.local if self.local is not None else self.globals, n,
                             {"cls": "const", "type": et, "value": i}, line)
            return et
        if k == "range":
            lo, hi = (self.const_value(e) for e in t[1:])
            if isinstance(lo, str):
                return CHAR
            return INT
        raise AssertionError(t)

    # --------------------------------------------------------- constantes
    def const_value(self, e):
        """Valeur Python d'une expression constante (int, float, str, bool)."""
        k = e[0]
        if k == "num":
            return e[1] if e[2] == "int" else float(e[1])
        if k == "str":
            return e[1]
        if k == "paren":
            return self.const_value(e[1])
        if k == "desig" and not e[2]:
            if e[1] in ("true", "false") and self.lookup(e[1], e[3], quiet=True) is None:
                return e[1] == "true"
            if e[1] == "maxint" and self.lookup(e[1], e[3], quiet=True) is None:
                return 32767
            sym = self.lookup(e[1], e[3])
            if sym["cls"] == "const":
                return sym["value"]
            self.err("%s n'est pas une constante" % e[1], e[3])
        if k == "desig" and e[1] in ("chr", "ord") and len(e[2]) == 1 and e[2][0][0] == "args":
            v = self.const_value(e[2][0][1][0])
            return chr(v) if e[1] == "chr" else ord_value(v)
        if k == "un":
            v = self.const_value(e[2])
            return -v if e[1] == "-" else (not v if isinstance(v, bool) else ~v)
        if k == "bin":
            a, b = self.const_value(e[2]), self.const_value(e[3])
            op = e[1]
            ops = {"+": lambda: a + b, "-": lambda: a - b, "*": lambda: a * b,
                   "/": lambda: a / b, "div": lambda: int(a / b), "mod": lambda: a - b * int(a / b),
                   "and": lambda: a and b if isinstance(a, bool) else a & b,
                   "or": lambda: a or b if isinstance(a, bool) else a | b,
                   "=": lambda: a == b, "<>": lambda: a != b, "<": lambda: a < b,
                   ">": lambda: a > b, "<=": lambda: a <= b, ">=": lambda: a >= b}
            if op in ops:
                return ops[op]()
        self.err("expression constante attendue")

    def const_int(self, e):
        v = self.const_value(e)
        if not isinstance(v, int) or isinstance(v, bool):
            self.err("constante entière attendue")
        return v

    def const_ord(self, e):
        try:
            return ord_value(self.const_value(e))
        except ValueError:
            self.err("borne de type ordinal attendue (entier, caractère)")

    def literal(self, v):
        """Texte QuickBASIC d'une valeur constante, et son type."""
        if isinstance(v, bool):
            return ("-1" if v else "0"), BOOL
        if isinstance(v, int):
            if -32768 <= v <= 32767:
                return ("(%d)" % v if v < 0 else str(v)), INT
            return "%d#" % v, REAL
        if isinstance(v, float):
            s = repr(v)
            if "e" in s:
                m, x = s.split("e")
                s = "%sD%s" % (m, x)
                return ("(%s)" % s if v < 0 else s), REAL
            return ("(%s#)" % s if v < 0 else s + "#"), REAL
        return self.qbstring(v), (CHAR if len(v) == 1 else string_t())

    @staticmethod
    def qbstring(s):
        """Chaîne QuickBASIC : guillemets et codes de contrôle par CHR$."""
        parts, cur = [], ""
        for c in s:
            if c == '"' or ord(c) < 32 or ord(c) > 126:
                if cur:
                    parts.append('"%s"' % cur)
                    cur = ""
                parts.append("CHR$(%d)" % (ord(c) & 0xFF))
            else:
                cur += c
        if cur or not parts:
            parts.append('"%s"' % cur)
        return parts[0] if len(parts) == 1 else "(" + " + ".join(parts) + ")"

    # ======================================================= déclarations
    def translate(self):
        p = self.prog
        routines = []
        self.declare_all(p["decls"], self.globals, routines)
        main = []
        saved = self.lines
        self.lines = main
        self.line = p["line"]
        for name, sym in self.globals.items():
            if sym["cls"] == "var" and sym.get("init") is not None:
                self.assign_value(self.var_access(sym, [], sym["line"]), sym["init"],
                                  sym["line"])
        self.stmt(p["body"])
        self.emit("END", self.line)
        bodies = []
        for r in routines:
            self.lines = []
            self.routine_body(r)
            bodies.append(self.lines)
        self.lines = saved
        # en-tête : DECLARE, variables partagées, puis le programme et les routines
        out = []
        for r in routines:
            out.append((r["decl"].replace("SUB ", "DECLARE SUB ", 1).replace(
                "FUNCTION ", "DECLARE FUNCTION ", 1), r["line"]))
        prelude = sorted(self.used)
        for n in prelude:
            out.append(("DECLARE " + PRELUDE[n][0], p["line"]))
        shared = []
        for name, sym in self.globals.items():
            if sym["cls"] == "var":
                shared += self.dim_list(sym)
        shared += sorted({PRELUDE_SHARED[n] for n in prelude if n in PRELUDE_SHARED})
        for k in range(0, len(shared), 6):
            out.append(("DIM SHARED " + ", ".join(shared[k:k + 6]), p["line"]))
        out += main
        for b in bodies:
            out += b
        for n in prelude:
            head, body = PRELUDE[n]
            out.append((head, p["line"]))
            out += [(l, p["line"]) for l in body.strip("\n").split("\n")]
            out.append(("END " + head.split()[0], p["line"]))
        return out

    def declare_all(self, decls, scope, routines):
        for d in decls:
            k = d[0]
            if k == "const":
                _, name, e, line = d
                self.line = line
                v = self.const_value(e)
                t = BOOL if isinstance(v, bool) else INT if isinstance(v, int) else \
                    REAL if isinstance(v, float) else (CHAR if len(v) == 1 else string_t())
                self.declare(scope, name, {"cls": "const", "type": t, "value": v}, line)
            elif k == "type":
                _, name, t, line = d
                self.line = line
                self.declare(scope, name, {"cls": "type", "type": self.resolve(t, line)}, line)
            elif k == "var":
                _, names, t, line, init = d
                self.line = line
                typ = self.resolve(t, line)
                for n in names:
                    self.declare(scope, n, {"cls": "var", "type": typ, "byref": False,
                                            "qb": self.qbname(n, scope is not self.globals),
                                            "line": line, "init": init}, line)
            elif k == "routine":
                self.declare_routine(d, scope, routines)

    def declare_routine(self, d, scope, routines):
        _, kind, name, params, ret, decls, body, line = d
        self.line = line
        sym = scope.get(name)
        if sym is not None and sym.get("forward") and decls is not None:
            sym["forward"] = False
            sym["decls"], sym["body"] = decls, body
            return
        if sym is not None:
            self.err("%s déjà déclaré" % name, line)
        rt = self.resolve(ret, line) if ret else None
        if rt is not None and not is_scalar(rt):
            self.err("une fonction rend un type simple (pas de tableau ni de record)", line)
        ptypes = [(n, self.resolve(t, line), byref) for n, t, byref in params]
        qb = self.qbname(name)
        sym = {"cls": "func" if kind == "function" else "proc", "name": name, "qb": qb,
               "params": ptypes, "ret": rt, "decls": decls, "body": body,
               "forward": decls is None, "line": line}
        sym["qbfull"] = qb + (suffix(rt) if rt else "")
        scope[name] = sym
        routines.append(sym)
        # paramètres QuickBASIC : une feuille par champ, « () » pour un tableau
        plist = []
        for pn, pt, byref in ptypes:
            for path, lt, dims in leaves(pt):
                plist.append(None)                    # nom fixé au corps de la routine
        sym["decl"] = None
        sym["pcount"] = len(plist)

    def dim_list(self, sym):
        out = []
        for path, lt, dims in leaves(sym["type"]):
            n = self.leaf_name(sym["qb"], path, lt)
            if dims:
                n += "(%s)" % ", ".join(str(hi - lo) for lo, hi in dims)
            out.append(n)
        return out

    @staticmethod
    def leaf_name(qb, path, t):
        return ".".join((qb,) + tuple(p.upper() for p in path)) + suffix(t)

    # ======================================================== routines
    def routine_body(self, r):
        if r["forward"]:
            self.err("%s : déclarée forward mais jamais définie" % r["name"], r["line"])
        self.routine = r
        self.local = {}
        self.line = r["line"]
        saved_names = set(self.qbnames)
        params = []
        for pn, pt, byref in r["params"]:
            sym = {"cls": "var", "type": pt, "byref": byref, "qb": self.qbname(pn, True),
                   "line": r["line"], "param": True, "init": None}
            self.declare(self.local, pn, sym, r["line"])
            for path, lt, dims in leaves(pt):
                n = self.leaf_name(sym["qb"], path, lt)
                params.append(n + ("()" if dims else ""))
        kind = "FUNCTION" if r["cls"] == "func" else "SUB"
        head = "%s %s" % (kind, r["qbfull"])
        if params:
            head += " (%s)" % ", ".join(params)
        r["decl"] = head
        self.emit(head, r["line"])
        self.indent += 1
        routines = []
        self.declare_all(r["decls"], self.local, routines)
        if routines:
            self.err("procédure imbriquée : non prise en charge", r["line"])
        for name, sym in self.local.items():
            if sym["cls"] == "var" and not sym.get("param"):
                dims = [n for n in self.dim_list(sym) if "(" in n]
                if dims:
                    self.emit("DIM " + ", ".join(dims), sym["line"])
                if sym.get("init") is not None:
                    self.assign_value(self.var_access(sym, [], sym["line"]), sym["init"],
                                      sym["line"])
        self.stmt(r["body"])
        self.indent -= 1
        self.emit("END " + kind, r["body"][2])
        self.local = None
        self.routine = None
        self.qbnames = saved_names | {r["qb"]}

    # ======================================================= instructions
    def stmt(self, s):
        if s is None:
            return
        k = s[0]
        self.line = s[-1]
        getattr(self, "s_" + k)(s)

    def s_block(self, s):
        for x in s[1]:
            self.stmt(x)

    def body(self, s):
        self.indent += 1
        self.stmt(s)
        self.indent -= 1

    def s_if(self, s):
        _, c, a, b, line = s
        self.emit("IF %s THEN" % self.cond(c), line)
        self.body(a)
        if b is not None:
            self.emit("ELSE", line)
            self.body(b)
        self.emit("END IF", line)

    def s_while(self, s):
        _, c, body, line = s
        self.emit("DO WHILE %s" % self.cond(c), line)
        self.body(body)
        self.emit("LOOP", line)

    def s_repeat(self, s):
        _, body, c, line = s
        self.emit("DO", line)
        self.indent += 1
        for x in body:
            self.stmt(x)
        self.indent -= 1
        self.line = line
        self.emit("LOOP UNTIL %s" % self.cond(c), line)

    def s_for(self, s):
        _, v, a, b, down, body, line = s
        target, vt = self.lvalue(v)
        if not is_ordinal(vt):
            self.err("for : variable de type ordinal attendue (entier, caractère...)", line)
        step = " STEP -1" if down else ""
        if vt[0] == "char":                       # caractère : compteur entier caché
            i = self.temp("%")
            self.emit("FOR %s = ASC(%s) TO ASC(%s)%s" % (i, self.value(a, CHAR),
                                                         self.value(b, CHAR), step), line)
            self.indent += 1
            self.emit("%s = CHR$(%s)" % (target, i), line)
            self.stmt(body)
            self.indent -= 1
            self.emit("NEXT %s" % i, line)
            return
        if not re.fullmatch(r"[A-Z0-9.]+%", target):
            self.err("for : la variable de boucle doit être une variable simple", line)
        self.emit("FOR %s = %s TO %s%s" % (target, self.value(a, INT), self.value(b, INT), step),
                  line)
        self.body(body)
        self.emit("NEXT %s" % target, line)

    def s_case(self, s):
        _, e, arms, other, line = s
        text, t = self.ex(e)
        if not is_ordinal(t):
            self.err("case : expression de type ordinal attendue", line)
        self.emit("SELECT CASE %s" % text, line)
        for labels, st in arms:
            parts = []
            for lo, hi in labels:
                a = self.literal(self.const_value(lo))[0]
                parts.append(a if hi is None else "%s TO %s" % (a, self.literal(
                    self.const_value(hi))[0]))
            self.emit("CASE %s" % ", ".join(parts), line)
            self.body(st)
        if other is not None:
            self.emit("CASE ELSE", line)
            self.indent += 1
            for x in other:
                self.stmt(x)
            self.indent -= 1
        self.emit("END SELECT", line)

    def s_with(self, s):
        _, recs, body, line = s
        n = 0
        for d in recs:
            acc = self.access(d)
            if acc["type"][0] != "record":
                self.err("with : record attendu", line)
            self.with_stack.append(acc)
            n += 1
        self.stmt(body)
        del self.with_stack[-n:]

    def s_assign(self, s):
        _, d, e, line = s
        if d[0] == "desig" and not d[2] and self.routine is not None and \
                self.routine["cls"] == "func" and d[1] == self.routine["name"] and \
                self.lookup(d[1], line) is self.routine:
            r = self.routine
            self.emit("%s = %s" % (r["qbfull"], self.value(e, r["ret"])), line)
            return
        acc = self.access(d)
        self.assign_value(acc, e, line)

    def assign_value(self, acc, e, line):
        t = acc["type"]
        if acc.get("strindex"):                   # s[i] := c
            s, i = acc["strindex"]
            self.emit("%s = LEFT$(%s, %s - 1) + %s + MID$(%s, %s + 1)"
                      % (s, s, i, self.value(e, CHAR), s, i), line)
            return
        if acc.get("special"):
            kind, arg = acc["special"]
            v = self.value(e, INT)
            self.emit("%s %s, %s" % ("POKE" if kind == "mem" else "OUT", arg, v), line)
            return
        if is_scalar(t):
            self.emit("%s = %s" % (self.scalar(acc), self.value(e, t)), line)
            return
        src = self.access(e) if e[0] == "desig" else None
        if src is None or not self.same_type(src["type"], t):
            self.err("affectation de %s : même type attendu des deux côtés" % tname(t), line)
        self.copy(acc, src, line)

    def copy(self, dst, src, line):
        """Copie d'un record ou d'un tableau : feuille par feuille, avec des
        boucles pour les dimensions qui ne sont pas encore indicées."""
        for path, lt, dims in leaves(dst["type"]):
            loops = []
            idx = []
            for lo, hi in dims:
                v = self.temp("%")
                loops.append(v)
                self.emit("FOR %s = 0 TO %d" % (v, hi - lo), line)
                self.indent += 1
                idx.append(v)
            a = self.leaf_text(dst, path, lt, idx)
            b = self.leaf_text(src, path, lt, idx)
            self.emit("%s = %s" % (a, b), line)
            for v in reversed(loops):
                self.indent -= 1
                self.emit("NEXT %s" % v, line)

    @staticmethod
    def same_type(a, b):
        if a[0] == "str" and b[0] == "str":
            return True
        return a == b

    def s_call(self, s):
        _, d, line = s
        name, sels = d[1], d[2]
        args = sels[0][1] if sels and sels[0][0] == "args" else []
        rest = sels[1:] if sels and sels[0][0] == "args" else sels
        if rest:
            self.err("instruction attendue (affectation « := » ou appel)", line)
        sym = self.lookup(name, line, quiet=True)
        if sym is None or sym.get("cls") not in ("proc", "func"):
            if self.builtin_proc(name, args, line, sym):
                return
            if sym is None:
                self.err("procédure inconnue : %s" % name, line)
            self.err("%s n'est pas une procédure" % name, line)
        if sym["cls"] == "func":
            text = self.call_text(sym, args, line)
            v = self.temp(suffix(sym["ret"]))         # résultat ignoré, comme en Pascal
            self.emit("%s = %s" % (v, text), line)
            return
        text = self.call_args(sym, args, line)
        self.emit(sym["qb"] + (" " + text if text else ""), line)

    # ================================================== procédures standard
    def builtin_proc(self, name, args, line, sym):
        if sym is not None:
            return False
        n = len(args)

        def need(k, what):
            if n not in (k if isinstance(k, tuple) else (k,)):
                self.err("%s : %s" % (name, what), line)
        if name in ("write", "writeln"):
            self.write(args, name == "writeln", line)
        elif name in ("read", "readln"):
            self.read(args, line)
        elif name == "clrscr":
            self.emit("CLS", line)
        elif name == "gotoxy":
            need(2, "GotoXY(colonne, ligne) attendu")
            self.emit("LOCATE %s, %s" % (self.value(args[1], INT), self.value(args[0], INT)), line)
        elif name == "delay":
            need(1, "Delay(millisecondes) attendu")
            self.use("TPDELAY")
            self.emit("TPDELAY %s" % self.byval(args[0], INT), line)
        elif name == "sound":
            need(1, "Sound(fréquence) attendu")
            self.use("TPDELAY")
            self.emit("TP.F% = " + self.value(args[0], INT), line)
        elif name == "nosound":
            self.use("TPDELAY")
            self.emit("TP.F% = 0", line)
        elif name == "beep":
            need(2, "Beep(note, durée) attendu (BEEP du X-07)")
            self.emit("BEEP %s, %s" % (self.value(args[0], INT), self.value(args[1], INT)), line)
        elif name == "randomize":
            self.emit("RANDOMIZE TIMER", line)
        elif name in ("halt",):
            self.emit("END", line)
        elif name == "exit":
            if self.routine is None:
                self.emit("END", line)
            else:
                self.emit("EXIT %s" % ("FUNCTION" if self.routine["cls"] == "func" else "SUB"),
                          line)
        elif name in ("inc", "dec"):
            need((1, 2), "%s(variable[, n]) attendu" % name)
            acc = self.access(args[0])
            t = acc["type"]
            if not is_ordinal(t):
                self.err("%s : variable entière attendue" % name, line)
            v = self.scalar(acc)
            k = self.value(args[1], INT) if n == 2 else "1"
            op = "+" if name == "inc" else "-"
            if t[0] == "char":
                self.emit("%s = CHR$(ASC(%s) %s %s)" % (v, v, op, k), line)
            else:
                self.emit("%s = %s %s %s" % (v, v, op, k), line)
        elif name == "str":
            need(2, "Str(nombre[:largeur[:décimales]], chaîne) attendu")
            acc = self.access(args[1])
            if not is_text(acc["type"]):
                self.err("Str : chaîne attendue en second paramètre", line)
            self.emit("%s = %s" % (self.scalar(acc), self.format_item(args[0], line)), line)
        elif name == "val":
            need(3, "Val(chaîne, variable, code) attendu")
            acc = self.access(args[1])
            code = self.access(args[2])
            self.emit("%s = VAL(%s)" % (self.scalar(acc), self.value(args[0], string_t())), line)
            self.emit("%s = 0" % self.scalar(code), line)
            self.warn("Val : le code d'erreur rendu vaut toujours 0")
        elif name == "insert":
            need(3, "Insert(source, chaîne, position) attendu")
            s = self.scalar(self.access(args[1]))
            i = self.value(args[2], INT)
            self.emit("%s = LEFT$(%s, %s - 1) + %s + MID$(%s, %s)"
                      % (s, s, i, self.value(args[0], string_t()), s, i), line)
        elif name == "delete":
            need(3, "Delete(chaîne, position, nombre) attendu")
            s = self.scalar(self.access(args[0]))
            i, k = self.value(args[1], INT), self.value(args[2], INT)
            self.emit("%s = LEFT$(%s, %s - 1) + MID$(%s, %s + %s)" % (s, s, i, s, i, k), line)
        elif name == "plot":
            need((2, 3), "Plot(x, y[, couleur]) attendu")
            p = "(%s, %s)" % (self.value(args[0], INT), self.value(args[1], INT))
            self.emit(("PRESET " if n == 3 and self.is_zero(args[2]) else "PSET ") + p, line)
        elif name == "draw":
            need((4, 5), "Draw(x1, y1, x2, y2[, couleur]) attendu")
            v = [self.value(a, INT) for a in args[:4]]
            self.emit("LINE (%s, %s)-(%s, %s)%s" % tuple(v + [", 0" if n == 5 and self.is_zero(
                args[4]) else ""]), line)
        elif name == "circle":
            need(3, "Circle(x, y, rayon) attendu")
            v = [self.value(a, INT) for a in args]
            self.emit("CIRCLE (%s, %s), %s" % tuple(v), line)
        else:
            return False
        return True

    def is_zero(self, e):
        try:
            return self.const_value(e) == 0
        except PasError:
            return False

    def use(self, name):
        self.used.add(name)

    def write(self, args, newline, line):
        parts = []
        for a in args:
            parts.append(self.format_item(a, line))
        text = "; ".join(parts)
        if not newline:
            text += ";"
        self.emit(("PRINT " + text).rstrip(), line)

    def format_item(self, a, line):
        """Texte QuickBASIC d'un élément de write, mis en forme comme Turbo
        Pascal (entiers sans espace, réels en notation scientifique...)."""
        w = d = None
        if a[0] == "fmt":
            a, w, d = a[1], a[2], a[3]
        text, t = self.ex(a)
        if t[0] in ("int", "enum"):
            self.use("TPINT$")
            s = "TPINT$(%s)" % text
        elif t[0] == "real":
            if d is not None:
                self.use("TPFIX$")
                s = "TPFIX$(%s, %s)" % (text, self.value(d, INT))
            else:
                self.use("TPSCI$")
                digits = "10" if w is None else "%s - 7" % self.value(w, INT)
                if w is not None:
                    try:
                        digits = str(max(1, self.const_int(w) - 7))
                    except PasError:
                        pass
                s = "TPSCI$(%s, %s)" % (text, digits)
        elif t[0] == "bool":
            self.use("TPBOOL$")
            s = "TPBOOL$(%s)" % text
        elif is_text(t):
            s = text
        else:
            self.err("write : impossible d'écrire un %s" % tname(t), line)
        if w is not None:
            self.use("TPPAD$")
            s = "TPPAD$(%s, %s)" % (s, self.value(w, INT))
        return s

    def read(self, args, line):
        if args and args[0][0] == "desig" and args[0][1] == "kbd" and not args[0][2]:
            for a in args[1:]:                    # read(kbd, c) : une touche, sans écho
                acc = self.access(a)
                self.use("TPRK$")
                self.emit("%s = TPRK$" % self.scalar(acc), line)
            return
        if not args:
            v = self.temp("$")
            self.emit('LINE INPUT "", %s' % v, line)
            return
        for a in args:
            acc = self.access(a)
            t = acc["type"]
            target = self.scalar(acc)
            if t[0] == "str":
                self.emit('LINE INPUT "", %s' % target, line)
            elif t[0] == "char":
                v = self.temp("$")
                self.emit('LINE INPUT "", %s' % v, line)
                self.emit("%s = LEFT$(%s, 1)" % (target, v), line)
            elif t[0] in ("int", "real"):
                self.emit('INPUT "", %s' % target, line)
            else:
                self.err("read : impossible de lire un %s" % tname(t), line)

    # ==================================================== accès aux variables
    def access(self, d):
        """Désignateur -> accès : symbole de base, champs, indices, type."""
        if d[0] != "desig":
            self.err("variable attendue")
        _, name, sels, line = d
        for w in reversed(self.with_stack):       # with r do : champs de r d'abord
            if w["type"][0] == "record" and any(f == name for f, _ in w["type"][1]):
                ft = dict(w["type"][1])[name]
                acc = dict(w, path=w["path"] + (name,), type=ft)
                return self.selectors(acc, sels, line)
        if name in ("mem", "port") and self.lookup(name, line, quiet=True) is None:
            if len(sels) != 1 or sels[0][0] != "idx":
                self.err("%s[adresse] attendu" % name.capitalize(), line)
            return {"type": INT, "special": (name, self.value(sels[0][1], INT))}
        sym = self.lookup(name, line)
        if sym["cls"] != "var":
            self.err("%s n'est pas une variable" % name, line)
        return self.selectors(self.var_access(sym, [], line), sels, line)

    def var_access(self, sym, sels, line):
        return {"sym": sym, "path": (), "idx": (), "type": sym["type"]}

    def selectors(self, acc, sels, line):
        for kind, v in sels:
            t = acc["type"]
            if kind == "idx":
                if t[0] == "array":
                    lo = t[1]
                    i, it = self.ex(v)
                    if it[0] == "char":
                        i = "ASC(%s)" % i
                    elif not is_ordinal(it):
                        self.err("indice de type ordinal attendu", line)
                    if lo:
                        i = "%s - %d" % (i, lo) if lo > 0 else "%s + %d" % (i, -lo)
                    acc = dict(acc, idx=acc["idx"] + (i,), type=t[3])
                elif t[0] == "str":
                    s = self.scalar(acc)
                    i = self.value(v, INT)
                    acc = {"type": CHAR, "strindex": (s, i), "text": "MID$(%s, %s, 1)" % (s, i)}
                else:
                    self.err("[ ] : tableau ou chaîne attendu", line)
            elif kind == "fld":
                if t[0] != "record":
                    self.err(".%s : record attendu" % v, line)
                f = dict(t[1])
                if v not in f:
                    self.err("champ inconnu : %s" % v, line)
                acc = dict(acc, path=acc["path"] + (v,), type=f[v])
            else:
                self.err("( ) inattendu après une variable", line)
        return acc

    def leaf_text(self, acc, path, lt, extra_idx=()):
        """Variable QuickBASIC d'une feuille d'un accès (record ou tableau)."""
        sym = acc["sym"]
        full = acc["path"] + tuple(path)
        n = self.leaf_name(sym["qb"], full, lt)
        idx = list(acc["idx"]) + list(extra_idx)
        return n + ("(%s)" % ", ".join(idx) if idx else "")

    def scalar(self, acc):
        """Variable QuickBASIC d'un accès à une valeur simple."""
        if "text" in acc:
            if acc.get("strindex"):
                return acc["text"]
        if acc.get("special"):
            kind, arg = acc["special"]
            return ("PEEK(%s)" if kind == "mem" else "INP(%s)") % arg
        if not is_scalar(acc["type"]):
            self.err("valeur simple attendue (pas un %s)" % tname(acc["type"]))
        sym = acc["sym"]
        n = self.leaf_name(sym["qb"], acc["path"], acc["type"])
        return n + ("(%s)" % ", ".join(acc["idx"]) if acc["idx"] else "")

    def lvalue(self, d):
        acc = self.access(d)
        return self.scalar(acc), acc["type"]

    # ======================================================= expressions
    def cond(self, e):
        text, t = self.ex(e)
        if t[0] not in ("bool", "int"):
            self.err("condition booléenne attendue")
        return text

    def value(self, e, want):
        """Expression convertie pour une destination de type want."""
        text, t = self.ex(e)
        if want[0] == "real" and t[0] in ("int", "real"):
            return text
        if want[0] in ("int", "enum", "bool") and t[0] in ("int", "enum", "bool"):
            return text
        if want[0] == "int" and t[0] == "real":
            self.err("réel affecté à un entier : utilisez Trunc ou Round")
        if is_text(want) and is_text(t):
            return text
        if want == t:
            return text
        self.err("type incompatible : %s attendu, %s trouvé" % (tname(want), tname(t)))

    def byval(self, e, want):
        return "(%s)" % self.value(e, want)

    def ex(self, e):
        """Expression -> (texte QuickBASIC complètement parenthésé, type)."""
        k = e[0]
        if k == "num":
            if e[2] == "int":
                return self.literal(e[1])
            return self.literal(float(e[1]))
        if k == "str":
            return self.literal(e[1])
        if k == "paren":
            text, t = self.ex(e[1])
            return "(%s)" % text, t
        if k == "un":
            text, t = self.ex(e[2])
            if e[1] == "-":
                if t[0] not in ("int", "real"):
                    self.err("- : nombre attendu")
                return "(-%s)" % text, t
            if t[0] not in ("bool", "int"):
                self.err("not : booléen ou entier attendu")
            return "(NOT %s)" % text, t
        if k == "bin":
            return self.binary(e)
        if k == "in":
            return self.membership(e)
        if k == "desig":
            return self.designator(e)
        if k == "fmt":
            self.err("« : » seulement dans write / str")
        raise AssertionError(e)

    def binary(self, e):
        _, op, a, b = e
        ta, tb = self.ex(a), self.ex(b)
        (x, t1), (y, t2) = ta, tb
        num = ("int", "real", "enum")
        if op in ("=", "<>", "<", ">", "<=", ">="):
            if is_text(t1) and is_text(t2) or (t1[0] in num and t2[0] in num) or \
                    (t1[0] == t2[0] == "bool"):
                return "(%s %s %s)" % (x, op, y), BOOL
            self.err("comparaison de %s et de %s" % (tname(t1), tname(t2)))
        if op == "+" and is_text(t1) and is_text(t2):
            return "(%s + %s)" % (x, y), string_t()
        if op in ("and", "or", "xor"):
            if t1[0] == t2[0] == "bool":
                return "(%s %s %s)" % (x, op.upper(), y), BOOL
            if t1[0] == t2[0] == "int":
                return "(%s %s %s)" % (x, op.upper(), y), INT
            self.err("%s : booléens ou entiers attendus" % op)
        if t1[0] not in ("int", "real") or t2[0] not in ("int", "real"):
            self.err("%s : nombres attendus (%s, %s)" % (op, tname(t1), tname(t2)))
        real = REAL if REAL in (t1, t2) else INT
        if op == "/":
            return "(CDBL(%s) / %s)" % (x, y), REAL
        if op in ("div", "mod", "shl", "shr"):
            if real == REAL:
                self.err("%s : entiers attendus" % op)
            if op in ("shl", "shr"):
                try:
                    n = self.const_int(b)
                except PasError:
                    self.err("%s : décalage constant attendu" % op)
                if op == "shl":
                    return "(%s * %d)" % (x, 2 ** n), INT
                return "(%s \\ %d)" % (x, 2 ** n), INT
            return "(%s %s %s)" % (x, "\\" if op == "div" else "MOD", y), INT
        return "(%s %s %s)" % (x, op, y), real

    def membership(self, e):
        _, a, items = e
        x, t = self.ex(a)
        if not is_ordinal(t):
            self.err("in : valeur de type ordinal attendue")
        conds = []
        for lo, hi in items:
            v = self.literal(self.const_value(lo))[0]
            if hi is None:
                conds.append("(%s = %s)" % (x, v))
            else:
                conds.append("(%s >= %s AND %s <= %s)" % (x, v, x, self.literal(
                    self.const_value(hi))[0]))
        return ("(%s)" % " OR ".join(conds) if conds else "0"), BOOL

    def designator(self, e):
        _, name, sels, line = e
        args = sels[0][1] if sels and sels[0][0] == "args" else None
        rest = sels[1:] if args is not None else sels
        for w in reversed(self.with_stack):
            if w["type"][0] == "record" and any(f == name for f, _ in w["type"][1]):
                acc = self.access(e)
                return self.acc_value(acc), acc["type"]
        sym = self.lookup(name, line, quiet=True)
        if sym is None:
            r = self.builtin_func(name, args, line)
            if r is not None:
                if rest:
                    self.err("( ) ou [ ] inattendu après %s" % name, line)
                return r
            if name in ("mem", "port"):
                acc = self.access(e)
                return self.scalar(acc), INT
            self.err("identificateur inconnu : %s" % name, line)
        cls = sym["cls"]
        if cls == "const":
            if sels:
                self.err("%s est une constante" % name, line)
            text, t = self.literal(sym["value"])
            return text, sym["type"] if sym["type"][0] == "enum" else t
        if cls == "func":
            if rest:
                self.err("( ) ou [ ] inattendu après l'appel de %s" % name, line)
            return self.call_text(sym, args or [], line), sym["ret"]
        if cls == "proc":
            self.err("%s est une procédure : elle ne rend pas de valeur" % name, line)
        if cls == "type":
            if args is not None and len(args) == 1:    # transtypage : integer(c)...
                text, t = self.ex(args[0])
                tt = sym["type"]
                if tt[0] in ("int", "enum") and t[0] == "char":
                    return "ASC(%s)" % text, tt
                if tt[0] == "char" and t[0] in ("int", "enum"):
                    return "CHR$(%s)" % text, CHAR
                return text, tt
            self.err("%s est un type" % name, line)
        acc = self.access(e)
        return self.acc_value(acc), acc["type"]

    def acc_value(self, acc):
        if acc.get("strindex"):
            return acc["text"]
        return self.scalar(acc)

    # ---------------------------------------------------------- appels
    def call_text(self, sym, args, line):
        text = self.call_args(sym, args, line)
        return sym["qbfull"] + ("(%s)" % text if text else "")

    def call_args(self, sym, args, line):
        params = sym["params"]
        if len(args) != len(params):
            self.err("%s : %d paramètre(s) attendu(s), %d donné(s)"
                     % (sym["name"], len(params), len(args)), line)
        out = []
        for (pn, pt, byref), a in zip(params, args):
            if is_scalar(pt):
                if byref:
                    acc = self.access(a) if a[0] == "desig" else None
                    if acc is None or acc.get("strindex") or acc.get("special"):
                        self.err("%s : paramètre var %s : variable attendue"
                                 % (sym["name"], pn), line)
                    if not (self.same_type(acc["type"], pt) or
                            (pt[0] in ("int", "enum") and acc["type"][0] in ("int", "enum"))):
                        self.err("%s : paramètre var %s : %s attendu" % (sym["name"], pn,
                                                                        tname(pt)), line)
                    out.append(self.scalar(acc))
                else:
                    out.append("(%s)" % self.value(a, pt))
                continue
            acc = self.access(a) if a[0] == "desig" else None
            if acc is None or not self.same_type(acc["type"], pt):
                self.err("%s : paramètre %s : %s du même type attendu"
                         % (sym["name"], pn, tname(pt)), line)
            if not byref and pt[0] == "array":
                self.warn("tableau passé par valeur : passé par adresse sur le X-07 "
                          "(une modification dans la procédure se voit chez l'appelant)")
            for path, lt, dims in leaves(pt):
                if dims and acc["idx"]:
                    self.err("%s : partie de tableau passée en paramètre : non prise en charge"
                             % sym["name"], line)
                n = self.leaf_text(acc, path, lt)
                if dims:
                    out.append(n.split("(")[0] + "()")
                elif byref:
                    out.append(n)
                else:
                    out.append("(%s)" % n)
        return ", ".join(out)

    # ------------------------------------------------- fonctions standard
    def builtin_func(self, name, args, line):
        n = len(args) if args is not None else 0
        a = args or []

        def one(t=None):
            if n != 1:
                self.err("%s : un paramètre attendu" % name, line)
            return self.ex(a[0])
        if name in ("true", "false"):
            return ("-1" if name == "true" else "0"), BOOL
        if name == "maxint":
            return "32767", INT
        if name == "pi":
            return "3.14159265358979#", REAL
        if name in ("keypressed",):
            self.use("TPKP%")
            return "TPKP%", BOOL
        if name == "readkey":
            self.use("TPRK$")
            return "TPRK$", CHAR
        if name == "wherex":
            return "POS(0)", INT
        if name == "wherey":
            return "CSRLIN", INT
        if name == "random":
            if n == 0:
                return "RND", REAL
            return "INT(RND * %s)" % self.value(a[0], INT), INT
        if name in ("abs", "sqr"):
            x, t = one()
            if t[0] not in ("int", "real"):
                self.err("%s : nombre attendu" % name, line)
            if name == "abs":
                return "ABS(%s)" % x, t
            return "(%s ^ 2)" % x if t == REAL else "(%s * %s)" % (x, x), t
        if name in ("sqrt", "sin", "cos", "arctan", "exp", "ln"):
            x, t = one()
            if t[0] not in ("int", "real"):
                self.err("%s : nombre attendu" % name, line)
            f = {"sqrt": "SQR", "arctan": "ATN", "ln": "LOG"}.get(name, name.upper())
            return "%s(CDBL(%s))" % (f, x), REAL
        if name in ("trunc", "round", "frac", "int"):
            x, t = one()
            if t[0] not in ("int", "real"):
                self.err("%s : nombre attendu" % name, line)
            if name == "trunc":
                return "FIX(%s)" % x, INT
            if name == "round":
                return "(SGN(%s) * INT(ABS(%s) + .5#))" % (x, x), INT
            if name == "frac":
                return "(%s - FIX(%s))" % (x, x), REAL
            return "CDBL(FIX(%s))" % x, REAL
        if name == "odd":
            x, t = one()
            return "((%s AND 1) <> 0)" % x, BOOL
        if name == "ord":
            x, t = one()
            if t[0] == "char":
                return "ASC(%s)" % x, INT
            if t[0] == "bool":
                return "(-%s)" % x, INT
            if t[0] in ("int", "enum"):
                return x, INT
            self.err("ord : valeur de type ordinal attendue", line)
        if name == "chr":
            x, t = one()
            return "CHR$(%s)" % x, CHAR
        if name in ("succ", "pred"):
            x, t = one()
            op = "+" if name == "succ" else "-"
            if t[0] == "char":
                return "CHR$(ASC(%s) %s 1)" % (x, op), CHAR
            if t[0] in ("int", "enum"):
                return "(%s %s 1)" % (x, op), t
            self.err("%s : valeur de type ordinal attendue" % name, line)
        if name == "length":
            x, t = one()
            if not is_text(t):
                self.err("length : chaîne attendue", line)
            return "LEN(%s)" % x, INT
        if name == "copy":
            if n != 3:
                self.err("copy(chaîne, position, nombre) attendu", line)
            return "MID$(%s, %s, %s)" % (self.value(a[0], string_t()), self.value(a[1], INT),
                                         self.value(a[2], INT)), string_t()
        if name == "concat":
            if n < 1:
                self.err("concat : au moins une chaîne attendue", line)
            return "(%s)" % " + ".join(self.value(x, string_t()) for x in a), string_t()
        if name == "pos":
            if n != 2:
                self.err("pos(motif, chaîne) attendu", line)
            self.use("TPPOS%")
            return "TPPOS%%(%s, %s)" % (self.byval(a[0], string_t()),
                                        self.byval(a[1], string_t())), INT
        if name == "upcase":
            x, t = one()
            self.use("TPUPC$")
            return "TPUPC$((%s))" % x, CHAR
        if name in ("lo", "hi"):
            x, t = one()
            return ("(%s AND 255)" % x if name == "lo" else "((%s \\ 256) AND 255)" % x), INT
        return None


def translate(text):
    """Programme Pascal -> (texte QuickBASIC, avertissements, correspondance
    ligne QuickBASIC (1, 2...) -> ligne Pascal)."""
    tr = Translator(text)
    lines = tr.translate()
    qb = "\n".join(t for t, _ in lines) + "\n"
    linemap = {k: l for k, (_, l) in enumerate(lines, 1)}
    return qb, tr.warnings, linemap


def pascal_line(msg, linemap):
    """Message d'erreur de qbcomp (« ligne n ») -> ligne du programme Pascal."""
    m = re.search(r"ligne (\d+)", msg)
    if not m:
        return msg
    n = linemap.get(int(m.group(1)))
    return msg[:m.start()] + ("ligne %d (Pascal)" % n if n else m.group()) + msg[m.end():]


def compile_pascal(text, name="PROG", org=0x1000, **opts):
    """Programme Pascal -> (texte assembleur, compilateur, avertissements,
    correspondance des lignes)."""
    from . import qbcomp
    from .qbasic import QBError
    qb, warns, linemap = translate(text)
    try:
        asm, comp, w2 = qbcomp.compile_qbasic(qb, name, org, **opts)
    except QBError as e:
        raise PasError("compilation : %s" % pascal_line(str(e), linemap))
    return asm, comp, warns + w2, linemap
