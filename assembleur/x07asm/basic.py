"""Compilateur BASIC -> assembleur Z80 pour le Canon X-07.

Dialecte : celui du BASIC du X-07 (Microsoft), avec des nombres ENTIERS
16 bits (-32768..32767) et des chaînes de STRCAP caractères au plus.
Le source produit s'assemble avec x07asm.asm ; il se lance par EXEC.

Voir COMPILATEUR.md pour la liste des instructions reconnues.
"""
import re

from . import runtime

# ======================================================================
#  Analyse lexicale
# ======================================================================

KEYWORDS = sorted("""
END FOR NEXT DATA INPUT DIM READ LET GOTO GOSUB RUN IF RESTORE RETURN REM STOP
ELSE THEN TO STEP ON OUT POKE PRINT LPRINT CLEAR CLS LOCATE PSET PRESET LINE
CIRCLE BEEP EXEC DEF FN DEFINT DEFSNG DEFDBL DEFSTR WHILE WEND TR MOTOR ERROR
RESUME LIST LLIST CONT NEW CONSOLE COLOR OFF SLEEP DIR DELETE FSET PAINT LOAD
SAVE INIT ERASE CLOAD CSAVE SCREEN USING STRING$ INSTR INKEY$ INP VARPTR USR
SNS ALM$ DATE$ TIME$ START$ FONT$ KEY$ NOT EQV IMP AND OR XOR MOD SGN INT ABS
FRE POS SQR RND LOG EXP COS SIN TAN ATN PEEK CINT CSNG CDBL FIX LEN HEX$ STR$
VAL ASC CHR$ TKEY LEFT$ RIGHT$ MID$ CSRLIN STICK STRIG POINT ERL ERR TAB( SPC(
""".split(), key=len, reverse=True)

OPS2 = ("<>", "<=", ">=", "=<", "=>", "><")
OPS1 = "+-*/\\^=<>(),;:"


class CompileError(Exception):
    def __init__(self, msg, line=None):
        self.msg, self.line = msg, line
        super().__init__(("ligne %s : " % line if line is not None else "") + msg)


class Tok:
    __slots__ = ("kind", "val")

    def __init__(self, kind, val):
        self.kind, self.val = kind, val

    def __repr__(self):
        return "%s:%r" % (self.kind, self.val)


def _kw_at(up, i):
    for k in KEYWORDS:
        if up.startswith(k, i):
            return k
    return None


def tokenize(text, line=None):
    """Découpe une ligne (sans son numéro) en lexèmes."""
    toks = []
    up = text.upper()
    i, n = 0, len(text)
    while i < n:
        c = text[i]
        if c in " \t":
            i += 1
            continue
        if c == '"':
            j = text.find('"', i + 1)
            if j < 0:
                j = n
            toks.append(Tok("str", text[i + 1:j]))
            i = j + 1
            continue
        if c.isdigit() or c == ".":
            j = i
            while j < n and text[j].isdigit():
                j += 1
            if j < n and text[j] in ".Ee" and not (text[j] in "Ee" and _kw_at(up, j)):
                raise CompileError("nombre décimal non géré (entiers seulement) : %s"
                                   % text[i:j + 3], line)
            if j < n and text[j] in "%!#":
                j += 1
            toks.append(Tok("num", int(text[i:j].rstrip("%!#") or "0")))
            i = j
            continue
        if c == "&":
            base, j = 8, i + 1
            if j < n and up[j] == "H":
                base, j = 16, j + 1
            elif j < n and up[j] == "O":
                j += 1
            k = j
            digits = "0123456789ABCDEF"[:base]
            while k < n and up[k] in digits:
                k += 1
            if k == j:
                raise CompileError("nombre hexadécimal incorrect", line)
            toks.append(Tok("num", int(up[j:k], base)))
            i = k
            continue
        if c == "'":
            break
        if c == "?":
            toks.append(Tok("kw", "PRINT"))
            i += 1
            continue
        if c.isalpha():
            kw = _kw_at(up, i)
            if kw:
                i += len(kw)
                if kw == "REM":
                    break
                if kw in ("TAB(", "SPC("):
                    toks.append(Tok("kw", kw[:-1]))
                    toks.append(Tok("op", "("))
                    continue
                toks.append(Tok("kw", kw))
                if kw == "DATA":
                    j, q = i, False
                    while j < n and (q or text[j] != ":"):
                        if text[j] == '"':
                            q = not q
                        j += 1
                    toks.append(Tok("data", text[i:j]))
                    i = j
                continue
            j = i + 1
            while j < n and up[j].isalnum() and not (up[j].isalpha() and _kw_at(up, j)):
                j += 1
            if j < n and text[j] in "$%!#":
                j += 1
            name = up[i:j]
            if name[-1] in "!#":
                name = name[:-1]
            toks.append(Tok("id", name))
            i = j
            continue
        if text[i:i + 2] in OPS2:
            op = {"=<": "<=", "=>": ">=", "><": "<>"}.get(text[i:i + 2], text[i:i + 2])
            toks.append(Tok("op", op))
            i += 2
            continue
        if c in OPS1:
            toks.append(Tok("op", c))
            i += 1
            continue
        raise CompileError("caractère inattendu : %r" % c, line)
    toks.append(Tok("eol", None))
    return toks


def split_data(raw):
    """Éléments d'une ligne DATA (texte brut)."""
    items, cur, q, quoted = [], [], False, False
    for c in raw:
        if c == '"':
            q = not q
            quoted = True
            continue
        if c == "," and not q:
            items.append("".join(cur) if quoted else "".join(cur).strip())
            cur, quoted = [], False
            continue
        cur.append(c)
    items.append("".join(cur) if quoted else "".join(cur).strip())
    return items


# ======================================================================
#  Analyse syntaxique
# ======================================================================
#  Expressions : ('num',v) ('str',s) ('var',nom) ('arr',nom,[indices])
#                ('un',op,e) ('bin',op,a,b) ('call',fonction,[args])
#                ('fn',nom,[args])

NUM_FUNCS = {   # nom : types des arguments
    "ABS": "n", "SGN": "n", "INT": "n", "FIX": "n", "CINT": "n", "CSNG": "n",
    "CDBL": "n", "PEEK": "n", "INP": "n", "RND": "n", "LEN": "s", "ASC": "s",
    "VAL": "s", "POINT": "nn", "STICK": "n", "STRIG": "n", "CSRLIN": "",
    "POS": "n",
}
STR_FUNCS = {
    "CHR$": "n", "STR$": "n", "HEX$": "n", "LEFT$": "sn", "RIGHT$": "sn",
    "MID$": "sn", "STRING$": "n?", "INKEY$": "",
}
OPTIONAL_LAST = {"MID$": "n"}       # MID$(s,p[,n])

REL = ("=", "<>", "<", ">", "<=", ">=")


