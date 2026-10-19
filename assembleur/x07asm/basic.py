"""Compilateur BASIC -> assembleur Z80 pour le Canon X-07.

Dialecte : celui du BASIC du X-07 (Microsoft), avec ses types :
  entier (%)  : 16 bits, calculé dans HL (rapide) ;
  simple (!)  : 6 chiffres BCD ;   double (#) : 14 chiffres BCD (défaut du X-07) ;
  chaîne ($)  : au plus STRCAP caractères.
DEFINT, DEFSNG, DEFDBL et DEFSTR changent le type par défaut d'une lettre.

Les nombres non entiers sont calculés par les routines de la ROM, dans son
accumulateur (FAC, $044E) avec le type réel en VALTYP ($01D9), exactement
comme l'interpréteur : mêmes conversions, mêmes arrondis, même affichage.
Les constantes sont converties à la compilation par la routine FIN de la ROM
(il faut donc ROM_x07/x07.bin pour compiler des nombres non entiers).

Voir COMPILATEUR.md.
"""
import re

from . import runtime

# ======================================================================
#  Analyse lexicale
# ======================================================================

KEYWORDS = sorted("""
END FOR NEXT DATA INPUT DIM READ LET GOTO GOSUB RUN IF RESTORE RETURN REM STOP
ELSE THEN TO STEP ON OUT POKE PRINT LPRINT CLEAR CLS LOCATE PSET PRESET LINE
CIRCLE BEEP EXEC DEFFN FN DEFINT DEFSNG DEFDBL DEFSTR WHILE WEND TR MOTOR ERROR
RESUME LIST LLIST CONT NEW CONSOLE COLOR OFF SLEEP DIR DELETE FSET PAINT LOAD
SAVE INIT ERASE CLOAD CSAVE SCREEN USING STRING$ INSTR INKEY$ INP VARPTR USR
SNS ALM$ DATE$ TIME$ START$ FONT$ KEY$ NOT EQV IMP AND OR XOR MOD SGN INT ABS
FRE POS SQR RND LOG EXP COS SIN TAN ATN PEEK CINT CSNG CDBL FIX LEN HEX$ STR$
VAL ASC CHR$ TKEY LEFT$ RIGHT$ MID$ CSRLIN STICK STRIG POINT ERL ERR TAB( SPC(
""".split(), key=len, reverse=True)

OPS2 = ("<>", "<=", ">=", "=<", "=>", "><")
OPS1 = "+-*/\\^=<>(),;:#"


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


_NUMBER = re.compile(r"(\d*\.?\d*)(?:([ED])([+-]?\d+))?([%!#]?)", re.I)


def tokenize(text, line=None):
    """Découpe une ligne (sans son numéro) en lexèmes.  Un nombre donne
    ('num', texte) ; son type est fixé par l'analyse syntaxique."""
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
        if c.isdigit() or (c == "." and i + 1 < n and text[i + 1].isdigit()):
            m = _NUMBER.match(up, i)             # « 1E » sans chiffres : pas d'exposant
            toks.append(Tok("num", m.group(0)))
            i = m.end()
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
            v = int(up[j:k], base)
            if v > 0xFFFF:
                raise CompileError("nombre hexadécimal trop grand", line)
            toks.append(Tok("int", _s16(v)))
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
            toks.append(Tok("id", up[i:j]))
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


def _s16(v):
    v &= 0xFFFF
    return v - 65536 if v > 32767 else v


# ======================================================================
#  Types
# ======================================================================
#  Type d'une variable : 'i' entier, 'f' simple, 'd' double, 's' chaîne.
#  Genre d'une expression : 'i' (dans HL), 'x' (nombre dans FAC), 's'.

SUFFIX_TYPE = {"%": "i", "!": "f", "#": "d", "$": "s"}


class Types:
    """Types par défaut des 26 lettres (DEFINT...), double au départ comme le X-07."""

    def __init__(self, default="d"):
        self.letters = {chr(65 + k): default for k in range(26)}

    def set_range(self, a, b, t):
        for k in range(ord(a), ord(b) + 1):
            self.letters[chr(k)] = t

    def of(self, name):
        if name[-1] in SUFFIX_TYPE:
            return SUFFIX_TYPE[name[-1]]
        return self.letters[name[0]]

    def base(self, name):
        return name[:-1] if name[-1] in SUFFIX_TYPE else name


# Expressions : ('int',v) ('flt',texte) ('str',s) ('var',nom) ('arr',nom,[indices])
#               ('un',op,e) ('bin',op,a,b) ('call',fonction,[args]) ('fn',nom,[args])

NUM_FUNCS = {   # nom : types des arguments ('n' nombre, 's' chaîne)
    "ABS": "n", "SGN": "n", "INT": "n", "FIX": "n", "CINT": "n", "CSNG": "n",
    "CDBL": "n", "PEEK": "n", "INP": "n", "RND": "n", "LEN": "s", "ASC": "s",
    "VAL": "s", "POINT": "nn", "STICK": "n", "STRIG": "n", "CSRLIN": "",
    "POS": "n", "SQR": "n", "LOG": "n", "EXP": "n", "SIN": "n", "COS": "n",
    "TAN": "n", "ATN": "n",
}
STR_FUNCS = {
    "CHR$": "n", "STR$": "n", "HEX$": "n", "LEFT$": "sn", "RIGHT$": "sn",
    "MID$": "sn", "STRING$": "n?", "INKEY$": "", "FONT$": "n",
}
OPTIONAL_LAST = {"MID$": "n"}       # MID$(s,p[,n])
X_FUNCS = {"CSNG": "FCSNG", "CDBL": "FCDBL", "SQR": "FSQR", "LOG": "FLOG", "EXP": "FEXP",
           "SIN": "FSIN", "COS": "FCOS", "TAN": "FTAN", "ATN": "FATN", "RND": "FRND",
           "VAL": None}
SAME_FUNCS = {"ABS": "FABS", "INT": "FINT", "FIX": "FFIX"}   # genre de l'argument

REL = ("=", "<>", "<", ">", "<=", ">=")
INT_OPS = ("\\", "MOD", "AND", "OR", "XOR", "EQV", "IMP")
ROM_OPS = {"+": 0, "-": 1, "*": 2, "/": 3, "^": 4}            # index du répartiteur


def etype(e, ty):
    k = e[0]
    if k == "int":
        return "i"
    if k == "flt":
        return "x"
    if k == "str":
        return "s"
    if k in ("var", "arr"):
        t = ty.of(e[1])
        return t if t in "is" else "x"
    if k == "un":
        return "i" if e[1] == "NOT" else etype(e[2], ty)
    if k == "fn":
        t = ty.of(e[1])
        return t if t in "is" else "x"
    if k == "call":
        if e[1] in STR_FUNCS:
            return "s"
        if e[1] in SAME_FUNCS:
            return etype(e[2][0], ty)
        return "x" if e[1] in X_FUNCS else "i"
    if k == "bin":
        op = e[1]
        if op in REL or op in INT_OPS:
            return "i"
        a, b = etype(e[2], ty), etype(e[3], ty)
        if op == "+" and a == "s":
            return "s"
        if op in ("/", "^"):
            return "x"
        return "i" if a == b == "i" else "x"
    if k in ("adesc", "qbound"):          # compilation directe : descripteur, UBOUND
        return "i"
    raise ValueError(e)