def etype(e):
    k = e[0]
    if k in ("num", "un", "fn"):
        return "n"
    if k == "str":
        return "s"
    if k in ("var", "arr"):
        return "s" if e[1].endswith("$") else "n"
    if k == "call":
        return "s" if e[1] in STR_FUNCS else "n"
    if k == "bin":
        if e[1] in REL:
            return "n"
        return etype(e[2]) if e[1] == "+" else "n"
    raise ValueError(e)


class Parser:
    def __init__(self, toks, line):
        self.t, self.i, self.line = toks, 0, line

    def err(self, msg):
        raise CompileError(msg, self.line)

    @property
    def cur(self):
        return self.t[self.i]

    def next(self):
        t = self.t[self.i]
        self.i += 1
        return t

    def isop(self, v):
        return self.cur.kind == "op" and self.cur.val == v

    def iskw(self, *v):
        return self.cur.kind == "kw" and self.cur.val in v

    def accept_op(self, v):
        if self.isop(v):
            self.i += 1
            return True
        return False

    def accept_kw(self, v):
        if self.iskw(v):
            self.i += 1
            return True
        return False

    def expect_op(self, v):
        if not self.accept_op(v):
            self.err("« %s » attendu%s" % (v, self._near()))

    def expect_kw(self, v):
        if not self.accept_kw(v):
            self.err("« %s » attendu%s" % (v, self._near()))

    def _near(self):
        c = self.cur
        if c.kind == "eol":
            return " (fin de ligne)"
        return " près de « %s »" % c.val

    def at_end(self):
        return self.cur.kind == "eol" or self.isop(":") or self.iskw("ELSE")

    # ---------------------------------------------------- expressions
    def expr(self):
        e = self.or_()
        while self.iskw("XOR"):
            self.next()
            e = ("bin", "XOR", e, self.or_())
        return self._check(e)

    def nexpr(self):
        e = self.expr()
        if etype(e) != "n":
            self.err("expression numérique attendue")
        return e

    def sexpr(self):
        e = self.expr()
        if etype(e) != "s":
            self.err("expression chaîne attendue")
        return e

    def _check(self, e):
        return e

    def or_(self):
        e = self.and_()
        while self.iskw("OR"):
            self.next()
            e = self._binn("OR", e, self.and_())
        return e

    def and_(self):
        e = self.not_()
        while self.iskw("AND"):
            self.next()
            e = self._binn("AND", e, self.not_())
        return e

    def not_(self):
        if self.accept_kw("NOT"):
            e = self.not_()
            self._needn(e)
            return ("un", "NOT", e)
        return self.rel()

    def rel(self):
        e = self.add()
        while self.cur.kind == "op" and self.cur.val in REL:
            op = self.next().val
            b = self.add()
            if etype(e) != etype(b):
                self.err("comparaison entre une chaîne et un nombre")
            e = ("bin", op, e, b)
        return e

    def add(self):
        e = self.mod()
        while self.cur.kind == "op" and self.cur.val in "+-":
            op = self.next().val
            b = self.mod()
            if op == "+" and etype(e) == "s" and etype(b) == "s":
                e = ("bin", "+", e, b)
            else:
                e = self._binn(op, e, b)
        return e

    def mod(self):
        e = self.idiv()
        while self.accept_kw("MOD"):
            e = self._binn("MOD", e, self.idiv())
        return e

    def idiv(self):
        e = self.mul()
        while self.accept_op("\\"):
            e = self._binn("/", e, self.mul())
        return e

    def mul(self):
        e = self.neg()
        while self.cur.kind == "op" and self.cur.val in "*/":
            op = self.next().val
            e = self._binn(op, e, self.neg())
        return e

    def neg(self):
        if self.accept_op("-"):
            e = self.neg()
            self._needn(e)
            return ("un", "-", e)
        if self.accept_op("+"):
            return self.neg()
        return self.pow()

    def pow(self):
        e = self.atom()
        while self.accept_op("^"):
            e = self._binn("^", e, self.atom())
        return e

    def _needn(self, e):
        if etype(e) != "n":
            self.err("opération numérique sur une chaîne")

    def _binn(self, op, a, b):
        self._needn(a)
        self._needn(b)
        return ("bin", op, a, b)

    def atom(self):
        t = self.cur
        if t.kind == "num":
            self.next()
            if t.val > 65535:
                self.err("nombre trop grand : %d" % t.val)
            return ("num", t.val - 65536 if t.val > 32767 else t.val)
        if t.kind == "str":
            self.next()
            return ("str", t.val)
        if self.accept_op("("):
            e = self.expr()
            self.expect_op(")")
            return e
        if t.kind == "kw":
            name = t.val
            if name == "FN":
                self.next()
                if self.cur.kind != "id":
                    self.err("nom de fonction attendu après FN")
                fname = self.next().val
                args = []
                if self.accept_op("("):
                    args = self._args()
                return ("fn", fname, args)
            if name in NUM_FUNCS or name in STR_FUNCS:
                self.next()
                sig = NUM_FUNCS.get(name, STR_FUNCS.get(name))
                args = []
                if sig:
                    self.expect_op("(")
                    args = self._args()
                elif self.accept_op("("):        # CSRLIN, INKEY$ sans argument
                    self.expect_op(")")
                self._check_args(name, sig, args)
                return ("call", name, args)
            self.err("« %s » inattendu dans une expression%s"
                     % (name, " (fonction non gérée)" if name.endswith("$") or name in
                        ("SQR", "SIN", "COS", "TAN", "ATN", "LOG", "EXP", "INSTR",
                         "FRE", "VARPTR", "USR", "ERR", "ERL", "TKEY", "SNS") else ""))
        if t.kind == "id":
            self.next()
            if self.accept_op("("):
                return ("arr", t.val, self._args())
            return ("var", t.val)
        self.err("expression attendue%s" % self._near())

    def _args(self):
        args = [self.expr()]
        while self.accept_op(","):
            args.append(self.expr())
        self.expect_op(")")
        return args

    def _check_args(self, name, sig, args):
        opt = name in OPTIONAL_LAST
        lo = len(sig) - sig.count("?")
        if not (lo <= len(args) <= len(sig) + opt):
            self.err("nombre d'arguments incorrect pour %s" % name)
        for k, a in enumerate(args):
            want = sig[k] if k < len(sig) else "n"
            if want != "?" and etype(a) != want:
                self.err("argument %d de %s : %s attendu" % (
                    k + 1, name, "nombre" if want == "n" else "chaîne"))

    # ---------------------------------------------------- instructions
    def statements(self):
        out = []
        while True:
            if self.cur.kind == "eol" or self.iskw("ELSE"):
                return out
            if self.accept_op(":"):
                continue
            out.append(self.statement())
            if not self.at_end():
                self.err("fin d'instruction attendue%s" % self._near())

    def target(self):
        t = self.cur
        if t.kind != "id":
            self.err("variable attendue%s" % self._near())
        self.next()
        if self.accept_op("("):
            return ("arr", t.val, self._args())
        return ("var", t.val)

    def line_number(self):
        t = self.cur
        if t.kind != "num":
            self.err("numéro de ligne attendu%s" % self._near())
        self.next()
        return t.val

    def statement(self):
        t = self.cur
        if t.kind == "id":
            return self._let()
        if t.kind != "kw":
            self.err("instruction attendue%s" % self._near())
        k = self.next().val
        m = getattr(self, "st_" + k.replace("$", "S"), None)
        if m is None:
            self.err("instruction non gérée par le compilateur : %s" % k)
        return m()

    def _let(self):
        tgt = self.target()
        self.expect_op("=")
        e = self.expr()
        if etype(e) != etype(tgt):
            self.err("types incompatibles dans l'affectation")
        return ("let", tgt, e)

    def st_LET(self):
        return self._let()

    def st_PRINT(self):
        items = []
        while not self.at_end():
            if self.accept_op(";"):
                items.append(("sep", ";"))
            elif self.accept_op(","):
                items.append(("sep", ","))
            elif self.iskw("TAB", "SPC"):
                k = self.next().val
                self.expect_op("(")
                e = self.nexpr()
                self.expect_op(")")
                items.append((k.lower(), e))
            else:
                items.append(("expr", self.expr()))
        nl = not items or items[-1][0] not in ("sep", "tab", "spc") or \
            (items[-1][0] in ("tab", "spc") and False)
        if items and items[-1][0] in ("tab", "spc"):
            nl = True
        return ("print", items, nl)

    def st_IF(self):
        cond = self.nexpr()
        if self.accept_kw("GOTO"):
            then = [("goto", self.line_number())]
        else:
            self.expect_kw("THEN")
            if self.cur.kind == "num":
                then = [("goto", self.line_number())]
            else:
                then = self.statements()
        els = []
        if self.accept_kw("ELSE"):
            if self.cur.kind == "num":
                els = [("goto", self.line_number())]
            else:
                els = self.statements()
        return ("if", cond, then, els)

    def st_GOTO(self):
        return ("goto", self.line_number())

    def st_GOSUB(self):
        return ("gosub", self.line_number())

    def st_RETURN(self):
        return ("return",)

    def st_END(self):
        return ("end",)

    def st_STOP(self):
        return ("end",)

    def st_FOR(self):
        v = self.target()
        if v[0] != "var" or v[1].endswith("$"):
            self.err("variable numérique simple attendue après FOR")
        self.expect_op("=")
        a = self.nexpr()
        self.expect_kw("TO")
        b = self.nexpr()
        s = self.nexpr() if self.accept_kw("STEP") else ("num", 1)
        return ("for", v[1], a, b, s)

    def st_NEXT(self):
        names = []
        if not self.at_end():
            names.append(self.target()[1])
            while self.accept_op(","):
                names.append(self.target()[1])
        return ("next", names)

    def st_WHILE(self):
        return ("while", self.nexpr())

    def st_WEND(self):
        return ("wend",)

    def st_DIM(self):
        decls = []
        while True:
            t = self.target()
            if t[0] != "arr":
                self.err("DIM : tableau attendu")
            dims = []
            for e in t[2]:
                if e[0] != "num" or e[1] < 0:
                    self.err("DIM : dimension constante attendue")
                dims.append(e[1])
            decls.append((t[1], dims))
            if not self.accept_op(","):
                return ("dim", decls)

    def st_CLS(self):
        return ("cls",)

    def st_LOCATE(self):
        x = self.nexpr()
        self.expect_op(",")
        y = self.nexpr()
        if self.accept_op(","):
            self.nexpr()                       # affichage du curseur : ignoré
        return ("locate", x, y)

    def st_POKE(self):
        a = self.nexpr()
        self.expect_op(",")
        return ("poke", a, self.nexpr())

    def st_OUT(self):
        a = self.nexpr()
        self.expect_op(",")
        return ("out", a, self.nexpr())

    def st_EXEC(self):
        return ("exec", self.nexpr())

    def st_BEEP(self):
        if self.at_end():
            return ("beep", None, None)
        a = self.nexpr()
        self.expect_op(",")
        return ("beep", a, self.nexpr())

    def _point(self):
        self.expect_op("(")
        x = self.nexpr()
        self.expect_op(",")
        y = self.nexpr()
        self.expect_op(")")
        return x, y

    def st_PSET(self):
        return ("t6", 0x11, list(self._point()))

    def st_PRESET(self):
        return ("t6", 0x12, list(self._point()))

    def st_LINE(self):
        a = self._point()
        self.expect_op("-")
        b = self._point()
        return ("t6", 0x14, list(a + b))

    def st_CIRCLE(self):
        a = self._point()
        self.expect_op(",")
        return ("t6", 0x15, list(a) + [self.nexpr()])

    def st_INPUT(self):
        prompt, q = None, True
        if self.cur.kind == "str":
            prompt = self.next().val
            if self.accept_op(","):
                q = False
            else:
                self.expect_op(";")
        tg = [self.target()]
        while self.accept_op(","):
            tg.append(self.target())
        return ("input", prompt, q, tg)

    def st_READ(self):
        tg = [self.target()]
        while self.accept_op(","):
            tg.append(self.target())
        return ("read", tg)

    def st_DATA(self):
        raw = self.next().val
        return ("data", split_data(raw))

    def st_RESTORE(self):
        if self.cur.kind == "num":
            return ("restore", self.line_number())
        return ("restore", None)

    def st_ON(self):
        e = self.nexpr()
        if self.accept_kw("GOTO"):
            kind = "goto"
        else:
            self.expect_kw("GOSUB")
            kind = "gosub"
        lines = [self.line_number()]
        while self.accept_op(","):
            lines.append(self.line_number())
        return ("on", e, kind, lines)

    def st_DEF(self):
        self.expect_kw("FN")
        if self.cur.kind != "id":
            self.err("nom de fonction attendu")
        name = self.next().val
        if name.endswith("$"):
            self.err("fonctions chaîne (DEF FN...$) non gérées")
        params = []
        if self.accept_op("("):
            while True:
                p = self.target()
                if p[0] != "var" or p[1].endswith("$"):
                    self.err("paramètre numérique attendu")
                params.append(p[1])
                if not self.accept_op(","):
                    break
            self.expect_op(")")
        self.expect_op("=")
        return ("deffn", name, params, self.nexpr())

    def _ignore(self):
        while not self.at_end():
            self.next()
        return ("nop",)

    st_CLEAR = st_DEFINT = st_DEFSNG = st_DEFDBL = _ignore

    def st_DEFSTR(self):
        self.err("DEFSTR non géré : utilisez des noms terminés par $")


# ======================================================================
#  Génération de code
# ======================================================================

_NUM_LINE = re.compile(r"^\s*(\d+)\s?(.*)$")


def _fold(e):
    """Calcul des sous-expressions constantes (arithmétique 16 bits)."""
    if e[0] == "un":
        a = _fold(e[2])
        if a[0] == "num":
            v = -a[1] if e[1] == "-" else ~a[1]
            return ("num", _s16(v))
        return ("un", e[1], a)
    if e[0] == "bin":
        a, b = _fold(e[2]), _fold(e[3])
        if a[0] == "num" and b[0] == "num":
            x, y, op = a[1], b[1], e[1]
            try:
                v = {"+": lambda: x + y, "-": lambda: x - y, "*": lambda: x * y,
                     "/": lambda: int(x / y), "MOD": lambda: x - y * int(x / y),
                     "AND": lambda: x & y, "OR": lambda: x | y, "XOR": lambda: x ^ y,
                     "=": lambda: -(x == y), "<>": lambda: -(x != y),
                     "<": lambda: -(x < y), ">": lambda: -(x > y),
                     "<=": lambda: -(x <= y), ">=": lambda: -(x >= y),
                     "^": lambda: x ** y if y >= 0 else 0}[op]()
                return ("num", _s16(v))
            except ZeroDivisionError:
                pass
        return ("bin", e[1], a, b)
    if e[0] in ("arr", "call", "fn"):
        return (e[0], e[1], [_fold(x) for x in e[2]])
    return e