# ======================================================================
#  Analyse syntaxique
# ======================================================================

class Parser:
    def __init__(self, toks, line, ty):
        self.t, self.i, self.line, self.ty = toks, 0, line, ty

    def et(self, e):
        return etype(e, self.ty)

    def num(self, e):
        return self.et(e) in "ix"

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
        e = self.eqv()
        while self.iskw("IMP"):
            self.next()
            e = self._binn("IMP", e, self.eqv())
        return e

    def eqv(self):
        e = self.xor()
        while self.iskw("EQV"):
            self.next()
            e = self._binn("EQV", e, self.xor())
        return e

    def xor(self):
        e = self.or_()
        while self.iskw("XOR"):
            self.next()
            e = self._binn("XOR", e, self.or_())
        return e

    def nexpr(self):
        e = self.expr()
        if not self.num(e):
            self.err("expression numérique attendue")
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
            if (self.et(e) == "s") != (self.et(b) == "s"):
                self.err("comparaison entre une chaîne et un nombre")
            e = ("bin", op, e, b)
        return e

    def add(self):
        e = self.mod()
        while self.cur.kind == "op" and self.cur.val in "+-":
            op = self.next().val
            b = self.mod()
            if op == "+" and self.et(e) == "s" and self.et(b) == "s":
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
            e = self._binn("\\", e, self.mul())
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
        if not self.num(e):
            self.err("opération numérique sur une chaîne")

    def _binn(self, op, a, b):
        self._needn(a)
        self._needn(b)
        return ("bin", op, a, b)

    def number(self, text):
        """Constante : entier si elle s'écrit comme tel et tient sur 16 bits."""
        t = text.upper()
        if re.fullmatch(r"\d+%?", t):
            v = int(t.rstrip("%"))
            if v <= 32767:
                return ("int", v)
            if t.endswith("%"):
                self.err("constante entière trop grande : %s" % text)
        return ("flt", t)

    def atom(self):
        t = self.cur
        if t.kind == "num":
            self.next()
            return self.number(t.val)
        if t.kind == "int":
            self.next()
            return ("int", t.val)
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
                        ("INSTR", "FRE", "VARPTR", "USR", "ERR", "ERL", "TKEY", "SNS")
                        else ""))
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
            if want == "?":
                continue
            if (want == "s") != (self.et(a) == "s"):
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
        if t.kind != "num" or not t.val.isdigit():
            self.err("numéro de ligne attendu%s" % self._near())
        self.next()
        return int(t.val)

    def statement(self):
        t = self.cur
        if t.kind == "id":
            nxt = self.t[self.i + 1]
            if t.val == "DEF" and nxt.kind == "kw" and nxt.val == "FN":
                self.err("écrivez DEFFN en un seul mot (le X-07 refuse « DEF FN »)")
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
        if (self.et(e) == "s") != (self.et(tgt) == "s"):
            self.err("types incompatibles dans l'affectation")
        return ("let", tgt, e)

    def st_LET(self):
        return self._let()

    def st_PRINT(self):
        if self.isop("#"):                      # PRINT #canal, ... : fichier
            self.next()
            ch = self.nexpr()
            if not self.at_end():
                self.expect_op(",")
            _, items, nl = self.st_PRINT()
            return ("fprint", ch, items, nl)
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
        nl = not items or items[-1][0] != "sep"
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
        if v[0] != "var" or self.ty.of(v[1]) == "s":
            self.err("variable numérique simple attendue après FOR")
        self.expect_op("=")
        a = self.nexpr()
        self.expect_kw("TO")
        b = self.nexpr()
        s = self.nexpr() if self.accept_kw("STEP") else ("int", 1)
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
                if e[0] != "int" or e[1] < 0:
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
        if self.accept_kw("INPUT"):             # LINE INPUT ["texte";] v$ / LINE INPUT #c, v$
            if self.isop("#"):
                self.next()
                ch = self.nexpr()
                self.expect_op(",")
                return ("flineinput", ch, self._string_target())
            prompt = None
            if self.cur.kind == "str":
                prompt = self.next().val
                self.expect_op(";")
            return ("lineinput", prompt, self._string_target())
        a = self._point()
        self.expect_op("-")
        b = self._point()
        return ("t6", 0x14, list(a + b))

    def _string_target(self):
        t = self.target()
        if self.ty.of(t[1]) != "s":
            self.err("LINE INPUT : variable chaîne attendue")
        return t

    def st_INIT(self):                          # INIT #canal,"RAM:NOM"[,taille]
        self.expect_op("#")
        ch = self.nexpr()
        self.expect_op(",")
        name = self.expr()
        if self.et(name) != "s":
            self.err("INIT # : nom de fichier attendu")
        size = self.nexpr() if self.accept_op(",") else None
        return ("finit", ch, name, size)

    def st_FSET(self):
        return ("fset", self.nexpr())

    def st_DELETE(self):                        # DELETE "NOM" : fichier en RAM
        e = self.expr()
        if self.et(e) != "s":
            self.err("DELETE : nom de fichier attendu (les lignes ne se suppriment pas "
                     "dans un programme compilé)")
        return ("fdel", e)

    def st_CIRCLE(self):
        a = self._point()
        self.expect_op(",")
        return ("t6", 0x15, list(a) + [self.nexpr()])

    def st_FONTS(self):
        self.expect_op("(")
        code = self.nexpr()
        self.expect_op(")")
        self.expect_op("=")
        e = self.expr()
        if self.et(e) != "s":
            self.err("FONT$(code) attend une chaîne : 8 nombres séparés par des virgules")
        return ("font", code, e)

    def st_INPUT(self):
        if self.isop("#"):                      # INPUT #canal, variables
            self.next()
            ch = self.nexpr()
            self.expect_op(",")
            tg = [self.target()]
            while self.accept_op(","):
                tg.append(self.target())
            return ("finput", ch, tg)
        prompt, q = None, True
        if self.cur.kind == "str":
            prompt = self.next().val
            if self.isop(","):
                self.err("INPUT : « ; » attendu après le texte (le X-07 refuse « , »)")
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

    def st_DEFFN(self):
        if self.cur.kind != "id":
            self.err("nom de fonction attendu")
        name = self.next().val
        if self.ty.of(name) == "s":
            self.err("fonctions chaîne (DEF FN...$) non gérées")
        params = []
        if self.accept_op("("):
            while True:
                p = self.target()
                if p[0] != "var" or self.ty.of(p[1]) == "s":
                    self.err("paramètre numérique attendu")
                params.append(p[1])
                if not self.accept_op(","):
                    break
            self.expect_op(")")
        self.expect_op("=")
        return ("deffn", name, params, self.nexpr())

    def _deftype(self):
        """DEFINT A-C,X : les plages ont déjà été appliquées (prescan)."""
        while not self.at_end():
            self.next()
        return ("nop",)

    st_DEFINT = st_DEFSNG = st_DEFDBL = st_DEFSTR = _deftype

    def st_CLEAR(self):
        while not self.at_end():
            self.next()
        return ("nop",)


def scan_deftypes(toks, ty, where):
    """Applique les DEFINT/DEFSNG/DEFDBL/DEFSTR d'une ligne."""
    kinds = {"DEFINT": "i", "DEFSNG": "f", "DEFDBL": "d", "DEFSTR": "s"}
    i = 0
    while i < len(toks):
        t = toks[i]
        i += 1
        if t.kind == "kw" and t.val in kinds:
            while i < len(toks) and toks[i].kind == "id":
                a = toks[i].val
                i += 1
                b = a
                if i + 1 < len(toks) and toks[i].kind == "op" and toks[i].val == "-":
                    b = toks[i + 1].val
                    i += 2
                if not (len(a) == 1 and len(b) == 1 and a.isalpha() and b.isalpha()):
                    raise CompileError("%s : lettres attendues" % t.val, where)
                ty.set_range(a, b, kinds[t.val])
                if i < len(toks) and toks[i].kind == "op" and toks[i].val == ",":
                    i += 1
                else:
                    break


# ======================================================================
#  Constantes : conversion par la ROM
# ======================================================================

_fin_cache = {}


def rom_constant(text):
    """(octets BCD sur 8, type 4 ou 8, ou 2 pour un entier) calculés par FIN."""
    if text in _fin_cache:
        return _fin_cache[text]
    from . import emu
    from .sim import EXIT, SimError
    try:
        m = emu.boot(16)
    except SimError as e:
        raise CompileError("nombre %s : %s" % (text, e))
    m.strict = False
    err = {}

    def hook(c):
        err["e"] = c.r["E"]
        raise SimError("erreur")
    m.mem[0xAB:0xAE] = bytes([0xC3, 0xF0, 0x7F])
    m.traps[0x7FF0] = hook
    b = text.encode("ascii") + b"\0"
    m.mem[0x3000:0x3000 + len(b)] = b
    m.set16("HL", 0x3000)
    m.push(EXIT)
    m.pc = 0xBA21
    try:
        m.run(200000)
    except SimError:
        raise CompileError("nombre %s : dépassement de capacité (OV)" % text)
    r = (bytes(m.mem[0x044E:0x0456]), m.mem[0x01D9])
    _fin_cache[text] = r
    return r


# ======================================================================
#  Génération de code
# ======================================================================

_NUM_LINE = re.compile(r"^\s*(\d+)\s?(.*)$")


def _fold(e):
    """Calcul des sous-expressions entières constantes.  Un débordement
    donne une constante double, comme le X-07 (300*300 -> 90000)."""
    if e[0] == "un":
        a = _fold(e[2])
        if a[0] == "int":
            if e[1] == "NOT":
                return ("int", _s16(~a[1]))
            if a[1] != -32768:
                return ("int", -a[1])
        return ("un", e[1], a)
    if e[0] == "bin":
        a, b = _fold(e[2]), _fold(e[3])
        op = e[1]
        if a[0] == "int" and b[0] == "int" and op not in ("/", "^"):
            x, y = a[1], b[1]
            try:
                v = {"+": lambda: x + y, "-": lambda: x - y, "*": lambda: x * y,
                     "\\": lambda: int(x / y), "MOD": lambda: x - y * int(x / y),
                     "AND": lambda: x & y, "OR": lambda: x | y, "XOR": lambda: x ^ y,
                     "EQV": lambda: ~(x ^ y), "IMP": lambda: ~x | y,
                     "=": lambda: -(x == y), "<>": lambda: -(x != y),
                     "<": lambda: -(x < y), ">": lambda: -(x > y),
                     "<=": lambda: -(x <= y), ">=": lambda: -(x >= y)}[op]()
            except ZeroDivisionError:
                return ("bin", op, a, b)
            if -32768 <= v <= 32767:
                return ("int", v)
            return ("flt", "%d#" % v)
        return ("bin", op, a, b)
    if e[0] in ("arr", "call", "fn"):
        return (e[0], e[1], [_fold(x) for x in e[2]])
    return e


def _label(name):
    return re.sub(r"[^A-Z0-9]", "_", name)


TYPE_TAG = {"i": "I", "f": "F", "d": "D"}
TYPE_SIZE = {"i": 2, "f": 4, "d": 8}