def _s16(v):
    v &= 0xFFFF
    return v - 65536 if v > 32767 else v


def _label(name):
    return re.sub(r"[^A-Z0-9]", "_", name.replace("$", "").replace("%", "_I"))


class Compiler:
    def __init__(self, strcap=80, brk=True, debug=False, bounds=True):
        if not 1 <= strcap <= 254:
            raise CompileError("capacité des chaînes entre 1 et 254")
        self.strcap, self.brk, self.debug, self.bounds = strcap, brk, debug, bounds
        self.warnings = []

    # ---------------------------------------------------- lecture
    def parse(self, text):
        lines = []
        last = -1
        for n, raw in enumerate(text.splitlines(), 1):
            if not raw.strip():
                continue
            m = _NUM_LINE.match(raw)
            if m:
                num, body = int(m.group(1)), m.group(2)
                if num <= last:
                    raise CompileError("numéro de ligne %d non croissant" % num, num)
                last = num
            else:
                num, body = None, raw
            where = num if num is not None else "(source %d)" % n
            p = Parser(tokenize(body, where), where)
            stmts = p.statements()
            if p.iskw("ELSE"):
                p.err("ELSE sans IF")
            lines.append((num, stmts, raw.strip(), where))
        return lines

    # ---------------------------------------------------- compilation
    def compile(self, text, name="PROG", org=0x1000):
        self.lines = self.parse(text)
        self.code = []
        self.lits = {}
        self.vars = {}           # étiquette -> taille
        self.arrays = {}         # nom -> dimensions
        self.temps = set()
        self.used = set()
        self.tables = []
        self.fors = []
        self.whiles = []
        self.nlab = 0
        self.fns = {}
        self.fnparams = {}
        self.tmpbase = 0
        self.linenums = [l[0] for l in self.lines if l[0] is not None]
        self._prescan()

        for num, stmts, src, where in self.lines:
            self.where = where
            self.cur_line = num
            self.emit("")
            self.emit("; %s" % src.replace("\t", " "))
            if num is not None and num in self.targets:
                self.label("LN_%d" % num)
            if self.debug and num is not None:
                self.emit("LD   HL,%d" % num)
                self.emit("LD   (RT_LINE),HL")
                self.used.add("RT_LINE")
            for s in stmts:
                self.stmt(s)
        if self.fors:
            raise CompileError("FOR %s sans NEXT" % self.fors[-1]["var"], self.fors[-1]["line"])
        if self.whiles:
            raise CompileError("WHILE sans WEND", self.whiles[-1][1])
        self.emit("")
        self.emit("JP   RT_END")
        self.used.add("RT_END")
        self._gen_fns()
        return self._assemble_text(name, org)

    def _prescan(self):
        self.targets = set()
        self.data = []           # (ligne, texte)
        self.data_at = {}        # ligne -> indice du premier élément
        walk = []

        def visit(stmts, num):
            for s in stmts:
                walk.append((s, num))
                if s[0] == "if":
                    visit(s[2], num)
                    visit(s[3], num)

        for num, stmts, _, where in self.lines:
            visit(stmts, where)
        for s, where in walk:
            k = s[0]
            if k in ("goto", "gosub"):
                self._need_line(s[1], where)
                self.targets.add(s[1])
            elif k == "on":
                for n in s[3]:
                    self._need_line(n, where)
                    self.targets.add(n)
            elif k == "restore" and s[1] is not None:
                self._need_line(s[1], where)
            elif k == "dim":
                for name, dims in s[1]:
                    if name in self.arrays:
                        raise CompileError("tableau %s dimensionné deux fois" % name, where)
                    self.arrays[name] = dims
            elif k == "deffn":
                if s[1] in self.fns:
                    raise CompileError("FN%s défini deux fois" % s[1], where)
                self.fns[s[1]] = (s[2], _fold(s[3]), where)
            elif k == "data":
                if isinstance(where, int):
                    self.data_at.setdefault(where, len(self.data))
                for item in s[1]:
                    if len(item) > 254:
                        raise CompileError("élément DATA trop long", where)
                    self.data.append(item)

    def _need_line(self, n, where):
        if n not in self.linenums:
            raise CompileError("ligne %d inexistante" % n, where)

    def err(self, msg):
        raise CompileError(msg, self.where)

    # ---------------------------------------------------- émission
    def emit(self, s):
        self.code.append(("        " + s) if s and not s.startswith(";") else s)
        for r in runtime.refs(s):
            self.used.add(r)

    def label(self, name):
        self.code.append("%s:" % name)

    def newlabel(self):
        self.nlab += 1
        return "G_%d" % self.nlab

    def lit(self, s):
        if s not in self.lits:
            self.lits[s] = "LIT_%d" % (len(self.lits) + 1)
        return self.lits[s]

    def tmp(self, d):
        d += self.tmpbase
        self.temps.add(d)
        return "TMP_%d" % d

    def var(self, name):
        if name in self.fnparams:
            return self.fnparams[name]
        if name.endswith("$"):
            lab = "S_" + _label(name)
            self.vars[lab] = self.strcap + 1
        else:
            lab = "V_" + _label(name)
            self.vars[lab] = 2
        return lab

    def array(self, name, nidx):
        if name not in self.arrays:
            self.arrays[name] = [10] * nidx
            self.warnings.append("%s : tableau %s non dimensionné, DIM %s(%s) supposé"
                                 % (self.where, name, name, ",".join(["10"] * nidx)))
        dims = self.arrays[name]
        if len(dims) != nidx:
            self.err("tableau %s : %d indice(s) attendu(s)" % (name, len(dims)))
        lab = ("AS_" if name.endswith("$") else "AV_") + _label(name)
        count = 1
        for d in dims:
            count *= d + 1
        esz = self.strcap + 1 if name.endswith("$") else 2
        self.vars[lab] = count * esz
        return lab, dims, esz

    # ---------------------------------------------------- instructions
    def stmt(self, s):
        getattr(self, "s_" + s[0])(s)

    def s_nop(self, s):
        pass

    def s_data(self, s):
        pass

    def s_deffn(self, s):
        pass

    def s_dim(self, s):
        for name, dims in s[1]:
            self.array(name, len(dims))

    def s_let(self, s):
        tgt, e = s[1], _fold(s[2])
        if etype(tgt) == "n":
            self.gen_n(e, 0)
            if tgt[0] == "var":
                self.emit("LD   (%s),HL" % self.var(tgt[1]))
            else:
                const = self.const_addr(tgt)
                if const:
                    self.emit("LD   (%s),HL" % const)
                else:
                    self.emit("PUSH HL")
                    self.gen_addr(tgt, 0)
                    self.emit("POP  DE")
                    self.emit("LD   (HL),E")
                    self.emit("INC  HL")
                    self.emit("LD   (HL),D")
            return
        # chaîne
        if tgt[0] == "var":
            dest = self.var(tgt[1])
            if e[0] == "bin" and e[2] == ("var", tgt[1]):     # A$=A$+...
                src = self.sptr(e[3], 0)
                self.emit("LD   HL,%s" % dest)
                self.emit("LD   DE,%s" % src)
                self.emit("CALL RT_SCAT")
                return
            src = self.sptr(e, 0)
            self.emit("LD   HL,%s" % dest)
            self.emit("LD   DE,%s" % src)
            self.emit("CALL RT_SCOPY")
        else:
            src = self.sptr(e, 0)
            if src.startswith("TMP_") or e[0] == "arr":
                pass
            self.gen_addr(tgt, 1)
            self.emit("LD   DE,%s" % src)
            self.emit("CALL RT_SCOPY")

    def s_print(self, s):
        for kind, e in s[1]:
            if kind == "sep":
                if e == ",":
                    self.emit("CALL RT_COMMA")
            elif kind in ("tab", "spc"):
                self.gen_n(_fold(e), 0)
                self.emit("CALL RT_%s" % kind.upper())
            else:
                e = _fold(e)
                if etype(e) == "s":
                    self.emit("LD   HL,%s" % self.sptr(e, 0))
                    self.emit("CALL RT_PRS")
                else:
                    self.gen_n(e, 0)
                    self.emit("CALL RT_PRN")
        if s[2]:
            self.emit("CALL RT_NL")

    def s_if(self, s):
        cond = _fold(s[1])
        lelse, lend = self.newlabel(), self.newlabel()
        self.gen_n(cond, 0)
        self.emit("LD   A,H")
        self.emit("OR   L")
        self.emit("JP   Z,%s" % lelse)
        for st in s[2]:
            self.stmt(st)
        if s[3]:
            self.emit("JP   %s" % lend)
        self.label(lelse)
        for st in s[3]:
            self.stmt(st)
        if s[3]:
            self.label(lend)

    def _jump_check(self, n):
        if self.brk and (self.cur_line is None or n <= self.cur_line):
            self.emit("CALL RT_BRK")

    def s_goto(self, s):
        self._jump_check(s[1])
        self.emit("JP   LN_%d" % s[1])

    def s_gosub(self, s):
        self.emit("CALL LN_%d" % s[1])

    def s_return(self, s):
        self.emit("RET")

    def s_end(self, s):
        self.emit("JP   RT_END")

    def s_for(self, s):
        _, name, a, b, st = s
        a, b, st = _fold(a), _fold(b), _fold(st)
        v = self.var(name)
        n = self.newlabel()
        f = {"var": name, "lab": n, "line": self.where}
        self.gen_n(a, 0)
        self.emit("LD   (%s),HL" % v)
        if b[0] == "num":
            f["lim"] = str(b[1])
        else:
            self.gen_n(b, 0)
            lim = n + "_L"
            self.vars[lim] = 2
            self.emit("LD   (%s),HL" % lim)
            f["lim"] = "(%s)" % lim
        if st[0] == "num":
            f["step"] = st[1]
        else:
            self.gen_n(st, 0)
            stp = n + "_S"
            self.vars[stp] = 2
            self.emit("LD   (%s),HL" % stp)
            f["step"] = stp
        self.label(n)
        self.fors.append(f)

    def s_next(self, s):
        names = s[1] or [None]
        for name in names:
            if not self.fors:
                self.err("NEXT sans FOR")
            if name is not None:
                while self.fors and self.fors[-1]["var"] != name:
                    self.fors.pop()                   # boucles internes abandonnées
                if not self.fors:
                    self.err("NEXT %s sans FOR correspondant" % name)
            f = self.fors.pop()
            v, n = self.var(f["var"]), f["lab"]
            out = n + "_X"
            if self.brk:
                self.emit("CALL RT_BRK")
            self.emit("LD   HL,(%s)" % v)
            step = f["step"]
            self.emit(("LD   DE,%d" if isinstance(step, int) else "LD   DE,(%s)") % step)
            self.emit("OR   A")
            self.emit("ADC  HL,DE")
            self.emit("JP   PE,%s" % out)              # dépassement : fin de boucle
            self.emit("LD   (%s),HL" % v)
            lim = f["lim"]
            ld_lim = "LD   %%s,%s" % lim
            if isinstance(step, int):
                if step >= 0:
                    self._next_up(ld_lim, n)
                else:
                    self._next_down(ld_lim, n)
            else:
                neg = self.newlabel()
                self.emit("LD   A,(%s+1)" % step)
                self.emit("RLA")
                self.emit("JR   C,%s" % neg)
                self._next_up(ld_lim, n)
                self.emit("JP   %s" % out)
                self.label(neg)
                self._next_down(ld_lim, n)
            self.label(out)

    def _next_up(self, ld_lim, n):            # continue tant que var <= limite
        self.emit(ld_lim % "DE")
        self.emit("CALL RT_ICMP")
        self.emit("JP   NC,%s" % n)

    def _next_down(self, ld_lim, n):          # continue tant que var >= limite
        self.emit("EX   DE,HL")
        self.emit(ld_lim % "HL")
        self.emit("CALL RT_ICMP")
        self.emit("JP   NC,%s" % n)

    def s_while(self, s):
        top, out = self.newlabel(), self.newlabel()
        self.label(top)
        self.gen_n(_fold(s[1]), 0)
        self.emit("LD   A,H")
        self.emit("OR   L")
        self.emit("JP   Z,%s" % out)
        self.whiles.append((top, self.where, out))

    def s_wend(self, s):
        if not self.whiles:
            self.err("WEND sans WHILE")
        top, _, out = self.whiles.pop()
        if self.brk:
            self.emit("CALL RT_BRK")
        self.emit("JP   %s" % top)
        self.label(out)

    def s_cls(self, s):
        self.emit("CALL LCDCLS")

    def s_locate(self, s):
        # comme LOCATE de la ROM ($E212) : H = colonne+1, L = ligne+1, CALL $C164
        self.gen_pair(_fold(s[1]), _fold(s[2]))
        self.emit("INC  L")
        self.emit("LD   H,E")
        self.emit("INC  H")
        self.emit("CALL CURSET")

    def s_poke(self, s):
        a, v = _fold(s[1]), _fold(s[2])
        if v[0] == "num":
            self.gen_n(a, 0)
            self.emit("LD   (HL),%d" % (v[1] & 0xFF))
        else:
            self.gen_pair(a, v)
            self.emit("LD   A,L")
            self.emit("LD   (DE),A")

    def s_out(self, s):
        self.gen_pair(_fold(s[1]), _fold(s[2]))
        self.emit("LD   C,E")
        self.emit("OUT  (C),L")

    def s_exec(self, s):
        self.gen_n(_fold(s[1]), 0)
        self.emit("CALL RT_JPHL")

    def s_beep(self, s):
        if s[1] is None:
            self.emit("LD   A,7")
            self.emit("CALL LCDPUT")
            return
        self.gen_pair(_fold(s[1]), _fold(s[2]))
        self.emit("LD   H,L")
        self.emit("LD   L,0")
        self.emit("PUSH DE")
        self.emit("POP  IY")
        self.emit("CALL BEEPR")

    def s_t6(self, s):
        cmd, args = s[1], s[2]
        self._t6_params(args)
        self.emit("LD   A,$%02X" % cmd)
        self.emit("LD   BC,$%02X00" % len(args))
        self.emit("CALL RT_T6")

    def _t6_params(self, args):
        for k, e in enumerate(args):
            self.gen_n(_fold(e), 0)
            self.emit("LD   A,L")
            self.emit("LD   (RT_GB+%d),A" % k)

    def s_input(self, s):
        _, prompt, q, targets = s
        if prompt:
            self.emit("LD   HL,%s" % self.lit(prompt))
            self.emit("CALL RT_PRS")
        self.emit("LD   A,%d" % (1 if q else 0))
        self.emit("CALL RT_INPUT")
        for t in targets:
            self.gen_target_addr(t)
            self.emit("CALL RT_IN%s" % ("S" if etype(t) == "s" else "N"))

    def s_read(self, s):
        if not self.data:
            self.err("READ sans DATA")
        for t in s[1]:
            self.gen_target_addr(t)
            self.emit("CALL RT_RD%s" % ("S" if etype(t) == "s" else "N"))

    def s_restore(self, s):
        if s[1] is None:
            lab = "DATA_0"
        else:
            idx = next((self.data_at[n] for n in sorted(self.data_at) if n >= s[1]),
                       len(self.data))
            lab = "DATA_%d" % idx
        self.emit("LD   HL,%s" % lab)
        self.emit("LD   (RT_DPTR),HL")

    def s_on(self, s):
        _, e, kind, lines = s
        tab = "ON_%d" % (len(self.tables) + 1)
        self.tables.append((tab, lines))
        end = self.newlabel()
        self.gen_n(_fold(e), 0)
        self.emit("LD   DE,%s" % tab)
        self.emit("CALL RT_ONSEL")
        self.emit("LD   A,H")
        self.emit("OR   L")
        self.emit("JP   Z,%s" % end)
        if kind == "gosub":
            self.emit("LD   DE,%s" % end)
            self.emit("PUSH DE")
        elif self.brk:
            self.emit("CALL RT_BRK")
        self.emit("JP   (HL)")
        self.label(end)

    def gen_target_addr(self, t):
        if t[0] == "var":
            self.emit("LD   HL,%s" % self.var(t[1]))
        else:
            self.gen_addr(t, 0)

    # ---------------------------------------------------- expressions
    def simple(self, e):
        return e[0] == "num" or (e[0] == "var" and not e[1].endswith("$"))

    def load(self, e, reg):
        if e[0] == "num":
            self.emit("LD   %s,%d" % (reg, e[1]))
        else:
            self.emit("LD   %s,(%s)" % (reg, self.var(e[1])))

    def gen_pair(self, a, b, d=0):
        """DE = a, HL = b."""
        if self.simple(b):
            self.gen_n(a, d)
            self.emit("EX   DE,HL")
            self.load(b, "HL")
        elif self.simple(a):
            self.gen_n(b, d)
            self.load(a, "DE")
        else:
            self.gen_n(a, d)
            self.emit("PUSH HL")
            self.gen_n(b, d)
            self.emit("POP  DE")

    def gen_n(self, e, d):
        k = e[0]
        if k == "num":
            self.emit("LD   HL,%d" % e[1])
        elif k == "var":
            self.emit("LD   HL,(%s)" % self.var(e[1]))
        elif k == "arr":
            const = self.const_addr(e)
            if const:
                self.emit("LD   HL,(%s)" % const)
            else:
                self.gen_addr(e, d)
                self.emit("LD   A,(HL)")
                self.emit("INC  HL")
                self.emit("LD   H,(HL)")
                self.emit("LD   L,A")
        elif k == "un":
            self.gen_n(e[2], d)
            if e[1] == "-":
                self.emit("CALL RT_NEG")
            else:
                for r in ("L", "H"):
                    self.emit("LD   A,%s" % r)
                    self.emit("CPL")
                    self.emit("LD   %s,A" % r)
        elif k == "bin":
            self.gen_bin(e, d)
        elif k == "call":
            self.gen_call(e, d)
        elif k == "fn":
            self.gen_fncall(e, d)
        else:
            self.err("expression numérique attendue")

    def gen_bin(self, e, d):
        op, a, b = e[1], e[2], e[3]
        if op in REL:
            flag = {"=": "FEQ", "<>": "FNE", "<": "FLT", ">": "FLT",
                    "<=": "FGE", ">=": "FGE"}[op]
            swap = op in (">", "<=")
            if etype(a) == "s":
                pa, pb = self.sptr(a, d), self.sptr(b, d + 1)
                if swap:
                    pa, pb = pb, pa
                self.emit("LD   DE,%s" % pa)
                self.emit("LD   HL,%s" % pb)
                self.emit("CALL RT_SCMP")
            else:
                self.gen_pair(a, b, d)
                if swap:
                    self.emit("EX   DE,HL")
                self.emit("CALL RT_ICMP")
            self.emit("CALL RT_%s" % flag)
            return
        if op == "*" and b[0] == "num" and b[1] > 0 and b[1] & (b[1] - 1) == 0:
            self.gen_n(a, d)
            for _ in range(b[1].bit_length() - 1):
                self.emit("ADD  HL,HL")
            return
        if op == "+" and b[0] == "num" and 0 <= b[1] <= 3:
            self.gen_n(a, d)
            for _ in range(b[1]):
                self.emit("INC  HL")
            return
        if op == "-" and b[0] == "num" and 0 <= b[1] <= 3:
            self.gen_n(a, d)
            for _ in range(b[1]):
                self.emit("DEC  HL")
            return
        self.gen_pair(a, b, d)
        if op == "+":
            self.emit("ADD  HL,DE")
        elif op == "-":
            self.emit("EX   DE,HL")
            self.emit("OR   A")
            self.emit("SBC  HL,DE")
        elif op in ("AND", "OR", "XOR"):
            for r1, r2 in (("E", "L"), ("D", "H")):
                self.emit("LD   A,%s" % r1)
                self.emit("%-4s %s" % (op, r2))
                self.emit("LD   %s,A" % r2)
        else:
            self.emit("CALL RT_%s" % {"*": "MUL", "/": "DIV", "MOD": "MOD", "^": "POW"}[op])

    def gen_call(self, e, d):
        name, args = e[1], e[2]
        if name in STR_FUNCS:
            self.err("fonction chaîne dans une expression numérique")
        if name in ("INT", "FIX", "CINT", "CSNG", "CDBL"):
            return self.gen_n(args[0], d)
        if name in ("ABS", "SGN", "RND"):
            self.gen_n(args[0], d)
            self.emit("CALL RT_%s" % name)
        elif name == "PEEK":
            self.gen_n(args[0], d)
            self.emit("LD   L,(HL)")
            self.emit("LD   H,0")
        elif name == "INP":
            self.gen_n(args[0], d)
            self.emit("LD   C,L")
            self.emit("IN   L,(C)")
            self.emit("LD   H,0")
        elif name == "LEN":
            p = self.sptr(args[0], d)
            self.emit("LD   A,(%s)" % p)
            self.emit("LD   L,A")
            self.emit("LD   H,0")
        elif name == "ASC":
            self.emit("LD   HL,%s" % self.sptr(args[0], d))
            self.emit("CALL RT_ASC")
        elif name == "VAL":
            self.emit("LD   HL,%s" % self.sptr(args[0], d))
            self.emit("CALL RT_VAL")
        elif name in ("CSRLIN", "POS"):
            self.emit("LD   A,(%s)" % ("CSRY" if name == "CSRLIN" else "CSRX"))
            self.emit("DEC  A")                       # comptés à partir de 1
            self.emit("LD   L,A")
            self.emit("LD   H,0")
        elif name == "POINT":
            self._t6_params(args)
            self.emit("LD   A,$10")
            self.emit("LD   BC,$0201")
            self.emit("CALL RT_T6")
            self.emit("LD   A,(T6BUF)")
            self.emit("OR   A")
            self.emit("CALL RT_FEQ")
        elif name == "STICK":
            self.emit("LD   A,$82")
            self.emit("LD   BC,$0001")
            self.emit("CALL RT_T6")
            self.emit("CALL T6FLUSH")                  # comme la ROM ($D7EC)
            self.emit("LD   A,(T6BUF)")
            self.emit("AND  $0F")
            self.emit("LD   L,A")
            self.emit("LD   H,0")
        elif name == "STRIG":
            a = args[0]
            if a[0] != "num":
                self.err("STRIG : argument constant attendu")
            self.emit("LD   A,$%02X" % (0x84 if a[1] == 0 else 0x83))
            self.emit("LD   BC,$0001")
            self.emit("CALL RT_T6")
            self.emit("CALL T6FLUSH")
            self.emit("LD   A,(T6BUF)")
            self.emit("OR   A")
            self.emit("CALL RT_FEQ")
        else:
            self.err("fonction non gérée : %s" % name)

    def gen_fncall(self, e, d):
        name, args = e[1], e[2]
        if name not in self.fns:
            self.err("FN%s non défini" % name)
        params = self.fns[name][0]
        if len(params) != len(args):
            self.err("FN%s : %d argument(s) attendu(s)" % (name, len(params)))
        for a in args:
            if etype(a) != "n":
                self.err("FN%s : argument numérique attendu" % name)
            self.gen_n(_fold(a), d)
            self.emit("PUSH HL")
        for p in reversed(params):
            self.emit("POP  HL")
            self.emit("LD   (P_%s_%s),HL" % (_label(name), _label(p)))
        self.emit("CALL FN_%s" % _label(name))

    def _gen_fns(self):
        for k, (name, (params, body, where)) in enumerate(sorted(self.fns.items())):
            self.where = where
            self.emit("")
            self.emit("; DEF FN%s" % name)
            self.label("FN_%s" % _label(name))
            self.fnparams = {}
            for p in params:
                lab = "P_%s_%s" % (_label(name), _label(p))
                self.vars[lab] = 2
                self.fnparams[p] = lab
            self.tmpbase = 50 + 10 * k
            self.gen_n(body, 0)
            self.emit("RET")
            self.fnparams, self.tmpbase = {}, 0

    # ---------------------------------------------------- tableaux
    def const_addr(self, e):
        """Adresse constante d'un élément si tous les indices sont constants."""
        if not all(i[0] == "num" for i in e[2]):
            return None
        lab, dims, esz = self.array(e[1], len(e[2]))
        idx = 0
        for i, dmax in zip(e[2], dims):
            if not 0 <= i[1] <= dmax:
                self.err("indice %d hors du tableau %s" % (i[1], e[1]))
            idx = idx * (dmax + 1) + i[1]
        return "%s+%d" % (lab, idx * esz) if idx else lab

    def gen_addr(self, e, d):
        """HL = adresse de l'élément de tableau e."""
        const = self.const_addr(e)
        if const:
            self.emit("LD   HL,%s" % const)
            return
        lab, dims, esz = self.array(e[1], len(e[2]))
        idx = [_fold(i) for i in e[2]]
        for i in idx:
            if etype(i) != "n":
                self.err("indice numérique attendu")
        self.gen_n(idx[0], d)
        self._chk(dims[0])
        for i, dmax in zip(idx[1:], dims[1:]):
            self.emit("PUSH HL")
            self.gen_n(i, d)
            self._chk(dmax)
            self.emit("POP  DE")
            self.emit("PUSH HL")
            self.emit("LD   HL,%d" % (dmax + 1))
            self.emit("CALL RT_MUL")
            self.emit("POP  DE")
            self.emit("ADD  HL,DE")
        if esz == 2:
            self.emit("ADD  HL,HL")
        else:
            self.emit("LD   DE,%d" % esz)
            self.emit("CALL RT_MUL")
        self.emit("LD   DE,%s" % lab)
        self.emit("ADD  HL,DE")

    def _chk(self, dmax):
        if self.bounds:
            self.emit("LD   DE,%d" % (dmax + 1))
            self.emit("CALL RT_CHK")

    # ---------------------------------------------------- chaînes
    def sptr(self, e, d):
        """Adresse d'une chaîne contenant la valeur de e (sans copie si possible)."""
        if e[0] == "str":
            return self.lit(e[1])
        if e[0] == "var":
            return self.var(e[1])
        self.gen_s(e, d)
        return self.tmp(d)

    def gen_s(self, e, d):
        """Calcule l'expression chaîne e dans TMP_d."""
        t = self.tmp(d)
        k = e[0]
        if k in ("str", "var"):
            self.emit("LD   HL,%s" % t)
            self.emit("LD   DE,%s" % self.sptr(e, d))
            self.emit("CALL RT_SCOPY")
        elif k == "arr":
            self.gen_addr(e, d)
            self.emit("EX   DE,HL")
            self.emit("LD   HL,%s" % t)
            self.emit("CALL RT_SCOPY")
        elif k == "bin":
            self.gen_s(e[2], d)
            q = self.sptr(e[3], d + 1)
            self.emit("LD   HL,%s" % t)
            self.emit("LD   DE,%s" % q)
            self.emit("CALL RT_SCAT")
        elif k == "call":
            name, args = e[1], [_fold(a) for a in e[2]]
            if name == "CHR$":
                self.gen_n(args[0], d)
                self.emit("LD   A,L")
                self.emit("LD   HL,%s" % t)
                self.emit("LD   (HL),1")
                self.emit("INC  HL")
                self.emit("LD   (HL),A")
            elif name in ("STR$", "HEX$"):
                self.gen_n(args[0], d)
                self.emit("LD   DE,%s" % t)
                self.emit("CALL RT_%s" % name[:-1])
            elif name in ("LEFT$", "RIGHT$"):
                self.gen_s(args[0], d)
                self.gen_n(args[1], d + 1)
                self.emit("LD   DE,%s" % t)
                self.emit("CALL RT_%s" % name[:-1])
            elif name == "MID$":
                self.gen_s(args[0], d)
                self.gen_n(args[1], d + 1)
                self.emit("PUSH HL")
                if len(args) > 2:
                    self.gen_n(args[2], d + 1)
                else:
                    self.emit("LD   HL,255")
                self.emit("POP  BC")
                self.emit("LD   DE,%s" % t)
                self.emit("CALL RT_MID")
            elif name == "STRING$":
                self.gen_n(args[0], d)
                self.emit("PUSH HL")
                if etype(args[1]) == "s":
                    p = self.sptr(args[1], d)
                    self.emit("LD   A,(%s+1)" % p)
                else:
                    self.gen_n(args[1], d)
                    self.emit("LD   A,L")
                self.emit("POP  HL")
                self.emit("LD   DE,%s" % t)
                self.emit("CALL RT_STRING")
            elif name == "INKEY$":
                self.emit("LD   HL,%s" % t)
                self.emit("CALL RT_INKEY")
            else:
                self.err("fonction chaîne non gérée : %s" % name)
        else:
            self.err("expression chaîne attendue")

    # ---------------------------------------------------- assemblage du texte
    def _assemble_text(self, name, org):
        routines, rvars = runtime.closure(self.used, self.debug)
        out = []
        w = out.append
        w("; %s - compilé par x07basic (BASIC entier pour Canon X-07)" % name)
        w("; Chargement : CLEAR 50,&H%X  puis  EXEC &H%X" % (org - 1, org))
        w("")
        w("STRCAP  EQU  %d               ; capacité des chaînes" % self.strcap)
        w("")
        w("        ORG  $%04X" % org)
        w("")
        w("START:  PUSH AF                  ; sauvegarde pour le retour au BASIC")
        w("        PUSH BC")
        w("        PUSH DE")
        w("        PUSH HL")
        w("        PUSH IX")
        w("        PUSH IY")
        w("        LD   (RT_SP),SP")
        w("        LD   HL,VARS")
        w("        LD   DE,VARS+1")
        w("        LD   BC,VARS_END-VARS-1")
        w("        LD   (HL),0")
        w("        LDIR                     ; variables à zéro")
        if "RT_DPTR" in rvars:
            w("        LD   HL,DATA_0")
            w("        LD   (RT_DPTR),HL")
        if "RT_SEED" in rvars:
            w("        LD   A,R                 ; germe du générateur aléatoire")
            w("        OR   1")
            w("        LD   L,A")
            w("        LD   H,$5A")
            w("        LD   (RT_SEED),HL")
        out += self.code
        w("")
        w("; ------------------------------------------------ bibliothèque")
        for r in routines:
            w("")
            w(runtime.routine(r, self.debug))
        if "RT_ASC" in self.used:
            pass
        if self.lits:
            w("")
            w("; ------------------------------------------------ chaînes")
            for s, lab in self.lits.items():
                w("%-8s DB   %s" % (lab + ":", _db_string(s)))
        if self.tables:
            w("")
            for tab, lines in self.tables:
                w("%-8s DB   %d" % (tab + ":", len(lines)))
                w("         DW   %s" % ",".join("LN_%d" % n for n in lines))
        if "RT_DPTR" in rvars:
            w("")
            w("; ------------------------------------------------ DATA")
            for k, item in enumerate(self.data):
                w("DATA_%d:" % k)
                w("         DB   %s" % _db_string(item))
            w("DATA_%d:" % len(self.data))
            w("         DB   $FF")
        w("")
        w("RT_SP:   DW   0")
        w("")
        w("; ------------------------------------------------ variables (non chargées)")
        w("VARS:")
        for lab, size in sorted(self.vars.items()):
            w("%-12s DS   %d" % (lab + ":", size))
        for lab in rvars:
            w("%-12s DS   %d" % (lab + ":", runtime.VARIABLES[lab]))
        for d in sorted(self.temps):
            w("%-12s DS   %d" % ("TMP_%d:" % d, self.strcap + 1))
        w("             DS   2")
        w("VARS_END:")
        w("")
        w("        END  START")
        return _add_x07_equ(out)


def _add_x07_equ(out):
    """Insère en tête la définition des symboles du X-07 employés, pour que
    le source soit autonome (lisible par un autre assembleur)."""
    from . import x07sym
    body = "\n".join(l.split(";")[0] for l in "\n".join(out).split("\n"))
    words = set(re.findall(r"\b[A-Z_][A-Z0-9_]*\b", body))
    rows = []
    for title, table, fmt in (("routines de la ROM", x07sym.ROUTINES, "$%04X"),
                              ("variables système", x07sym.VARIABLES, "$%04X")):
        used = sorted((v, n, c) for n, (v, c) in table.items() if n in words)
        if used:
            rows.append("; Canon X-07 : %s (« Les mystères du X-07 »)" % title)
            rows += ["%-8s EQU  %-6s ; %s" % (n, fmt % v, c) for v, n, c in used]
            rows.append("")
    i = next(k for k, l in enumerate(out) if l.startswith("        ORG"))
    return "\n".join(out[:i] + rows + out[i:]) + "\n"


def _db_string(s):
    b = s.encode("latin-1", "replace")
    parts = [str(len(b))]
    run = ""
    for c in b:
        if 32 <= c < 127 and c != 34:
            run += chr(c)
        else:
            if run:
                parts.append('"%s"' % run)
                run = ""
            parts.append("$%02X" % c)
    if run:
        parts.append('"%s"' % run)
    return ",".join(parts)


# RT_ASC est simple ; on l'ajoute à la bibliothèque ici
runtime._r("RT_ASC", """
RT_ASC:                         ; HL = code du 1er caractère de (HL), 0 si vide
        LD   A,(HL)
        OR   A
        JR   Z,.Z
        INC  HL
        LD   A,(HL)
.Z:     LD   L,A
        LD   H,0
        RET
""")


def compile_basic(text, name="PROG", org=0x1000, **opts):
    c = Compiler(**opts)
    return c.compile(text, name, org), c