class Compiler:
    def __init__(self, strcap=80, brk=True, debug=False, bounds=True, default="d"):
        if not 1 <= strcap <= 254:
            raise CompileError("capacité des chaînes entre 1 et 254")
        self.strcap, self.brk, self.debug, self.bounds = strcap, brk, debug, bounds
        self.default = default
        self.warnings = []

    # ---------------------------------------------------- lecture
    def parse(self, text):
        self.ty = Types(self.default)
        raw_lines = []
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
            toks = tokenize(body, where)
            scan_deftypes(toks, self.ty, where)
            raw_lines.append((num, toks, raw.strip(), where))
        lines = []
        for num, toks, src, where in raw_lines:
            p = Parser(toks, where, self.ty)
            stmts = p.statements()
            if p.iskw("ELSE"):
                p.err("ELSE sans IF")
            lines.append((num, stmts, src, where))
        return lines

    def et(self, e):
        return etype(e, self.ty)

    # ---------------------------------------------------- compilation
    def compile(self, text, name="PROG", org=0x1000):
        self.lines = self.parse(text)
        self.code = []
        self.lits = {}
        self.flits = {}          # texte -> (étiquette, octets, type)
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
            if num is not None:                 # chaque ligne : sauts, et débogueur
                self.label("LN_%d" % num)
            if self.debug and num is not None:
                self.emit("LD   HL,%d" % num)
                self.emit("LD   (RT_LINE),HL")
            for s in stmts:
                self.stmt(s)
        if self.fors:
            raise CompileError("FOR %s sans NEXT" % self.fors[-1]["var"], self.fors[-1]["line"])
        if self.whiles:
            raise CompileError("WHILE sans WEND", self.whiles[-1][1])
        self.emit("")
        self.emit("JP   RT_END")
        self._gen_fns()
        return self._assemble_text(name, org)

    def _prescan(self):
        self.targets = set()
        self.data = []
        self.data_at = {}
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
                    key = self.akey(name)
                    if key in self.arrays:
                        raise CompileError("tableau %s dimensionné deux fois" % name, where)
                    self.arrays[key] = dims
            elif k == "deffn":
                key = self.vkey(s[1])
                if key in self.fns:
                    raise CompileError("FN%s défini deux fois" % s[1], where)
                self.fns[key] = (s[1], s[2], _fold(s[3]), where)
            elif k == "data":
                if isinstance(where, int):
                    self.data_at.setdefault(where, len(self.data))
                for item in s[1]:
                    if len(item) > 254:
                        raise CompileError("élément DATA trop long", where)
                    self.data.append((where if isinstance(where, int) else 0, item))

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

    def flit(self, text):
        """Constante flottante convertie par la ROM -> (étiquette, type)."""
        if text not in self.flits:
            try:
                data, t = rom_constant(text)
            except CompileError as e:
                raise CompileError(e.msg, self.where)
            self.flits[text] = ("FLT_%d" % (len(self.flits) + 1), data, t)
        lab, data, t = self.flits[text]
        return lab, t

    def tmp(self, d):
        d += self.tmpbase
        self.temps.add(d)
        return "TMP_%d" % d

    def vkey(self, name):
        return (self.ty.base(name), self.ty.of(name))

    def akey(self, name):
        return ("A",) + self.vkey(name)

    def var(self, name):
        """Étiquette d'une variable simple (selon son type)."""
        if name in self.fnparams:
            return self.fnparams[name]
        base, t = self.vkey(name)
        if t == "s":
            lab = "S_" + _label(base)
            self.vars[lab] = self.strcap + 1
        else:
            lab = "V_%s_%s" % (_label(base), TYPE_TAG[t])
            self.vars[lab] = TYPE_SIZE[t]
        return lab

    def vtype(self, name):
        return self.ty.of(name)

    def array(self, name, nidx):
        key = self.akey(name)
        if key not in self.arrays:
            self.arrays[key] = [10] * nidx
            self.warnings.append("%s : tableau %s non dimensionné, DIM %s(%s) supposé"
                                 % (self.where, name, name, ",".join(["10"] * nidx)))
        dims = self.arrays[key]
        if len(dims) != nidx:
            self.err("tableau %s : %d indice(s) attendu(s)" % (name, len(dims)))
        base, t = key[1], key[2]
        lab = ("AS_%s" % _label(base)) if t == "s" else "A%s_%s" % (TYPE_TAG[t], _label(base))
        count = 1
        for d in dims:
            count *= d + 1
        esz = self.strcap + 1 if t == "s" else TYPE_SIZE[t]
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
        t = self.vtype(tgt[1])
        if t == "s":
            return self._let_string(tgt, e)
        if tgt[0] == "var":
            self.gen_value(e, t)
            self.store_value(t, self.var(tgt[1]))
            return
        const = self.const_addr(tgt)
        if const:
            self.gen_value(e, t)
            self.store_value(t, const)
            return
        if t == "i":
            self.gen_i(e, 0)
            self.emit("PUSH HL")
            self.gen_addr(tgt, 0)
            self.emit("POP  DE")
            self.emit("LD   (HL),E")
            self.emit("INC  HL")
            self.emit("LD   (HL),D")
        else:
            self.gen_addr(tgt, 0)
            self.emit("PUSH HL")
            self.gen_value(e, t)
            self.emit("POP  HL")
            self.store_value(t, None)

    def gen_value(self, e, t):
        """Valeur de e convertie au type t : HL pour 'i', FAC sinon."""
        if t == "i":
            self.gen_i(e, 0)
        else:
            self.gen_x(e, 0)
            self.emit("CALL %s" % ("FCSNG" if t == "f" else "FCDBL"))

    def store_value(self, t, lab):
        """Range la valeur (HL ou FAC) dans lab, ou à l'adresse HL si lab est None."""
        if t == "i":
            self.emit("LD   (%s),HL" % lab)
            return
        if lab is not None:
            self.emit("LD   HL,%s" % lab)
        self.emit("CALL RT_STF%d" % TYPE_SIZE[t])

    def load_var(self, name, lab=None):
        """FAC <- variable flottante (étiquette ou adresse dans HL)."""
        t = self.vtype(name)
        if lab is not None:
            self.emit("LD   HL,%s" % lab)
        self.emit("CALL RT_LDF%d" % TYPE_SIZE[t])

    def _let_string(self, tgt, e):
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
            self.gen_addr(tgt, 1)
            self.emit("LD   DE,%s" % src)
            self.emit("CALL RT_SCOPY")

    def s_print(self, s):
        for kind, e in s[1]:
            if kind == "sep":
                if e == ",":
                    self.emit("CALL RT_COMMA")
            elif kind in ("tab", "spc"):
                self.gen_i(_fold(e), 0)
                self.emit("CALL RT_%s" % kind.upper())
            elif kind == "using":                  # PRINT USING : routine de la ROM
                v, flags, before, after = e
                self.gen_x(_fold(v), 0)
                self.emit("LD   A,$%02X" % flags)
                self.emit("LD   BC,$%02X%02X" % (before, after))
                self.emit("CALL RT_PUSING")
            else:
                e = _fold(e)
                if self.et(e) == "s":
                    self.emit("LD   HL,%s" % self.sptr(e, 0))
                    self.emit("CALL RT_PRS")
                else:
                    self.gen_x(e, 0)
                    self.emit("CALL RT_PRNUM")
        if s[2]:
            self.emit("CALL CRLF")

    # ---------------------------------------------------- fichiers en RAM
    def s_fprint(self, s):
        self.gen_i(_fold(s[1]), 0)
        self.emit("CALL RT_FSEL")               # le fichier devient le périphérique courant
        self.s_print(("print", s[2], s[3]))
        self.emit("CALL RT_FEND")

    def s_finput(self, s):
        self.gen_i(_fold(s[1]), 0)
        self.emit("CALL RT_FSEL")
        self.emit("CALL RT_FINPUT")
        self._input_targets(s[2])
        self.emit("CALL $E89E")                 # retour à l'écran

    def s_lineinput(self, s):
        _, prompt, t = s
        if prompt:
            self.emit("LD   HL,%s" % self.lit(prompt))
            self.emit("CALL RT_PRS")
        self.emit("LD   A,0")                   # sans « ? »
        self.emit("CALL RT_INPUT")
        self.gen_target_addr(t)
        self.emit("CALL RT_INLINE")

    def s_flineinput(self, s):
        self.gen_i(_fold(s[1]), 0)
        self.emit("CALL RT_FSEL")
        self.emit("CALL RT_FINPUT")
        self.gen_target_addr(s[2])
        self.emit("CALL RT_INLINE")
        self.emit("CALL $E89E")

    def s_finit(self, s):
        _, ch, name, size = s
        self.gen_i(_fold(ch), 0)
        self.emit("LD   (RT_FCH),HL")
        if size is None:
            self.emit("LD   HL,-1")
        else:
            self.gen_i(_fold(size), 0)
        self.emit("LD   (RT_FSZ),HL")
        self.emit("LD   HL,%s" % self.sptr(_fold(name), 0))
        self.emit("CALL RT_FINIT")

    def s_fset(self, s):
        e = _fold(s[1])
        if e[0] == "int":                       # place du code : sous la zone des fichiers
            self.file_space = max(getattr(self, "file_space", 0), e[1])
        self.gen_i(e, 0)
        self.emit("CALL RT_FSET")

    def s_fdel(self, s):
        self.emit("LD   HL,%s" % self.sptr(_fold(s[1]), 0))
        self.emit("CALL RT_FDEL")

    def s_rtcall(self, s):                      # routine d'exécution, HL = valeur
        self.gen_i(_fold(s[2]), 0)
        self.emit("CALL %s" % s[1])

    def gen_cond(self, cond, false_label):
        cond = _fold(cond)
        if self.et(cond) == "i":
            self.gen_i(cond, 0)
        else:
            self.gen_x(cond, 0)
            self.emit("CALL FSGN")                     # HL = signe (0 si faux)
        self.emit("LD   A,H")
        self.emit("OR   L")
        self.emit("JP   Z,%s" % false_label)

    def s_if(self, s):
        lelse, lend = self.newlabel(), self.newlabel()
        self.gen_cond(s[1], lelse)
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

    # ---------------------------------------------------- FOR / NEXT
    def s_for(self, s):
        _, name, a, b, st = s
        a, b, st = _fold(a), _fold(b), _fold(st)
        t = self.vtype(name)
        v = self.var(name)
        n = self.newlabel()
        f = {"var": name, "lab": n, "line": self.where, "type": t}
        self.gen_value(a, t)
        self.store_value(t, v)
        if t == "i":
            if b[0] == "int":
                f["lim"] = str(b[1])
            else:
                self.gen_i(b, 0)
                lim = n + "_L"
                self.vars[lim] = 2
                self.emit("LD   (%s),HL" % lim)
                f["lim"] = "(%s)" % lim
            if st[0] == "int":
                f["step"] = st[1]
            else:
                self.gen_i(st, 0)
                stp = n + "_S"
                self.vars[stp] = 2
                self.emit("LD   (%s),HL" % stp)
                f["step"] = stp
        else:
            size = TYPE_SIZE[t]
            for key, e in (("lim", b), ("step", st)):
                lab = "%s_%s" % (n, key[0].upper())
                self.vars[lab] = size
                self.gen_value(e, t)
                self.store_value(t, lab)
                f[key] = lab
            if st[0] == "int":
                f["sign"] = (st[1] > 0) - (st[1] < 0)
            else:
                self.load_var(name, f["step"])
                self.emit("CALL FSGN")
                sg = n + "_G"
                self.vars[sg] = 1
                self.emit("LD   A,H")
                self.emit("LD   (%s),A" % sg)
                f["sign"] = sg
        self.label(n)
        self.fors.append(f)

    def s_next(self, s):
        names = s[1] or [None]
        for name in names:
            if not self.fors:
                self.err("NEXT sans FOR")
            if name is not None:
                while self.fors and self.vkey(self.fors[-1]["var"]) != self.vkey(name):
                    self.fors.pop()                   # boucles internes abandonnées
                if not self.fors:
                    self.err("NEXT %s sans FOR correspondant" % name)
            f = self.fors.pop()
            if self.brk:
                self.emit("CALL RT_BRK")
            if f["type"] == "i":
                self._next_int(f)
            else:
                self._next_float(f)

    def _next_int(self, f):
        v, n = self.var(f["var"]), f["lab"]
        out = n + "_X"
        self.emit("LD   HL,(%s)" % v)
        step = f["step"]
        self.emit(("LD   DE,%d" if isinstance(step, int) else "LD   DE,(%s)") % step)
        self.emit("OR   A")
        self.emit("ADC  HL,DE")
        self.emit("JP   PE,%s" % out)              # dépassement : fin de boucle
        self.emit("LD   (%s),HL" % v)
        ld_lim = "LD   %%s,%s" % f["lim"]
        if isinstance(step, int):
            (self._next_up if step >= 0 else self._next_down)(ld_lim, n)
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

    def _next_float(self, f):
        """var = var + pas (par la ROM, puis arrondi au type de var) ;
        on continue tant que var <= limite (pas >= 0) ou var >= limite."""
        name, n, t = f["var"], f["lab"], f["type"]
        v = self.var(name)
        ret = self.newlabel()
        self.emit("LD   HL,%s" % ret)
        self.emit("PUSH HL")
        self.load_var(name, v)
        self.emit("LD   C,0")
        self.emit("CALL RT_FPUSHL")
        self.load_var(name, f["step"])
        self.emit("JP   FOPDISP")
        self.label(ret)
        self.emit("CALL %s" % ("FCSNG" if t == "f" else "FCDBL"))
        self.store_value(t, v)
        self.load_var(name, v)                 # compare la valeur rangée à la limite
        self.emit("CALL FCDBL")
        self.emit("CALL RT_FPUSH8")
        self.load_var(name, f["lim"])
        self.emit("CALL FCDBL")
        self.emit("CALL RT_FPOPARG")
        self.emit("CALL DCMP")                 # A = 1 si var < lim, -1 si var > lim
        sign = f["sign"]
        if isinstance(sign, int):
            self.emit("CP   %s" % ("$FF" if sign >= 0 else "1"))
            self.emit("JP   NZ,%s" % n)
        else:
            down = self.newlabel()
            self.emit("LD   B,A")
            self.emit("LD   A,(%s)" % sign)
            self.emit("RLA")
            self.emit("LD   A,B")
            self.emit("JR   C,%s" % down)
            self.emit("CP   $FF")
            self.emit("JP   NZ,%s" % n)
            self.emit("JR   %s_X" % n)
            self.label(down)
            self.emit("CP   1")
            self.emit("JP   NZ,%s" % n)
        self.label(n + "_X")

    def s_while(self, s):
        top, out = self.newlabel(), self.newlabel()
        self.label(top)
        self.gen_cond(s[1], out)
        self.whiles.append((top, self.where, out))

    def s_wend(self, s):
        if not self.whiles:
            self.err("WEND sans WHILE")
        top, _, out = self.whiles.pop()
        if self.brk:
            self.emit("CALL RT_BRK")
        self.emit("JP   %s" % top)
        self.label(out)

    # ---------------------------------------------------- écran, E/S
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
        if v[0] == "int":
            self.gen_i(a, 0)
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
        self.gen_i(_fold(s[1]), 0)
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
        back = self.newlabel()                   # $C2DF dépile une adresse de trop :
        self.emit("LD   BC,%s" % back)           # on la fournit, comme le livre
        self.emit("PUSH BC")
        self.emit("CALL BEEPR")
        self.label(back)

    def s_t6(self, s):
        cmd, args = s[1], s[2]
        self._t6_params(args)
        self.emit("LD   A,$%02X" % cmd)
        self.emit("LD   BC,$%02X00" % len(args))
        self.emit("CALL RT_T6")

    def s_font(self, s):
        self.gen_i(_fold(s[1]), 0)
        self.emit("LD   A,L")
        self.emit("LD   (RT_GB),A")
        self.emit("LD   HL,%s" % self.sptr(s[2], 0))
        self.emit("CALL RT_FONT")

    def _t6_params(self, args):
        for k, e in enumerate(args):
            self.gen_i(_fold(e), 0)
            self.emit("LD   A,L")
            self.emit("LD   (RT_GB+%d),A" % k)

    def s_input(self, s):
        _, prompt, q, targets = s
        if prompt:
            self.emit("LD   HL,%s" % self.lit(prompt))
            self.emit("CALL RT_PRS")
        self.emit("LD   A,%d" % (1 if q else 0))
        self.emit("CALL RT_INPUT")
        self._input_targets(targets)

    def _input_targets(self, targets):
        for t in targets:
            if self.vtype(t[1]) == "s":
                self.gen_target_addr(t)
                self.emit("CALL RT_INS")
            else:
                self._read_number(t, "CALL RT_INFLD", "CALL FIN")

    def s_read(self, s):
        if not self.data:
            self.err("READ sans DATA")
        for t in s[1]:
            if self.vtype(t[1]) == "s":
                self.gen_target_addr(t)
                self.emit("CALL RT_RDS")
            else:
                self._read_number(t, "CALL RT_RDX")

    def _read_number(self, t, *calls):
        """Lit un nombre (texte -> FAC par FIN) et le range dans la cible t."""
        ty = self.vtype(t[1])
        if t[0] == "arr":
            self.gen_addr(t, 0)
            self.emit("PUSH HL")
        for c in calls:
            self.emit(c)
        if ty == "i":
            self.emit("CALL FCINT")
            self.emit("LD   HL,(FACINT)")
            if t[0] == "arr":
                self.emit("EX   DE,HL")
                self.emit("POP  HL")
                self.emit("LD   (HL),E")
                self.emit("INC  HL")
                self.emit("LD   (HL),D")
            else:
                self.emit("LD   (%s),HL" % self.var(t[1]))
        else:
            self.emit("CALL %s" % ("FCSNG" if ty == "f" else "FCDBL"))
            if t[0] == "arr":
                self.emit("POP  HL")
                self.store_value(ty, None)
            else:
                self.store_value(ty, self.var(t[1]))

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
        self.gen_i(_fold(e), 0)
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

    # ---------------------------------------------------- expressions entières
    def simple(self, e):
        return e[0] == "int" or (e[0] == "var" and self.vtype(e[1]) == "i")

    def load(self, e, reg):
        if e[0] == "int":
            self.emit("LD   %s,%d" % (reg, e[1]))
        else:
            self.emit("LD   %s,(%s)" % (reg, self.var(e[1])))

    def gen_pair(self, a, b, d=0):
        """DE = a, HL = b (entiers)."""
        if self.simple(b):
            self.gen_i(a, d)
            self.emit("EX   DE,HL")
            self.load(b, "HL")
        elif self.simple(a):
            self.gen_i(b, d)
            self.load(a, "DE")
        else:
            self.gen_i(a, d)
            self.emit("PUSH HL")
            self.gen_i(b, d)
            self.emit("POP  DE")

    def gen_i(self, e, d):
        """HL = valeur entière de e (un nombre est converti par CINT, qui
        tronque sur le X-07 ; OV au-delà de 16 bits)."""
        if self.et(e) == "x":
            self.gen_x(e, d)
            self.emit("CALL FCINT")
            self.emit("LD   HL,(FACINT)")
            return
        k = e[0]
        if k == "int":
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
            self.gen_i(e[2], d)
            if e[1] == "-":
                self.emit("CALL RT_INEG")
            else:
                self._cpl()
        elif k == "bin":
            self.gen_ibin(e, d)
        elif k == "call":
            self.gen_icall(e, d)
        elif k == "fn":
            self.gen_fncall(e, d)
        else:
            self.err("expression numérique attendue")

    def _cpl(self):
        for r in ("L", "H"):
            self.emit("LD   A,%s" % r)
            self.emit("CPL")
            self.emit("LD   %s,A" % r)

    def gen_ibin(self, e, d):
        op, a, b = e[1], e[2], e[3]
        if op in REL:
            return self.gen_rel(op, a, b, d)
        self.gen_pair(a, b, d)
        if op == "+":
            self.emit("OR   A")
            self.emit("ADC  HL,DE")
            self.emit("JP   PE,RT_OV")
        elif op == "-":
            self.emit("EX   DE,HL")
            self.emit("OR   A")
            self.emit("SBC  HL,DE")
            self.emit("JP   PE,RT_OV")
        elif op in ("AND", "OR", "XOR", "EQV", "IMP"):
            if op == "IMP":                          # (NOT a) OR b
                self.emit("LD   A,E")
                self.emit("CPL")
                self.emit("LD   E,A")
                self.emit("LD   A,D")
                self.emit("CPL")
                self.emit("LD   D,A")
            z80 = {"AND": "AND", "OR": "OR", "XOR": "XOR", "EQV": "XOR", "IMP": "OR"}[op]
            for r1, r2 in (("E", "L"), ("D", "H")):
                self.emit("LD   A,%s" % r1)
                self.emit("%-4s %s" % (z80, r2))
                self.emit("LD   %s,A" % r2)
            if op == "EQV":
                self._cpl()
        else:
            self.emit("CALL RT_%s" % {"*": "MUL", "\\": "DIV", "MOD": "MOD"}[op])

    def gen_rel(self, op, a, b, d):
        """Comparaison -> HL = -1 (vrai) ou 0."""
        ka, kb = self.et(a), self.et(b)
        swap = op in (">", "<=")
        if ka == "s":
            flag = {"=": "FEQ", "<>": "FNE", "<": "FLT", ">": "FLT",
                    "<=": "FGE", ">=": "FGE"}[op]
            pa, pb = self.sptr(a, d), self.sptr(b, d + 1)
            if swap:
                pa, pb = pb, pa
            self.emit("LD   DE,%s" % pa)
            self.emit("LD   HL,%s" % pb)
            self.emit("CALL RT_SCMP")
            self.emit("CALL RT_%s" % flag)
        elif ka == kb == "i":
            flag = {"=": "FEQ", "<>": "FNE", "<": "FLT", ">": "FLT",
                    "<=": "FGE", ">=": "FGE"}[op]
            self.gen_pair(a, b, d)
            if swap:
                self.emit("EX   DE,HL")
            self.emit("CALL RT_ICMP")
            self.emit("CALL RT_%s" % flag)
        else:
            # nombres : comparaison en double par la ROM ; A = 1 (<), 0 (=), $FF (>)
            self.gen_x(a, d)
            self.emit("CALL FCDBL")
            self.emit("CALL RT_FPUSH8")
            self.gen_x(b, d)
            self.emit("CALL FCDBL")
            self.emit("CALL RT_FPOPARG")
            self.emit("CALL DCMP")
            test, flag = {"<": ("CP   1", "FEQ"), ">": ("CP   $FF", "FEQ"),
                          "=": ("OR   A", "FEQ"), "<>": ("OR   A", "FNE"),
                          "<=": ("CP   $FF", "FNE"), ">=": ("CP   1", "FNE")}[op]
            self.emit(test)
            self.emit("CALL RT_%s" % flag)

    def gen_icall(self, e, d):
        name, args = e[1], e[2]
        if name == "EOF":                       # compilation directe de QuickBASIC
            self.gen_i(args[0], d)
            self.emit("CALL RT_FEOF")
            return
        if name in ("INT", "FIX"):
            return self.gen_i(args[0], d)
        if name == "ABS":
            self.gen_i(args[0], d)
            self.emit("CALL RT_IABS")
        elif name == "SGN":
            if self.et(args[0]) == "i":
                self.gen_i(args[0], d)
                self.emit("CALL RT_SGN")
            else:
                self.gen_x(args[0], d)
                self.emit("CALL FSGN")
        elif name == "CINT":
            self.gen_i(args[0], d)
        elif name == "PEEK":
            self.gen_i(args[0], d)
            self.emit("LD   L,(HL)")
            self.emit("LD   H,0")
        elif name == "INP":
            self.gen_i(args[0], d)
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
            if a[0] != "int":
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

    # ---------------------------------------------------- expressions flottantes
    def gen_x(self, e, d):
        """FAC = valeur de e, avec son type réel en VALTYP (comme l'interpréteur)."""
        kind = self.et(e)
        if kind == "s":
            self.err("expression numérique attendue")
        if kind == "i":
            # Opération entière dont le résultat va dans FAC : la ROM la calcule
            # et passe en double en cas de dépassement (30000+30000 -> 60000).
            if e[0] == "bin" and e[1] in ("+", "-", "*"):
                return self.gen_rom_op(ROM_OPS[e[1]], e[2], e[3], d)
            if e[0] == "un" and e[1] == "-":
                self.gen_x(e[2], d)
                self.emit("CALL FNEG")
                return
            if e[0] == "call" and e[1] == "ABS":
                self.gen_x(e[2][0], d)
                self.emit("CALL FABS")
                return
            self.gen_i(e, d)
            self.emit("CALL HL2FAC")
            return
        k = e[0]
        if k == "flt":
            lab, t = self.flit(e[1])
            if t == 2:                                   # FIN a rendu un entier
                data = self.flits[e[1]][1]
                self.emit("LD   HL,%d" % _s16(data[2] | data[3] << 8))
                self.emit("CALL HL2FAC")
            else:
                self.emit("LD   HL,%s" % lab)
                self.emit("CALL RT_LDF%d" % t)
        elif k == "var":
            self.load_var(e[1], self.var(e[1]))
        elif k == "arr":
            const = self.const_addr(e)
            if const:
                self.load_var(e[1], const)
            else:
                self.gen_addr(e, d)
                self.load_var(e[1])
        elif k == "un":                                  # « - » (NOT est entier)
            self.gen_x(e[2], d)
            self.emit("CALL FNEG")
        elif k == "bin":
            self.gen_rom_op(ROM_OPS[e[1]], e[2], e[3], d)
        elif k == "call":
            self.gen_xcall(e, d)
        elif k == "fn":
            self.gen_fncall(e, d)
        else:
            self.err("expression numérique attendue")

    def gen_rom_op(self, op, a, b, d):
        """a op b par le répartiteur de la ROM ($F9E4), comme l'interpréteur :
        on empile a comme l'évaluateur, b dans FAC, puis saut en FOPDISP."""
        ret = self.newlabel()
        self.emit("LD   HL,%s" % ret)
        self.emit("PUSH HL")
        self.gen_x(a, d)
        self.emit("LD   C,%d" % op)
        self.emit("CALL RT_FPUSHL")
        self.gen_x(b, d)
        self.emit("JP   FOPDISP")
        self.label(ret)

    def gen_xcall(self, e, d):
        name, args = e[1], e[2]
        if name in SAME_FUNCS:                   # ABS, INT, FIX d'un nombre
            self.gen_x(args[0], d)
            self.emit("CALL %s" % SAME_FUNCS[name])
        elif name == "VAL":
            self.emit("LD   HL,%s" % self.sptr(args[0], d))
            self.emit("CALL RT_VALX")
        elif name in X_FUNCS:
            self.gen_x(args[0], d)
            if name not in ("CSNG", "CDBL"):
                # comme le répartiteur des fonctions ($FBEB) : entier et simple -> double
                self.emit("CALL FCDBL")
            self.emit("CALL %s" % X_FUNCS[name])
        else:
            self.err("fonction non gérée : %s" % name)

    # ---------------------------------------------------- DEF FN
    def gen_fncall(self, e, d):
        name, args = e[1], e[2]
        key = self.vkey(name)
        if key not in self.fns:
            self.err("FN%s non défini" % name)
        _, params, body, _ = self.fns[key]
        if len(params) != len(args):
            self.err("FN%s : %d argument(s) attendu(s)" % (name, len(params)))
        for p, a in zip(params, args):
            if self.et(a) == "s":
                self.err("FN%s : argument numérique attendu" % name)
            if any(x[0] == "fn" and self.vkey(x[1]) == key for x in _walk(a)):
                self.err("FN%s appelée dans ses propres arguments : non géré" % name)
            t = self.vtype(p)
            self.gen_value(_fold(a), t)
            self.store_value(t, self.fnparam_label(name, p))
        self.emit("CALL FN_%s" % self.fn_label(name))

    def fn_label(self, name):
        base, t = self.vkey(name)
        return "%s_%s" % (_label(base), TYPE_TAG[t])

    def fnparam_label(self, name, p):
        base, t = self.vkey(p)
        return "P_%s_%s_%s" % (self.fn_label(name), _label(base), TYPE_TAG[t])

    def _gen_fns(self):
        for k, (key, (name, params, body, where)) in enumerate(sorted(self.fns.items())):
            self.where = where
            self.emit("")
            self.emit("; DEF FN%s" % name)
            self.label("FN_%s" % self.fn_label(name))
            self.fnparams = {}
            for p in params:
                lab = self.fnparam_label(name, p)
                self.vars[lab] = TYPE_SIZE[self.vtype(p)]
                self.fnparams[p] = lab
            self.tmpbase = 50 + 10 * k
            t = key[1]
            self.gen_value(body, t)              # résultat au type de la fonction
            self.emit("RET")
            self.fnparams, self.tmpbase = {}, 0

    # ---------------------------------------------------- tableaux
    def const_addr(self, e):
        """Adresse constante d'un élément si tous les indices sont constants."""
        if not all(i[0] == "int" for i in e[2]):
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
            if self.et(i) == "s":
                self.err("indice numérique attendu")
        self.gen_i(idx[0], d)
        self._chk(dims[0])
        for i, dmax in zip(idx[1:], dims[1:]):
            self.emit("PUSH HL")
            self.gen_i(i, d)
            self._chk(dmax)
            self.emit("POP  DE")
            self.emit("PUSH HL")
            self.emit("LD   HL,%d" % (dmax + 1))
            self.emit("CALL RT_MUL")
            self.emit("POP  DE")
            self.emit("ADD  HL,DE")
        for _ in range({2: 1, 4: 2, 8: 3}.get(esz, 0)):
            self.emit("ADD  HL,HL")
        if esz not in (2, 4, 8):
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
                self.gen_i(args[0], d)
                self.emit("LD   A,L")
                self.emit("LD   HL,%s" % t)
                self.emit("LD   (HL),1")
                self.emit("INC  HL")
                self.emit("LD   (HL),A")
            elif name == "STR$":
                self.gen_x(args[0], d)
                self.emit("LD   DE,%s" % t)
                self.emit("CALL RT_STRX")
            elif name == "HEX$":
                self.gen_i(args[0], d)
                self.emit("LD   DE,%s" % t)
                self.emit("CALL RT_HEX")
            elif name == "FONT$":
                self.gen_i(args[0], d)
                self.emit("LD   A,L")
                self.emit("LD   HL,%s" % t)
                self.emit("CALL RT_FONTR")
            elif name in ("LEFT$", "RIGHT$"):
                self.gen_s(args[0], d)
                self.gen_i(args[1], d + 1)
                self.emit("LD   DE,%s" % t)
                self.emit("CALL RT_%s" % name[:-1])
            elif name == "MID$":
                self.gen_s(args[0], d)
                self.gen_i(args[1], d + 1)
                self.emit("PUSH HL")
                if len(args) > 2:
                    self.gen_i(args[2], d + 1)
                else:
                    self.emit("LD   HL,255")
                self.emit("POP  BC")
                self.emit("LD   DE,%s" % t)
                self.emit("CALL RT_MID")
            elif name == "STRING$":
                self.gen_i(args[0], d)
                self.emit("PUSH HL")
                if self.et(args[1]) == "s":
                    p = self.sptr(args[1], d)
                    self.emit("LD   A,(%s+1)" % p)
                else:
                    self.gen_i(args[1], d)
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
        base = self.used | {"RT_END", "RT_FERR"}
        routines, rvars = runtime.closure(base, self.debug)
        keep_cmd = "RT_INPUT" in routines       # INPUT écrase la ligne « EXEC &H... »
        if keep_cmd:
            routines, rvars = runtime.closure(base | {"RT_CSAV", "RT_CRST"}, self.debug)
        out = []
        w = out.append
        w("; %s - compilé par x07basic (BASIC du Canon X-07)" % name)
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
        w("        LD   HL,(HKERROR)        ; détourne le crochet d'erreur de la ROM")
        w("        LD   (RT_HSAV),HL")
        w("        LD   A,(HKERROR+2)")
        w("        LD   (RT_HSAV+2),A")
        w("        LD   A,$C3               ; JP RT_FERR")
        w("        LD   (HKERROR),A")
        w("        LD   HL,RT_FERR")
        w("        LD   (HKERROR+1),HL")
        w("        LD   HL,VARS")
        w("        LD   DE,VARS+1")
        w("        LD   BC,VARS_END-VARS-1")
        w("        LD   (HL),0")
        w("        LDIR                     ; variables à zéro")
        if keep_cmd:
            w("        CALL RT_CSAV             ; ligne EXEC, que INPUT écrasera")
        if "RT_DPTR" in rvars:
            w("        LD   HL,DATA_0")
            w("        LD   (RT_DPTR),HL")
        if "FRND" in self._words():
            w("        CALL RNDINIT             ; RND repart comme après RUN")
        out += self.code
        w("")
        w("; ------------------------------------------------ bibliothèque")
        for r in routines:
            w("")
            text = runtime.routine(r, self.debug)
            if r == "RT_END" and keep_cmd:
                text = text.replace("RT_END:\n", "RT_END:\n        CALL RT_CRST\n", 1)
            w(text)
        if self.lits:
            w("")
            w("; ------------------------------------------------ chaînes")
            for s, lab in self.lits.items():
                w("%-8s DB   %s" % (lab + ":", _db_string(s)))
        if self.flits:
            w("")
            w("; ------------------------------------------------ nombres (BCD, convertis par la ROM)")
            for text, (lab, data, t) in self.flits.items():
                n = 4 if t == 4 else 8
                w("%-8s DB   %s   ; %s" % (lab + ":", ",".join("$%02X" % b for b in data[:n]),
                                            text))
        if self.tables:
            w("")
            for tab, lines in self.tables:
                w("%-8s DB   %d" % (tab + ":", len(lines)))
                w("         DW   %s" % ",".join("LN_%d" % n for n in lines))
        if "RT_DPTR" in rvars:
            w("")
            w("; ------------------------------------------------ DATA")
            for k, (line, item) in enumerate(self.data):   # ligne, longueur, texte
                w("DATA_%d:" % k)
                w("         DW   %d" % line)
                w("         DB   %s" % _db_string(item))
            w("DATA_%d:" % len(self.data))
            w("         DW   $FFFF")
        w("")
        w("RT_SP:   DW   0")
        w("RT_HSAV: DB   0,0,0")
        w("")
        w("; ------------------------------------------------ variables (non chargées)")
        w("VARS:")
        for lab, size in sorted(self.vars.items()):
            w("%-14s DS   %d" % (lab + ":", size))
        for lab in rvars:
            w("%-14s DS   %d" % (lab + ":", runtime.VARIABLES[lab]))
        for d in sorted(self.temps):
            w("%-14s DS   %d" % ("TMP_%d:" % d, self.strcap + 1))
        w("               DS   2")
        w("VARS_END:")
        w("")
        w("        END")
        return _add_x07_equ(out)

    def _words(self):
        return set(re.findall(r"\b[A-Z_][A-Z0-9_]*\b", "\n".join(self.code)))


def _walk(e):
    yield e
    if e[0] in ("arr", "call", "fn"):
        for x in e[2]:
            yield from _walk(x)
    elif e[0] == "un":
        yield from _walk(e[2])
    elif e[0] == "bin":
        yield from _walk(e[2])
        yield from _walk(e[3])


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
            rows.append("; Canon X-07 : %s" % title)
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
